"""Notes MCP server — FastMCP app exposing 4 tools backed by PiperVault."""

import datetime
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from notes.client import NotesClient, NotesClientError
from notes.core import get_daily_filename

mcp = FastMCP("notes-mcp")


def _get_client() -> NotesClient:
    url = os.environ.get("PIPERVAULT_URL", "")
    token = os.environ.get("PIPERVAULT_API_TOKEN", "")
    if not url or not token:
        raise RuntimeError("PIPERVAULT_URL and PIPERVAULT_API_TOKEN must be set")
    return NotesClient(url, token)


# ---------------------------------------------------------------------------
# Tool 1: search_notes
# ---------------------------------------------------------------------------


@mcp.tool()
def search_notes(query: str, top_k: int = 5) -> str:
    """Search notes semantically. Returns titles and excerpts of the most relevant notes."""
    try:
        client = _get_client()
        results = client.search(query, top_k=top_k)
    except NotesClientError as exc:
        return f"Search failed: {exc}"

    if not results:
        return f"No notes found matching '{query}'."

    # Deduplicate by source.id — keep highest-score chunk per source.
    seen: dict[str, dict] = {}
    for item in results:
        source = item.get("source", {})
        source_id = source.get("id", "")
        score = item.get("score", 0)
        if source_id not in seen or score > seen[source_id]["score"]:
            seen[source_id] = {"score": score, "item": item}

    # Take up to top_k unique sources in score order.
    unique = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    lines: list[str] = []
    for entry in unique:
        item = entry["item"]
        source = item.get("source", {})
        source_id = source.get("id", "")
        filename = source.get("filename", "")
        chunk_content = item.get("chunk", {}).get("content", "")

        # Try to fetch the full note title; fall back to filename.
        title = filename
        try:
            note = client.get_note(source_id)
            title = note.get("title", filename) or filename
        except Exception:
            pass

        excerpt = chunk_content[:300]
        lines.append(f"## {title}\n> {excerpt}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: get_note
# ---------------------------------------------------------------------------


@mcp.tool()
def get_note(title: str) -> str:
    """Retrieve a note by title (exact or partial match). Returns the full markdown content."""
    try:
        client = _get_client()
        notes = client.list_notes(q=title, limit=10)
    except NotesClientError as exc:
        return f"Error retrieving note: {exc}"

    if not notes:
        return f"No note found matching '{title}'."

    # Prefer exact case-insensitive title match; fall back to substring match.
    title_lower = title.lower()
    match = None
    for note in notes:
        note_title = note.get("title", "")
        if note_title.lower() == title_lower:
            match = note
            break
    if match is None:
        for note in notes:
            note_title = note.get("title", "")
            if title_lower in note_title.lower():
                match = note
                break

    if match is None:
        return f"No note found matching '{title}'."

    try:
        full_note = client.get_note(match["id"])
        return full_note.get("content", "")
    except NotesClientError as exc:
        return f"Error retrieving note: {exc}"


# ---------------------------------------------------------------------------
# Tool 3: get_daily_note
# ---------------------------------------------------------------------------


@mcp.tool()
def get_daily_note(date: str = "") -> str:
    """Retrieve a daily note by date (YYYY-MM-DD). Defaults to today."""
    if not date or not date.strip():
        d = datetime.date.today()
        date_str = d.isoformat()
    else:
        try:
            d = datetime.date.fromisoformat(date)
            date_str = date
        except ValueError:
            return "Invalid date format. Use YYYY-MM-DD."

    title_stem = Path(get_daily_filename(d)).stem

    try:
        client = _get_client()
        notes = client.list_notes(q=title_stem, limit=5)
    except NotesClientError as exc:
        return f"Error: {exc}"

    match = None
    for note in notes:
        if note.get("title", "").lower() == title_stem.lower():
            match = note
            break

    if match is None:
        return f"No daily note found for {date_str}."

    try:
        full_note = client.get_note(match["id"])
        return full_note.get("content", "")
    except NotesClientError as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 4: create_note
# ---------------------------------------------------------------------------


@mcp.tool()
def create_note(title: str, content: str, tags: list[str] = []) -> str:
    """Create a new note in the inbox with the given title and content."""
    try:
        client = _get_client()
        note = client.create_note(title=title, content=content, parent_path="/inbox", tags=tags)
        return f"Created note '{title}' with ID {note['id']}."
    except NotesClientError as exc:
        return f"Failed to create note: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
