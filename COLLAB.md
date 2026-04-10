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
- studio backend / Gemini API path: Claude
- studio UI / UX polish and prompt assembly: Codex
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

---

### Session 005 — GPT Codex — 2026-04-04

**Work done:**
- reviewed the new `Crop & Export` tab and fixed the two biggest correctness issues
- made crop export preserve sensible output formats instead of forcing everything to JPEG:
  - PNG alpha is now preserved
  - uploaded crops now export into `REVO_CROPS_DIR` / `/Users/tobiaslundgren/Movies/CapCut/crops` instead of the stray `~/Movies/CapCut/Edited` folder
- normalized crop input handling across both crop routes:
  - EXIF orientation is applied before cropping so phone photos match the browser preview
  - bounds parsing now uses the shared numeric helpers instead of raw `int(...)`
- tightened the crop UI a bit:
  - aspect-ratio lock now re-applies from the numeric inputs
  - drag state is cleared on mouse leave so the crop box does not get stuck
  - crop output now shows the export format in the UI
- extended smoke coverage for both `POST /crop_image` and `POST /crop_upload`

**Verification:**
- `./scripts/check.sh` passes
- `node --check static/app.js` passes
- `python3 -m py_compile ffmpeg_editor.py` passes
- live `POST /crop_upload` succeeded with a transparent PNG test asset
- verified exported file at `/Users/tobiaslundgren/Movies/CapCut/crops/revo_crop_alpha_live_crop_20_20_120x80.png`
- confirmed exported crop remained `PNG RGBA` instead of flattening to JPEG

**Notes for next session:**
- crop export is more correct now, but the crop UI still does not support resize handles or touch gestures
- `ffmpeg_editor.py` continues to accumulate responsibilities; crop logic is another sign it should be split if work continues

---

### Session 006 — GPT Codex — 2026-04-06

**Work done:**
- reviewed Claude's new compressor work in the crop tab
- verified the compressor concept is solid and kept the UI/backend shape intact
- fixed the main breakage and rough edges:
  - confirmed the running app needed a restart before `/compress_upload` existed live
  - hardened the compressor route so transparent uploads converted to JPEG get composited onto white instead of black
  - normalized compressor format reporting back to the UI
  - added compressor smoke coverage in `tests/smoke_test.py`

**Verification:**
- `./scripts/check.sh` passes
- live `POST /compress_upload` returns `200`
- verified output at `/Users/tobiaslundgren/Movies/CapCut/crops/revo_compress_alpha_compressed.jpg`
- confirmed the compressed JPEG is `RGB` with a white background in transparent areas

**Notes for next session:**
- the repo is still in a dirty working-tree state because the crop/compress pass has not been committed yet
- crop/compress UX is usable now, but output naming still overwrites the same `_compressed` file for repeated runs of the same source

---

### Session 007 — GPT Codex — 2026-04-06

**Work done:**
- set up a Revoexpert-specific Claude change watcher at `scripts/claude_change_watcher.py`
- added a macOS LaunchAgent at `/Users/tobiaslundgren/Library/LaunchAgents/com.tobias.revoexpert.claude-watch.plist`
- ignored `.claude-watch/` in git so watcher state does not pollute the repo
- matched the Vivi pattern so the watcher writes:
  - `.claude-watch/last_change.json`
  - `.claude-watch/events.jsonl`
  - a Notification Center alert when repo changes are observed while the Claude CLI is running

**Verification:**
- LaunchAgent plist passes `plutil -lint`
- `launchctl print gui/501/com.tobias.revoexpert.claude-watch` shows the service in `state = running`
- watcher log confirms startup at `/Users/tobiaslundgren/Library/Logs/revoexpert-claude-watch.log`
- fixed the process matcher to recognize the actual local Claude CLI process name (`claude`)
- verified live signal output in `.claude-watch/last_change.json` and `.claude-watch/events.jsonl`

**Notes for next session:**
- watcher attribution is best-effort and intentionally depends on the local Claude CLI process being active
- the signal files live under `.claude-watch/`; check them before assuming there was or was not a recent Claude change

---

### Session 008 — GPT Codex — 2026-04-07

**Work done:**
- moved compressor outputs onto a dedicated folder via `REVO_COMPRESSED_DIR`
- changed the default compressor destination to `REVO_CROPS_DIR/compressed`
- exposed the `crops` and `compressed` directories in the app workspace snapshot / health payload
- updated docs and env examples so the new output path is explicit
- extended the compressor smoke test to assert the output lands in the compressed subfolder

**Verification:**
- `./scripts/check.sh` passes
- live `GET /health` returns `200`
- verified the compressor route now reports output paths under the compressed folder

**Notes for next session:**
- compressor outputs are now separated cleanly, but repeated compressions of the same source still reuse the same `_compressed` basename
- subtitle generation remains Claude's lane; keep compressor/crop changes adjacent only

