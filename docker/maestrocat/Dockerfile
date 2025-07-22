# docker/maestrocat/Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy MaestroCat code
COPY . /app/

# Install MaestroCat and dependencies
RUN pip install --no-cache-dir -e .

# Create necessary directories
RUN mkdir -p /app/logs /app/config

EXPOSE 8080 8765

# Default command
CMD ["python", "-m", "core.apps.debug_ui"]