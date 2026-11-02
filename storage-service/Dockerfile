# ------------------------------------------------------------
# HIAS Storage Service Dockerfile
# ------------------------------------------------------------
# Base image – a small, official Python image with pip.
FROM python:3.11-slim

# Create a non‑root user (optional but good practice)
RUN useradd -m appuser

# Set the working directory inside the container
WORKDIR /app

# Switch to the non‑root user
USER appuser

# Install the Python dependencies listed in the service’s requirements file.
# Build context is the repository root (..). Copy from the storage-service subdirectory.
COPY storage-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the storage-service source code (app package and other files).
COPY storage-service/. .

# Copy the shared contract schemas so validators can locate them.
COPY shared-contracts ./shared-contracts

# Expose the port that the FastAPI server listens on (Compose already maps it).
EXPOSE 8005

# Default command – launch the FastAPI app with uvicorn via the Python module loader.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
