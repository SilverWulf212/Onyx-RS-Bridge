# RepairShopr Connector for Onyx
# Multi-stage build for optimal image size

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Production stage
FROM python:3.11-slim AS production

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash connector && \
    chown -R connector:connector /app && \
    mkdir -p /home/connector/.onyx-rs-bridge && \
    chown -R connector:connector /home/connector/.onyx-rs-bridge

USER connector

# Set Python path
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from repairshopr_connector import RepairShoprConnector; print('OK')"

# Default command - run sync (can be overridden)
CMD ["rs-onyx", "sync"]
