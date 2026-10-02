# Build from the monorepo root:
#   docker build -f products/kenn/packages/chat/Dockerfile .
# The index is built from the notes under apps/backend/src/kenn, which are
# git-ignored data, so this only works on a checkout that has them on disk.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUDIO_TOO_LLM_ENABLED=0 \
    KENN_CHAT_INDEX_DIR=/app/runtime-index \
    KENN_CHAT_RUNTIME_DIR=/tmp/kenn-chat-runtime

WORKDIR /app

# The wrapper finds the engine at ../../apps/backend/src relative to itself,
# and its requirements file includes the backend's, so keep the product layout.
COPY products/kenn/apps/backend/requirements.txt /app/products/kenn/apps/backend/requirements.txt
COPY products/kenn/packages/chat/requirements.txt /app/products/kenn/packages/chat/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/products/kenn/packages/chat/requirements.txt

COPY products/kenn/apps/backend/src /app/products/kenn/apps/backend/src
COPY products/kenn/packages/chat /app/products/kenn/packages/chat

RUN python /app/products/kenn/packages/chat/build_runtime_index.py

WORKDIR /app/products/kenn/packages/chat
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
