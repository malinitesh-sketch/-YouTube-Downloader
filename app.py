import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, after_this_request, jsonify, request, send_file, send_from_directory
from yt_dlp import YoutubeDL

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")


def is_allowed_url(url: str) -> bool:
    """Allow common YouTube URL hosts only."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        return parsed.scheme in {"http", "https"} and host in {
            "youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }
    except Exception:
        return False


def clean_title(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name or "download")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:90] or "download"


def ydl_info(url: str):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def format_selector(kind: str, quality: str, file_format: str) -> str:
    quality = str(quality or "best").lower()
    file_format = str(file_format or "mp4").lower()

    height_map = {
        "2160": 2160,
        "4k": 2160,
        "1440": 1440,
        "2k": 1440,
        "1080": 1080,
        "720": 720,
        "480": 480,
        "360": 360,
    }
    height = None
    for key, value in height_map.items():
        if key in quality:
            height = value
            break

    if kind == "audio":
        return "bestaudio/best"

    if height:
        if file_format == "webm":
            return f"bestvideo[height<={height}][ext=webm]+bestaudio[ext=webm]/best[height<={height}]/best"
        return f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]/best"

    if file_format == "webm":
        return "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"
    return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"


@app.route("/")
def home():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.post("/api/info")
def api_info():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()

    if not is_allowed_url(url):
        return jsonify({"error": "Please enter a valid YouTube link."}), 400

    try:
        info = ydl_info(url)
        formats = []
        seen = set()
        for f in info.get("formats", []):
            height = f.get("height")
            ext = f.get("ext")
            if height and ext:
                key = (height, ext)
                if key not in seen:
                    seen.add(key)
                    formats.append({"height": height, "ext": ext})
        formats = sorted(formats, key=lambda x: x["height"], reverse=True)[:30]

        return jsonify({
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
            "formats": formats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/download")
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    kind = (data.get("type") or "video").lower()
    quality = data.get("quality") or "best"
    file_format = (data.get("format") or "mp4").lower().replace(".", "")
    include_subtitles = bool(data.get("subtitles"))
    embed_thumbnail = bool(data.get("embedThumbnail"))

    if not is_allowed_url(url):
        return jsonify({"error": "Please enter a valid YouTube link."}), 400
    if kind not in {"video", "audio", "thumbnail"}:
        return jsonify({"error": "Invalid download type."}), 400

    tmpdir = tempfile.mkdtemp(prefix="yt_download_")

    @after_this_request
    def cleanup(response):
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        return response

    try:
        if kind == "thumbnail":
            info = ydl_info(url)
            thumb_url = info.get("thumbnail")
            if not thumb_url:
                return jsonify({"error": "Thumbnail not found."}), 404
            response = requests.get(thumb_url, timeout=30)
            response.raise_for_status()
            ext = "jpg"
            content_type = response.headers.get("content-type", "")
            if "webp" in content_type:
                ext = "webp"
            filename = f"{clean_title(info.get('title'))}-thumbnail.{ext}"
            file_path = Path(tmpdir) / filename
            file_path.write_bytes(response.content)
            return send_file(file_path, as_attachment=True, download_name=filename)

        outtmpl = str(Path(tmpdir) / "%(title).90s-%(id)s.%(ext)s")
        postprocessors = []

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": format_selector(kind, quality, file_format),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "windowsfilenames": True,
        }

        if kind == "video":
            if file_format in {"mp4", "webm"}:
                ydl_opts["merge_output_format"] = file_format
        else:
            if file_format not in {"mp3", "m4a", "opus", "wav"}:
                file_format = "mp3"
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": file_format,
                "preferredquality": "192",
            })

        if include_subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["en", "en.*"]
            ydl_opts["subtitlesformat"] = "srt/best"

        if embed_thumbnail:
            ydl_opts["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail"})

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = [p for p in Path(tmpdir).iterdir() if p.is_file()]
        if not files:
            return jsonify({"error": "Download failed. No output file was created."}), 500

        media_exts = {"mp4", "webm", "mkv", "mp3", "m4a", "opus", "wav"}
        media_files = [p for p in files if p.suffix.lower().lstrip(".") in media_exts]

        # If subtitles or thumbnails created extra files, return a zip so nothing is lost.
        if include_subtitles and len(files) > 1:
            zip_path = Path(tmpdir) / "download-with-subtitles.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in files:
                    if p != zip_path:
                        zf.write(p, arcname=p.name)
            return send_file(zip_path, as_attachment=True, download_name=zip_path.name)

        chosen = media_files[0] if media_files else files[0]
        return send_file(chosen, as_attachment=True, download_name=chosen.name)

    except Exception as e:
        return jsonify({
            "error": str(e),
            "hint": "If this is MP3, 1080p, 2K, or 4K, install ffmpeg and restart the app. Also make sure you have permission to download this video.",
        }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
