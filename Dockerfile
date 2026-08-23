# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY collectors ./collectors
COPY db ./db
COPY engine ./engine
COPY packages ./packages
COPY services ./services
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SIRIUS_ROOT=/app
RUN groupadd --system sirius && useradd --system --gid sirius --home /app sirius
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=sirius:sirius alembic.ini ./
COPY --chown=sirius:sirius alembic ./alembic
COPY --chown=sirius:sirius data ./data
COPY --chown=sirius:sirius docs ./docs
RUN mkdir -p /app/storage && chown sirius:sirius /app/storage
USER sirius
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=4s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
