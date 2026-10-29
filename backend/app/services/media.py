"""Image and video conversion. Images are converted in memory and returned. Videos are kept only in blob storage (Cloudflare R2): the upload, the converted file and nothing in the database."""
import io, json, os, re, shutil, subprocess
from pathlib import Path

IMAGE_IN = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "ico", "heic", "avif"}
IMAGE_OUT = {"jpg": ("JPEG", "image/jpeg"), "png": ("PNG", "image/png"), "gif": ("GIF", "image/gif"), "webp": ("WEBP", "image/webp"), "bmp": ("BMP", "image/bmp"),
             "tiff": ("TIFF", "image/tiff"), "ico": ("ICO", "image/x-icon"), "pdf": ("PDF", "application/pdf")}
VIDEO_IN = {"mp4", "mov", "webm", "mkv", "avi", "m4v", "wmv", "flv", "mpg", "mpeg", "3gp", "ts"}
COMPRESS = {"hevc": "H.265 (HEVC)", "av1": "AV1"}          # re-encode into a smaller MP4
QUALITY = {"small": 0, "balanced": 1, "high": 2}
VIDEO_OUT = {"hevc": "video/mp4", "av1": "video/mp4", "mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm", "mkv": "video/x-matroska", "avi": "video/x-msvideo", "gif": "image/gif", "mp3": "audio/mpeg"}

class MediaError(Exception): pass

def ext(name: str) -> str:
    return Path(name or "").suffix.lower().lstrip(".")

def convert_image(data: bytes, to: str, name: str = "") -> tuple[bytes, str]:
    from PIL import Image, ImageSequence
    if to not in IMAGE_OUT: raise MediaError("That output format is not available.")
    fmt, mime = IMAGE_OUT[to]
    try: im = Image.open(io.BytesIO(data)); im.load()
    except Exception:
        if ext(name) in ("heic", "avif"): raise MediaError("This HEIC/AVIF picture could not be read on this server.")
        raise MediaError("That file could not be read as a picture.")
    out = io.BytesIO()
    if fmt == "GIF" and getattr(im, "is_animated", False):
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
        frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], loop=0, duration=im.info.get("duration", 80), disposal=2)
    elif getattr(im, "is_animated", False) and fmt == "WEBP":
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
        frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], loop=0, duration=im.info.get("duration", 80))
    else:
        if fmt in ("JPEG", "BMP", "PDF") and (im.mode in ("RGBA", "LA", "P") or "transparency" in im.info):
            rgba = im.convert("RGBA"); bg = Image.new("RGB", rgba.size, (255, 255, 255)); bg.paste(rgba, mask=rgba.split()[3]); im = bg      # transparent areas become white
        elif fmt in ("JPEG", "BMP", "PDF") and im.mode != "RGB": im = im.convert("RGB")
        elif fmt == "GIF" and im.mode not in ("P", "L", "RGB", "RGBA"): im = im.convert("RGBA")
        kw = {"quality": 92} if fmt in ("JPEG", "WEBP") else {}
        if fmt == "ICO": im = im.convert("RGBA"); kw["sizes"] = [(min(256, im.width), min(256, im.height))]
        if fmt == "PDF": kw["resolution"] = 150.0
        im.save(out, fmt, **kw)
    return out.getvalue(), mime

def probe_seconds(path: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, timeout=60)
        return float(json.loads(r.stdout or b"{}").get("format", {}).get("duration") or 0)
    except Exception: return 0.0

def out_ext(to: str) -> str:
    return "mp4" if to in COMPRESS else to

def _encoders() -> str:
    try: return subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    except Exception: return ""

def _compress_args(to: str, q: str, threads: int = 2) -> list[str]:
    lvl = QUALITY.get(q, 1); enc = _encoders()
    if to == "hevc":
        if "libx265" not in enc: raise MediaError("H.265 is not available on this server.")
        return ["-c:v", "libx265", "-preset", ("medium", "fast", "fast")[lvl], "-crf", str((30, 26, 23)[lvl]), "-x265-params", f"pools={threads}:frame-threads=2", "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-c:a", "aac", "-b:a", ("96k", "128k", "160k")[lvl], "-movflags", "+faststart"]
    if "libsvtav1" in enc:
        v = ["-c:v", "libsvtav1", "-preset", "9", "-crf", str((40, 35, 30)[lvl]), "-svtav1-params", f"lp={threads}", "-pix_fmt", "yuv420p"]
    elif "libaom-av1" in enc:
        v = ["-c:v", "libaom-av1", "-crf", str((38, 33, 28)[lvl]), "-b:v", "0", "-cpu-used", "6", "-row-mt", "1", "-pix_fmt", "yuv420p"]
    else: raise MediaError("AV1 is not available on this server.")
    return [*v, "-c:a", "aac", "-b:a", ("96k", "128k", "160k")[lvl], "-movflags", "+faststart"]

def _args(to: str, q: str = "balanced", threads: int = 2) -> list[str]:
    if to in COMPRESS: return _compress_args(to, q, threads)
    return {
        "mp4": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        "mov": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        "mkv": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"],
        "webm": ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-deadline", "realtime", "-cpu-used", "6", "-row-mt", "1", "-c:a", "libopus", "-b:a", "96k"],
        "avi": ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame", "-b:a", "128k"],
        "gif": ["-vf", "fps=12,scale='min(480,iw)':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse", "-an", "-loop", "0"],
        "mp3": ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"]}[to]

def convert_video(src: Path, dst: Path, to: str, on_progress=None, timeout: int = 7200, quality: str = "balanced"):
    """Runs ffmpeg; on_progress gets a 0..1 fraction. Raises MediaError with a plain reason."""
    if not shutil.which("ffmpeg"): raise MediaError("Video conversion is not available on this server (ffmpeg is missing).")
    total = probe_seconds(src)
    threads = max(1, min(int(os.environ.get("MEDIA_THREADS", "2")), os.cpu_count() or 1))      # leave the rest of the server to everyone else: a big encode must never starve the website
    cmd = ["ffmpeg", "-y", "-nostdin", "-threads", str(threads), "-i", str(src), *_args(to, quality, threads), "-progress", "pipe:1", "-nostats", str(dst)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=lambda: os.nice(15))
    import threading, time
    t0 = time.time(); err = []
    threading.Thread(target=lambda: err.append(p.stderr.read()), daemon=True).start()
    for line in p.stdout:
        if on_progress and total and line.startswith("out_time_ms="):
            try: on_progress(min(0.99, int(line.split("=")[1]) / 1e6 / total))
            except ValueError: pass
        if time.time() - t0 > timeout: p.kill(); raise MediaError("The conversion took too long and was stopped.")
    p.wait()
    if p.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        tail = re.sub(r"\s+", " ", (err[0] if err else "")[-300:]).strip()
        raise MediaError("That video could not be converted" + (" (" + tail + ")" if tail else "") + ".")