---

### Session 009 — GPT Codex — 2026-04-07

**Work done:**
- fixed the new `Batch Photos` feature so manual crop mode uses the first image's real dimensions as the proportional reference instead of the crop box size
- made batch reference loading reliable when:
  - files are added before switching to manual mode
  - the first queued file changes
  - the queue is cleared and rebuilt
- surfaced the batch export directory through `/status` and `/health`
- wired the batch output note in the UI to the real configured destination instead of a hardcoded string
- documented `REVO_BATCH_DIR` and the new batch/compress endpoints
- added smoke coverage for:
  - batch manual proportional crop
  - batch compress

**Verification:**
- `./scripts/check.sh` passes
- `node --check static/app.js` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes
- live `GET /status` exposes `directories.batch`
- live `POST /batch_crop_upload` returns `200` and produced `(40, 32)` and `(80, 64)` outputs for the manual proportional test

**Notes for next session:**
- batch crop/compress now work end to end, but repeated exports still overwrite the same basename if the uploaded filenames match
- subtitle generation remains Claude's lane; avoid overlapping the reels caption flow unless coordinated

---

### Session 010 — GPT Codex — 2026-04-09

**Work done:**
- took the Codex side of the new Studio split while keeping Claude on backend/API logic
- rebuilt the Studio tab into a more guided workflow:
  - stronger upload state and source-status cues
  - a clearer `Shoot Direction` panel with framing / energy / use-case controls
  - a live prompt-preview card that compiles those UI choices into the existing `style_notes` contract
  - a `Result Deck` with reference-vs-generated comparison, current brief chips, and clearer result status
  - a separate run log so generation feedback is easier to follow
- added lightweight frontend state handling for:
  - brief reset
  - source/result status pills
  - better drag/drop affordances
  - result reset when the source image changes
- extended the smoke test to assert the new Studio UI markers render on `/`

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes

**Notes for next session:**
- Studio backend generation still lives in `ffmpeg_editor.py` and remains Claude's lane
- the new Studio controls only shape the existing `style_notes` payload; if the API contract changes, sync the frontend brief-builder with Claude's backend expectations

---

### Session 011 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing the Studio frontend lane while leaving Claude on backend/API duty
- made the Studio workflow durable across sessions:
  - persistent brief state via local storage
  - reusable recent-shot history with reopen + brief reuse
  - prompt copy support
  - clearer result download naming based on the brief metadata
- used Claude in print mode as an ideation sidecar, then implemented a few of the safe frontend ideas immediately:
  - added `Output Ratio` intent controls (`Original`, `1:1`, `4:5`, `9:16`) that feed the existing `style_notes` prompt path
  - added `Cmd/Ctrl + Enter` to trigger Studio generation when the Studio tab is active
  - added `Saved Looks` presets with local save/apply/delete for repeatable brand shoots
- updated docs and smoke assertions so the expanded Studio feature set is represented outside the UI

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes

**Notes for next session:**
- Studio now has a meaningful frontend memory layer; if Claude changes the prompt contract, keep the brief/preset/history schemas aligned with that backend expectation
- the next safe frontend-only expansions from Claude's idea list are likely:
  - multi-variant runs from one brief
  - a better visual compare slider
  - richer preset management than the current prompt-based naming flow

---

### Session 012 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing the Studio frontend while explicitly using Claude in print mode as a sidecar for implementation advice and pitfalls
- upgraded the Studio execution loop from single-shot only into a brief-iteration workflow:
  - added `Variant Run Size` controls for `1x`, `2x`, and `4x`
  - made Studio generation run sequentially for multiple variants from the same brief
  - built a `Current Run Variants` filmstrip so the latest outputs from one run can be reopened instantly
- improved the compare experience without changing the backend API:
  - the generated pane is now a reveal-slider compare view when both a source reference and generated result are present
  - the compare slider remains disabled gracefully when there is no source reference loaded
- applied one of Claude's main implementation cautions:
  - the brief metadata is snapshotted at generation start so mid-run UI edits do not silently change later variants in the same multi-run batch
- updated docs and smoke assertions to cover the new Studio labels and workflow shape

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes

**Notes for next session:**
- Studio multi-variant runs are still intentionally sequential to keep the single progress bar and backend contract simple
- compare currently uses the active source reference against the selected generated result; if backend-side source tracking is ever added, that would make history comparisons more explicit
- Claude's remaining safe frontend/product ideas still include:
  - richer compare-mode toggles
  - preset UX beyond `prompt()` naming
  - explicit cancel / stop controls for long multi-variant runs

---

### Session 013 — GPT Codex — 2026-04-09

