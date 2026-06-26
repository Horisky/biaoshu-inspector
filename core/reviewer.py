"""
投标文件 AI 审核引擎 —— 八大维度合规/规范性检测（核心资产，完整移植）。

八大审核维度：
  1. 评标办法审核   招标条款逐条对照应答核查
  2. 资格审核       营业执照、企业信用、资质证书
  3. 技术规范审核   招标要求 vs 投标响应核查
  4. 合同条款审核   合同条款核查
  5. 规范性审核     签名、签章规范性核查
  6. 法律法规审核   《政府采购法》《招投标法》合规性
  7. 一致性审核     报价、签名、签章一致性检查
  8. 有效性审核     日期、报价有效性核查

每条问题四色分级：
  red    = 否决项·必改（废标风险）
  yellow = 扣分项·建议改
  blue   = 待人工核验（仅凭扫描件/印章/图片才能判断，纯文本无法断定）
  green  = 合规
"""
import json
from core.llm_client import get_llm_client
from loguru import logger

_SYSTEM_PROMPT = """你是中国政府采购/招投标领域的专业合规审核专家，精通：
- 《招标投标法》及其实施条例
- 《政府采购法》及其实施条例
- 《评标委员会和评标方法暂行规定》
- 各地政府采购评分办法

你的任务是对投标文件进行全面审核，发现废标风险和扣分隐患。

【最高铁律 · 严禁凭空捏造（违反即视为严重错误）】
1. 每一条问题都必须有据可查：必须给出 rule_reference（招标文件原文逐字引用）和
   bid_reference（投标文件中的对应原文逐字引用）。不得编造原文。
2. 判定"缺失/未提供"前，必须在投标文件全文中检索确认确实没有；切勿因为某段摘要里
   没出现就断定缺失。常见误报（务必避免）：把实际已提供的承诺函、已写明的品牌型号、
   已附的表格报成"缺失/未写明"。若不确定是否真的缺失，宁可标 blue（待核验），不要标 red/yellow。
3. 凡是"是否盖章/签字、证书或社保等扫描件是否真实附上、印章是否与营业执照一致、图片
   内容"这类【只能看图像/扫描件】才能判断的事项，纯文本无法识别，severity 一律标 blue
   （待人工核验），绝不可标 red 或 yellow，更不可断言"未盖章/未提供"。
4. 招标规则中"偏差表空白或填'无'视为完全响应"——投标偏差表为空白时，应视为完全响应，
   不得据此报缺失。
5. 宁缺毋滥：没有把握、文本无依据的，不写。每条结论都要经得起逐字对照核对。

审核原则：
1. 以招标文件条款为最高准则，逐条比对投标响应
2. 严格区分"否决项"（废标）、"扣分项"（失分）与"待核验"（需看扫描件）
3. 每个问题必须给出：招标文件条款原文 + 投标文件原文 + 相关法律法规条文
4. 修改建议必须具体可执行，不能泛泛而谈
5. 输出必须是合法 JSON，不得有任何额外文字"""

_USER_PROMPT = """请对以下投标文件进行全面审核，按八大维度逐条输出问题清单。

═══ 项目信息 ═══
项目名称：{project_name}
采购人：{purchaser}
预算金额：{budget}
投标截止：{deadline}

═══ 招标需求摘要（从招标文件抽取） ═══
{requirements_text}

═══ 投标文件各章节内容 ═══
{sections_text}

═══ 全局项目术语 ═══
{global_terms}

请按以下 JSON 格式输出审核结果（不要输出任何其他文字）：
{{
  "overall_score": <预估得分 0-100 整数，考虑扣分项后的估算>,
  "overall_verdict": "<当前状态一句话：如'存在否决项风险·建议修改后再投'或'基本合规·建议优化后提交'>",
  "score_note": "<若修改全部问题，预计可提升到XX分>",
  "counts": {{
    "red": <否决项数量>,
    "yellow": <扣分项数量>,
    "blue": <待人工核验项数量>,
    "green": <合规项数量>
  }},
  "findings": [
    {{
      "id": "H-01",
      "dimension": "<八大维度之一：评标办法|资格|技术规范|合同条款|规范性|法律法规|一致性|有效性>",
      "severity": "<red|yellow|blue|green>",
      "is_knockout": <true 表示否决项/废标风险；blue/green 一律 false>,
      "title": "<问题标题，一句话，20字以内>",
      "location": "<投标文件位置，如'七、资格审查资料 7-3'>",
      "description": "<问题详细描述，说明哪里不符合要求、为什么有风险>",
      "rule_reference": "<招标文件中的具体条款原文，逐字引用>",
      "bid_reference": "<投标文件中的对应原文，逐字引用；若你判定为缺失，请先全文确认，再填'【全文核查后确实未找到】'>",
      "law_reference": "<相关法律法规条文，如'《招标投标法》第26条'，无则留空>",
      "suggestion": "<修改建议，具体说明怎么改>",
      "actions": ["<具体动作1>", "<具体动作2>"],
      "score_impact": "<对评分的影响，如'-2.5分（此项满分5分）'或'待核验·缺则废标'>",
      "category": "<资质/信誉|技术响应|商务条款|价格策略|格式/完整性>"
    }}
  ],
  "knockout_distribution": {{
    "<分类名>": <该分类下 severity=red 的条数>
  }},
  "deduction_distribution": {{
    "<分类名>": <该分类下 severity=yellow 的条数>
  }},
  "fix_priority": [
    {{"rank": 1, "id": "H-01", "reason": "<为什么优先修改这条>"}}
  ]
}}

说明：
- knockout_distribution 仅统计 severity=red（否决项）按 category 的条数；
- deduction_distribution 仅统计 severity=yellow（扣分项）按 category 的条数；
- 两个分布的 category 取值范围：资质/信誉 | 技术响应 | 商务条款 | 价格策略 | 格式/完整性；只列条数>0 的分类。
- 同时尽量给出 2-4 条 severity=green 的关键合规项（说明哪些实质性要求已满足），以体现"未捏造"。

审核维度说明：
1. 【评标办法审核】招标文件评分标准逐条检查，投标文件是否有对应应答，有无遗漏或不符
2. 【资格审核】营业执照经营范围、资质证书是否覆盖项目要求，企业信用是否正常
3. 【技术规范审核】技术参数响应是否满足招标要求（特别是带★的必须满足项）
4. 【合同条款审核】合同草案响应是否有重大异议，违约条款是否接受
5. 【规范性审核】签名、盖章、授权委托书、法人代表身份证是否齐全规范
6. 【法律法规审核】是否符合《招投标法》《政府采购法》强制性条款
7. 【一致性审核】报价在不同表格间是否一致，签名盖章是否统一
8. 【有效性审核】投标有效期、业绩时间、证书有效期是否满足要求

重点检查否决项（废标条件）——但凡只能凭扫描件/印章判断的，改标 blue（待核验）：
- 未提供投标保证金（如有要求）—— 文本若已列明金额，则按已提供处理；到账/形式以凭证为准 → 多为 blue
- 法定代表人未签字或未授权 —— 签字/章为图像，纯文本不可断言 → blue
- 未加盖公章或公章与营业执照不符 —— 印章为图像 → blue
- 投标报价超出最高限价或低于成本价 —— 文本可判定 → 可 red
- 资质证书不满足要求或已过期 —— 证书为扫描件 → 多为 blue；招标明确写出的资格门槛（如业绩金额）文本可判定时可 red
- 联合体投标未提交联合协议（如有要求）—— 文本可判定
- 投标有效期不足 —— 文本可判定

最后再次自检：每条 red/yellow 是否都能在投标文件原文中找到 bid_reference 支撑？凡"缺失类"
结论是否已全文确认？凡涉及印章/签字/扫描件的是否已改为 blue？不满足则删除或改判。"""


