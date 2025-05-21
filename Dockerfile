FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Environment variables can be specified at runtime
ENV TELEGRAM_BOT_TOKEN=""
ENV MAX_FILE_SIZE=52428800
ENV DEBUG_MODE=false

# Create volume for downloads and cookies
# VOLUME ["/app/downloads"]

# Set the entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the bot
CMD ["python", "main.py"]
