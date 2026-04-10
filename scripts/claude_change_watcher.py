#!/usr/bin/env python3
"""Watch the Revoexpert repo and emit a signal when Claude likely changed files.

This watcher is intentionally simple and dependency-free so it can run as a
launchd agent on macOS using the system Python. It does three things whenever
it detects repo changes while the Claude Code CLI appears to be running:

1. Writes the latest event to `.claude-watch/last_change.json`
2. Appends the event to `.claude-watch/events.jsonl`
3. Fires a macOS Notification Center alert

The detection is best-effort rather than cryptographic attribution. It assumes
changes observed while the local Claude CLI process is active are Claude-driven.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".claude-watch",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".pyc",
    ".pyo",
}
EXCLUDED_FILES = {
    ".DS_Store",
}
CLAUDE_PROCESS_MATCH = "/Users/tobiaslundgren/.local/bin/claude"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_DEBOUNCE_SECONDS = 4.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_dir_for(repo_root: Path) -> Path:
    return repo_root / ".claude-watch"


def collect_snapshot(repo_root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for root, dirnames, filenames in os.walk(repo_root):
        root_path = Path(root)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in EXCLUDED_DIRS and not name.startswith(".git")
        ]
        for filename in filenames:
            if filename in EXCLUDED_FILES:
                continue
            path = root_path / filename
            if path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rel = path.relative_to(repo_root).as_posix()
            snapshot[rel] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def diff_snapshots(
    previous: dict[str, tuple[int, int]],
    current: dict[str, tuple[int, int]],
) -> list[str]:
    changed: list[str] = []
    previous_keys = set(previous)
    current_keys = set(current)
    changed.extend(sorted(current_keys - previous_keys))
    changed.extend(sorted(previous_keys - current_keys))
    changed.extend(
        sorted(path for path in (previous_keys & current_keys) if previous[path] != current[path])
    )
    return changed


def claude_cli_is_running() -> bool:
    exact_name = subprocess.run(
        ["pgrep", "-x", "claude"],
        capture_output=True,
        text=True,
        check=False,
    )
    if exact_name.returncode == 0 and bool(exact_name.stdout.strip()):
        return True

    result = subprocess.run(
        ["pgrep", "-f", CLAUDE_PROCESS_MATCH],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def write_event(repo_root: Path, changed_files: list[str]) -> dict:
    payload = {
        "ts": now_iso(),
        "repo": str(repo_root),
        "repo_name": repo_root.name,
        "changed_files": changed_files,
        "changed_count": len(changed_files),
        "source": "claude-code-best-effort",
    }
    signal_dir = state_dir_for(repo_root)
    signal_dir.mkdir(parents=True, exist_ok=True)

    last_change_path = signal_dir / "last_change.json"
    events_path = signal_dir / "events.jsonl"

    last_change_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


def applescript_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def send_notification(payload: dict) -> None:
    files = payload["changed_files"]
    if not files:
        return
    preview = ", ".join(files[:3])
    if len(files) > 3:
        preview += f", +{len(files) - 3} more"
    title = "Claude changed Revoexpert"
    subtitle = payload["repo_name"]
    message = preview[:220]
    script = (
        "display notification "
        f"{applescript_quote(message)} "
        f"with title {applescript_quote(title)} "
        f"subtitle {applescript_quote(subtitle)}"
    )
    subprocess.run(["osascript", "-e", script], check=False)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: claude_change_watcher.py <repo_root> [poll_seconds] [debounce_seconds]",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(sys.argv[1]).expanduser().resolve()
    poll_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_POLL_SECONDS
    debounce_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_DEBOUNCE_SECONDS

    if not repo_root.exists():
        print(f"repo root does not exist: {repo_root}", file=sys.stderr)
        return 2

    print(f"[claude-watch] watching {repo_root}", flush=True)
    previous = collect_snapshot(repo_root)
    pending: set[str] = set()
    quiet_since: float | None = None

    while True:
        current = collect_snapshot(repo_root)
        changed = diff_snapshots(previous, current)
        previous = current

        if changed and claude_cli_is_running():
            pending.update(changed)
            quiet_since = time.time()
            print(
                f"[claude-watch] observed {len(changed)} changed file(s) while Claude was running",
                flush=True,
            )

        if pending and quiet_since and (time.time() - quiet_since) >= debounce_seconds:
            payload = write_event(repo_root, sorted(pending))
            send_notification(payload)
            print(
                f"[claude-watch] notified for {payload['changed_count']} file(s): "
                + ", ".join(payload["changed_files"][:5]),
                flush=True,
            )
            pending.clear()
            quiet_since = None

        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
