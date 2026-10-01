FROM python:3.12-slim

# Metadata
LABEL maintainer="Cyber Ghost"
LABEL description="AIS Global Tracker — Real-time ship tracking"
LABEL version="16.1"

# Working directory
WORKDIR /app

# Install system deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY CGOSM.py .

# Data volume
ENV AIS_DATA_DIR=/data
RUN mkdir -p /data
VOLUME ["/data"]

# Port
EXPOSE 7999

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7999/api/health')" || exit 1

# Run
CMD ["python", "CGOSM.py"]