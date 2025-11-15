# -------------------------
# BASE IMAGE
# -------------------------
FROM python:3.12-slim

# -------------------------
# INSTALL STATIC FFMPEG (FULL CODECS)
# -------------------------
RUN apt-get update && apt-get install -y wget xz-utils && \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar -xvf ffmpeg-release-amd64-static.tar.xz && \
    cp ffmpeg-*-static/ffmpeg /usr/local/bin/ && \
    cp ffmpeg-*-static/ffprobe /usr/local/bin/ && \
    rm -rf ffmpeg-*-static ffmpeg-release-amd64-static.tar.xz && \
    apt-get purge -y wget xz-utils && apt-get autoremove -y && apt-get clean

# -------------------------
# WORKDIR & APP FILES
# -------------------------
WORKDIR /app
COPY . /app

# -------------------------
# PYTHON DEPENDENCIES
# -------------------------
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade yt-dlp

# -------------------------
# ENVIRONMENT & PORT
# -------------------------
ENV PORT=8000

EXPOSE 8000

# -------------------------
# RUNNING FASTAPI
# -------------------------
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port $PORT"]
