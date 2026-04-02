FROM python:3.12-slim

LABEL maintainer="jai@akilamirthya.in"
LABEL description="Alchemy AI Trading Platform"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install git+https://github.com/QuantInsti/pyfolio.git || true && \
    pip install git+https://github.com/QuantInsti/zipline-pipeline.git || true

COPY . .
RUN pip install -e . --no-deps

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
