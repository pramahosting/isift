"""Podcast video editing with ffmpeg.

The editor works on a timeline: an ordered list of segments, each one a stretch of one source file (`start`..`end` seconds).
Everything the editor offers is a change to that list, so one renderer covers all of it:

  * cut / trim        - a segment's start and end move in
  * cut out a section - split a segment in two and drop the middle
  * join videos       - put segments from different files one after the other
  * insert a clip     - split a segment where the clip goes and put the clip between the two halves. A 10 second video with a
                        2 second clip inserted at the 4th second is 4 s + 2 s + 6 s = 12 s. The original is not overwritten.
  * smooth            - a short crossfade (picture and sound) at every join, and a fade in and out at the ends
  * voice-over        - recordings laid on top of the final timeline at a chosen time; the original sound can be lowered or muted
  * background        - a green (or other plain) background keyed out and replaced by a colour or a picture
  * polish            - gentle noise reduction and even loudness

Output is H.264 / AAC in an MP4 file, which YouTube and every device accept."""
import json, shutil, subprocess
from dataclasses import dataclass, field
from pathlib import Path

class EditError(Exception): pass

MAX_SEGMENTS = 60
MAX_VOICEOVERS = 12
MAX_OUTPUT_SECONDS = 4 * 3600
FADE_MAX = 3.0
XFADE_MAX = 2.0
HEIGHTS = {"source": 0, "1080": 1080, "720": 720, "480": 480}

@dataclass
class Segment:
    source: str                     # a key into the files given to render()
    start: float
    end: float

@dataclass
class VoiceOver:
    source: str
    at: float                       # seconds on the finished timeline
    gain: float = 1.0

@dataclass
class Background:
    mode: str                       # "color" | "image"
    key_color: str = "00ff00"       # the plain colour to remove (green screen by default)
    similarity: float = 0.25
    color: str = "1b2a41"           # replacement colour (mode=color)
    image: str = ""                 # key into files (mode=image)

@dataclass
class Plan:
    segments: list[Segment]
    crossfade: float = 0.0          # seconds of overlap at every join
    fade_in: float = 0.0
    fade_out: float = 0.0
    voiceovers: list[VoiceOver] = field(default_factory=list)
    original_volume: float = 1.0    # 0 mutes the original sound, 1 keeps it
    background: Background | None = None
    polish: bool = False
    height: str = "source"

def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

