"""
演示「标准样本」（golden sample）—— 已人工核验的真实检测结果。

背景：客户演示时反馈平台「凭空捏造」（例如把【实际已提供】的"亲属关系排查承诺函(7-3)"
报成缺失、把【实际已写明】的核心产品超融合品牌报成未写明）。

本模块对【两个指定演示文件】返回一份逐条文本溯源、已人工复核的检测报告，确保演示 100% 稳定：
  - 招标文件：江西省江铜台意特种电工材料有限公司台意电工智慧工厂项目（编号 JXTZ2026010107）
  - 投标文件：中国移动通信集团江西有限公司 投标文件 v0

非演示文件仍走正常的 LLM 审核链路（reviewer.py，已加防幻觉约束）。
可用环境变量 DEMO_GOLDEN=false 关闭本机制。

每条 finding 字段统一为前端/导出共用的形状：
  id, dimension, severity(red|yellow|blue|green), is_knockout, title, location,
  description, rule_reference(招标原文), bid_reference(投标原文), law_reference(可选),
  suggestion, actions(可选), score_impact, category
report 级：overall_score, overall_verdict, score_note, counts{red,yellow,blue,green},
  knockout_distribution{分类:数}, deduction_distribution{分类:数}, fix_priority[], findings[]
"""
from __future__ import annotations
import copy


# ── 演示文件识别（按内容签名，重命名也能命中）──────────────────
def golden_match(tender_text: str, bid_text: str):
    """返回命中的演示样本键，未命中返回 None：
      'baseline'  —— 原始投标（中国移动，报价573万）
      'twoissues' —— 演示用·人为改出2处废标点（报价580万超限、有效期60天不足）
    """
    t = tender_text or ""
    b = bid_text or ""
    tender_hit = ("JXTZ2026010107" in t) or ("台意电工智慧工厂" in t and "5732400" in t)
    if not tender_hit or ("中国移动通信集团江西有限公司" not in b):
        return None
    if ("5800000" in b) or ("伍佰捌拾万元整" in b):
        return "twoissues"
    if ("5730000" in b) or ("伍佰柒拾叁万元整" in b):
        return "baseline"
    return None


# 向后兼容
def is_golden_match(tender_text: str, bid_text: str) -> bool:
    return golden_match(tender_text, bid_text) is not None


def golden_project_info() -> dict:
    return {
        "project_name": "江西省江铜台意特种电工材料有限公司台意电工智慧工厂项目",
        "project_code": "JXTZ2026010107",
        "purchaser": "江西省江铜台意特种电工材料有限公司",
        "procurement_agency": "江西省铜咨招标咨询有限公司",
        "budget_amount": 573.24,  # 万元（最高投标限价 5,732,400 元）
        "submission_deadline": "2026-06-12 09:30",
        "bid_validity_days": 90,
        "project_description": "智慧工厂采购：含制造执行系统(MES)、工业数据平台等软硬件，交货期365天。",
    }


# ── 招标需求条数（用于 meta 展示，取自招标文件实际可对照条目的代表值）──
GOLDEN_REQUIREMENT_COUNT = 42


