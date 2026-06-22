# 部署到 Render + 绑定 biaoshu.aivault.asia

本应用已容器化（Dockerfile 内含中文字体），可一键部署到 Render 免费版。

## 一、推送到 GitHub

```powershell
cd bid-inspector
git init
git add .
git commit -m "标书规范性检测 - 可部署版"
# 在 github.com 新建一个空仓库（例如 biaoshu-inspector），然后：
git remote add origin https://github.com/<你的用户名>/biaoshu-inspector.git
git branch -M main
git push -u origin main
```

> `.env` 已被 `.gitignore` 排除，密钥不会进仓库。

## 二、在 Render 创建服务

1. 打开 https://dashboard.render.com → **New +** → **Web Service**
2. 连接上面的 GitHub 仓库
3. Render 会自动识别 `render.yaml`（Docker 运行时，free 计划）。若手动配置：
   - Runtime: **Docker**
   - Health Check Path: `/api/health`
   - Instance Type: **Free**
4. **Environment** 里填入环境变量（关键，密钥在这里填，不入库）：
   | Key | Value |
   |-----|-------|
   | `DEEPSEEK_BASE_URL` | `https://api.router.one/v1` |
   | `DEEPSEEK_API_KEY`  | `（你的 key）` |
   | `DEEPSEEK_MODEL`    | `deepseek-v4-pro` |
   | `MAX_UPLOAD_MB`     | `30` |
5. 部署完成后会得到一个地址，形如 `https://biaoshu-inspector.onrender.com`，先访问确认能打开。

## 三、绑定子域名 biaoshu.aivault.asia

1. Render 服务页 → **Settings → Custom Domains → Add** → 填 `biaoshu.aivault.asia`
2. Render 会给出一个 CNAME 目标，形如 `biaoshu-inspector.onrender.com`
3. 到 Cloudflare → `aivault.asia` → **DNS → Add record**：
   - Type: **CNAME**
   - Name: `biaoshu`
   - Target: `（Render 给的 onrender.com 地址）`
   - Proxy status: **DNS only（灰云）** ← 重要，见下方说明
4. 等 Render 显示 “Certificate Issued” 即可用 https://biaoshu.aivault.asia 访问。

### 为什么用「DNS only / 灰云」
单次检测要跑 3 次大模型调用，约 100~130 秒。Cloudflare 免费版对**代理（橙云）**的请求有 **100 秒超时**（会报 524）。设为 DNS only 让请求直连 Render，避开该限制；Render 自己会签发 HTTPS 证书。

## 注意事项

- **免费版会休眠**：15 分钟无访问后休眠，下次访问冷启动约需 30~60 秒。
- **无访问控制 + 内置付费 key**：当前完全公开，任何人都能用并消耗你的 API 额度。若日后要收口，可加共享密码或 Cloudflare Access。
- 若检测请求偶发超时，可把检测改为「异步任务 + 轮询」模式（找我改）。
