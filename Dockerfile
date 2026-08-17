FROM python:3.12-slim

# 1. 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. 工作目录
WORKDIR /app

# 3. 先装依赖(利用 Docker 缓存)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 4. 拷应用代码
COPY app/ ./app/
COPY h5/ ./h5/
COPY admin-web/ ./admin-web/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY upload.js package.json package-lock.json* ./

# 5. 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 6. 运行时配置
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    UPLOAD_DIR=/data/uploads

# 7. 数据目录(挂卷)
RUN mkdir -p /data/uploads /data/db
VOLUME ["/data/uploads", "/data/db"]

EXPOSE 8000

# 8. 启动:4 worker(可以按机器调)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
