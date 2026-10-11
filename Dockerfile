# 常驻容器 —— ⚠️ **刻意不用 serverless**：
# 多 agent 串行调 LLM，一次审计可能几十秒，会撞上 Vercel/Lambda 免费档的执行时长上限。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY src/ ./src/
COPY mcp_server/ ./mcp_server/
COPY scripts/ ./scripts/
COPY assets/ ./assets/
# 把响应缓存打进镜像：/example 与示例报告全部命中缓存，于是「演示路径零 API 花费」，
# 公开演示不会被访客烧钱（访客上传新截图才会真调模型）。
COPY llm_cache/ ./llm_cache/
COPY frontend/index.html ./frontend/index.html
# 数据只管投档线那部分，原始 CSV 不进镜像（见 .dockerignore）
COPY data/gaokao.db ./data/gaokao.db

ENV PYTHONPATH=/app/src
# 容器内必须绑 0.0.0.0，否则宿主连不上（端口映射形同虚设）
ENV HOST=0.0.0.0
EXPOSE 8000
# 只读查询 + 进程内护栏；对外必须经过配额（api/main.py 的 conn_factory + guard）
CMD ["python", "scripts/serve.py"]
