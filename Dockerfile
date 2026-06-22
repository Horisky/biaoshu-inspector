FROM python:3.11-slim

# 中文字体（PDF 导出需要）：文泉驿微米黑/正黑，体积小、覆盖广
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-microhei fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render 会注入 PORT 环境变量；本地默认 8100
ENV PORT=8100
EXPOSE 8100

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8100}"]
