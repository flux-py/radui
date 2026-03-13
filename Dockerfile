# Production Dockerfile for RADUI v1.0.0 Applications
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools and compile dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY RADUI ./RADUI

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir ".[server,postgres,redis]"

# Runtime stage
FROM python:3.12-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -r RADUI && useradd -r -g RADUI -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . /app
RUN chown -R appuser:RADUI /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PORT=3000 \
    HOST=0.0.0.0

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/_gx/health || exit 1

CMD ["python", "-m", "RADUI.cli", "serve", "--port", "3000", "--host", "0.0.0.0"]