def probe(path: Path) -> dict:
    """Length, picture size and whether there is a picture and sound, read from the file itself."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)], capture_output=True, timeout=120)
        j = json.loads(r.stdout or b"{}")
    except Exception: raise EditError("That file could not be read as a video.")
    st = j.get("streams") or []
    v = next((s for s in st if s.get("codec_type") == "video"), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    dur = float((j.get("format") or {}).get("duration") or 0)
    if dur <= 0:
        # a browser recording (WebM) carries no length in its header: count the frames and samples instead
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-stats", "-i", str(path), "-f", "null", "-"], capture_output=True, timeout=1800, text=True)
            import re
            m = re.findall(r"time=(\d+):(\d+):(\d+\.?\d*)", (r.stderr or "").replace("\r", "\n"))
            if m: h, mi, s = m[-1]; dur = int(h) * 3600 + int(mi) * 60 + float(s)
        except Exception: pass
    if dur <= 0 and not (v or a): raise EditError("That file could not be read as a video or sound.")
    return {"duration": round(dur, 3), "has_video": bool(v), "has_audio": bool(a), "width": int((v or {}).get("width") or 0), "height": int((v or {}).get("height") or 0)}

def remux(src: Path, dst: Path, fmt: str = "webm") -> bool:
    """Copy a browser WebM into a file that has a length and can be searched, without re-encoding (nothing is lost)."""
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", "-f", fmt, str(dst)], capture_output=True, timeout=1800)
        return r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
    except Exception:
        dst.unlink(missing_ok=True); return False

def total_seconds(plan: Plan) -> float:
    n = len(plan.segments)
    t = sum(max(0.0, s.end - s.start) for s in plan.segments)
    return max(0.0, t - xfade_for(plan) * max(0, n - 1))

def xfade_for(plan: Plan) -> float:
    """A crossfade can never be longer than half of the shortest segment, or it would eat the segment."""
    if plan.crossfade <= 0 or len(plan.segments) < 2: return 0.0
    shortest = min(max(0.0, s.end - s.start) for s in plan.segments)
    return round(max(0.0, min(plan.crossfade, XFADE_MAX, shortest / 2 - 0.01)), 3)

def validate(plan: Plan, info: dict[str, dict]) -> None:
    if not plan.segments: raise EditError("The timeline is empty. Add at least one clip.")
    if len(plan.segments) > MAX_SEGMENTS: raise EditError(f"At most {MAX_SEGMENTS} pieces on one timeline.")
    if len(plan.voiceovers) > MAX_VOICEOVERS: raise EditError(f"At most {MAX_VOICEOVERS} voice-overs.")
    for s in plan.segments:
        i = info.get(s.source)
        if not i: raise EditError("A clip on the timeline could not be found.")
        if not (0 <= s.start < s.end): raise EditError("A clip has an end before its start.")
        if s.end > i["duration"] + 0.25: raise EditError(f"A clip runs past the end of its video ({i['duration']:.1f} s).")
        if not i["has_video"] and not i["has_audio"]: raise EditError("A clip has no picture or sound.")
    if total_seconds(plan) > MAX_OUTPUT_SECONDS: raise EditError("The finished video would be longer than 4 hours.")
    if plan.height not in HEIGHTS: raise EditError("Unknown output size.")
    if plan.background and plan.background.mode not in ("color", "image"): raise EditError("Unknown background.")
    for v in plan.voiceovers:
        if v.source not in info: raise EditError("A voice-over file could not be found.")

def _hex(c: str, default: str) -> str:
    c = (c or "").lstrip("#").lower()
    return c if len(c) == 6 and all(ch in "0123456789abcdef" for ch in c) else default

def build_command(plan: Plan, files: dict[str, Path], info: dict[str, dict], out: Path) -> list[str]:
    """The ffmpeg command for a plan. Kept apart from running it, so it can be tested without rendering."""
    validate(plan, info)
    order: list[str] = []
    for s in plan.segments:
        if s.source not in order: order.append(s.source)
    for v in plan.voiceovers:
        if v.source not in order: order.append(v.source)
    if plan.background and plan.background.mode == "image":
        if plan.background.image not in files: raise EditError("The background picture could not be found.")
        if plan.background.image not in order: order.append(plan.background.image)
    idx = {k: i for i, k in enumerate(order)}
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    for k in order:
        if plan.background and plan.background.mode == "image" and k == plan.background.image: cmd += ["-loop", "1"]
        cmd += ["-i", str(files[k])]

    # output picture size: the first clip with a picture sets it, unless a smaller size was chosen
    first = next((info[s.source] for s in plan.segments if info[s.source]["has_video"]), None)
    W, H = (first["width"], first["height"]) if first else (1280, 720)
    cap = HEIGHTS[plan.height]
    if cap and H > cap: W, H = round(W * cap / H), cap
    W, H = max(2, W - W % 2), max(2, H - H % 2)
    fps = 30
    xf = xfade_for(plan)
    n = len(plan.segments)
    f: list[str] = []
    vlabels, alabels, durs = [], [], []
    for i, s in enumerate(plan.segments):
        src = info[s.source]; d = round(s.end - s.start, 3); durs.append(d); k = idx[s.source]
        # picture: a clip with no picture (sound only) becomes a plain dark frame, so audio-only pieces can sit among videos
        if src["has_video"]:
            vf = f"[{k}:v]trim=start={s.start}:end={s.end},setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p[v{i}]"
        else:
            vf = f"color=c=0x101820:s={W}x{H}:r={fps}:d={d},format=yuv420p[v{i}]"
        f.append(vf)
        if src["has_audio"]:
            f.append(f"[{k}:a]atrim=start={s.start}:end={s.end},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:
            f.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d},asetpts=PTS-STARTPTS[a{i}]")
        vlabels.append(f"v{i}"); alabels.append(f"a{i}")
    # join the pieces: a plain join, or a crossfade at each join (smooth)
    if n == 1:
        f.append(f"[{vlabels[0]}]null[vj]"); f.append(f"[{alabels[0]}]anull[aj]")
    elif xf > 0:
        cur, acur, elapsed = vlabels[0], alabels[0], durs[0]
        for i in range(1, n):
            nv, na = ("vj" if i == n - 1 else f"vx{i}"), ("aj" if i == n - 1 else f"ax{i}")
            f.append(f"[{cur}][{vlabels[i]}]xfade=transition=fade:duration={xf}:offset={round(elapsed - xf, 3)}[{nv}]")
            f.append(f"[{acur}][{alabels[i]}]acrossfade=d={xf}:c1=tri:c2=tri[{na}]")
            elapsed = elapsed + durs[i] - xf; cur, acur = nv, na
    else:
        f.append("".join(f"[{v}][{a}]" for v, a in zip(vlabels, alabels)) + f"concat=n={n}:v=1:a=1[vj][aj]")
    total = total_seconds(plan)
    vcur = "vj"
    # background: remove a plain colour behind the person and put a colour or a picture there
    bg = plan.background
    if bg:
        key = _hex(bg.key_color, "00ff00"); sim = max(0.05, min(0.6, bg.similarity))
        f.append(f"[{vcur}]colorkey=0x{key}:{sim}:0.1,format=yuva420p[fg]")
        if bg.mode == "image":
            f.append(f"[{idx[bg.image]}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps},format=yuv420p[bgi]")
        else:
            f.append(f"color=c=0x{_hex(bg.color, '1b2a41')}:s={W}x{H}:r={fps}:d={round(total + 1, 3)},format=yuv420p[bgi]")
        f.append("[bgi][fg]overlay=shortest=1:format=auto,format=yuv420p[vbg]"); vcur = "vbg"
    vf = []
    if plan.polish: vf.append("hqdn3d=2:1.5:3:3")
    fi, fo = max(0.0, min(plan.fade_in, FADE_MAX, total / 2)), max(0.0, min(plan.fade_out, FADE_MAX, total / 2))
    if fi: vf.append(f"fade=t=in:st=0:d={fi}")
    if fo: vf.append(f"fade=t=out:st={round(total - fo, 3)}:d={fo}")
    f.append(f"[{vcur}]{','.join(vf) if vf else 'null'}[vout]")
    # sound: the original (louder or quieter), voice-overs on top, then fades and an even level
    af = []
    ov = max(0.0, min(2.0, plan.original_volume))
    af.append(f"volume={ov}")
    f.append(f"[aj]{','.join(af)}[abase]")
    mix = ["abase"]
    for j, v in enumerate(plan.voiceovers):
        at = max(0.0, v.at); ms = int(round(at * 1000)); g = max(0.0, min(3.0, v.gain))
        f.append(f"[{idx[v.source]}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={g},adelay={ms}|{ms}[vo{j}]"); mix.append(f"vo{j}")
    if len(mix) > 1:
        f.append("".join(f"[{m}]" for m in mix) + f"amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0[amixed]"); acur = "amixed"
    else: acur = "abase"
    ach = []
    if plan.polish: ach += ["highpass=f=70", "afftdn=nf=-30", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    if fi: ach.append(f"afade=t=in:st=0:d={fi}")
    if fo: ach.append(f"afade=t=out:st={round(total - fo, 3)}:d={fo}")
    f.append(f"[{acur}]{','.join(ach) if ach else 'anull'}[aout]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", str(round(total, 3)), str(out)]
    return cmd

def render(plan: Plan, files: dict[str, Path], out: Path, timeout: int = 7200, on_progress=None) -> dict:
    """Make the finished MP4. Returns its measured length, size and picture size. on_progress(percent) is called while it works."""
    import time
    if not have_ffmpeg(): raise EditError("Video editing needs ffmpeg on the server, and it is not installed.")
    info = {k: probe(p) for k, p in files.items()}
    cmd = build_command(plan, files, info, out)
    cmd[1:1] = ["-progress", "pipe:1", "-nostats"]
    total = max(0.1, total_seconds(plan)); err = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import threading
    t = threading.Thread(target=lambda: err.append(p.stderr.read()), daemon=True); t.start()
    t0 = time.time()
    try:
        for line in p.stdout:
            if line.startswith("out_time_us=") and on_progress:
                try: on_progress(min(99, int(int(line.split("=")[1]) / 1e6 * 100 / total)))
                except ValueError: pass
            if time.time() - t0 > timeout: p.kill(); out.unlink(missing_ok=True); raise EditError("The edit took too long and was stopped. Try a shorter timeline.")
        p.wait(); t.join(5)
    finally:
        if p.poll() is None: p.kill()
    if p.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        tail = ((err[0] if err else "") or "").strip().splitlines()[-1:] or [""]
        raise EditError("The video could not be put together: " + tail[0][:200])
    got = probe(out)
    return {"duration": got["duration"], "width": got["width"], "height": got["height"], "size_bytes": out.stat().st_size}
