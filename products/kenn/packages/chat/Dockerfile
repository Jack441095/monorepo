FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUDIO_TOO_LLM_ENABLED=0 \
    KENN_ENGINE_ROOT=/app/Audio_Too/studio/kenn \
    KENN_CHAT_INDEX_DIR=/app/runtime-index \
    KENN_CHAT_RUNTIME_DIR=/tmp/kenn-chat-runtime

WORKDIR /app

# Keep the engine as a read-only source dependency. Generated index state is
# built below in /app/runtime-index, never in Audio_Too.
COPY Audio_Too/requirements.txt /app/Audio_Too/requirements.txt
COPY Audio_Too/studio/kenn /app/Audio_Too/studio/kenn
COPY products/kenn/chat /app/products/kenn/chat

RUN python -m pip install --no-cache-dir \
    -r /app/Audio_Too/studio/kenn/kenn/requirements.txt \
    && python /app/products/kenn/chat/build_runtime_index.py

WORKDIR /app/products/kenn/chat
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
