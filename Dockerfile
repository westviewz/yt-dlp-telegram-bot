# Use the official lightweight Python image
FROM python:3.10-slim

# Install system dependencies
# - ffmpeg: Required by yt-dlp to merge video and audio streams
# - curl & unzip: Required to install Deno (the JS runtime for yt-dlp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip && \
    curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
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
