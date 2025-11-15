FROM python:3.12-slim

# Add Debian multimedia repo for full ffmpeg
RUN apt-get update && apt-get install -y wget gnupg && \
    echo "deb http://www.deb-multimedia.org bookworm main non-free" \
    >> /etc/apt/sources.list && \
    wget http://www.deb-multimedia.org/pool/main/d/deb-multimedia-keyring/deb-multimedia-keyring_2023.02.18_all.deb && \
    dpkg -i deb-multimedia-keyring_2023.02.18_all.deb && \
    apt-get update && \
    apt-get install -y ffmpeg

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade yt-dlp

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port $PORT"]
