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
