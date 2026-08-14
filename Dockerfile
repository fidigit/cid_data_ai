FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Node 运行时用于调用 scripts/build_report.mjs。生产镜像还必须在 /app/node_modules
# 提供经组织审核的 @oai/artifact-tool（建议由内部基础镜像或构建缓存注入）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app ./app
COPY scripts ./scripts
COPY sql ./sql

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

