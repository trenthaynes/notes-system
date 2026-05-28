"""Notes CLI entry point."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import typer

from notes.client import NotesClient, NotesClientError
from notes.config import load_config
from notes.core import (
    find_incomplete_tasks,
    find_most_recent_daily_note,
    get_daily_filename,
    render_daily_note,
    slugify,
)

app = typer.Typer(name="notes", no_args_is_help=True, help="Personal notes management.")


def _today_impl(web: bool = False) -> None:
    """Core logic for the today command — separated for testability."""
    config = load_config()

    today_date = date.today()
    filename = get_daily_filename(today_date)
    filename_stem = Path(filename).stem
    local_path = config.notes_dir / "journal" / filename

    # Step 4: if local file already exists, open in editor and return
    if local_path.exists():
        subprocess.Popen([config.editor, str(local_path)])
        typer.echo(f"✓ Opened: {local_path}")
        return

    # Step 5: find carry-over source
    prior_date = today_date - timedelta(days=1)
    prior_path = find_most_recent_daily_note(config.notes_dir, prior_date)

    prior_content = ""
    if prior_path is not None:
        prior_content = prior_path.read_text()
    else:
        # Try API
        prior_filename = get_daily_filename(prior_date)
        prior_stem = Path(prior_filename).stem
        client = NotesClient(config.server_url, config.api_token)
        try:
            results = client.list_notes(q=prior_stem)
            match = next((n for n in results if n.get("title") == prior_stem), None)
            if match is not None:
                note_data = client.get_note(match["id"])
                prior_content = note_data.get("content", "")
        except NotesClientError:
            prior_content = ""
        finally:
            client.close()

    # Step 6: gather carry-over tasks
    carryover = find_incomplete_tasks(prior_content)

    # Step 7: render note (piper_vault_id is "" at this point)
    content = render_daily_note(carryover, today_date)

    # Step 8-9: create note in PiperVault
    client = NotesClient(config.server_url, config.api_token)
    try:
        created = client.create_note(
            title=filename_stem,
            content=content,
            parent_path="/journal",
            tags=["daily_note"],
        )
    except NotesClientError as exc:
        typer.echo(str(exc), err=True)
        sys.exit(1)
        return  # unreachable in production but allows test mocking of sys.exit

    note_id = created["id"]

    # Step 10: inject piper_vault_id into frontmatter
    content = content.replace('piper_vault_id: ""', f'piper_vault_id: "{note_id}"')

    # --web flag: just print URL, no local file
    if web:
        parsed = urlparse(config.server_url)
        typer.echo(f"https://{parsed.netloc}/notes/{note_id}")
        return

    # Step 11-12: write local file
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content)

    # Step 13-14: open in editor (non-blocking)
    subprocess.Popen([config.editor, str(local_path)])
    typer.echo(f"✓ Opened: {local_path}")


@app.command()
def today(
    web: bool = typer.Option(False, "--web", help="Print the PiperVault URL instead of opening locally."),
) -> None:
    """Open or create today's daily note."""
    _today_impl(web=web)


# ---------------------------------------------------------------------------
# notes new
# ---------------------------------------------------------------------------

_PARENT_PATH_MAP = {
    "/journal": "journal",
    "/inbox": "inbox",
    "/projects": "projects",
}


def _new_impl(title: str) -> None:
    """Core logic for the new command — separated for testability."""
    config = load_config()

    slug = slugify(title)
    filename = slug + ".md"
    local_path = config.notes_dir / "inbox" / filename

    # If file already exists locally, just open it
    if local_path.exists():
        subprocess.Popen([config.editor, str(local_path)])
        typer.echo(f"✓ Opened: {local_path}")
        return

    today_str = date.today().strftime("%Y-%m-%d")
    content = (
        "---\n"
        f'title: "{title}"\n'
        f"creation date: {today_str}\n"
        "tags: []\n"
        'piper_vault_id: ""\n'
        "---\n"
        "\n"
    )

    client = NotesClient(config.server_url, config.api_token)
    try:
        created = client.create_note(title=title, content=content, parent_path="/inbox")
    except NotesClientError as exc:
        typer.echo(str(exc), err=True)
        sys.exit(1)
        return  # unreachable in production but allows test mocking of sys.exit
    finally:
        client.close()

    note_id = created["id"]
    content = content.replace('piper_vault_id: ""', f'piper_vault_id: "{note_id}"')

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content)

    subprocess.Popen([config.editor, str(local_path)])
    typer.echo(f"✓ Created: {local_path}")


@app.command(name="new")
def new(title: str = typer.Argument(..., help="Title of the new note.")) -> None:
    """Create a new note with the given title."""
    _new_impl(title)


# ---------------------------------------------------------------------------
# notes open
# ---------------------------------------------------------------------------


