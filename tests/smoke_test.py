import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ffmpeg_editor


def main():
    client = ffmpeg_editor.app.test_client()

    sample_srt = ROOT / "tests" / "_sample.srt"
    trimmed_srt = ROOT / "tests" / "_trimmed_sample.srt"
    sample_srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\nSecond line\n",
        encoding="utf-8",
    )
    try:
        assert ffmpeg_editor.trim_srt_segment(str(sample_srt), 1.0, 4.0, str(trimmed_srt))
        trimmed_entries = ffmpeg_editor.read_srt_entries(str(trimmed_srt))
        assert len(trimmed_entries) == 2
        assert trimmed_entries[0]["text"] == "Hello world"

        image_path = ffmpeg_editor.build_caption_overlay_image("Hello world", 608, 1080, 18, 2, True, "smoke", 1, 1)
        assert image_path.endswith(".png")
        assert Path(image_path).exists()
    finally:
        for path in (sample_srt, trimmed_srt):
            if path.exists():
                path.unlink()
        for path in Path("/tmp").glob("reel_caption_smoke_*.png"):
            path.unlink()

    status = client.get("/status")
    assert status.status_code == 200, status.status_code
    status_payload = status.get_json()
    assert sorted(status_payload["counts"].keys()) == ["edited", "reels", "source"]

    health = client.get("/health")
    assert health.status_code in {200, 503}, health.status_code
    health_payload = health.get_json()
    assert sorted(health_payload["tools"].keys()) == ["ffmpeg", "ffprobe", "overlay", "yt_dlp"]
    assert "port" in health_payload

    outputs = client.get("/outputs")
    assert outputs.status_code == 200, outputs.status_code
    outputs_payload = outputs.get_json()
    assert sorted(outputs_payload.keys()) == ["edited", "reels"]

    files = client.get("/files")
    assert files.status_code == 200, files.status_code
    assert isinstance(files.get_json(), list)

    index = client.get("/")
    assert index.status_code == 200, index.status_code
    assert b"NEXUS // Video Editor" in index.data

    css = client.get("/static/app.css")
    assert css.status_code == 200, css.status_code

    js = client.get("/static/app.js")
    assert js.status_code == 200, js.status_code

    invalid_info = client.post("/info", json={"path": "/etc/passwd"})
    assert invalid_info.status_code == 400, invalid_info.status_code

    invalid_render = client.post("/render", json={"path": "/etc/passwd"})
    assert invalid_render.status_code == 400, invalid_render.status_code

    missing_yt_info = client.post("/yt_info", json={})
    assert missing_yt_info.status_code == 400, missing_yt_info.status_code

    missing_yt_reels = client.post("/yt_reels", json={})
    assert missing_yt_reels.status_code == 400, missing_yt_reels.status_code

    invalid_video = client.get("/video?path=/etc/passwd")
    assert invalid_video.status_code == 404, invalid_video.status_code


if __name__ == "__main__":
    main()