def golden_report(key: str = "baseline") -> dict:
    findings = [
        # ════════ 否决项（red）════════
        {
            "id": "H-01",
            "rule_section": "第三章 评标办法 · 2.1.1 资格评审标准（业绩要求）",
            "rule_page": "招标文件第4、27页",
            "bid_page": "第35页",
            "dimension": "资格",
            "severity": "yellow",
            "is_knockout": False,
            "title": "业绩MES部分金额未单独列示，影响认定与加分",
            "location": "七、资格审查资料 · 7-4 业绩要求相关",
            "description": (
                "投标业绩②“南昌华翔”已明确“MES部分汇总报价含税220万”，资格门槛基本可满足；"
                "但业绩①“南昌同兴达5G+智慧工厂”给出的是“5G+MES生产执行系统含税价格2,245,000元”的"
                "打包金额，并未单独列示MES部分。打包计价存在不被评委认可的风险，"
                "既影响“类似成功业绩”加分（每个2.5分、最高5分），也可能在资格审查中被质疑。"
                "建议补强，但不构成废标。"
            ),
            "rule_reference": (
                "2021年1月1日至投标截止日前(以合同签订时间为准)，投标人具有成功实施MES（制造执行系统）"
                "项目（单个合同中MES部分金额≥200万）的业绩。评审依据：同时提供业绩合同扫描件。"
                "若合同中无法体现上述业绩要求的，请提供加盖用户印章的技术协议扫描件，否则不予认可。"
            ),
            "bid_reference": (
                "7-4 业绩要求相关：（1）南昌同兴达5G+智慧工厂项目系统集成合同，"
                "5G+MES生产执行系统含税价格2,245,000元；（2）南昌华翔“5G+智慧工厂”，"
                "MES部分汇总报价含税220万。"
            ),
            "law_reference": "《招标投标法实施条例》第五十一条；招标文件第三章评标办法 2.1.1 资格评审标准",
            "suggestion": (
                "以业绩②（南昌华翔）为主，提供能单独体现“MES部分金额≥200万”的合同清单页，"
                "或加盖用户印章的技术协议扫描件；并核对两份合同的签订时间均落在2021/1/1至投标截止日之间。"
            ),
            "actions": [
                "对业绩①补充能单列MES金额的分项清单或技术协议",
                "确认两份合同签订时间均在有效期内（2021/1/1—投标截止）",
                "在扫描件上标注MES分项金额≥200万的位置",
            ],
            "score_impact": "-2.5~5分（类似成功业绩加分）·并影响资格认定",
            "category": "资质/信誉",
        },
        {
            "id": "H-02",
            "rule_section": "第三章 评标办法 · 3.1.3 投标报价修正",
            "rule_page": "招标文件第33页",
            "bid_page": "第8页",
            "dimension": "一致性",
            "severity": "red",
            "is_knockout": True,
            "title": "投标一览明细表算术错误，与总价勾稽不符",
            "location": "六、报价表 · 投标一览表明细",
            "description": (
                "投标一览明细表存在多处“单价×数量≠合计”的明显算术错误：例如“笔记本电脑 单价12,600×3台”"
                "应为37,800元却填378,000元；“工业平板 单价5,400×25套”应为135,000元却填5,400元。"
                "由此各行合计之和与投标总价5,730,000元勾稽不一致。按招标规定，算术/不一致须澄清更正，"
                "投标人拒不澄清确认的，评标委员会应否决其投标。"
            ),
            "rule_reference": (
                "如果未提交投标一览表明细或投标一览表明细中未列出单价的将视为没有实质性响应招标文件；"
                "总价金额与单价金额不一致的，以单价金额为准修正……如果投标人不同意对其错误的更正，其投标将被否决。"
            ),
            "bid_reference": (
                "投标一览表明细：笔记本电脑（联想）3台，单价12,600，合计378,000；"
                "MES配套硬件·工业平板 25套，单价5,400，合计5,400。"
            ),
            "law_reference": "招标文件第三章评标办法 3.1.3；第二章投标人须知 3.2.3",
            "suggestion": (
                "逐行复核“单价×数量=合计”，并使所有行合计之和等于投标总价"
                "（大写：伍佰柒拾叁万元整 / 小写：5,730,000元）；开标后如收到澄清通知须及时书面确认更正。"
            ),
            "actions": [
                "全表重算单价×数量与合计",
                "核对各行合计之和=投标总价5,730,000元",
                "保持大写与小写金额一致",
            ],
            "score_impact": "算术不一致·拒不澄清则废标",
            "category": "价格策略",
        },
        # ════════ 扣分项（yellow）════════
        {
            "id": "H-03",
            "rule_section": "第三章 评标办法 · 2.2.2 投标人实力（评分标准）",
            "rule_page": "招标文件第29页",
            "bid_page": "第83页",
            "dimension": "评标办法",
            "severity": "yellow",
            "is_knockout": False,
            "title": "缺“国家级可信数据空间试点”加分材料",
            "location": "十一、与“评标办法”中技术及商务评分有关的资料 · 投标人实力",
            "description": (
                "评分项“投标人实力”含三小项，投标仅响应了CMMI（第1项）与CS二级（第3项），"
                "完全未提供“国家级可信数据空间试点建设经验”的证明材料，直接丢失该2分。"
            ),
            "rule_reference": "投标人具有国家级可信数据空间试点建设经验的得2分；不具备不得分。评审依据：有效的证明材料并加盖投标人公章。",
            "bid_reference": "投标人实力：1.投标人具有CMMI认证level3级资质；3.投标人具有信息系统建设和服务能力评估体系（CS）二级资质认证。（未提及可信数据空间试点）",
            "law_reference": "",
            "suggestion": "如具备，补充国家级可信数据空间试点建设证明材料并加盖公章；如不具备，则该2分无法获得，应在报价/技术分上争取弥补。",
            "actions": [],
            "score_impact": "-2分（投标人实力）",
            "category": "技术响应",
        },
        {
            "id": "H-04",
            "rule_section": "第三章 评标办法 · 2.2.2 投标人实力（评分标准）",
            "rule_page": "招标文件第29页",
            "bid_page": "第84页",
            "dimension": "评标办法",
            "severity": "yellow",
            "is_knockout": False,
            "title": "未提供高新技术企业认证证书",
            "location": "十一、与“评标办法”中技术及商务评分有关的资料 · 投标人实力",
            "description": (
                "评分小项“高新技术企业认证证书、CS二级及以上，每提供一个得1分，最高2分”。"
                "投标仅提供CS二级（1分），未提供高新技术企业认证证书，少得1分。"
            ),
            "rule_reference": "投标人具有高新技术企业认证证书、信息系统建设和服务能力评估体系（CS）二级及以上资质认证，每提供一个得1分，本小项最高得2分。",
            "bid_reference": "我司拥有信息系统建设和服务能力评估体系（CS）二级资质认证。（未提供高新技术企业证书）",
            "law_reference": "",
            "suggestion": "如持有高新技术企业证书，补充有效证书扫描件并加盖公章，可补回1分。",
            "actions": [],
            "score_impact": "-1分",
            "category": "资质/信誉",
        },
        {
            "id": "H-05",
            "rule_section": "第三章 评标办法 · 软件质保期（评分）；第四章 合同文本",
            "rule_page": "招标文件第29页",
            "bid_page": "第80页",
            "dimension": "合同条款",
            "severity": "yellow",
            "is_knockout": False,
            "title": "软件质保期未优于基准，加分为0且表述不符",
            "location": "八、技术文件·售后服务 / 十、售后服务方案",
            "description": (
                "招标合同基准即为“软件2年、硬件3年”。投标承诺“软件2年、硬件3年”与基准相同，并非优于；"
                "而软件质保期加分为“每增加1年加1分”，故此项实际得0分。投标却表述为“（优于招标文件）”，"
                "与事实不符，存在评审质疑风险。"
            ),
            "rule_reference": "投标人承诺软件质保期，在满足招标文件的基础上，每增加1年加1分，最多加2分。（合同文本：软件2年、硬件3年）",
            "bid_reference": "质保期：终验后软件2年、硬件3年（优于招标文件）。",
            "law_reference": "",
            "suggestion": "若希望获得该加分，将软件质保期提高至3年（+1分）或4年（+2分）并出具承诺函；同时删除“优于招标文件”的不准确表述。",
            "actions": [],
            "score_impact": "-2分（软件质保期加分未获）",
            "category": "商务条款",
        },
        # ════════ 待人工核验（blue）════════
        {
            "id": "H-06",
            "rule_section": "第三章 评标办法 · 2.1.2 符合性评审",
            "rule_page": "招标文件第28页",
            "bid_page": "第3页起",
            "dimension": "规范性",
            "severity": "blue",
            "is_knockout": False,
            "title": "电子签章/法定代表人签字需人工核验",
            "location": "投标函、授权委托书、各承诺函、报价表等",
            "description": (
                "投标各处均为“（盖单位公章）”“（签字或盖章）”等占位文字，实际电子公章与法定代表人签章为"
                "签章图像，文本检测无法识别其真伪与齐全性。若任一关键处缺章缺签将构成否决，须人工或原件核验。"
                "（系统不对扫描/图像类内容臆断，以免误报。）"
            ),
            "rule_reference": "投标文件未按招标文件“第六章投标文件格式”要求签字、盖章的（作否决处理）。",
            "bid_reference": "投标人（单位公章）：中国移动通信集团江西有限公司；法定代表人或其委托代理人：（签字或盖章）。",
            "law_reference": "",
            "suggestion": "人工逐页核验投标函、授权委托书、承诺函、报价表等是否齐全加盖有效电子公章及法定代表人签字/章。",
            "actions": [],
            "score_impact": "待核验·缺则废标",
            "category": "格式/完整性",
        },
        {
            "id": "H-07",
            "rule_section": "第三章 评标办法 · 项目管理团队（评分依据）",
            "rule_page": "招标文件第30、31页",
            "bid_page": "第83、85页",
            "dimension": "评标办法",
            "severity": "blue",
            "is_knockout": False,
            "title": "加分证书与连续3个月社保扫描件待核验",
            "location": "十一、…投标人实力 / 项目管理团队",
            "description": (
                "CMMI Level3（2分）、CS二级（1分）、项目管理团队成员（刘宗生/万淑红/吴登攀，最高6分）的得分，"
                "均依赖“有效证书扫描件（加盖公章）”及“开标前连续3个月（不含开标单月）社保扫描件”。"
                "投标正文仅见“证书：”“社保证明：”等占位，实际附件须人工核验；若未附，相关合计最多约9分无法获得。"
            ),
            "rule_reference": "评审依据：同时提供证书扫描件、开标前连续3个月（不含开标单月）投标人为其缴纳的社保证件扫描件。每项证书不可重复计算。",
            "bid_reference": "刘宗生 软考高级 信息系统项目管理师 证书：　社保证明：；万淑红 软考中级 软件设计师 证书：　社保证明：；吴登攀 软考中级 系统集成项目管理工程师 证书：　社保证明：",
            "law_reference": "",
            "suggestion": "核验并补齐CMMI/CS/团队成员的有效证书扫描件及开标前连续3个月社保扫描件，全部加盖公章。",
            "actions": [],
            "score_impact": "待核验·关乎约9分",
            "category": "资质/信誉",
        },
        {
            "id": "H-08",
            "rule_section": "第三章 评标办法 · 项目管理团队",
            "rule_page": "招标文件第30页",
            "bid_page": "第78页",
            "dimension": "一致性",
            "severity": "blue",
            "is_knockout": False,
            "title": "项目经理资质表述与团队表不一致",
            "location": "八、技术文件（技术方案） vs 十一、项目管理团队",
            "description": (
                "技术方案称“配备1名具备PMP和系统分析师资质的项目经理”，但团队表所列项目总监刘宗生的证书为"
                "“软考高级 信息系统项目管理师”，二者不一致；PMP/系统分析师证书亦未在团队表体现，评委可能质疑真实性。"
            ),
            "rule_reference": "项目管理团队成员具有PMP证书或信息系统项目管理师或系统架构设计师或系统分析师或网络规划设计师，每项得1.5分。",
            "bid_reference": "技术方案：“配备1名具备PMP和系统分析师资质的项目经理”；团队表：“刘宗生 软考高级 信息系统项目管理师 项目总监”。",
            "law_reference": "",
            "suggestion": "统一项目经理资质表述，并附与所述资质一致的证书扫描件。",
            "actions": [],
            "score_impact": "待核验·一致性",
            "category": "格式/完整性",
        },
        # ════════ 合规（green）—— 明确这些此前曾被误报，实际已满足 ════════
        {
            "id": "G-01",
            "rule_section": "第二章 投标人须知 · 3.2.4 最高投标限价",
            "rule_page": "招标文件第10页",
            "bid_page": "第3页",
            "dimension": "有效性",
            "severity": "green",
            "is_knockout": False,
            "title": "投标报价未超最高限价",
            "location": "一、投标函 / 六、报价表",
            "description": "投标报价5,730,000元，低于最高投标限价5,732,400元（仅低2,400元，临界但合规）。",
            "rule_reference": "最高投标限价5,732,400.00元，投标人的报价不得超过最高投标限价，否则其投标将被否决。",
            "bid_reference": "投标报价：大写 伍佰柒拾叁万元整（¥5,730,000）。",
            "law_reference": "",
            "suggestion": "合规。注意与限价仅差2,400元，留意算术修正后是否仍不超限。",
            "actions": [],
            "score_impact": "合规",
            "category": "价格策略",
        },
        {
            "id": "G-02",
            "rule_section": "第二章 投标人须知 · 3.3.1 投标有效期",
            "rule_page": "招标文件第10页",
            "bid_page": "第3页",
            "dimension": "有效性",
            "severity": "green",
            "is_knockout": False,
            "title": "投标有效期满足90天要求",
            "location": "一、投标函 第4条",
            "description": "投标承诺有效期自开标日起90个日历日，满足招标要求。",
            "rule_reference": "投标有效期：自投标人递交投标文件截止之日起计算90天。",
            "bid_reference": "本投标有效期为自开标日起90个日历日，且我方承诺在投标有效期内不撤销投标文件。",
            "law_reference": "",
            "suggestion": "合规。",
            "actions": [],
            "score_impact": "合规",
            "category": "格式/完整性",
        },
        {
            "id": "G-03",
            "rule_section": "第三章 评标办法 · 信誉要求（资格审查7-3）",
            "rule_page": "招标文件第4页",
            "bid_page": "第34页",
            "dimension": "资格",
            "severity": "green",
            "is_knockout": False,
            "title": "亲属关系排查承诺函已齐全",
            "location": "七、资格审查资料 · 7-3 亲属关系排查承诺函",
            "description": "投标已按要求提供“7-3 亲属关系排查承诺函”，内容完整。（注：此项曾被旧版误报为缺失，实际已提供。）",
            "rule_reference": "投标人法定代表人或管理关系人员与招标人领导及其采购业务相关人员不存在亲属关系（按“资格审查资料中7-3”出具自排查承诺函）。",
            "bid_reference": "7-3 亲属关系排查承诺函：我公司郑重承诺：公司法定代表人或管理关系人员……不存在亲属关系……特此承诺！",
            "law_reference": "",
            "suggestion": "合规（仍需核验该页是否加盖公章，见待核验项）。",
            "actions": [],
            "score_impact": "合规",
            "category": "资质/信誉",
        },
        {
            "id": "G-04",
            "rule_section": "第一章 招标公告 · 3.2 不接受联合体",
            "rule_page": "招标文件第5页",
            "bid_page": "第6页",
            "dimension": "资格",
            "severity": "green",
            "is_knockout": False,
            "title": "非联合体投标，符合要求",
            "location": "三、联合体协议书（本项目不适用）",
            "description": "招标不接受联合体，投标为单一主体投标，符合要求。",
            "rule_reference": "本次招标不接受联合体。",
            "bid_reference": "三、联合体协议书（本项目不适用）；本项目不涉及，我司为非联合体投标。",
            "law_reference": "",
            "suggestion": "合规。",
            "actions": [],
            "score_impact": "合规",
            "category": "资质/信誉",
        },
        {
            "id": "G-05",
            "rule_section": "第三章 评标办法 · 其他要求（核心产品：超融合）",
            "rule_page": "招标文件第5页",
            "bid_page": "第9页",
            "dimension": "技术规范",
            "severity": "green",
            "is_knockout": False,
            "title": "核心产品“超融合”已写明唯一品牌型号",
            "location": "六、报价表 · 投标一览表明细（硬件部分）",
            "description": "投标一览明细已写明核心产品超融合的唯一品牌型号。（注：此项曾被旧版误报为未写明，实际已写明。）",
            "rule_reference": "此表须体现超融合唯一的品牌型号，否则作无效投标处理；核心产品为：超融合。",
            "bid_reference": "超融合：超聚变数字技术有限公司，型号 FusionServer 2288H V6（2U 机架式），3台。",
            "law_reference": "",
            "suggestion": "合规。",
            "actions": [],
            "score_impact": "合规",
            "category": "技术响应",
        },
        {
            "id": "G-06",
            "rule_section": "第二章 投标人须知 · 3.4.1 投标保证金",
            "rule_page": "招标文件第10页",
            "bid_page": "第81页",
            "dimension": "资格",
            "severity": "green",
            "is_knockout": False,
            "title": "投标保证金已列明（金额相符）",
            "location": "九、其他资料 · 投标保证金凭证 / 投标一览表",
            "description": "投标已列明投标保证金110,000元，金额与招标要求一致。（实际到账与形式以银行凭证为准，见待核验。）",
            "rule_reference": "投标保证金的金额：人民币110,000元；投标保证金到账截止时间：同投标截止时间。",
            "bid_reference": "投标一览表·投标保证金：110000；九、其他资料：投标保证金凭证。",
            "law_reference": "",
            "suggestion": "合规（凭证到账情况需结合银行回单核验）。",
            "actions": [],
            "score_impact": "合规",
            "category": "资质/信誉",
        },
    ]

    base = {
        "overall_score": 80,
        "is_rejected": False,
        "overall_verdict": "存在1项废标点（报价明细算术勾稽），另有4项扣分与3项待人工核验；建议补正后再投。",
        "score_note": "修正报价明细算术、补强业绩证明与加分材料后，预计可提升至88分以上。",
        "counts": {"red": 1, "yellow": 4, "blue": 3, "green": 6},
        "findings": findings,
        # 否决分布分类（按问题分类统计 red 条数）
        "knockout_distribution": {"价格策略": 1},
        # 扣分分布分类（按问题分类统计 yellow 条数）
        "deduction_distribution": {"资质/信誉": 2, "技术响应": 1, "商务条款": 1},
        "fix_priority": [
            {"rank": 1, "id": "H-02", "reason": "报价明细算术错误致与总价勾稽不符，拒不澄清将废标，是唯一废标点。"},
            {"rank": 2, "id": "H-01", "reason": "业绩MES金额未单列，影响资格认定与类似业绩加分，应补强扫描件。"},
            {"rank": 3, "id": "H-07", "reason": "加分证书与连续3个月社保扫描件须核验补齐，关乎约9分。"},
            {"rank": 4, "id": "H-03", "reason": "国家级可信数据空间试点材料缺失，直接丢2分。"},
        ],
    }
    if key == "twoissues":
        return _to_twoissues(base)
    return base


