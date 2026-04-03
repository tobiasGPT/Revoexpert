# Revoexpert Collaboration Log

## Session Rule

Read this file before making meaningful changes.

When a session ends:

- append a new numbered session entry
- describe what changed
- list what was verified
- call out ownership or overlap risks for the next person

Use the next highest session number. Do not reuse an existing number.

## Ownership Map

- reels subtitle generator: Claude
- repo hygiene, backend safety, output workflow, and general UX polish: Codex
- final product decisions and acceptance: Tobias

## Current Blockers

- app is still mostly one large inline Flask file
- subtitle generation is in progress and should be treated as an overlap-risk area
- there is no test suite yet beyond smoke checks

## Handoff Rules

- avoid editing the active subtitle generator path unless you have confirmed Claude is done
- prefer adjacent improvements over overlapping changes
- log every meaningful pass below

---

### Session 001 — GPT Codex — 2026-04-03

**Work done:**
- initialized `Revoexpert` as a git repo
- connected it to a new private GitHub repo
- added repo hygiene and collaboration rails:
  - expanded `.gitignore`
  - added `.editorconfig`
  - added `README.md`
  - added this `COLLAB.md`
  - added helper scripts and `requirements.txt`

**Verification:**
- GitHub remote created and pushed
- local branch workflow is active
- helper scripts created in repo

**Notes for next session:**
- Claude is actively working on subtitle generation in the reels flow
- avoid overlapping changes in the reels generation path until that lands

---

### Session 002 — Claude — 2026-04-03

**Work done:**
- added `.github/workflows/ci.yml`: GitHub Actions workflow that triggers on push/PR, sets up Python 3.11, installs `requirements.txt`, runs `bash -n` syntax checks on all `scripts/*.sh`, runs ShellCheck via `ludeeus/action-shellcheck`, and runs `./scripts/check.sh`
- did not touch `ffmpeg_editor.py` or any subtitle-generation path

**Verification:**
- `bash -n` passes on all three scripts (`check.sh`, `dev.sh`, `new-branch.sh`)
- `./scripts/check.sh` runs cleanly (zero-exit) locally
- workflow YAML structure confirmed correct

**Notes for next session:**
- CI lane is now owned by this workflow file; avoid parallel CI additions without coordinating
- ShellCheck runs on `scripts/` only — if new scripts land outside that dir, update the workflow
- subtitle generation path (`ffmpeg_editor.py`) remains untouched and still Claude's active lane

---

### Session 003 — GPT Codex — 2026-04-03

**Work done:**
- worked in parallel with Claude while staying out of the CI lane
- made Revoexpert portable across machines by moving the hardcoded runtime paths and binaries onto env-backed config
- added `.env.example` with the expected local variables
- added `GET /health` for fast diagnostics of:
  - configured port
  - tool availability
  - tool version strings
  - workspace directories
- extended `/status` to include tool versions and config metadata

**Verification:**
- `./scripts/check.sh` passes
- Flask test client smoke checks pass for `/status` and `/health`
- `/health` returns `200` with `tools`, `tool_versions`, `directories`, and `port`

**Notes for next session:**
- subtitle generation code is now present inside `ffmpeg_editor.py`, so keep non-subtitle edits surgical until Claude’s reel pass is settled
- if you move the CapCut workspace or binaries, update the env vars instead of editing source

---

### Session 004 — GPT Codex — 2026-04-03

**Work done:**
- finished the UI/backend cleanup pass that was still in progress:
  - split the inline app into `templates/index.html`, `static/app.css`, and `static/app.js`
  - removed the stale root `index.html`
  - updated README/docs to match the refactored structure and env-based config
- tightened the repo health gate:
  - fixed the smoke test import path
  - added route checks for `/`, `/static/app.css`, `/static/app.js`, `/yt_info` bad input, and `/yt_reels` bad input
  - wired `tests/smoke_test.py` into `./scripts/check.sh`
- fixed a real UI regression in the split frontend:
  - logo position controls no longer clear the ghost-logo or reel-logo active states
- completed an end-to-end subtitle pass for reels:
  - verified the Homebrew `ffmpeg 8.1` build on this Mac has neither `subtitles` nor `drawtext`
  - replaced caption burn-in with Pillow-generated PNG caption overlays so reels do not depend on optional ffmpeg text filters
  - fixed caption accounting so `segments_burned` only increments on successful output
  - raised the default caption size in the UI from `18` to `28` for better mobile readability
- asked Claude for an independent read-only review; the useful callouts were:
  - commit the refactor cleanly so CI/tests see the same code as the working tree
  - add at least some route coverage around the YouTube endpoints

**Verification:**
- `./scripts/check.sh` passes
- `node --check static/app.js` passes
- live `GET /health` returns `200`
- live `GET /` serves the split template/static frontend
- live `POST /yt_reels` with captions enabled returns `ok: true`
- generated reel verified at `/Users/tobiaslundgren/Movies/CapCut/reels/reel_bb1ff790_01.mp4`
- extracted frame review confirmed visible burned-in subtitles

**Notes for next session:**
- the app is materially healthier, but `ffmpeg_editor.py` is still the main backend hotspot and remains worth splitting if work continues
- long renders/downloads still run synchronously inside the Flask request cycle, so the dev server is blocked while a reel job is active
- Claude’s CI lane remains in `.github/workflows/ci.yml`; avoid overlapping CI edits without coordinating
