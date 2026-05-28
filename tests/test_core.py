"""Unit tests for notes.core — all pure functions."""

from __future__ import annotations

import datetime
import pathlib
import textwrap

import pytest

from notes.core import (
    find_incomplete_tasks,
    find_most_recent_daily_note,
    get_daily_filename,
    render_daily_note,
    slugify,
)


# ---------------------------------------------------------------------------
# get_daily_filename
# ---------------------------------------------------------------------------


class TestGetDailyFilename:
    def test_known_date(self) -> None:
        assert (
            get_daily_filename(datetime.date(2026, 5, 28))
            == "2026-05-28 Week 22 Day 148 - Thursday.md"
        )

    def test_new_year_day_2026(self) -> None:
        # 2026-01-01 is ISO week 1, day 1, Thursday
        assert (
            get_daily_filename(datetime.date(2026, 1, 1))
            == "2026-01-01 Week 01 Day 001 - Thursday.md"
        )

    def test_iso_week_crosses_year_boundary(self) -> None:
        # 2027-01-01 falls in ISO week 53 of 2026 (not week 1 of 2027)
        result = get_daily_filename(datetime.date(2027, 1, 1))
        assert result == "2027-01-01 Week 53 Day 001 - Friday.md"


# ---------------------------------------------------------------------------
# find_incomplete_tasks
# ---------------------------------------------------------------------------

_SAMPLE_NOTE = textwrap.dedent("""\
    ## Journal

    Some text.

    ### Tasks:
    - [ ] Buy groceries
    - [x] Write tests
    - [ ] Call dentist
    - [ ]
    - [ ]
      - [ ] Sub-task one
    - [ ] Another task

    ## Notes

    Not a task section.
    - [ ] Should be ignored
""")


class TestFindIncompleteTasks:
    def test_returns_only_tasks_under_tasks_heading(self) -> None:
        tasks = find_incomplete_tasks(_SAMPLE_NOTE)
        assert "- [ ] Buy groceries" in tasks
        assert "- [ ] Call dentist" in tasks
        assert "- [ ] Another task" in tasks

    def test_skips_blank_checkbox_lines(self) -> None:
        tasks = find_incomplete_tasks(_SAMPLE_NOTE)
        # Lines that are just "- [ ]" or "- [ ]   " (only whitespace after)
        for t in tasks:
            # After "- [ ]" there must be non-whitespace content
            remainder = t.lstrip()
            assert remainder.startswith("- [ ] "), repr(t)
            after_checkbox = remainder[len("- [ ] "):]
            assert after_checkbox.strip() != "", repr(t)

    def test_stops_at_next_heading(self) -> None:
        tasks = find_incomplete_tasks(_SAMPLE_NOTE)
        # "Should be ignored" is under a different heading
        for t in tasks:
            assert "Should be ignored" not in t

    def test_preserves_indented_subtasks(self) -> None:
        tasks = find_incomplete_tasks(_SAMPLE_NOTE)
        assert "  - [ ] Sub-task one" in tasks

    def test_returns_empty_when_no_tasks_section(self) -> None:
        content = "## Journal\n\n- [ ] This has no Tasks heading\n"
        assert find_incomplete_tasks(content) == []

    def test_returns_empty_when_all_tasks_are_blank_placeholders(self) -> None:
        content = textwrap.dedent("""\
            ### Tasks:
            - [ ]
            - [ ]
        """)
        assert find_incomplete_tasks(content) == []

    def test_completed_tasks_not_included(self) -> None:
        tasks = find_incomplete_tasks(_SAMPLE_NOTE)
        for t in tasks:
            assert "[x]" not in t


# ---------------------------------------------------------------------------
# render_daily_note
# ---------------------------------------------------------------------------


class TestRenderDailyNote:
    _date = datetime.date(2026, 5, 28)

    def test_contains_journal_section(self) -> None:
        result = render_daily_note([], self._date)
        assert "### Journal:" in result

    def test_contains_tasks_section(self) -> None:
        result = render_daily_note([], self._date)
        assert "### Tasks:" in result

    def test_carryover_tasks_present(self) -> None:
        tasks = ["- [ ] Buy milk", "  - [ ] Organic if possible"]
        result = render_daily_note(tasks, self._date)
        assert "**Carried over:**" in result
        assert "- [ ] Buy milk" in result
        assert "  - [ ] Organic if possible" in result

    def test_no_carryover_block_when_empty(self) -> None:
        result = render_daily_note([], self._date)
        assert "**Carried over:**" not in result

    def test_piper_vault_id_in_frontmatter(self) -> None:
        result = render_daily_note([], self._date, piper_vault_id="abc-123")
        assert 'piper_vault_id: "abc-123"' in result

    def test_piper_vault_id_empty_string_in_frontmatter(self) -> None:
        result = render_daily_note([], self._date)
        assert 'piper_vault_id: ""' in result

    def test_frontmatter_has_tags(self) -> None:
        result = render_daily_note([], self._date)
        assert '#daily_note' in result

    def test_frontmatter_has_title(self) -> None:
        result = render_daily_note([], self._date)
        assert 'Title: "2026-05-28 Week 22 Day 148 - Thursday"' in result

    def test_frontmatter_has_dates(self) -> None:
        result = render_daily_note([], self._date)
        assert "creation date: 2026-05-28" in result
        assert "modified date: 2026-05-28" in result


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_my_new_note(self) -> None:
        assert slugify("My New Note") == "my-new-note"

    def test_hello_world_with_exclamation(self) -> None:
        assert slugify("Hello World!") == "hello-world"

    def test_all_lowercase(self) -> None:
        assert slugify("UPPER CASE") == "upper-case"

    def test_strips_special_chars(self) -> None:
        assert slugify("foo@bar.baz") == "foobarbaz"


# ---------------------------------------------------------------------------
# find_most_recent_daily_note
# ---------------------------------------------------------------------------


class TestFindMostRecentDailyNote:
    def test_finds_yesterdays_note(self, tmp_path: pathlib.Path) -> None:
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        today = datetime.date(2026, 5, 28)
        yesterday = today - datetime.timedelta(days=1)
        note_name = get_daily_filename(yesterday)
        (journal_dir / note_name).write_text("# Yesterday")

        result = find_most_recent_daily_note(tmp_path, today)
        assert result == journal_dir / note_name

    def test_skips_missing_dates_finds_three_days_ago(
        self, tmp_path: pathlib.Path
    ) -> None:
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        today = datetime.date(2026, 5, 28)
        three_days_ago = today - datetime.timedelta(days=3)
        note_name = get_daily_filename(three_days_ago)
        (journal_dir / note_name).write_text("# Three days ago")

        result = find_most_recent_daily_note(tmp_path, today)
        assert result == journal_dir / note_name

    def test_returns_none_when_nothing_found(self, tmp_path: pathlib.Path) -> None:
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        today = datetime.date(2026, 5, 28)

        result = find_most_recent_daily_note(tmp_path, today)
        assert result is None

    def test_respects_max_lookback(self, tmp_path: pathlib.Path) -> None:
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        today = datetime.date(2026, 5, 28)
        eight_days_ago = today - datetime.timedelta(days=8)
        note_name = get_daily_filename(eight_days_ago)
        (journal_dir / note_name).write_text("# Old note")

        # Default max_lookback=7 should not find a note 8 days ago
        result = find_most_recent_daily_note(tmp_path, today)
        assert result is None
