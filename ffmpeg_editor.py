from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
import glob
import json
import os
import re
import shutil
import subprocess
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:  # pragma: no cover
    pass

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # pragma: no cover - handled at runtime if dependency is missing
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None

try:
    from google import genai as google_genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    google_genai = None
    genai_types = None

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def env_path(name, default):
    return os.path.expanduser(os.getenv(name, default))


def env_int(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_str(name, default=""):
    return (os.getenv(name, default) or default).strip()


def file_mtime(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


def static_asset_version():
    root = os.path.dirname(os.path.abspath(__file__))
    return str(
        max(
            file_mtime(os.path.join(root, "static", "app.css")),
            file_mtime(os.path.join(root, "static", "app.js")),
        )
    )


def env_bin(name, default, executable):
    configured = env_path(name, default)
    if os.path.exists(configured):
        return configured
    return shutil.which(executable) or configured


def parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ts_to_seconds(ts):
    ts = ts.strip().split()[0]
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_ts(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def parse_srt_entries(raw):
    entries = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block in blocks:
        lines = [line.rstrip() for line in block.strip().split("\n") if line.strip()]
        ts_line = next((line for line in lines if "-->" in line), None)
        if not ts_line:
            continue
        parts = ts_line.split("-->")
        if len(parts) != 2:
            continue
        try:
            start_time = ts_to_seconds(parts[0])
            end_time = ts_to_seconds(parts[1])
        except Exception:
            continue
        text_lines = [line for line in lines if line != ts_line and not line.strip().isdigit()]
        text = re.sub(r"<[^>]+>", "", "\n".join(text_lines)).strip()
        if not text:
            continue
        entries.append({"start": start_time, "end": end_time, "text": text})
    return entries


def read_srt_entries(srt_path):
    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as handle:
            return parse_srt_entries(handle.read())
    except OSError:
        return []


def pick_font_file():
    return next(
        (
            path
            for path in (
                "/System/Library/Fonts/HelveticaNeue.ttc",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            )
            if os.path.exists(path)
        ),
        None,
    )


def get_caption_position(alignment, margin):
    vertical_group = ((alignment - 1) // 3) if 1 <= alignment <= 9 else 0
    horizontal_group = (alignment - 1) % 3 if 1 <= alignment <= 9 else 1

    if horizontal_group == 0:
        x_expr = str(margin)
    elif horizontal_group == 1:
        x_expr = "(w-text_w)/2"
    else:
        x_expr = f"w-text_w-{margin}"

    if vertical_group == 0:
        y_expr = f"h-text_h-{margin}"
    elif vertical_group == 1:
        y_expr = "(h-text_h)/2"
    else:
        y_expr = str(margin)
    return x_expr, y_expr


def get_text_anchor(alignment):
    horizontal_group = (alignment - 1) % 3 if 1 <= alignment <= 9 else 1
    return ("left", "center", "right")[horizontal_group]


def load_caption_font(fontsize):
    if ImageFont is None:
        raise RuntimeError("Pillow is not installed")
    font = pick_font_file()
    if font:
        try:
            return ImageFont.truetype(font, fontsize)
        except OSError:
            pass
    return ImageFont.load_default()


def wrap_caption_text(text, font, max_width):
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is not installed")
    probe = ImageDraw.Draw(Image.new("RGBA", (max_width, 10), (0, 0, 0, 0)))
    lines = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            bbox = probe.textbbox((0, 0), trial, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return "\n".join(lines)


def build_caption_overlay_image(text, frame_width, frame_height, fontsize, alignment, boxed, job_id, segment_index, cue_index):
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is not installed")

    font = load_caption_font(fontsize)
    margin = 72
    canvas = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    anchor = get_text_anchor(alignment)
    max_text_width = max(200, int(frame_width * 0.82))
    wrapped_text = wrap_caption_text(text, font, max_text_width)
    spacing = 10
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=spacing, align=anchor)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding_x = 26
    padding_y = 18
    box_width = min(frame_width - margin * 2, text_width + padding_x * 2)
    box_height = text_height + padding_y * 2

    x_expr, y_expr = get_caption_position(alignment, margin)
    if x_expr == "(w-text_w)/2":
        box_x = int((frame_width - box_width) / 2)
    elif x_expr.startswith("w-text_w-"):
        box_x = frame_width - box_width - margin
    else:
        box_x = margin

    if y_expr == "(h-text_h)/2":
        box_y = int((frame_height - box_height) / 2)
    elif y_expr.startswith("h-text_h-"):
        box_y = frame_height - box_height - margin
    else:
        box_y = margin

    box_x = max(margin // 2, min(box_x, frame_width - box_width - margin // 2))
    box_y = max(margin // 2, min(box_y, frame_height - box_height - margin // 2))
    text_x = box_x + (box_width - text_width) / 2 if anchor == "center" else box_x + padding_x
    if anchor == "right":
        text_x = box_x + box_width - text_width - padding_x
    text_y = box_y + padding_y

    if boxed:
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_width, box_y + box_height],
            radius=24,
            fill=(0, 0, 0, 168),
        )

    draw.multiline_text(
        (text_x, text_y),
        wrapped_text,
        font=font,
        fill=(255, 255, 255, 255),
        spacing=spacing,
        align=anchor,
        stroke_width=2 if boxed else 3,
        stroke_fill=(0, 0, 0, 220),
    )

    image_path = os.path.join("/tmp", f"reel_caption_{job_id}_{segment_index:02d}_{cue_index:02d}.png")
    canvas.save(image_path)
    return image_path


def trim_srt_segment(srt_path, start_s, end_s, out_path):
    """Trim an SRT file to [start_s, end_s] and write shifted timestamps."""

    entries = []
    for entry in read_srt_entries(srt_path):
        start_time = entry["start"]
        end_time = entry["end"]
        text = entry["text"]
        if end_time <= start_s or start_time >= end_s:
            continue
        clipped_start = max(0.0, start_time - start_s)
        clipped_end = min(end_s - start_s, end_time - start_s)
        if (clipped_end - clipped_start) < 0.15:
            continue
        entries.append((clipped_start, clipped_end, text))

    if not entries:
        return False

    out_blocks = []
    for idx, (start_time, end_time, text) in enumerate(entries, 1):
        out_blocks.append(f"{idx}\n{seconds_to_ts(start_time)} --> {seconds_to_ts(end_time)}\n{text}")

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("\n\n".join(out_blocks) + "\n")
    return True


CAPCUT_DIR = env_path("REVO_CAPCUT_DIR", "/Users/tobiaslundgren/Movies/CapCut")
EDITED_DIR = env_path("REVO_EDITED_DIR", os.path.join(CAPCUT_DIR, "vivi_edited"))
REELS_DIR = env_path("REVO_REELS_DIR", os.path.join(CAPCUT_DIR, "reels"))
CROPS_DIR = env_path("REVO_CROPS_DIR", os.path.join(CAPCUT_DIR, "crops"))
COMPRESSED_DIR = env_path("REVO_COMPRESSED_DIR", os.path.join(CROPS_DIR, "compressed"))
BATCH_EXPORTS_DIR = env_path("REVO_BATCH_DIR", os.path.expanduser("~/Desktop/Nexus Exports"))
STUDIO_DIR = env_path("REVO_STUDIO_DIR", os.path.join(os.path.expanduser("~/Desktop/Nexus Exports"), "studio"))
MODELS_DIR = env_path("REVO_MODELS_DIR", os.path.join(os.path.expanduser("~/Desktop/Nexus Exports"), "studio", "models"))
MODELS_JSON = os.path.join(MODELS_DIR, "models.json")
OVERLAY = env_path("REVO_OVERLAY_PATH", os.path.join(CAPCUT_DIR, "viviandco_overlay.png"))
FFMPEG = env_bin("REVO_FFMPEG_BIN", "/opt/homebrew/bin/ffmpeg", "ffmpeg")
FFPROBE = env_bin("REVO_FFPROBE_BIN", "/opt/homebrew/bin/ffprobe", "ffprobe")
YTDLP = env_bin("REVO_YTDLP_BIN", "/opt/homebrew/bin/yt-dlp", "yt-dlp")
PORT = env_int("REVO_PORT", 7777)

VIDEO_PATTERNS = ("*.mov", "*.mp4", "*.MOV", "*.MP4")
ALLOWED_MEDIA_ROOTS = (CAPCUT_DIR, EDITED_DIR, REELS_DIR)
POSITION_MAP = {
    "top-left": "x=W*0.03:y=H*0.04",
    "top-center": "x=(W-w)/2:y=H*0.04",
    "top-right": "x=W-w-W*0.03:y=H*0.04",
    "center-left": "x=W*0.03:y=(H-h)/2",
    "center": "x=(W-w)/2:y=(H-h)/2",
    "center-right": "x=W-w-W*0.03:y=(H-h)/2",
    "bottom-left": "x=W*0.03:y=H-h-H*0.04",
    "bottom-center": "x=(W-w)/2:y=H-h-H*0.04",
    "bottom-right": "x=W-w-W*0.03:y=H-h-H*0.04",
}
LOGO_CROP_FILTER = "crop=615:188:132:1827"

os.makedirs(EDITED_DIR, exist_ok=True)
os.makedirs(REELS_DIR, exist_ok=True)
os.makedirs(CROPS_DIR, exist_ok=True)
os.makedirs(COMPRESSED_DIR, exist_ok=True)
os.makedirs(BATCH_EXPORTS_DIR, exist_ok=True)
os.makedirs(STUDIO_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


def iter_video_paths(directory):
    for pattern in VIDEO_PATTERNS:
        yield from glob.glob(os.path.join(directory, pattern))


def describe_video(path):
    size = os.path.getsize(path)
    return {
        "name": os.path.basename(path),
        "path": path,
        "size": f"{size / 1024 / 1024:.1f}MB",
        "mtime": int(os.path.getmtime(path)),
    }


def list_videos(directory):
    files = [describe_video(path) for path in iter_video_paths(directory) if os.path.isfile(path)]
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files


def resolve_media_path(raw_path):
    if not raw_path:
        return None
    candidate = os.path.realpath(raw_path)
    if not os.path.isfile(candidate):
        return None
    if os.path.splitext(candidate)[1].lower() not in {".mov", ".mp4"}:
        return None
    for root in ALLOWED_MEDIA_ROOTS:
        root_path = os.path.realpath(root)
        if candidate == root_path or candidate.startswith(root_path + os.sep):
            return candidate
    return None


def get_tool_status():
    return {
        "ffmpeg": os.path.exists(FFMPEG),
        "ffprobe": os.path.exists(FFPROBE),
        "yt_dlp": os.path.exists(YTDLP),
        "overlay": os.path.exists(OVERLAY),
    }


def get_tool_versions():
    commands = {
        "ffmpeg": [FFMPEG, "-version"],
        "ffprobe": [FFPROBE, "-version"],
        "yt_dlp": [YTDLP, "--version"],
    }
    versions = {}
    for key, command in commands.items():
        if not os.path.exists(command[0]):
            versions[key] = None
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            first_line = (result.stdout or result.stderr or "").strip().splitlines()
            versions[key] = first_line[0] if first_line else None
        except Exception:
            versions[key] = None
    return versions


def get_workspace_snapshot(include_versions=False):
    tools = get_tool_status()
    source_files = list_videos(CAPCUT_DIR)
    edited_files = list_videos(EDITED_DIR)
    reel_files = list_videos(REELS_DIR)
    snapshot = {
        "tools": tools,
        "counts": {
            "source": len(source_files),
            "edited": len(edited_files),
            "reels": len(reel_files),
        },
        "directories": {
            "source": CAPCUT_DIR,
            "edited": EDITED_DIR,
            "reels": REELS_DIR,
            "crops": CROPS_DIR,
            "compressed": COMPRESSED_DIR,
            "batch": BATCH_EXPORTS_DIR,
        },
        "config": {
            "overlay": OVERLAY,
            "port": PORT,
        },
        "recent_outputs": {
            "edited": edited_files[:8],
            "reels": reel_files[:8],
        },
        "ready": all(tools.values()),
    }
    if include_versions:
        snapshot["tool_versions"] = get_tool_versions()
    return snapshot


def json_body():
    return request.get_json(silent=True) or {}


@app.route("/")
def index():
    return render_template(
        "index.html",
        ga4_measurement_id=env_str("REVO_GA4_MEASUREMENT_ID"),
        asset_version=static_asset_version(),
    )


@app.route("/status")
def status():
    return jsonify(get_workspace_snapshot())


@app.route("/health")
def health():
    snapshot = get_workspace_snapshot(include_versions=True)
    return (
        jsonify(
            {
                "ok": snapshot["ready"],
                "port": PORT,
                "tools": snapshot["tools"],
                "tool_versions": snapshot["tool_versions"],
                "directories": snapshot["directories"],
                "overlay": snapshot["config"]["overlay"],
            }
        ),
        200 if snapshot["ready"] else 503,
    )


@app.route("/outputs")
def outputs():
    return jsonify(get_workspace_snapshot()["recent_outputs"])


@app.route("/files")
def list_files():
    return jsonify(list_videos(CAPCUT_DIR))


@app.route("/info", methods=["POST"])
def video_info():
    path = resolve_media_path(json_body().get("path", ""))
    if not path:
        return jsonify({"error": "Invalid or unsupported video path"}), 400
    if not os.path.exists(FFPROBE):
        return jsonify({"error": "ffprobe is not available on this machine"}), 503
    try:
        result = subprocess.run(
            [
                FFPROBE,
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})
        return jsonify(
            {
                "width": stream.get("width"),
                "height": stream.get("height"),
                "duration": fmt.get("duration", 0),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)})


@app.route("/video")
def serve_video():
    path = resolve_media_path(request.args.get("path", ""))
    if path:
        return send_file(path, conditional=True)
    return "Not found", 404


@app.route("/render", methods=["POST"])
def render_video():
    data = json_body()
    path = resolve_media_path(data.get("path"))
    if not path:
        return jsonify({"ok": False, "error": "Pick a valid source video from the workspace first"}), 400
    if not os.path.exists(FFMPEG):
        return jsonify({"ok": False, "error": "ffmpeg is not available on this machine"}), 503
    if not os.path.exists(OVERLAY):
        return jsonify({"ok": False, "error": "Overlay asset is missing"}), 503

    position = data.get("position", "center")
    logo_size = parse_int(data.get("logo_size"), 600)
    fade = bool(data.get("fade", True))
    fade_duration = parse_float(data.get("fade_duration"), 3.0)
    fade_len = parse_float(data.get("fade_len"), 2.0)
    bg = bool(data.get("bg", False))
    duration = max(parse_float(data.get("video_duration"), 0.0), 0.0)
    cta = bool(data.get("cta", False))
    cta_text = str(data.get("cta_text", "@viviandco"))
    cta_effect = data.get("cta_effect", "slide")
    cta_arrow = bool(data.get("cta_arrow", True))
    cta_pill = bool(data.get("cta_pill", False))
    cta_start_offset = parse_float(data.get("cta_start"), 3.0)
    ghost = bool(data.get("ghost", False))
    ghost_size = parse_int(data.get("ghost_size"), 1000)
    ghost_opacity = parse_float(data.get("ghost_opacity"), 0.12)
    ghost_position = data.get("ghost_position", "center")
    ghost_fade = bool(data.get("ghost_fade", False))
    ghost_start_offset = parse_float(data.get("ghost_start_offset"), 3.0)
    ghost_fade_len = parse_float(data.get("ghost_fade_len"), 1.5)

    overlay_pos = POSITION_MAP.get(position, POSITION_MAP["top-center"])
    ghost_pos = POSITION_MAP.get(ghost_position, POSITION_MAP["center"])

    logo_chain = f"[1:v]{LOGO_CROP_FILTER},scale={logo_size}:-1,format=rgba"
    if bg:
        logo_chain += ",pad=w=iw+40:h=ih+24:x=20:y=12:color=black@0.5"
    logo_chain += "[logo_scaled]"

    if fade and duration > 0:
        fade_start = max(0.0, duration - fade_duration)
        logo_chain += (
            f";[logo_scaled]loop=loop=-1:size=1:start=0,trim=end={duration},"
            f"setpts=PTS-STARTPTS,geq=lum='p(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
            f"a='clip(((T-{fade_start})/{fade_len})*alpha(X,Y)*255,0,255)'[logo_final]"
        )
    else:
        logo_chain += ";[logo_scaled]null[logo_final]"

    if ghost_fade and duration > 0:
        ghost_start = max(0.0, duration - ghost_start_offset)
        ghost_chain = (
            f"[1:v]{LOGO_CROP_FILTER},scale={ghost_size}:-1,format=rgba,"
            f"colorchannelmixer=aa={ghost_opacity:.3f},loop=loop=-1:size=1:start=0,"
            f"trim=end={duration},setpts=PTS-STARTPTS,fade=t=in:st={ghost_start}:"
            f"d={ghost_fade_len}:alpha=1[ghost_logo]"
        )
    else:
        ghost_chain = (
            f"[1:v]{LOGO_CROP_FILTER},scale={ghost_size}:-1,format=rgba,"
            f"colorchannelmixer=aa={ghost_opacity:.3f}[ghost_logo]"
        )

    base = os.path.splitext(os.path.basename(path))[0]
    output = os.path.join(EDITED_DIR, f"{base}_vivi.mov")

    filter_complex = None
    if cta and duration > 0:
        cta_start = max(0.0, duration - cta_start_offset)
        font = pick_font_file()
        font_opt = f"fontfile={font}:" if font else ""
        safe_text = cta_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        if cta_effect == "slide":
            y_expr = f"'(H*0.55-th/2)+120*max(0,1-(t-{cta_start})/0.7)'"
            alpha_expr = f"'clip((t-{cta_start})/0.7,0,1)'"
        else:
            y_expr = "'(H*0.55-th/2)'"
            alpha_expr = f"'clip((t-{cta_start})/1.0,0,1)'"
        box_str = ":box=1:boxcolor=black@0.35:boxborderw=28" if cta_pill else ""
        drawtext_chain = (
            f"drawtext={font_opt}text='{safe_text}':fontsize=88:fontcolor=white:"
            f"x='(W-tw)/2':y={y_expr}:alpha={alpha_expr}{box_str}"
        )
        if cta_arrow:
            arrow_start = cta_start + 0.4
            drawtext_chain += (
                f",drawtext={font_opt}text='↑':fontsize=60:fontcolor=white:"
                f"x='(W-tw)/2':y='(H*0.55+80)+15*sin(t*5)':"
                f"alpha='clip((t-{arrow_start})/0.5,0,1)'"
            )
        if ghost:
            filter_complex = (
                f"{ghost_chain};{logo_chain};"
                f"[0:v][ghost_logo]overlay={ghost_pos}[vg];"
                f"[vg][logo_final]overlay={overlay_pos}[vlogo];"
                f"[vlogo]{drawtext_chain}[vfinal]"
            )
        else:
            filter_complex = (
                f"{logo_chain};[0:v][logo_final]overlay={overlay_pos}[vlogo];"
                f"[vlogo]{drawtext_chain}[vfinal]"
            )
        cmd = [
            FFMPEG,
            "-i",
            path,
            "-i",
            OVERLAY,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vfinal]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            output,
            "-y",
        ]
    else:
        if ghost:
            filter_complex = (
                f"{ghost_chain};{logo_chain};"
                f"[0:v][ghost_logo]overlay={ghost_pos}[vg];"
                f"[vg][logo_final]overlay={overlay_pos}[vfinal]"
            )
            cmd = [
                FFMPEG,
                "-i",
                path,
                "-i",
                OVERLAY,
                "-filter_complex",
                filter_complex,
                "-map",
                "[vfinal]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "fast",
                "-c:a",
                "copy",
                output,
                "-y",
            ]
        else:
            filter_complex = f"{logo_chain};[0:v][logo_final]overlay={overlay_pos}"
            cmd = [
                FFMPEG,
                "-i",
                path,
                "-i",
                OVERLAY,
                "-filter_complex",
                filter_complex,
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "fast",
                "-c:a",
                "copy",
                output,
                "-y",
            ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return jsonify({"ok": True, "output": output})
        return jsonify({"ok": False, "error": (result.stderr or "Render failed")[-600:]})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/yt_info", methods=["POST"])
def yt_info():
    url = str(json_body().get("url", "")).strip()
    if not url:
        return jsonify({"error": "Enter a YouTube URL first"}), 400
    if not os.path.exists(YTDLP):
        return jsonify({"error": "yt-dlp is not installed"}), 503
    try:
        result = subprocess.run(
            [YTDLP, "--dump-json", "--no-playlist", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return jsonify({"error": (result.stderr or "Could not fetch video info")[-400:]})
        data = json.loads(result.stdout)
        return jsonify(
            {
                "title": data.get("title"),
                "uploader": data.get("uploader"),
                "duration": data.get("duration"),
                "thumbnail": data.get("thumbnail"),
                "view_count": data.get("view_count"),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)})


@app.route("/yt_reels", methods=["POST"])
def yt_reels():
    data = json_body()
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "Enter a YouTube URL first"}), 400
    if not os.path.exists(YTDLP):
        return jsonify({"ok": False, "error": "yt-dlp is not installed"}), 503
    if not os.path.exists(FFMPEG) or not os.path.exists(FFPROBE):
        return jsonify({"ok": False, "error": "ffmpeg and ffprobe are required to cut reels"}), 503

    reel_dur = parse_int(data.get("reel_duration"), 30)
    cut_mode = data.get("cut_mode", "auto")
    manual_cuts = data.get("manual_cuts", [])
    add_logo = bool(data.get("add_logo", True))
    logo_position = data.get("logo_position", "top-center")
    crop_portrait = bool(data.get("crop_portrait", True))
    add_captions = bool(data.get("add_captions", False))
    caption_lang = str(data.get("caption_lang", "en")).strip() or "en"
    caption_fontsize = parse_int(data.get("caption_fontsize"), 28)
    caption_alignment = parse_int(data.get("caption_alignment"), 2)
    caption_box = bool(data.get("caption_box", True))
    if add_captions and Image is None:
        return jsonify({"ok": False, "error": "Pillow is required for caption overlays"}), 503
    if add_logo and not os.path.exists(OVERLAY):
        return jsonify({"ok": False, "error": "Overlay asset is missing"}), 503

    job_id = str(uuid.uuid4())[:8]
    dl_path = os.path.join(REELS_DIR, f"source_{job_id}.mp4")

    download_cmd = [
        YTDLP,
        "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format",
        "mp4",
        "-o",
        dl_path,
        "--no-playlist",
        url,
    ]
    try:
        download = subprocess.run(download_cmd, capture_output=True, text=True, timeout=300)
        if download.returncode != 0:
            return jsonify({"ok": False, "error": (download.stderr or "Download failed")[-400:]})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})

    srt_master = None
    if add_captions:
        subtitle_base = os.path.join(REELS_DIR, f"source_{job_id}")
        subtitle_cmd = [
            YTDLP,
            "--write-auto-subs",
            "--sub-langs",
            caption_lang,
            "--convert-subs",
            "srt",
            "--skip-download",
            "-o",
            subtitle_base,
            "--no-playlist",
            url,
        ]
        try:
            subprocess.run(subtitle_cmd, capture_output=True, text=True, timeout=60)
            candidates = glob.glob(f"{subtitle_base}.*.srt")
            if candidates:
                srt_master = candidates[0]
        except Exception:
            srt_master = None

    try:
        probe = subprocess.run(
            [
                FFPROBE,
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                dl_path,
            ],
            capture_output=True,
            text=True,
        )
        probe_data = json.loads(probe.stdout or "{}")
        total_dur = float((probe_data.get("format") or {}).get("duration") or 0)
        stream = (probe_data.get("streams") or [{}])[0]
        source_width = parse_int(stream.get("width"), 0)
        source_height = parse_int(stream.get("height"), 0)
    except Exception:
        total_dur = 0.0
        source_width = 0
        source_height = 0

    if cut_mode == "manual" and manual_cuts:
        cuts = []
        for cut in manual_cuts:
            try:
                start = float(cut["start"])
                end = float(cut["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end > start >= 0:
                cuts.append((start, end))
        if not cuts:
            return jsonify({"ok": False, "error": "Manual cut points are missing or invalid"}), 400
    else:
        if total_dur <= 0:
            return jsonify({"ok": False, "error": "Could not detect video duration after download"}), 500
        cuts = []
        start = 0.0
        while start < total_dur:
            end = min(start + reel_dur, total_dur)
            if (end - start) >= 1:
                cuts.append((start, end))
            start += reel_dur

    if source_width <= 0 or source_height <= 0:
        return jsonify({"ok": False, "error": "Could not detect source video dimensions after download"}), 500

    if crop_portrait:
        final_width = min(source_width, max(1, int(source_height * 9 / 16)))
        final_height = source_height
    else:
        final_width = source_width
        final_height = source_height

    overlay_pos = POSITION_MAP.get(logo_position, POSITION_MAP["top-center"])
    reels = []
    last_error = None
    captions_burned = 0

    for index, (start, end) in enumerate(cuts, 1):
        output = os.path.join(REELS_DIR, f"reel_{job_id}_{index:02d}.mp4")
        segment_duration = end - start
        extra_inputs = []
        filter_parts = []
        current_video = "[0:v]"
        segment_has_subtitles = False

        if crop_portrait:
            filter_parts.append(f"{current_video}crop=ih*9/16:ih[vc]")
            current_video = "[vc]"

        next_input_index = 1
        if add_logo:
            extra_inputs += ["-i", OVERLAY]
            filter_parts.append(f"[{next_input_index}:v]{LOGO_CROP_FILTER},scale=500:-1,format=rgba[logo]")
            filter_parts.append(f"{current_video}[logo]overlay={overlay_pos}[vl]")
            current_video = "[vl]"
            next_input_index += 1

        if add_captions and srt_master:
            segment_srt = os.path.join("/tmp", f"reel_sub_{job_id}_{index:02d}.srt")
            has_subs = trim_srt_segment(srt_master, start, end, segment_srt)
            if has_subs:
                segment_entries = read_srt_entries(segment_srt)
                for cue_index, entry in enumerate(segment_entries, 1):
                    caption_image = build_caption_overlay_image(
                        entry["text"],
                        final_width,
                        final_height,
                        caption_fontsize,
                        caption_alignment,
                        caption_box,
                        job_id,
                        index,
                        cue_index,
                    )
                    extra_inputs += ["-i", caption_image]
                    next_label = f"[vsub{cue_index}]"
                    filter_parts.append(
                        f"{current_video}[{next_input_index}:v]overlay=0:0:"
                        f"enable='between(t,{entry['start']:.3f},{entry['end']:.3f})'{next_label}"
                    )
                    current_video = next_label
                    next_input_index += 1
                if segment_entries:
                    segment_has_subtitles = True

        base_inputs = [FFMPEG, "-ss", str(start), "-t", str(segment_duration), "-i", dl_path]
        codec = ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac", "-b:a", "128k"]

        if filter_parts:
            cmd = (
                base_inputs
                + extra_inputs
                + ["-filter_complex", ";".join(filter_parts), "-map", current_video, "-map", "0:a?"]
                + codec
                + [output, "-y"]
            )
        else:
            cmd = base_inputs + codec + [output, "-y"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(output):
                reels.append(output)
                if segment_has_subtitles:
                    captions_burned += 1
            else:
                last_error = (result.stderr or "FFmpeg did not write an output file")[-400:]
        except Exception as exc:
            last_error = str(exc)

    try:
        os.remove(dl_path)
    except OSError:
        pass
    if srt_master:
        try:
            os.remove(srt_master)
        except OSError:
            pass
    for path in glob.glob(f"/tmp/reel_sub_{job_id}_*.srt"):
        try:
            os.remove(path)
        except OSError:
            pass
    for path in glob.glob(f"/tmp/reel_caption_{job_id}_*.png"):
        try:
            os.remove(path)
        except OSError:
            pass

    caption_status = {
        "requested": add_captions,
        "source_found": bool(srt_master),
        "segments_burned": captions_burned,
    }
    if reels:
        return jsonify({"ok": True, "reels": reels, "caption_status": caption_status})
    return jsonify({"ok": False, "error": last_error or "No reels were created", "caption_status": caption_status})


ALLOWED_IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp'}

def safe_img_path(path):
    """Validate image path is an allowed extension and exists."""
    if not path:
        return None
    path = os.path.realpath(os.path.expanduser(path.strip()))
    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in ALLOWED_IMG_EXTS:
        return path
    return None


def image_has_alpha(img):
    return "A" in img.getbands() or (img.mode == "P" and "transparency" in img.info)


def normalize_image_for_crop(img):
    if ImageOps is not None:
        img = ImageOps.exif_transpose(img)
    return img


def crop_bounds(img, x, y, w, h):
    iw, ih = img.size
    x = min(max(0, x), max(0, iw - 1))
    y = min(max(0, y), max(0, ih - 1))
    w = min(max(1, w), iw - x)
    h = min(max(1, h), ih - y)
    return x, y, w, h


def build_crop_export(cropped, stem, source_ext, quality):
    source_ext = source_ext.lower()
    has_alpha = image_has_alpha(cropped)

    if source_ext in {".jpg", ".jpeg"} and not has_alpha:
        return {
            "path": f"{stem}.jpg",
            "format": "JPEG",
            "image": cropped.convert("RGB"),
            "save_kwargs": {"quality": quality, "subsampling": 0, "optimize": True},
        }
    if source_ext == ".webp":
        return {
            "path": f"{stem}.webp",
            "format": "WEBP",
            "image": cropped.convert("RGBA" if has_alpha else "RGB"),
            "save_kwargs": {"quality": quality, "method": 6},
        }

    compress_level = max(0, min(9, round((100 - quality) / 10)))
    return {
        "path": f"{stem}.png",
        "format": "PNG",
        "image": cropped.convert("RGBA" if has_alpha else "RGB"),
        "save_kwargs": {"optimize": True, "compress_level": compress_level},
    }

@app.route('/img_preview')
def img_preview():
    path = safe_img_path(request.args.get('path', ''))
    if path:
        return send_file(path)
    return 'Not found', 404

@app.route('/crop_image', methods=['POST'])
def crop_image():
    if Image is None:
        return jsonify({'ok': False, 'error': 'Pillow is not installed'})
    data = request.json or {}
    path = safe_img_path(data.get('path', ''))
    if not path:
        return jsonify({'ok': False, 'error': 'Invalid or missing image path'})
    x = max(0, parse_int(data.get('x'), 0))
    y = max(0, parse_int(data.get('y'), 0))
    w = max(1, parse_int(data.get('w'), 1))
    h = max(1, parse_int(data.get('h'), 1))
    quality = max(60, min(100, parse_int(data.get('quality'), 97)))
    try:
        img = normalize_image_for_crop(Image.open(path))
        x, y, w, h = crop_bounds(img, x, y, w, h)
        cropped = img.crop((x, y, x + w, y + h))
        base, _ = os.path.splitext(path)
        export = build_crop_export(cropped, f"{base}_crop_{x}_{y}_{w}x{h}", os.path.splitext(path)[1], quality)
        export["image"].save(export["path"], format=export["format"], **export["save_kwargs"])
        return jsonify({
            'ok': True,
            'output': export["path"],
            'format': export["format"],
            'size': f"{os.path.getsize(export['path'])/1024/1024:.1f}MB",
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/crop_upload', methods=['POST'])
def crop_upload():
    if Image is None:
        return jsonify({'ok': False, 'error': 'Pillow is not installed'})
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'No file uploaded'})
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMG_EXTS:
        return jsonify({'ok': False, 'error': 'Unsupported image type'})
    x = max(0, parse_int(request.form.get('x'), 0))
    y = max(0, parse_int(request.form.get('y'), 0))
    w = max(1, parse_int(request.form.get('w'), 1))
    h = max(1, parse_int(request.form.get('h'), 1))
    quality = max(60, min(100, parse_int(request.form.get('quality'), 97)))
    try:
        img = normalize_image_for_crop(Image.open(file.stream))
        x, y, w, h = crop_bounds(img, x, y, w, h)
        cropped = img.crop((x, y, x + w, y + h))
        base_name = os.path.splitext(filename)[0]
        export = build_crop_export(cropped, os.path.join(CROPS_DIR, f"{base_name}_crop_{x}_{y}_{w}x{h}"), ext, quality)
        export["image"].save(export["path"], format=export["format"], **export["save_kwargs"])
        return jsonify({
            'ok': True,
            'output': export["path"],
            'format': export["format"],
            'size': f"{os.path.getsize(export['path'])/1024/1024:.1f}MB",
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/compress_upload', methods=['POST'])
def compress_upload():
    if Image is None:
        return jsonify({'ok': False, 'error': 'Pillow is not installed'})
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'No file uploaded'})
    fmt = request.form.get('format', 'jpeg').lower()
    quality = max(40, min(100, parse_int(request.form.get('quality'), 90)))

    fmt_map = {
        'jpeg': ('JPEG', '.jpg'),
        'webp': ('WEBP', '.webp'),
        'png': ('PNG', '.png'),
    }
    if fmt not in fmt_map:
        return jsonify({'ok': False, 'error': 'Unsupported format'})
    pil_fmt, out_ext = fmt_map[fmt]

    try:
        import io
        raw = file.read()
        original_mb = len(raw) / 1024 / 1024
        img = normalize_image_for_crop(Image.open(io.BytesIO(raw)))
        has_alpha = image_has_alpha(img)

        if fmt == 'jpeg':
            if has_alpha:
                background = Image.new('RGB', img.size, (255, 255, 255))
                alpha_source = img.convert('RGBA')
                background.paste(alpha_source, mask=alpha_source.getchannel('A'))
                img = background
            else:
                img = img.convert('RGB')
        elif fmt == 'webp':
            img = img.convert('RGBA' if has_alpha else 'RGB')
        else:
            img = img.convert('RGBA' if has_alpha else 'RGB')

        base_name = os.path.splitext(os.path.basename(file.filename))[0]
        out = os.path.join(COMPRESSED_DIR, f"{base_name}_compressed{out_ext}")

        save_kwargs = {'optimize': True}
        if fmt == 'jpeg':
            save_kwargs.update({'quality': quality, 'subsampling': 0})
        elif fmt == 'webp':
            save_kwargs.update({'quality': quality, 'method': 6})
        else:
            save_kwargs['compress_level'] = max(0, min(9, round((100 - quality) / 10)))

        img.save(out, format=pil_fmt, **save_kwargs)
        out_mb = os.path.getsize(out) / 1024 / 1024
        savings = max(0.0, (original_mb - out_mb) / original_mb * 100) if original_mb > 0 else 0
        return jsonify({
            'ok': True,
            'output': out,
            'format': pil_fmt,
            'original_size': f"{original_mb:.1f} MB",
            'output_size': f"{out_mb:.1f} MB",
            'savings': f"{savings:.0f}%",
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def center_crop_to_ratio(img, ratio_w, ratio_h):
    iw, ih = img.size
    target = ratio_w / ratio_h
    current = iw / ih
    if current > target:
        new_w = round(ih * target)
        x = (iw - new_w) // 2
        return img.crop((x, 0, x + new_w, ih))
    else:
        new_h = round(iw / target)
        y = (ih - new_h) // 2
        return img.crop((0, y, iw, y + new_h))


@app.route('/batch_crop_upload', methods=['POST'])
def batch_crop_upload():
    if Image is None:
        return jsonify({'ok': False, 'error': 'Pillow is not installed'})
    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'ok': False, 'error': 'No files uploaded'})

    mode = request.form.get('mode', 'manual')  # 'center_ratio' or 'manual'
    ratio_w = max(1, parse_int(request.form.get('ratio_w'), 1))
    ratio_h = max(1, parse_int(request.form.get('ratio_h'), 1))
    x = max(0, parse_int(request.form.get('x'), 0))
    y = max(0, parse_int(request.form.get('y'), 0))
    w = max(1, parse_int(request.form.get('w'), 1))
    h = max(1, parse_int(request.form.get('h'), 1))
    quality = max(60, min(100, parse_int(request.form.get('quality'), 97)))
    proportional = request.form.get('proportional', 'true') == 'true'
    ref_w = max(1, parse_int(request.form.get('ref_w'), 1))
    ref_h = max(1, parse_int(request.form.get('ref_h'), 1))

    results = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = os.path.basename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_IMG_EXTS:
            results.append({'name': filename, 'ok': False, 'error': 'Unsupported format'})
            continue
        try:
            img = normalize_image_for_crop(Image.open(file.stream))
            iw, ih = img.size

            if mode == 'center_ratio':
                cropped = center_crop_to_ratio(img, ratio_w, ratio_h)
            else:
                if proportional:
                    ax = round(x * iw / ref_w)
                    ay = round(y * ih / ref_h)
                    aw = round(w * iw / ref_w)
                    ah = round(h * ih / ref_h)
                else:
                    ax, ay, aw, ah = x, y, w, h
                ax, ay, aw, ah = crop_bounds(img, ax, ay, aw, ah)
                cropped = img.crop((ax, ay, ax + aw, ay + ah))

            base_name = os.path.splitext(filename)[0]
            export = build_crop_export(
                cropped,
                os.path.join(BATCH_EXPORTS_DIR, f"{base_name}_crop"),
                ext,
                quality,
            )
            export["image"].save(export["path"], format=export["format"], **export["save_kwargs"])
            results.append({
                'name': filename,
                'ok': True,
                'output': export["path"],
                'size': f"{os.path.getsize(export['path']) / 1024:.0f} KB",
            })
        except Exception as e:
            results.append({'name': filename, 'ok': False, 'error': str(e)})

    return jsonify({'ok': True, 'results': results, 'dest': BATCH_EXPORTS_DIR})


@app.route('/batch_compress_upload', methods=['POST'])
def batch_compress_upload():
    import io as _io
    if Image is None:
        return jsonify({'ok': False, 'error': 'Pillow is not installed'})
    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'ok': False, 'error': 'No files uploaded'})

    fmt = request.form.get('format', 'jpeg').lower()
    quality = max(40, min(100, parse_int(request.form.get('quality'), 90)))
    fmt_map = {
        'jpeg': ('JPEG', '.jpg'),
        'webp': ('WEBP', '.webp'),
        'png': ('PNG', '.png'),
    }
    if fmt not in fmt_map:
        return jsonify({'ok': False, 'error': 'Unsupported format'})
    pil_fmt, out_ext = fmt_map[fmt]

    results = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = os.path.basename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_IMG_EXTS:
            results.append({'name': filename, 'ok': False, 'error': 'Unsupported format'})
            continue
        try:
            raw = file.read()
            original_kb = len(raw) / 1024
            img = normalize_image_for_crop(Image.open(_io.BytesIO(raw)))
            has_alpha = image_has_alpha(img)

            if fmt == 'jpeg':
                if has_alpha:
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    alpha_src = img.convert('RGBA')
                    bg.paste(alpha_src, mask=alpha_src.getchannel('A'))
                    img = bg
                else:
                    img = img.convert('RGB')
            elif fmt == 'webp':
                img = img.convert('RGBA' if has_alpha else 'RGB')
            else:
                img = img.convert('RGBA' if has_alpha else 'RGB')

            base_name = os.path.splitext(filename)[0]
            out = os.path.join(BATCH_EXPORTS_DIR, f"{base_name}_compressed{out_ext}")
            save_kwargs = {'optimize': True}
            if fmt == 'jpeg':
                save_kwargs.update({'quality': quality, 'subsampling': 0})
            elif fmt == 'webp':
                save_kwargs.update({'quality': quality, 'method': 6})
            else:
                save_kwargs['compress_level'] = max(0, min(9, round((100 - quality) / 10)))
            img.save(out, format=pil_fmt, **save_kwargs)
            out_kb = os.path.getsize(out) / 1024
            savings = max(0.0, (original_kb - out_kb) / original_kb * 100) if original_kb > 0 else 0
            results.append({
                'name': filename,
                'ok': True,
                'output': out,
                'original_size': f"{original_kb:.0f} KB",
                'output_size': f"{out_kb:.0f} KB",
                'savings': f"{savings:.0f}%",
            })
        except Exception as e:
            results.append({'name': filename, 'ok': False, 'error': str(e)})

    return jsonify({'ok': True, 'results': results, 'dest': BATCH_EXPORTS_DIR})


# ── Studio Models ─────────────────────────────────────────────────────────────

def _load_models():
    if not os.path.exists(MODELS_JSON):
        return []
    try:
        with open(MODELS_JSON, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def _save_models(models):
    with open(MODELS_JSON, 'w') as f:
        json.dump(models, f, indent=2)


@app.route('/studio_models', methods=['GET'])
def studio_models_list():
    return jsonify({'ok': True, 'models': _load_models()})


@app.route('/studio_save_model', methods=['POST'])
def studio_save_model():
    model_type = request.form.get('type', 'preset')
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Name is required'})

    model_id = uuid.uuid4().hex[:12]
    entry = {
        'id': model_id,
        'type': model_type,
        'name': name,
    }

    if model_type == 'reference':
        photo = request.files.get('photo')
        if not photo:
            return jsonify({'ok': False, 'error': 'No photo uploaded'})
        ext = os.path.splitext(photo.filename)[1].lower() or '.jpg'
        filename = f"model_{model_id}{ext}"
        photo.save(os.path.join(MODELS_DIR, filename))
        entry['filename'] = filename
    else:
        entry['skin_tone'] = request.form.get('skin_tone', '').strip()
        entry['body_type'] = request.form.get('body_type', '').strip()
        entry['hair'] = request.form.get('hair', '').strip()
        entry['age_range'] = request.form.get('age_range', '').strip()
        entry['style'] = request.form.get('style', '').strip()

    models = _load_models()
    models.insert(0, entry)
    _save_models(models)
    return jsonify({'ok': True, 'model': entry})


@app.route('/studio_delete_model/<model_id>', methods=['DELETE'])
def studio_delete_model(model_id):
    models = _load_models()
    to_remove = next((m for m in models if m['id'] == model_id), None)
    if to_remove and to_remove.get('filename'):
        photo_path = os.path.join(MODELS_DIR, to_remove['filename'])
        if os.path.exists(photo_path):
            os.remove(photo_path)
    models = [m for m in models if m['id'] != model_id]
    _save_models(models)
    return jsonify({'ok': True})


@app.route('/studio_model_photo/<model_id>')
def studio_model_photo(model_id):
    models = _load_models()
    model = next((m for m in models if m['id'] == model_id), None)
    if not model or not model.get('filename'):
        return ('Not found', 404)
    return send_from_directory(MODELS_DIR, model['filename'])


# ── Studio Generate ────────────────────────────────────────────────────────────

@app.route('/studio_generate', methods=['POST'])
def studio_generate():
    if google_genai is None:
        return jsonify({'ok': False, 'error': 'google-genai not installed. Run: pip install google-genai'})

    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'ok': False, 'error': 'GEMINI_API_KEY env var not set'})

    file = request.files.get('image')
    if not file:
        return jsonify({'ok': False, 'error': 'No image uploaded'})

    bg_color = request.form.get('bg_color', 'warm cream').strip()
    style_notes = request.form.get('style_notes', '').strip()
    model_id = request.form.get('model_id', '').strip()

    img_bytes = file.read()
    mime_type = file.content_type or 'image/jpeg'

    # Resolve selected model
    model_entry = None
    model_ref_bytes = None
    model_ref_mime = 'image/jpeg'
    if model_id:
        models = _load_models()
        model_entry = next((m for m in models if m['id'] == model_id), None)
        if model_entry and model_entry.get('type') == 'reference' and model_entry.get('filename'):
            ref_path = os.path.join(MODELS_DIR, model_entry['filename'])
            if os.path.exists(ref_path):
                with open(ref_path, 'rb') as fh:
                    model_ref_bytes = fh.read()
                ext = os.path.splitext(model_entry['filename'])[1].lower()
                model_ref_mime = 'image/png' if ext == '.png' else 'image/jpeg'

    # Build prompt
    if model_ref_bytes:
        # Reference photo mode — instruct Gemini to dress the person in the product
        prompt = (
            f"The first image is a reference photo of a model. "
            f"The second image shows a fashion garment. "
            f"Generate a professional fashion photograph of the exact same model from the first image "
            f"wearing the garment from the second image. "
            f"Match the model's face, skin tone, hair, and body exactly. "
            f"Photograph them in a clean studio with a {bg_color} background. "
            f"Professional studio lighting, sharp focus, editorial quality. "
            f"Keep the garment exactly as shown — same color, pattern, texture, and style."
        )
    elif model_entry and model_entry.get('type') == 'preset':
        # AI preset mode — inject model description into prompt
        desc_parts = []
        if model_entry.get('skin_tone'):
            desc_parts.append(f"{model_entry['skin_tone']} skin tone")
        if model_entry.get('body_type'):
            desc_parts.append(f"{model_entry['body_type']} build")
        if model_entry.get('hair'):
            desc_parts.append(f"{model_entry['hair']} hair")
        if model_entry.get('age_range'):
            desc_parts.append(f"{model_entry['age_range']}")
        model_desc = ', '.join(desc_parts) if desc_parts else 'a fashion model'

        style_prefix = ''
        model_style = model_entry.get('style', '')
        if 'boho' in model_style.lower():
            style_prefix = (
                "Bohemian editorial style — natural wavy or loosely braided hair, relaxed free-spirited posture, "
                "warm earthy atmosphere, soft organic feel. "
            )

        prompt = (
            f"{style_prefix}"
            f"Transform this product photo into a professional fashion photograph. "
            f"Place the garment on a model with {model_desc}, standing in a clean studio with a {bg_color} background. "
            f"Professional studio lighting, sharp focus, editorial quality. "
            f"Keep the garment exactly as shown — same color, pattern, texture, and style."
        )
    else:
        prompt = (
            f"Transform this product photo into a professional fashion photograph. "
            f"Place the garment on a model standing in a clean photo studio with a {bg_color} background. "
            f"Professional studio lighting, sharp focus, editorial quality. "
            f"Keep the garment exactly as shown — same color, pattern, texture, and style."
        )

    if style_notes:
        prompt += f" {style_notes}"

    try:
        client = google_genai.Client(api_key=api_key)
        contents = []
        if model_ref_bytes:
            contents.append(genai_types.Part.from_bytes(data=model_ref_bytes, mime_type=model_ref_mime))
        contents.append(genai_types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
        contents.append(genai_types.Part.from_text(text=prompt))

        response = client.models.generate_content(
            model='gemini-2.5-flash-image',
            contents=contents,
            config=genai_types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE']
            )
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

    out_bytes = None
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            raw = part.inline_data.data
            out_bytes = raw if isinstance(raw, (bytes, bytearray)) else __import__('base64').b64decode(raw)
            break

    if not out_bytes:
        text_parts = [p.text for p in response.candidates[0].content.parts if getattr(p, 'text', None)]
        msg = ' '.join(text_parts) if text_parts else 'Gemini returned no image'
        return jsonify({'ok': False, 'error': msg})

    out_name = f"studio_{uuid.uuid4().hex[:10]}.jpg"
    out_path = os.path.join(STUDIO_DIR, out_name)
    with open(out_path, 'wb') as fh:
        fh.write(out_bytes)

    return jsonify({'ok': True, 'path': out_path})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
