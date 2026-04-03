# Revoexpert

Local Flask app for two video workflows:

- adding a Vivi&Co logo + optional CTA to local CapCut exports
- downloading a YouTube source and cutting it into portrait reels

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
- logo overlay: `/Users/tobiaslundgren/Movies/CapCut/viviandco_overlay.png`

Override them with env vars instead of editing source:

- `REVO_CAPCUT_DIR`
- `REVO_EDITED_DIR`
- `REVO_REELS_DIR`
- `REVO_OVERLAY_PATH`
- `REVO_FFMPEG_BIN`
- `REVO_FFPROBE_BIN`
- `REVO_YTDLP_BIN`
- `REVO_PORT`

Copy [`.env.example`](/Users/tobiaslundgren/Revoexpert/.env.example) if you want a starting point.

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

## Structure

- [ffmpeg_editor.py](/Users/tobiaslundgren/Revoexpert/ffmpeg_editor.py): Flask routes and ffmpeg/yt-dlp orchestration
- [templates/index.html](/Users/tobiaslundgren/Revoexpert/templates/index.html): app markup
- [static/app.css](/Users/tobiaslundgren/Revoexpert/static/app.css): visual styling
- [static/app.js](/Users/tobiaslundgren/Revoexpert/static/app.js): client-side UI logic
- [tests/smoke_test.py](/Users/tobiaslundgren/Revoexpert/tests/smoke_test.py): route-level smoke coverage

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