**Work done:**
- continued the Studio frontend lane after the multi-variant / compare pass instead of stopping at the larger feature drop
- added a lightweight curation layer to `Recent Studio Shots`:
  - outputs can now be favorited locally
  - favorites float to the top of Studio history
  - favorite state persists in local storage alongside the rest of the Studio frontend memory layer
- updated the Studio workflow docs so favorites are part of the described workflow instead of a hidden extra

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes

**Notes for next session:**
- Studio history is now serving two jobs: recall and curation
- if more frontend iteration continues, a natural next step would be combining favorites with a richer compare flow or a cleaner preset-management UI

---

### Session 014 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing only on the Studio / image-generation frontend lane rather than branching into unrelated tooling
- expanded the Studio run controls and compare flow into something safer for longer image sessions:
  - added an explicit `Stop Run` path with `AbortController` support so multi-variant runs can be interrupted without losing already-finished outputs
  - added compare-mode toggles and fixed the reveal slider alignment by clipping the overlay instead of shrinking the image layer
  - fixed drag/drop flicker in the source zone and added confirmation before replacing an active Studio run with a new reference image
- made Studio curation and recall more usable during repeated prompt iterations:
  - added an active-result favorite action plus `All` / `Favorites` history filtering
  - persisted the main Studio UI mode state locally (`variantCount`, compare mode, history filter)
  - replaced fragile inline history actions with delegated `data-studio-action` / `data-studio-path` handling
  - added preset rename support
- added a new `Source Readiness` panel in the Product Photo card:
  - analyzes uploaded reference images for dimensions, orientation, megapixels, and file size
  - surfaces readiness badges plus practical warnings about low resolution, oversized files, or extreme crops before generation starts
  - upgraded the source status pill from simple load state to analyzed readiness state
