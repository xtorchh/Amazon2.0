# Use a Python 3.12 slim image based on Debian Bookworm (Debian 12)
# Slim images are smaller and good for production, while Bookworm is a recent stable Debian.
FROM python:3.12-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Set environment variables to prevent Python from writing .pyc files
# and to unbuffer stdout/stderr, which is good for logging in containers.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies required by Playwright browsers.
# This list is comprehensive for Debian-based distributions.
# --no-install-recommends helps keep the image size down.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm-dev \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence-dev \
    libxkbcommon0 \
    xdg-utils \
    libgbm-dev \
    libpulse0 \
    libexpat1 \
    libfontconfig1 \
    libpng16-16 \
    libfreetype6 \
    libjpeg62-turbo \
    libwebp7 \
    libharfbuzz0b \
    libevent-2.1-7 \
    ca-certificates \
    # Clean up apt caches to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the working directory
# This step is done early to leverage Docker's build cache.
COPY requirements.txt .

# Install Python dependencies from requirements.txt
# --no-cache-dir prevents pip from storing cached wheels, reducing image size.
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries and their additional dependencies.
# This is the crucial step that was previously done as a build command.
RUN playwright install --with-deps

# Copy the rest of your application code into the working directory
# The '.' at the end means "copy everything from the current directory on the host"
# to the current WORKDIR (/app) in the container.
COPY . .

# Command to run the application when the container starts.
# This will execute your scraper.py script.
CMD ["python", "scraper.py"]