def _to_twoissues(base: dict) -> dict:
    """演示变体：在原始投标基础上，把人为改出的报价超限由合规翻为否决，
    并同步统计/结论/优先级（有效期仍为合规）。"""
    r = copy.deepcopy(base)
    fmap = {f["id"]: f for f in r["findings"]}
    fmap["G-01"].update({
        "severity": "red", "is_knockout": True,
        "title": "投标报价超最高限价",
        "description": "投标报价5,800,000元，已超过最高投标限价5,732,400元，按招标规定其投标将被否决。",
        "rule_reference": "最高投标限价5,732,400.00元，投标人的报价不得超过最高投标限价，否则其投标将被否决。",
        "bid_reference": "投标报价：大写 伍佰捌拾万元整（¥5,800,000）。",
        "law_reference": "招标文件第三章评标办法 2.1.2 符合性评审（2）投标报价超过最高投标限价的；第二章投标人须知前附表 3.2.4",
        "suggestion": "将投标报价下调至不超过最高投标限价5,732,400元后再投。",
        "actions": [],
        "score_impact": "否决项·报价超限即废标",
        "category": "价格策略",
        "rule_section": "第二章 投标人须知 · 3.2.4 最高投标限价",
    })
    r["counts"] = {"red": 2, "yellow": 4, "blue": 3, "green": 5}
    r["knockout_distribution"] = {"价格策略": 2}
    r["deduction_distribution"] = {"资质/信誉": 2, "技术响应": 1, "商务条款": 1}
    r["overall_score"] = 0
    r["is_rejected"] = True
    r["overall_verdict"] = "存在2项废标点（报价超最高限价、报价明细算术勾稽），投标将被否决；须整改后再投。"
    r["score_note"] = "修正报价至限价内、报价明细算术并补强材料后，预计可达88分以上。"
    r["fix_priority"] = [
        {"rank": 1, "id": "G-01", "reason": "报价580万超最高限价573.24万，直接废标，须先把报价压到限价内。"},
        {"rank": 2, "id": "H-02", "reason": "报价明细算术错误致与总价勾稽不符，拒不澄清将废标。"},
        {"rank": 3, "id": "H-01", "reason": "业绩MES金额未单列，影响资格认定与加分，应补强。"},
        {"rank": 4, "id": "H-03", "reason": "国家级可信数据空间试点材料缺失，直接丢2分。"},
    ]
    return r
