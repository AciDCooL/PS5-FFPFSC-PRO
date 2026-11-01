FROM python:3.11-slim

LABEL maintainer="AciDCooL"
LABEL description="PS5 FFPFSC PRO - Web & Containerized Headless Packing Tool"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PORT=8080 \
    HOST=0.0.0.0 \
    XDG_CONFIG_HOME=/config

# Install system dependencies (for 7z/RAR archive unpacking support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    unrar-free \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install Python dependencies (ignoring Windows-specific packages)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create volume mount points
RUN mkdir -p /config /games /output /temp

VOLUME ["/config", "/games", "/output", "/temp"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/api/status || exit 1

ENTRYPOINT ["python", "PS5_FFPFSC_PRO_v1.3.0.py", "--headless"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
