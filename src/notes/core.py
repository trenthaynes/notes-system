"""Pure business-logic functions for the notes system.

All functions in this module are side-effect-free (no I/O beyond the
filesystem stat calls in find_most_recent_daily_note).
"""

from __future__ import annotations

import datetime
import pathlib
import re


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------


def get_daily_filename(date: datetime.date) -> str:
    """Return the canonical filename for a daily note.

    Format: ``YYYY-MM-DD Week WW Day DDD - dddd.md``

    Example::

        >>> get_daily_filename(datetime.date(2026, 5, 28))
        '2026-05-28 Week 22 Day 148 - Thursday.md'

    Week number uses ISO 8601 (``date.isocalendar()[1]``), zero-padded to 2
    digits.  Day-of-year is zero-padded to 3 digits.
    """
    iso_week = date.isocalendar()[1]
    day_of_year = date.timetuple().tm_yday
    weekday_name = date.strftime("%A")
    date_str = date.strftime("%Y-%m-%d")
    return f"{date_str} Week {iso_week:02d} Day {day_of_year:03d} - {weekday_name}.md"


# ---------------------------------------------------------------------------
# Task extraction
# ---------------------------------------------------------------------------

_TASKS_HEADING_RE = re.compile(r"^#{1,6}\s+Tasks", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
_INCOMPLETE_TASK_RE = re.compile(r"^(\s*)- \[ \] (\S.*)$")


def find_incomplete_tasks(content: str) -> list[str]:
    """Return all incomplete task lines from the first ``Tasks`` section.

    A task line matches ``- [ ] <non-whitespace content>``.  Sub-tasks
    (indented lines) are included with their original leading whitespace.
    Blank placeholders (``- [ ]`` followed only by whitespace or nothing)
    are skipped.

    The search stops at the heading immediately following the Tasks heading.
    Returns an empty list when no Tasks heading is found or when all task
    lines are blank placeholders.
    """
    m = _TASKS_HEADING_RE.search(content)
    if m is None:
        return []

    # Slice the content starting just after the Tasks heading line.
    after_heading = content[m.end():]

    # Find the next heading, if any, and truncate there.
    next_heading = _ANY_HEADING_RE.search(after_heading)
    section = after_heading if next_heading is None else after_heading[: next_heading.start()]

    tasks: list[str] = []
    for line in section.splitlines():
        task_match = _INCOMPLETE_TASK_RE.match(line)
        if task_match:
            tasks.append(line)

    return tasks


# ---------------------------------------------------------------------------
# Daily note rendering
# ---------------------------------------------------------------------------


def render_daily_note(
    carryover_tasks: list[str],
    date: datetime.date,
    piper_vault_id: str = "",
) -> str:
    """Render a full daily-note markdown string including YAML frontmatter.

    Args:
        carryover_tasks: Incomplete task lines carried over from a previous note.
        date: The date for this daily note.
        piper_vault_id: Optional PiperVault note ID to embed in frontmatter.

    Returns:
        A complete markdown string ready to be written to disk.
    """
    filename_without_ext = get_daily_filename(date)[: -len(".md")]
    date_str = date.strftime("%Y-%m-%d")

    frontmatter = (
        "---\n"
        'tags: ["#daily_note"]\n'
        f'Title: "{filename_without_ext}"\n'
        f"creation date: {date_str}\n"
        f"modified date: {date_str}\n"
        f'piper_vault_id: "{piper_vault_id}"\n'
        "---\n"
    )

    body = (
        "### Journal:\n"
        "-\n"
        "\n"
        "### Tasks:\n"
        "- [ ]\n"
        "- [ ]\n"
    )

    if carryover_tasks:
        carried = "\n".join(carryover_tasks)
        body += f"\n**Carried over:**\n{carried}\n"

    return frontmatter + "\n" + body


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def find_most_recent_daily_note(
    notes_dir: pathlib.Path,
    from_date: datetime.date,
    max_lookback: int = 7,
) -> pathlib.Path | None:
    """Walk backwards from *from_date* (exclusive) to find the most recent daily note.

    Checks ``notes_dir / "journal" / <expected_filename>`` for each candidate
    date.  Returns the first path that exists, or ``None`` if nothing is found
    within *max_lookback* days.
    """
    journal_dir = notes_dir / "journal"
    for days_back in range(1, max_lookback + 1):
        candidate_date = from_date - datetime.timedelta(days=days_back)
        filename = get_daily_filename(candidate_date)
        candidate_path = journal_dir / filename
        if candidate_path.exists():
            return candidate_path
    return None


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def slugify(title: str) -> str:
    """Convert a title to a URL/filename-safe slug.

    Lowercases the string, replaces spaces with hyphens, then strips any
    character that is not alphanumeric or a hyphen.

    Example::

        >>> slugify("My New Note")
        'my-new-note'
        >>> slugify("Hello World!")
        'hello-world'
    """
    slug = title.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Collapse multiple consecutive hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug
