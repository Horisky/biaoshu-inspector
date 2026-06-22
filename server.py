"""
标书规范性检测 · 独立服务

完全独立的小应用，可单独交付：
  - 上传【招标文件】+【投标文件】(.pdf / .docx)
  - 自动解析 → 抽取招标需求 → 八维度合规/规范性审核 → 返回结构化报告

运行：
  python server.py
  浏览器打开 http://localhost:8100
"""
import asyncio
import time
import uuid
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


# ── 异步任务存储（单进程内存；单 worker 部署适用）──────────────
JOBS: dict[str, dict] = {}
JOB_TTL = 3600  # 任务结果保留 1 小时


def _prune_jobs():
    now = time.time()
    for k in [k for k, v in JOBS.items() if now - v.get("created", now) > JOB_TTL]:
        JOBS.pop(k, None)


async def _run_inspect_job(job_id: str, tender_bytes: bytes, tender_name: str,
                           bid_bytes: bytes, bid_name: str):
    """后台执行：解析 → 抽取 → 八维审核，把进度/结果写入 JOBS。"""
    job = JOBS[job_id]
    t0 = job["created"]
    try:
        job["step"] = "parsing"
        try:
            tender_text = parse_document(tender_bytes, tender_name)
            bid_text = parse_document(bid_bytes, bid_name)
        except Exception as e:
            raise ValueError(f"文档解析失败：{e}")
        if len(tender_text.strip()) < 50:
            raise ValueError("招标文件解析后内容过少，可能是扫描件或加密文件，请换用可复制文本的版本")
        if len(bid_text.strip()) < 50:
            raise ValueError("投标文件解析后内容过少，可能是扫描件或加密文件，请换用可复制文本的版本")

        job["step"] = "extracting"
        extraction = await extract_tender(tender_text)
        project_info = extraction.get("project_info", {}) or {}
        requirements = extraction.get("requirements", []) or []
        sections = split_into_sections(bid_text)

        job["step"] = "reviewing"
        report = await run_review(
            project_name=project_info.get("project_name") or (bid_name or "投标文件"),
            purchaser=project_info.get("purchaser") or "",
            budget=str(project_info.get("budget_amount") or ""),
            deadline=str(project_info.get("submission_deadline") or ""),
            global_terms={"项目名称": project_info.get("project_name") or "本项目",
                          "采购人": project_info.get("purchaser") or "采购人"},
            requirements=requirements,
            sections=sections,
        )

        elapsed = round(time.time() - t0, 1)
        job["result"] = {
            "project_info": project_info,
            "report": report,
            "meta": {
                "tender_file": tender_name,
                "bid_file": bid_name,
                "tender_chars": len(tender_text),
                "bid_chars": len(bid_text),
                "requirement_count": len(requirements),
                "section_count": len(sections),
                "elapsed_seconds": elapsed,
            },
        }
        job["status"] = "done"
        logger.info(f"检测完成 job={job_id}，用时 {elapsed}s")
    except Exception as e:
        logger.exception(f"检测失败 job={job_id}")
        job["status"] = "error"
        job["error"] = str(e)


@app.post("/api/inspect")
async def inspect(
    tender_file: UploadFile = File(..., description="招标文件"),
    bid_file: UploadFile = File(..., description="投标文件"),
):
    """提交检测任务，立即返回 job_id；前端轮询 /api/inspect/status/{job_id}。"""
    tender_bytes = await _read_upload(tender_file, "招标文件")
    bid_bytes = await _read_upload(bid_file, "投标文件")
    _prune_jobs()
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "step": "queued", "created": time.time()}
    asyncio.create_task(
        _run_inspect_job(job_id, tender_bytes, tender_file.filename, bid_bytes, bid_file.filename)
    )
    return JSONResponse({"job_id": job_id}, status_code=202)


@app.get("/api/inspect/status/{job_id}")
async def inspect_status(job_id: str):
    """查询检测任务进度/结果。"""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在或已过期")
    resp = {"status": job["status"], "step": job.get("step")}
    if job["status"] == "done":
        resp.update(job["result"])
    elif job["status"] == "error":
        resp["error"] = job.get("error")
    return resp


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


@app.get("/api/export/{fmt}")
async def export_by_job(fmt: str, job: str):
    """按任务号导出（浏览器原生下载，不依赖前端 JS）。"""
    if fmt not in ("docx", "pdf"):
        raise HTTPException(400, "仅支持 docx / pdf")
    j = JOBS.get(job)
    if not j or j.get("status") != "done" or not j.get("result"):
        raise HTTPException(404, "报告不存在或已过期，请重新检测后再导出")
    payload = j["result"]
    try:
        data = build_docx(payload) if fmt == "docx" else build_pdf(payload)
    except Exception as e:
        logger.exception("导出失败")
        raise HTTPException(500, f"导出失败：{e}")
    media = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             if fmt == "docx" else "application/pdf")
    return Response(content=data, media_type=media, headers=_attachment_headers(_download_name(payload, fmt)))


# 静态资源（放在路由之后，避免覆盖 /api）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"标书规范性检测 启动于 http://localhost:{settings.port}")
    if not settings.deepseek_api_key:
        logger.warning("未配置 DEEPSEEK_API_KEY，检测将失败。请在 .env 中填写。")
    uvicorn.run(app, host=settings.host, port=settings.port)
