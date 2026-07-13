FROM python:3.9.13
WORKDIR /app

# 1. Install system dependencies needed for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 2. Directly download and install the official Chrome package
RUN wget -q https://google.com \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# 3. Python application setup (Cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy code last (Speeds up future builds)
COPY . .

EXPOSE 3000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
