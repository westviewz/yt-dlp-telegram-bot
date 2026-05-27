# Use the official lightweight Python image
FROM python:3.10-slim

# Install system dependencies (FFmpeg is required by yt-dlp to merge formats)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy requirements file first to take advantage of Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Run the Telegram Bot
CMD ["python", "bot.py"]
