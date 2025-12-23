# KIAI Assistant Dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  gcc curl \
  && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy dependency metadata first (for better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies without the project source (for cache friendliness)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and assets
COPY src/ ./src/
COPY web_client/ ./web_client/
COPY README.md ./
# COPY .env* ./

# Install the project into the venv
RUN uv sync --frozen --no-dev

# Create sessions directory
RUN mkdir -p sessions

# Use the uv-managed virtualenv by default
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 5050

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5050/')" || exit 1

# Run application
CMD ["uv", "run", "uvicorn", "cti.app:app", "--host", "0.0.0.0", "--port", "5050"]
