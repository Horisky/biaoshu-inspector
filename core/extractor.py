"""
招标文件结构化抽取（精简自包含版）—— 两轮 LLM 调用：
  第一轮：项目概况 + 资格要求 + 否决项 + 格式要求
  第二轮：技术需求 + 商务需求 + 评分标准

输出已归一化为审核引擎可直接消费的 dict（无 Pydantic 依赖）：
  { "project_info": {...}, "requirements": [ {seq_no, dimension, content, is_knockout, score_points} ] }
"""
from loguru import logger
from core.llm_client import get_llm_client

_PASS1_SYSTEM = """你是一名资深的招投标专家，负责从招标文件中结构化提取关键信息。
请严格按照要求的 JSON 格式输出，不得遗漏字段，不得输出 JSON 以外的内容。
所有文本内容使用招标文件中的原话，不要改写或补充不存在的内容。"""

_PASS1_USER = """从以下招标文件原文中，提取第一部分信息，输出合法 JSON：

```
{text}
```

输出以下 JSON 结构（所有字段都需要，缺失的填 null 或空数组）：
{{
  "project_info": {{
    "project_name": "项目名称",
    "project_code": "项目编号或招标编号（无则null）",
    "purchaser": "采购人/招标人名称",
    "procurement_agency": "代理机构名称（无则null）",
    "budget_amount": 预算金额数字（无则null，单位万元）,
    "submission_deadline": "投标截止时间（无则null）",
    "bid_validity_days": 投标有效期天数（无则null）,
    "project_description": "项目概况简述（2-3句话）"
  }},
  "qualification_requirements": [
    {{"id":"Q001","content":"条款原文","is_knockout":true,"evidence_hint":"需提供什么文件"}}
  ],
  "format_requirements": {{
    "copies_original": 1,
    "copies_duplicate": 2,
    "binding_method": "胶装或null",
    "seal_requirements": ["封面盖公章","骑缝章"],
    "page_limit": null,
    "envelope_sealing": "密封要求描述或null",
    "bid_validity_days": 90,
    "other_notes": []
  }}
}}"""

_PASS2_SYSTEM = """你是一名资深的招投标专家。请从招标文件原文中结构化提取技术需求、商务需求和评分标准。
严格按 JSON 格式输出，不输出 JSON 以外的内容，所有内容来自原文不得编造。"""

_PASS2_USER = """从以下招标文件原文中，提取技术需求、商务需求、评分标准，输出合法 JSON：

```
{text}
```

输出以下 JSON 结构：
{{
  "technical_requirements": [
    {{"id":"T001","category":"功能需求|性能需求|安全需求|接口需求|其他","content":"条款原文","is_knockout":false}}
  ],
  "commercial_requirements": [
    {{"id":"C001","content":"条款原文","is_knockout":false,"category":"报价|付款|质保|交付期|售后|其他"}}
  ],
  "scoring_criteria": [
    {{"id":"S001","category":"技术分|商务分|价格分|资信分","item":"评分项名称","max_score":10,"scoring_rules":"评分细则"}}
  ],
  "total_score": 100
}}"""


async def extract_tender(raw_text: str) -> dict:
    """两轮抽取并归一化为审核引擎可消费的结构。两轮互相独立，并发执行以缩短耗时。"""
    import asyncio
    llm = get_llm_client()
    text_slice = raw_text[:28000]  # 放宽切片，覆盖资格/评分/技术要求，减少漏抽导致的误判

    async def _safe(system_prompt, user_prompt, label):
        try:
            return await llm.extract_json(system_prompt, user_prompt)
        except Exception as e:
            logger.error(f"{label}抽取失败: {e}")
            return {}

    logger.info("招标文件抽取 · 两轮并发（概况+资格+格式 / 技术+商务+评分）...")
    pass1, pass2 = await asyncio.gather(
        _safe(_PASS1_SYSTEM, _PASS1_USER.format(text=text_slice), "第一轮"),
        _safe(_PASS2_SYSTEM, _PASS2_USER.format(text=text_slice), "第二轮"),
    )

    project_info = pass1.get("project_info") or {}
    format_req = pass1.get("format_requirements") or {}

    # 归一化为审核引擎需要的 requirements 列表
    requirements: list[dict] = []

    for q in pass1.get("qualification_requirements") or []:
        requirements.append({
            "seq_no": q.get("id", ""),
            "dimension": "资格",
            "content": q.get("content", ""),
            "is_knockout": bool(q.get("is_knockout", True)),
            "score_points": 0,
        })
    for t in pass2.get("technical_requirements") or []:
        requirements.append({
            "seq_no": t.get("id", ""),
            "dimension": "技术规范",
            "content": t.get("content", ""),
            "is_knockout": bool(t.get("is_knockout", False)),
            "score_points": 0,
        })
    for c in pass2.get("commercial_requirements") or []:
        requirements.append({
            "seq_no": c.get("id", ""),
            "dimension": "合同条款",
            "content": c.get("content", ""),
            "is_knockout": bool(c.get("is_knockout", False)),
            "score_points": 0,
        })
    for s in pass2.get("scoring_criteria") or []:
        item = s.get("item", "")
        rules = s.get("scoring_rules", "")
        requirements.append({
            "seq_no": s.get("id", ""),
            "dimension": "评标办法",
            "content": f"{item}：{rules}".strip("："),
            "is_knockout": False,
            "score_points": s.get("max_score", 0) or 0,
        })

    # 把格式/密封要求也作为可对照条目（规范性维度）
    seals = format_req.get("seal_requirements") or []
    if seals:
        requirements.append({
            "seq_no": "F001",
            "dimension": "规范性",
            "content": "盖章/密封要求：" + "、".join(str(x) for x in seals),
            "is_knockout": True,
            "score_points": 0,
        })
    if format_req.get("bid_validity_days"):
        requirements.append({
            "seq_no": "F002",
            "dimension": "有效性",
            "content": f"投标有效期要求：{format_req.get('bid_validity_days')}天",
            "is_knockout": True,
            "score_points": 0,
        })

    logger.info(f"抽取完成：需求条目 {len(requirements)} 条")
    return {
        "project_info": project_info,
        "format_requirements": format_req,
        "requirements": requirements,
    }
