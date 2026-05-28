"""Notes CLI entry point."""

from __future__ import annotations

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
