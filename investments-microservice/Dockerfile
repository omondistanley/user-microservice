FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/build

WORKDIR /app

# Build deps for building wheels (e.g. multitasking from yfinance); removed after pip install
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 build-essential \
    && mkdir -p /build

COPY requirements.txt ./requirements.txt
# Use TMPDIR to avoid /tmp I/O contention; prefer binary wheels where possible
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefer-binary -r requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y --purge \
    && rm -rf /var/lib/apt/lists/* /build/*

COPY app ./app
COPY framework ./framework
COPY migrations ./migrations
COPY run_migration.py ./run_migration.py

EXPOSE 3003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3003"]
