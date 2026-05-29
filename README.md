# YouTube Downloader Web App

A small local web app that can fetch video information and download **video, audio, or thumbnail** using `yt-dlp`.

> Use this only for videos you own, videos with permission, or content that is legally allowed to download. Do not use it to bypass DRM, paywalls, private access, or copyright restrictions.

## Requirements

- Python 3.10+
- `ffmpeg` installed for MP3 conversion, audio extraction, and merging best video + audio.

### Install ffmpeg

**Windows:** Download from https://ffmpeg.org/download.html and add `ffmpeg/bin` to PATH.  
**macOS:** `brew install ffmpeg`  
**Ubuntu/Debian:** `sudo apt install ffmpeg`

## Run

```bash
cd youtube-downloader-app
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open in browser:

```text
http://127.0.0.1:5000
```

## Notes

- 1080p/2K/4K often needs ffmpeg because YouTube stores video and audio separately.
- If MP3 download fails, install ffmpeg and restart the app.
- Very long videos can take time to process.
