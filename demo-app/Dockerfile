FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /app/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY templates ./templates
COPY static ./static
ENV DEMO_DB_PATH=/app/data/demo.db
EXPOSE 8000
# Render sets PORT
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
