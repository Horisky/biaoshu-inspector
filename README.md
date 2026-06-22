# 标书规范性检测（独立版）

一个**完全独立**的小应用，从主平台「标书智造」分离出的 AI 合规审核能力。
上传【招标文件】+【投标文件】，自动出具八大维度的规范性 / 废标风险检测报告。

## 能力

- 📄 解析 PDF / Word，自动抽取招标需求与评分标准
- 🔍 **八大维度**检测：评标办法 · 资格 · 技术规范 · 合同条款 · 规范性 · 法律法规 · 一致性 · 有效性
- 🚦 **三色分级**：🔴 否决项（废标风险） / 🟡 扣分项 / 🟢 合规
- 📊 预估得分、问题清单（含招标条款依据、法律依据、修改建议、扣分影响）、修改优先级

## 运行

```powershell
# 1. 配置（已内置可用 key；交付时复制 .env.example 为 .env 并填写）
#    DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY / DEEPSEEK_MODEL

# 2. 安装依赖（若用主项目 conda 环境 bidgen 则已齐，可跳过）
pip install -r requirements.txt

# 3. 启动
.\start.ps1
#    或： python server.py
```

打开浏览器 → http://localhost:8100

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/`            | 检测页面 |
| GET  | `/api/health`  | 健康检查（含 LLM 配置状态） |
| POST | `/api/inspect` | `multipart`：`tender_file`（招标）+ `bid_file`（投标）→ 检测报告 JSON |

## 结构

```
bid-inspector/
  server.py            独立 FastAPI 服务（端口 8100）
  core/
    config.py          配置（读 .env）
    parser.py          PDF/Word → 文本 + 章节切分
    llm_client.py      LLM 客户端（OpenAI 兼容）
    extractor.py       招标需求抽取（两轮 LLM）
    reviewer.py        八维度审核引擎（核心）
  static/index.html    前端单页
  .env                 配置
  requirements.txt
```

> 与主平台共享审核 prompt 逻辑，但代码自包含、可单独打包部署。
