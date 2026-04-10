import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ffmpeg_editor
from PIL import Image


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
            try:
                if path.exists():
                    path.unlink()
            except FileNotFoundError:
                pass
        for path in Path("/tmp").glob("reel_caption_smoke_*.png"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    status = client.get("/status")
    assert status.status_code == 200, status.status_code
    status_payload = status.get_json()
    assert sorted(status_payload["counts"].keys()) == ["edited", "reels", "source"]
    assert "batch" in status_payload["directories"]
    assert "compressed" in status_payload["directories"]
    assert "crops" in status_payload["directories"]

    health = client.get("/health")
    assert health.status_code in {200, 503}, health.status_code
    health_payload = health.get_json()
    assert sorted(health_payload["tools"].keys()) == ["ffmpeg", "ffprobe", "overlay", "yt_dlp"]
    assert "port" in health_payload
    assert "batch" in health_payload["directories"]

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
    assert b"Shoot Direction" in index.data
    assert b"Result Deck" in index.data
    assert b"Recent Studio Shots" in index.data
    assert b"Copy Brief" in index.data
    assert b"Output Ratio" in index.data
    assert b"Saved Looks" in index.data
    assert b"Variant Run Size" in index.data
    assert b"Current Run Variants" in index.data
    assert b"Compare View" in index.data
    assert b"Stop Run" in index.data
    assert b"Source Readiness" in index.data
    assert b"Remove Photo" in index.data
    assert b"Use Suggested Ratio" in index.data
    assert b"Rotate Left" in index.data
    assert b"Rotate Right" in index.data
    assert b"Reset Orientation" in index.data
    assert b"Crop 1:1" in index.data
    assert b"Crop 4:5" in index.data
    assert b"Crop 9:16" in index.data
    assert b"Reset Crop" in index.data
    assert b"Shortlist" in index.data
    assert b"Approve" in index.data
    assert b"Shortlisted" in index.data
    assert b"Approved" in index.data
    assert b"Shot Notes" in index.data
    assert b"Save Note" in index.data
    assert b"Clear Note" in index.data

    prev_ga_measurement_id = os.environ.get("REVO_GA4_MEASUREMENT_ID")
    os.environ["REVO_GA4_MEASUREMENT_ID"] = "G-TEST123ABC"
    try:
        index_with_ga = client.get("/")
        assert index_with_ga.status_code == 200, index_with_ga.status_code
        assert b"googletagmanager.com/gtag/js?id=G-TEST123ABC" in index_with_ga.data
        assert b'window.REVO_GA4_MEASUREMENT_ID = "G-TEST123ABC"' in index_with_ga.data
    finally:
        if prev_ga_measurement_id is None:
            os.environ.pop("REVO_GA4_MEASUREMENT_ID", None)
        else:
            os.environ["REVO_GA4_MEASUREMENT_ID"] = prev_ga_measurement_id

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

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = Path(tmpdir) / "alpha-source.png"
        Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(png_path)

        crop = client.post("/crop_image", json={"path": str(png_path), "x": 0, "y": 0, "w": 20, "h": 10, "quality": 97})
        assert crop.status_code == 200, crop.status_code
        crop_payload = crop.get_json()
        assert crop_payload["ok"] is True
        assert crop_payload["output"].endswith(".png")
        assert crop_payload["format"] == "PNG"

        cropped = Image.open(crop_payload["output"])
        assert cropped.mode == "RGBA"
        assert cropped.size == (20, 10)

        old_crops_dir = ffmpeg_editor.CROPS_DIR
        ffmpeg_editor.CROPS_DIR = tmpdir
        try:
            upload_buffer = BytesIO()
            Image.new("RGBA", (32, 24), (0, 255, 0, 128)).save(upload_buffer, format="PNG")
            upload_buffer.seek(0)
            upload = client.post(
                "/crop_upload",
                data={
                    "file": (upload_buffer, "upload-alpha.png"),
                    "x": "0",
                    "y": "0",
                    "w": "12",
                    "h": "8",
                    "quality": "95",
                },
                content_type="multipart/form-data",
            )
            assert upload.status_code == 200, upload.status_code
            upload_payload = upload.get_json()
            assert upload_payload["ok"] is True
            assert upload_payload["output"].endswith(".png")
            assert upload_payload["format"] == "PNG"
            uploaded = Image.open(upload_payload["output"])
            assert uploaded.mode == "RGBA"
            assert uploaded.size == (12, 8)
        finally:
            ffmpeg_editor.CROPS_DIR = old_crops_dir

        old_crops_dir = ffmpeg_editor.CROPS_DIR
        old_compressed_dir = ffmpeg_editor.COMPRESSED_DIR
        ffmpeg_editor.CROPS_DIR = tmpdir
        ffmpeg_editor.COMPRESSED_DIR = os.path.join(tmpdir, "compressed")
        os.makedirs(ffmpeg_editor.COMPRESSED_DIR, exist_ok=True)
        try:
            upload_buffer = BytesIO()
            Image.new("RGBA", (24, 18), (0, 255, 0, 128)).save(upload_buffer, format="PNG")
            upload_buffer.seek(0)
            compress = client.post(
                "/compress_upload",
                data={
                    "file": (upload_buffer, "compress-alpha.png"),
                    "format": "jpeg",
                    "quality": "85",
                },
                content_type="multipart/form-data",
            )
            assert compress.status_code == 200, compress.status_code
            compress_payload = compress.get_json()
            assert compress_payload["ok"] is True
            assert compress_payload["output"].endswith(".jpg")
            assert "/compressed/" in compress_payload["output"]
            assert compress_payload["format"] == "JPEG"
            compressed = Image.open(compress_payload["output"])
            assert compressed.mode == "RGB"
            assert compressed.size == (24, 18)
        finally:
            ffmpeg_editor.CROPS_DIR = old_crops_dir
            ffmpeg_editor.COMPRESSED_DIR = old_compressed_dir

        old_batch_dir = ffmpeg_editor.BATCH_EXPORTS_DIR
        ffmpeg_editor.BATCH_EXPORTS_DIR = os.path.join(tmpdir, "batch")
        os.makedirs(ffmpeg_editor.BATCH_EXPORTS_DIR, exist_ok=True)
        try:
            first = BytesIO()
            second = BytesIO()
            Image.new("RGBA", (100, 80), (255, 0, 0, 180)).save(first, format="PNG")
            Image.new("RGBA", (200, 160), (0, 0, 255, 180)).save(second, format="PNG")
            first.seek(0)
            second.seek(0)
            batch_crop = client.post(
                "/batch_crop_upload",
                data={
                    "files[]": [(first, "batch-one.png"), (second, "batch-two.png")],
                    "mode": "manual",
                    "x": "10",
                    "y": "8",
                    "w": "40",
                    "h": "32",
                    "quality": "94",
                    "proportional": "true",
                    "ref_w": "100",
                    "ref_h": "80",
                },
                content_type="multipart/form-data",
            )
            assert batch_crop.status_code == 200, batch_crop.status_code
            batch_crop_payload = batch_crop.get_json()
            assert batch_crop_payload["ok"] is True
            assert batch_crop_payload["dest"] == ffmpeg_editor.BATCH_EXPORTS_DIR
            first_crop = Image.open(batch_crop_payload["results"][0]["output"])
            second_crop = Image.open(batch_crop_payload["results"][1]["output"])
            assert first_crop.size == (40, 32)
            assert second_crop.size == (80, 64)

            first = BytesIO()
            second = BytesIO()
            Image.new("RGBA", (40, 30), (255, 0, 0, 180)).save(first, format="PNG")
            Image.new("RGBA", (32, 24), (0, 255, 0, 180)).save(second, format="PNG")
            first.seek(0)
            second.seek(0)
            batch_compress = client.post(
                "/batch_compress_upload",
                data={
                    "files[]": [(first, "compress-one.png"), (second, "compress-two.png")],
                    "format": "jpeg",
                    "quality": "82",
                },
                content_type="multipart/form-data",
            )
            assert batch_compress.status_code == 200, batch_compress.status_code
            batch_compress_payload = batch_compress.get_json()
            assert batch_compress_payload["ok"] is True
            assert batch_compress_payload["dest"] == ffmpeg_editor.BATCH_EXPORTS_DIR
            assert batch_compress_payload["results"][0]["output"].endswith(".jpg")
            batch_output = Image.open(batch_compress_payload["results"][0]["output"])
            assert batch_output.mode == "RGB"
        finally:
            ffmpeg_editor.BATCH_EXPORTS_DIR = old_batch_dir


if __name__ == "__main__":
    main()
