# Revoexpert

Local Flask app for two video workflows:

- adding a Vivi&Co logo + optional CTA to local CapCut exports
- downloading a YouTube source and cutting it into portrait reels
- cropping/exporting still images with ratio presets
- generating studio-style fashion shots from a product reference image

## Stack

- Python 3
- Flask
- Pillow
- `ffmpeg`
- `ffprobe`
- `yt-dlp`

## Local Media Assumptions

The app defaults to these paths on this Mac:

- source clips: `/Users/tobiaslundgren/Movies/CapCut`
- edited outputs: `/Users/tobiaslundgren/Movies/CapCut/vivi_edited`
- reels outputs: `/Users/tobiaslundgren/Movies/CapCut/reels`
- crop outputs: `/Users/tobiaslundgren/Movies/CapCut/crops`
- compressed image outputs: `/Users/tobiaslundgren/Movies/CapCut/crops/compressed`
- batch photo outputs: `~/Desktop/Nexus Exports`
- studio image outputs: `~/Desktop/Nexus Exports/studio`
- logo overlay: `/Users/tobiaslundgren/Movies/CapCut/viviandco_overlay.png`

Override them with env vars instead of editing source:

- `REVO_CAPCUT_DIR`
- `REVO_EDITED_DIR`
- `REVO_REELS_DIR`
- `REVO_CROPS_DIR`
- `REVO_COMPRESSED_DIR`
- `REVO_BATCH_DIR`
- `REVO_STUDIO_DIR`
- `REVO_OVERLAY_PATH`
- `REVO_FFMPEG_BIN`
- `REVO_FFPROBE_BIN`
- `REVO_YTDLP_BIN`
- `REVO_PORT`
- `REVO_GA4_MEASUREMENT_ID`

Copy [`.env.example`](/Users/tobiaslundgren/Revoexpert/.env.example) if you want a starting point.

## Analytics

Set `REVO_GA4_MEASUREMENT_ID` to a GA4 Measurement ID (`G-...`) to enable Google Analytics.

When enabled, the app sends virtual page views for tab switches plus events for major editor, reels, batch, and Studio actions.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/dev.sh
```

Then open [http://127.0.0.1:7777/](http://127.0.0.1:7777/).

## Quick Commands

```bash
./scripts/dev.sh
./scripts/check.sh
./scripts/new-branch.sh subtitles-pass
```

## Current App Endpoints

- `GET /`
- `GET /health`
- `GET /status`
- `GET /outputs`
- `GET /files`
- `POST /info`
- `GET /video`
- `POST /render`
- `POST /yt_info`
- `POST /yt_reels`
- `GET /img_preview`
- `POST /crop_image`
- `POST /crop_upload`
- `POST /compress_upload`
- `POST /batch_crop_upload`
- `POST /batch_compress_upload`
- `POST /studio_generate`

## Structure

- [ffmpeg_editor.py](/Users/tobiaslundgren/Revoexpert/ffmpeg_editor.py): Flask routes and ffmpeg/yt-dlp orchestration
- [templates/index.html](/Users/tobiaslundgren/Revoexpert/templates/index.html): app markup
- [static/app.css](/Users/tobiaslundgren/Revoexpert/static/app.css): visual styling
- [static/app.js](/Users/tobiaslundgren/Revoexpert/static/app.js): client-side UI logic
- [tests/smoke_test.py](/Users/tobiaslundgren/Revoexpert/tests/smoke_test.py): route-level smoke coverage

## Studio Workflow

The `Studio` tab is designed as a fast creative brief builder for product photography:

- drop a garment or product image as the reference
- review source-readiness diagnostics before generating
- rotate the source photo before generation if the original upload orientation is wrong
- apply quick centered source crops before generation when you need a cleaner frame
- apply the suggested output ratio when the uploaded source calls for a cleaner crop
- choose background, framing, energy, use-case direction, and intended output ratio
- add optional styling notes
- save reusable looks and bring them back from local storage
- generate one or multiple variants from the same brief
- compare the generated result against the original with a reveal slider when the matching source is loaded
- shortlist or approve strong generated shots directly inside Studio history
- save shot-specific notes for internal review context
- reuse recent briefs and outputs from the in-app history
- favorite strong outputs so they stay floated to the top of the Studio history
- stop long Studio runs without losing the variants that already finished

## Collaboration Notes

Read [COLLAB.md](/Users/tobiaslundgren/Revoexpert/COLLAB.md) before making a meaningful change.

Right now:

- subtitle generation on the reels path is Claude's active lane
- adjacent UX, safety, docs, and output workflow can be handled in parallel

## Suggested Workflow

1. Create a branch before significant work.
2. Keep reel subtitle changes isolated from unrelated UI work.
3. Run `./scripts/check.sh` before committing.
4. Push branch work to GitHub early if Claude or Codex is also active.
