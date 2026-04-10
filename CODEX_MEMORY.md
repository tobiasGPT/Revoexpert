# Codex Memory

This file is a standing working agreement for Codex in this project.

## Default Autonomy Rule

For safe, focused work inside this repo, Codex should continue without waiting for extra permission or repeated "go ahead" messages.

Codex should keep building, testing, and improving the active lane by default.

## When To Pause

Codex should only stop to ask when a change:

- is destructive or hard to undo
- risks overwriting or reverting user or Claude work
- changes scope in a non-obvious way
- involves commits, pushes, deploys, secrets, billing, or external side effects
- has meaningful product tradeoffs that need a real decision

## Communication Rule

Codex should not pause for routine checkpoint approval.

Short progress updates are fine, but the default behavior is to continue working until there is a real blocker, risk, or decision.

## Current Project Context

The current priority is the Studio / image-generation workflow for the Vivi&Co brand app.