def _format_requirements(reqs: list[dict]) -> str:
    if not reqs:
        return "（无抽取到的需求条目）"
    lines = []
    for r in reqs[:60]:  # 限量避免超 token
        ko = "【否决项】" if r.get("is_knockout") else ""
        score = f"({r['score_points']}分)" if r.get("score_points") else ""
        dim = f"[{r.get('dimension')}]" if r.get("dimension") else ""
        lines.append(f"[{r.get('seq_no','')}]{dim}{ko}{score} {r.get('content','')}")
    return "\n".join(lines)


def _format_sections(sections: list[dict]) -> str:
    if not sections:
        return "（未提供投标文件内容）"
    parts = []
    for s in sections:
        content = s.get("content", "")
        if content:
            # 放宽每章截断上限，给模型足够上下文，减少"看不全→臆测"的幻觉
            parts.append(f"## 第{s.get('order_index','')}章 {s.get('title','')}\n{content[:6000]}")
    return "\n\n---\n\n".join(parts) if parts else "（未提供投标文件内容）"


async def run_review(
    project_name: str,
    purchaser: str,
    budget: str,
    deadline: str,
    global_terms: dict,
    requirements: list[dict],
    sections: list[dict],
) -> dict:
    """调用 LLM 执行八维度审核，返回结构化审核报告。"""
    llm = get_llm_client()

    requirements_text = _format_requirements(requirements)
    sections_text = _format_sections(sections)
    terms_text = "\n".join(f"{k}={v}" for k, v in (global_terms or {}).items())

    user_prompt = _USER_PROMPT.format(
        project_name=project_name,
        purchaser=purchaser,
        budget=budget or "未知",
        deadline=deadline or "未知",
        requirements_text=requirements_text,
        sections_text=sections_text,
        global_terms=terms_text or "（无）",
    )

    logger.info(f"开始 AI 审核：{project_name}")

    raw = await llm.extract_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    if isinstance(raw, str):
        raw = json.loads(raw)

    findings = raw.get("findings", [])
    for i, f in enumerate(findings):
        if not f.get("id"):
            f["id"] = f"I-{i+1:02d}"
        # blue/green 不应是否决项
        if f.get("severity") in ("blue", "green"):
            f["is_knockout"] = False
    raw["findings"] = findings

    # ── 兜底归一化：缺失字段时从 findings 推导，保证前端/导出一致 ──
    counts = raw.get("counts") or {}
    for sev in ("red", "yellow", "blue", "green"):
        if sev not in counts:
            counts[sev] = sum(1 for f in findings if f.get("severity") == sev)
    raw["counts"] = counts

    def _dist(sev):
        d: dict[str, int] = {}
        for f in findings:
            if f.get("severity") == sev:
                cat = f.get("category") or "其他"
                d[cat] = d.get(cat, 0) + 1
        return d

    if not raw.get("knockout_distribution"):
        raw["knockout_distribution"] = _dist("red")
    if not raw.get("deduction_distribution"):
        raw["deduction_distribution"] = _dist("yellow")

    logger.info(
        f"审核完成：{project_name}，发现 {len(findings)} 条问题"
        f"（否决{counts.get('red',0)}/扣分{counts.get('yellow',0)}/待核验{counts.get('blue',0)}），"
        f"预估得分 {raw.get('overall_score')}"
    )
    return raw
