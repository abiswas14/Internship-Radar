FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/swe-job-radar.db

WORKDIR /app

RUN addgroup --system radar && adduser --system --ingroup radar radar

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data && chown -R radar:radar /app
USER radar

VOLUME ["/app/data"]
CMD ["python", "-m", "swe_job_radar", "run"]

