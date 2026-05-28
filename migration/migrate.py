#!/usr/bin/env python3
"""
One-time migration script: import Obsidian vault into PiperVault.

Usage:
    python migrate.py --vault ~/obsidian/trent --server https://vault.yourdomain.com --token <api_token>

State is tracked in state.json (same directory as this script) so re-runs skip
already-migrated files. Preserve state.json after migration to avoid duplicates.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import frontmatter
import httpx

# Directories to skip entirely when walking the vault.
SKIP_DIRS = {".obsidian", ".notecompanion", "_assets", "_bases", ".git"}

# Map Obsidian top-level folder names to PiperVault parentPath values.
FOLDER_MAP = {
    "01 inbox": "/inbox",
    "02 projects": "/projects",
    "03 areas": "/areas",
    "04 resources": "/resources",
    "05 journal": "/journal",
    "06 input": "/input",
    "07 output": "/output",
    "zettelkasten": "/zettelkasten",
    "_templates": "/templates",
}


def resolve_parent_path(relative_path: Path) -> str:
    """Map the top-level folder of a vault-relative path to a PiperVault parentPath."""
    parts = relative_path.parts
    if not parts:
        return "/inbox"
    top = parts[0]
    mapped = FOLDER_MAP.get(top)
    if mapped is None:
        print(f"  ⚠ Unknown folder '{top}' → defaulting to /inbox")
        return "/inbox"
    # For nested paths, append the sub-path within the top folder.
    if len(parts) > 2:
        sub = "/".join(parts[1:-1])  # exclude the filename
        return f"{mapped}/{sub}"
    return mapped


def extract_tags(post: frontmatter.Post) -> list[str]:
    """Pull tags from parsed frontmatter, normalising to a flat list of strings."""
    raw = post.metadata.get("tags", [])
    if isinstance(raw, str):
        raw = [raw]
    return [str(t).lstrip("#") for t in raw if t]


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.write_text(json.dumps(state, indent=2))


def create_note(
    client: httpx.Client,
    server: str,
    token: str,
    title: str,
    content: str,
    parent_path: str,
    tags: list[str],
) -> str:
    """POST /api/v1/notes and return the note UUID."""
    resp = client.post(
        f"{server.rstrip('/')}/api/v1/notes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": title,
            "content": content,
            "parentPath": parent_path,
            "tags": tags,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def collect_files(vault: Path) -> list[Path]:
    """Return all .md files in the vault, skipping ignored directories."""
    results = []
    for path in vault.rglob("*.md"):
        # Skip if any component is in SKIP_DIRS.
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        results.append(path)
    return sorted(results)


def migrate(
    vault: Path,
    server: str,
    token: str,
    state_path: Path,
    delay: float = 0.1,
    dry_run: bool = False,
) -> int:
    """Run the migration. Returns exit code (0 = success, 1 = had errors)."""
    state = load_state(state_path)
    files = collect_files(vault)

    total = len(files)
    migrated = skipped = errors = 0

    print(f"Found {total} markdown files in {vault}")
    if dry_run:
        print("DRY RUN — no notes will be created\n")

    with httpx.Client() as client:
        for i, path in enumerate(files, 1):
            rel = path.relative_to(vault)
            key = str(rel)

            if key in state:
                skipped += 1
                continue

            try:
                post = frontmatter.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ✗ [{i}/{total}] Parse error {rel}: {e}")
                errors += 1
                continue

            title = path.stem
            content = path.read_text(encoding="utf-8")
            parent_path = resolve_parent_path(rel)
            tags = extract_tags(post)

            if dry_run:
                print(f"  → [{i}/{total}] Would migrate: {rel} → {parent_path}")
                migrated += 1
                continue

            try:
                note_id = create_note(client, server, token, title, content, parent_path, tags)
                state[key] = note_id
                save_state(state_path, state)
                print(f"  ✓ [{i}/{total}] {rel} → {parent_path} (id: {note_id})")
                migrated += 1
                if delay:
                    time.sleep(delay)
            except httpx.HTTPStatusError as e:
                print(f"  ✗ [{i}/{total}] HTTP {e.response.status_code}: {rel}: {e.response.text[:120]}")
                errors += 1
            except Exception as e:
                print(f"  ✗ [{i}/{total}] {rel}: {e}")
                errors += 1

    print(f"\nMigration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return 1 if errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Obsidian vault to PiperVault")
    parser.add_argument("--vault", required=True, type=Path, help="Path to Obsidian vault root")
    parser.add_argument("--server", required=True, help="PiperVault base URL (e.g. https://vault.yourdomain.com)")
    parser.add_argument("--token", required=True, help="PiperVault API token (Bearer)")
    parser.add_argument("--state", type=Path, default=Path(__file__).parent / "state.json",
                        help="Path to state file (default: state.json next to this script)")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="Seconds to wait between API calls (default: 0.1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be migrated without making API calls")
    args = parser.parse_args()

    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        print(f"Error: vault directory not found: {vault}", file=sys.stderr)
        sys.exit(1)

    sys.exit(migrate(vault, args.server, args.token, args.state, args.delay, args.dry_run))


if __name__ == "__main__":
    main()
