"""
标书规范性检测 · 独立服务

完全独立的小应用，可单独交付：
  - 上传【招标文件】+【投标文件】(.pdf / .docx)
  - 自动解析 → 抽取招标需求 → 八维度合规/规范性审核 → 返回结构化报告

运行：
  python server.py
  浏览器打开 http://localhost:8100
"""
import time
from pathlib import Path

from urllib.parse import quote

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from core.config import get_settings
from core.parser import parse_document, split_into_sections
from core.extractor import extract_tender
from core.reviewer import run_review
from core.report_export import build_docx, build_pdf

settings = get_settings()
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="标书规范性检测", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.deepseek_model,
        "llm_configured": bool(settings.deepseek_api_key),
    }


async def _read_upload(f: UploadFile, label: str) -> bytes:
    data = await f.read()
    if not data:
        raise HTTPException(400, f"{label}为空文件")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, f"{label}超过 {settings.max_upload_mb}MB 上限")
    ext = Path(f.filename or "").suffix.lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(400, f"{label}格式不支持（仅 .pdf / .docx）：{f.filename}")
    return data


@app.post("/api/inspect")
async def inspect(
    tender_file: UploadFile = File(..., description="招标文件"),
    bid_file: UploadFile = File(..., description="投标文件"),
):
    """招标 + 投标 → 八维度规范性检测报告。"""
    t0 = time.time()

    tender_bytes = await _read_upload(tender_file, "招标文件")
    bid_bytes = await _read_upload(bid_file, "投标文件")

    # 1) 解析
    try:
        tender_text = parse_document(tender_bytes, tender_file.filename)
        bid_text = parse_document(bid_bytes, bid_file.filename)
    except Exception as e:
        logger.exception("文档解析失败")
        raise HTTPException(400, f"文档解析失败：{e}")

    if len(tender_text.strip()) < 50:
        raise HTTPException(400, "招标文件解析后内容过少，可能是扫描件或加密文件，请换用可复制文本的版本")
    if len(bid_text.strip()) < 50:
        raise HTTPException(400, "投标文件解析后内容过少，可能是扫描件或加密文件，请换用可复制文本的版本")

    # 2) 抽取招标需求
    try:
        extraction = await extract_tender(tender_text)
    except Exception as e:
        logger.exception("招标需求抽取失败")
        raise HTTPException(502, f"招标需求抽取失败（请检查 LLM 配置）：{e}")

    project_info = extraction.get("project_info", {}) or {}
    requirements = extraction.get("requirements", []) or []

    # 3) 切分投标文件为章节
    sections = split_into_sections(bid_text)

    # 4) 八维审核
    global_terms = {
        "项目名称": project_info.get("project_name") or "本项目",
        "采购人": project_info.get("purchaser") or "采购人",
    }
    try:
        report = await run_review(
            project_name=project_info.get("project_name") or (bid_file.filename or "投标文件"),
            purchaser=project_info.get("purchaser") or "",
            budget=str(project_info.get("budget_amount") or ""),
            deadline=str(project_info.get("submission_deadline") or ""),
            global_terms=global_terms,
            requirements=requirements,
            sections=sections,
        )
    except Exception as e:
        logger.exception("AI 审核失败")
        raise HTTPException(502, f"AI 审核失败（请检查 LLM 配置）：{e}")

    elapsed = round(time.time() - t0, 1)
    logger.info(f"检测完成，用时 {elapsed}s")

    return JSONResponse({
        "project_info": project_info,
        "report": report,
        "meta": {
            "tender_file": tender_file.filename,
            "bid_file": bid_file.filename,
            "tender_chars": len(tender_text),
            "bid_chars": len(bid_text),
            "requirement_count": len(requirements),
            "section_count": len(sections),
            "elapsed_seconds": elapsed,
        },
    })


def _download_name(payload: dict, ext: str) -> str:
    pi = payload.get("project_info") or {}
    base = pi.get("project_name") or "标书规范性检测报告"
    base = "".join(ch for ch in str(base) if ch not in '\\/:*?"<>|').strip()[:40] or "检测报告"
    return f"{base}_检测报告.{ext}"


def _attachment_headers(filename: str) -> dict:
    # 中文文件名走 RFC 5987 编码，兼容各浏览器
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


@app.post("/api/export/docx")
async def export_docx(payload: dict = Body(...)):
    """接收 /api/inspect 的报告 JSON，返回 Word 文件（不重跑 LLM）。"""
    if not (payload.get("report") or {}).get("findings") and not payload.get("report"):
        raise HTTPException(400, "缺少报告数据")
    try:
        data = build_docx(payload)
    except Exception as e:
        logger.exception("Word 导出失败")
        raise HTTPException(500, f"Word 导出失败：{e}")
    fn = _download_name(payload, "docx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers(fn),
    )


@app.post("/api/export/pdf")
async def export_pdf(payload: dict = Body(...)):
    """接收 /api/inspect 的报告 JSON，返回 PDF 文件（不重跑 LLM）。"""
    if not payload.get("report"):
        raise HTTPException(400, "缺少报告数据")
    try:
        data = build_pdf(payload)
    except Exception as e:
        logger.exception("PDF 导出失败")
        raise HTTPException(500, f"PDF 导出失败：{e}")
    fn = _download_name(payload, "pdf")
    return Response(content=data, media_type="application/pdf", headers=_attachment_headers(fn))


# 静态资源（放在路由之后，避免覆盖 /api）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"标书规范性检测 启动于 http://localhost:{settings.port}")
    if not settings.deepseek_api_key:
        logger.warning("未配置 DEEPSEEK_API_KEY，检测将失败。请在 .env 中填写。")
    uvicorn.run(app, host=settings.host, port=settings.port)
