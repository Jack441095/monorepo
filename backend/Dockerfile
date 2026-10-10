FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations as a separate deployment step. Keep the web
# container focused on serving the already-migrated application so an ordinary
# restart cannot implicitly execute schema changes.
# app.main already logs status and latency without query strings. Uvicorn access
# logs would copy magic-link and download tokens from URLs into provider logs.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
