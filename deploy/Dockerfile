FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 ANONYMIZED_TELEMETRY=False \
    REPORT_FONT_PATH=/usr/share/fonts/truetype/wqy/wqy-microhei.ttc
WORKDIR /app
COPY deploy/requirements.txt /tmp/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/storage /app/docs \
    && chown -R appuser:appuser /app/storage
COPY backend /app/backend
COPY data/cases /app/data/cases
COPY data/knowledge /app/data/knowledge
COPY index.html app.js client-ui.js styles.css /app/
COPY ["docs/数据与材料收集清单.md", "/app/docs/"]
COPY assets/reports/qinghe_plan_demo.pdf /app/assets/reports/
RUN python backend/scripts/check_readiness.py --json
USER appuser
EXPOSE 8000
CMD ["python", "backend/run.py"]
