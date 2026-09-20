# ==============================================================================
# Multi-Stage Production Dockerfile for Audio_Too Platform
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: Builder (Compiles C++ native DSP kernels and installs dependencies)
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install C++ compiler toolchain and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang \
    g++ \
    make \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and C++ native kernel source files
COPY requirements.txt pyproject.toml /build/
COPY studio/audio_analysis/audio_analysis/dsp_engine/native /build/studio/audio_analysis/audio_analysis/dsp_engine/native

# Compile native C++ DSP kernels
RUN clang++ -shared -fPIC -O3 \
    studio/audio_analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.cpp \
    -o studio/audio_analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.so && \
    clang++ -shared -fPIC -O3 \
    studio/audio_analysis/audio_analysis/dsp_engine/native/limiter_kernel.cpp \
    -o studio/audio_analysis/audio_analysis/dsp_engine/native/limiter_kernel.so

# Build Python wheels into wheelhouse
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt fpdf2

# ------------------------------------------------------------------------------
# STAGE 2: Production Runner (Minimal runtime container)
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app:/app/studio/audio_analysis:/app/studio/audiogen/audiogen:/app/studio/kenn:/app/server/app"

WORKDIR /app

# Install runtime shared libraries (libgomp for openmp / math libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled wheels and install
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application source code
COPY . /app/

# Copy compiled native C++ shared libraries from builder stage
COPY --from=builder /build/studio/audio_analysis/audio_analysis/dsp_engine/native/*.so /app/studio/audio_analysis/audio_analysis/dsp_engine/native/

# Make entrypoint executable
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Expose FastAPI web server port
EXPOSE 8080

# Healthcheck endpoint -- the real server (server/app/server.py, launched
# by docker-entrypoint.sh) has no /healthz route. "/" is public and cheap
# (serves the static index), so it's used as the liveness check instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["web-server"]