def _resolve_parent_dir(notes_dir: Path, parent_path: str | None) -> Path:
    """Map a PiperVault parentPath to a local directory."""
    if parent_path and parent_path in _PARENT_PATH_MAP:
        return notes_dir / _PARENT_PATH_MAP[parent_path]
    return notes_dir / "inbox"


def _open_impl(query: str) -> None:
    """Core logic for the open command — separated for testability."""
    config = load_config()

    # Search local notes_dir recursively for .md files whose stem contains query
    local_matches = [
        p for p in config.notes_dir.rglob("*.md")
        if query.lower() in p.stem.lower()
    ]

    if len(local_matches) == 1:
        local_path = local_matches[0]
        subprocess.Popen([config.editor, str(local_path)])
        typer.echo(f"✓ Opened: {local_path}")
        return

    if len(local_matches) > 1:
        for i, p in enumerate(local_matches, start=1):
            typer.echo(f"{i}. {p}")
        choice = typer.prompt("Select number", type=int)
        if choice < 1 or choice > len(local_matches):
            typer.echo(f"Invalid selection: {choice}", err=True)
            sys.exit(1)
            return
        local_path = local_matches[choice - 1]
        subprocess.Popen([config.editor, str(local_path)])
        typer.echo(f"✓ Opened: {local_path}")
        return

    # No local match — try API
    client = NotesClient(config.server_url, config.api_token)
    try:
        results = client.list_notes(q=query, limit=10)
    except NotesClientError as exc:
        typer.echo(str(exc), err=True)
        sys.exit(1)
        return
    finally:
        client.close()

    if not results:
        typer.echo(f"No notes found matching '{query}'. Try: notes new '{query}'")
        sys.exit(1)
        return

    for i, note in enumerate(results, start=1):
        typer.echo(f"{i}. {note.get('title', note.get('id', '?'))}")

    choice = typer.prompt("Select number", type=int)
    if choice < 1 or choice > len(results):
        typer.echo(f"Invalid selection: {choice}", err=True)
        sys.exit(1)
        return

    selected = results[choice - 1]
    note_id = selected["id"]
    title = selected.get("title", slugify(query))
    parent_path = selected.get("parentPath")

    client2 = NotesClient(config.server_url, config.api_token)
    try:
        note_data = client2.get_note(note_id)
    except NotesClientError as exc:
        typer.echo(str(exc), err=True)
        sys.exit(1)
        return
    finally:
        client2.close()

    content = note_data.get("content", "")
    # Inject piper_vault_id if not already present
    if 'piper_vault_id: ""' in content:
        content = content.replace('piper_vault_id: ""', f'piper_vault_id: "{note_id}"')

    local_dir = _resolve_parent_dir(config.notes_dir, parent_path)
    local_path = local_dir / (slugify(title) + ".md")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content)

    subprocess.Popen([config.editor, str(local_path)])
    typer.echo(f"✓ Opened: {local_path}")


@app.command(name="open")
def open_(query: str = typer.Argument(..., help="Partial title or keyword to search for.")) -> None:
    """Open an existing note by partial title match."""
    _open_impl(query)


# ---------------------------------------------------------------------------
# notes push
# ---------------------------------------------------------------------------


def _extract_piper_vault_id(content: str) -> str | None:
    """Extract the piper_vault_id value from YAML frontmatter, or None if absent/empty."""
    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return None
    fm_text = m.group(1)
    id_match = re.search(r'^piper_vault_id:\s*["\']?([^"\'\\n]*)["\']?', fm_text, re.MULTILINE)
    if not id_match:
        return None
    value = id_match.group(1).strip()
    return value if value else None


def _push_impl(dry_run: bool = False) -> None:
    """Core logic for the push command — separated for testability."""
    config = load_config()

    updated = 0
    skipped = 0
    errors = 0

    client = NotesClient(config.server_url, config.api_token)
    try:
        for md_file in sorted(config.notes_dir.rglob("*.md")):
            rel = md_file.relative_to(config.notes_dir)
            content = md_file.read_text()
            vault_id = _extract_piper_vault_id(content)

            if not vault_id:
                typer.echo(f"⚠ Skipping {rel} (no piper_vault_id)")
                skipped += 1
                continue

            if dry_run:
                typer.echo(f"  → Would push: {rel}")
                updated += 1
                continue

            try:
                client.update_note(vault_id, content)
                typer.echo(f"✓ Pushed: {rel}")
                updated += 1
            except NotesClientError as exc:
                typer.echo(f"✗ Failed: {rel}: {exc}")
                errors += 1
    finally:
        client.close()

    typer.echo(f"Push complete: {updated} updated, {skipped} skipped, {errors} errors")

    if errors:
        sys.exit(1)


@app.command(name="push")
def push(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be pushed without calling the API."),
) -> None:
    """Push all local .md notes with a piper_vault_id to PiperVault."""
    _push_impl(dry_run=dry_run)