- updated smoke coverage and README notes so the Studio source-diagnostics workflow is visible outside the UI

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 -m py_compile ffmpeg_editor.py tests/smoke_test.py` passes

**Notes for next session:**
- Studio now guides both the prompt and the source-image quality before generation starts
- the next strong frontend-only Studio steps are probably either:
  - better source controls (`remove source`, source swap history, or crop helpers before generation)
  - result-side organization (collections, notes, or lightweight shot approvals)

---

### Session 015 — GPT Codex — 2026-04-09

**Work done:**
- kept the focus strictly on the Studio / image-generation workflow after the source-readiness pass instead of stopping at the first green check
- added an explicit source reset path:
  - `Remove Photo` now clears the active reference, compare state, and current run without deleting saved Studio history
  - the source action stays hidden until a reference is loaded, so the Product Photo card stays clean when Studio is empty
- turned source diagnostics into something actionable instead of informational only:
  - Studio now computes a suggested output ratio from the uploaded source orientation / crop shape
  - added a one-click `Use Suggested Ratio` action in the `Source Readiness` panel
  - the suggestion state updates live when the selected output ratio already matches the recommendation
- extended smoke coverage and README notes so the new source-reset / suggested-ratio workflow is represented outside the browser

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- the Studio source panel now does three jobs: load, evaluate, and steer the setup
- the next high-value Studio-only step is probably either:
  - lightweight pre-generation source adjustments (crop/rotate helpers)
  - post-generation decision tooling (approve/reject notes or shortlisting)

---

### Session 016 — GPT Codex — 2026-04-09

**Work done:**
- kept moving further down the Studio source-control path instead of stopping after diagnostics and ratio suggestions
- added real pre-generation orientation controls to the Product Photo card:
  - `Rotate Left` and `Rotate Right` now rebuild the uploaded source through canvas and replace the actual `studioFile` used for generation
  - `Reset Orientation` restores the original upload without removing the reference entirely
  - source actions disable while a Studio run is active so the generation input cannot change mid-run
- kept the transform behavior safe:
  - each rotation is derived from the original uploaded image rather than repeatedly re-encoding the already-rotated preview
  - source metadata now reflects the current rotation so the operator can see what will be sent into the next run
- extended smoke coverage and README notes so the new orientation workflow is captured outside the live UI

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- Studio source prep now covers load, evaluate, steer, and orientation correction
- the next strong Studio-only step is likely:
  - source crop helpers before generation
  - shortlist / approval tooling after generation

---

### Session 017 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing the Studio iteration loop after source rotation instead of treating the source-prep work as finished
- made Studio history more traceable:
  - each generated Studio item now stores the source filename and source rotation used for that run
  - the recent-shot cards surface that source provenance so repeated garment tests are easier to distinguish
- fixed an important compare-safety issue:
  - the reveal slider now only activates when the currently loaded source actually matches the source that generated the selected Studio result
  - older history items that predate source tracking no longer compare against whatever reference happens to be loaded, avoiding misleading visual diffs
- tightened the smoke harness after a flaky cleanup race showed up during repeated verification runs:
  - temp caption overlay cleanup in `tests/smoke_test.py` now ignores already-removed files

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- Studio compare is now safer, not just richer
- the most valuable next Studio step still looks like:
  - source crop helpers before generation
  - post-generation shortlist / approval controls

---

### Session 018 — GPT Codex — 2026-04-09

**Work done:**
- kept moving down the Studio source-prep path and added lightweight crop tooling before generation instead of leaving the new rotation controls as a dead end
- added quick centered crop helpers in the Product Photo card:
  - `Crop 1:1`, `Crop 4:5`, and `Crop 9:16` now rebuild the Studio source from the original upload plus the current rotation
  - `Reset Crop` restores the uncropped frame while preserving any active rotation
- kept the transform pipeline clean and reversible:
  - source transforms are now derived from the original upload rather than compounding crop-on-crop or rotate-on-rotate degradation
  - source metadata, history provenance, and compare safety all include crop state alongside rotation
- updated smoke coverage and README notes so the new pre-generation crop workflow is captured outside the live UI

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- Studio source prep now covers diagnostics, suggestion, rotation, and fast crop correction
- the next high-value Studio-only move is probably:
  - a lightweight freeform crop modal before generation
  - result shortlisting / approval states after generation

---

### Session 019 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing the Studio image-generation lane into the output-review phase instead of stopping at source-prep controls
- added lightweight decision tooling for generated results:
  - current result actions now include `Shortlist` and `Approve`
  - recent Studio history now supports `All`, `Favorites`, `Shortlisted`, and `Approved` filters
  - history cards surface decision tags so strong outputs are easier to scan at a glance
- made the review state durable and meaningful:
  - review status persists in the same local Studio history layer as favorites and source provenance
  - approved and shortlisted shots now sort ahead of ordinary history items
  - current-result actions read from the persisted history copy so state stays accurate even when a shot is still in the current run strip
- updated smoke coverage and README notes so the new review flow is represented outside the live UI

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- Studio now handles both source prep and output triage inside one loop
- the next strong Studio-only step is probably:
  - a freeform pre-generation crop modal
  - short notes / comments per generated shot

---

### Session 020 — GPT Codex — 2026-04-09

**Work done:**
- added env-driven Google Analytics 4 support to the app instead of leaving analytics as an unimplemented idea
- wired the Google tag into the Flask template path:
  - `REVO_GA4_MEASUREMENT_ID` is now passed from the backend into the template
  - the GA tag only renders when that measurement ID is configured
  - page views are handled as virtual SPA views rather than relying on the default single-page load only
- added frontend analytics events for the major user workflows:
  - virtual page views for tab switches
  - render / reels / batch job start-success-failure events
  - Studio generate, stop/failure, download, shortlist, and approve events
- updated `.env.example`, README, and smoke coverage so the analytics setup is documented and verified

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- GA4 is now wired, but it still needs the real measurement ID in the environment before anything is sent
- if analytics becomes a deeper product workflow later, the next useful step would be aligning event names and custom dimensions with the reports you actually want in GA4

---

### Session 021 — GPT Codex — 2026-04-09

**Work done:**
- kept pushing the Studio image workflow after analytics instead of drifting into unrelated tooling
- added shot-specific note support inside the Result Deck:
  - each generated Studio shot can now carry its own saved note
  - notes are stored in the same local history layer as favorites, review status, and source provenance
  - the current note editor follows the selected variant / history item instead of sticking to stale state
- surfaced note context back into the browsing workflow:
  - recent Studio history now shows a truncated note preview when a shot has saved comments
  - note save / clear flows are tracked through the existing Studio state updates and analytics event path
- updated smoke coverage and README notes so the note workflow is represented outside the browser

**Verification:**
- `node --check static/app.js` passes
- `./scripts/check.sh` passes
- `python3 tests/smoke_test.py` passes

**Notes for next session:**
- Studio now supports source prep, generation, review states, and shot notes in one loop
- the next strong Studio-only step is probably:
  - a freeform crop modal
  - bulk actions for shortlisted / approved shots

---

### Session 022 — Claude — 2026-04-10

**Work done:**
- added `python-dotenv` to `requirements.txt` and wired `load_dotenv` at the top of `ffmpeg_editor.py` so a local `.env` file is picked up automatically on startup
- created `.env` from `.env.example` with all existing paths pre-filled and a blank `GEMINI_API_KEY=` slot ready for the real key
- added `REVO_STUDIO_DIR` and `GEMINI_API_KEY` to `.env.example` so they are documented alongside the rest of the config
- no changes to any route logic, frontend, or subtitle path

**Verification:**
- `python3 -m py_compile ffmpeg_editor.py` passes
- `./scripts/check.sh` passes

**Notes for next session:**
- Studio tab is fully blocked until `GEMINI_API_KEY` is filled in `.env` — that is the only remaining blocker for end-to-end testing
- `.env` is gitignored; the real key should never be committed
