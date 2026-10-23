# ==============================================================================
# Production Dockerfile for HIAS FastAPI Backend
# ==============================================================================

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthchecks, build-essential for C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY . .

# Ensure storage directories exist for SQLite database or data files
RUN mkdir -p /app/data /app/logs_data

# Create dedicated non-root application user for production security compliance
RUN adduser --disabled-password --gecos "" hias && \
    chown -R hias:hias /app

USER hias

# Expose internal backend application port
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI backend on internal port 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
