"""Tests for the `notes today` CLI command."""

from __future__ import annotations

import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from notes.client import NotesClientError
from notes.config import NotesConfig
from notes.core import get_daily_filename


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_TODAY = date(2026, 5, 28)
_TODAY_FILENAME = get_daily_filename(_TODAY)
_TODAY_STEM = Path(_TODAY_FILENAME).stem

_YESTERDAY = _TODAY - timedelta(days=1)
_YESTERDAY_FILENAME = get_daily_filename(_YESTERDAY)
_YESTERDAY_STEM = Path(_YESTERDAY_FILENAME).stem

_NOTE_ID = "abc-1234-uuid"


def _make_config(tmp_path: Path) -> NotesConfig:
    return NotesConfig(
        server_url="https://vault.example.com",
        api_token="token123",
        notes_dir=tmp_path,
        editor="code",
    )


def _created_note(note_id: str = _NOTE_ID) -> dict:
    return {"id": note_id, "title": _TODAY_STEM}


# ---------------------------------------------------------------------------
# Test 1: Happy path — today's note does not exist locally
# ---------------------------------------------------------------------------


class TestTodayHappyPath:
    def test_creates_note_and_opens_editor(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        local_path = tmp_path / "journal" / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note()
        mock_client.list_notes.return_value = []

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
            patch("notes.cli.find_most_recent_daily_note", return_value=None),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        mock_client.create_note.assert_called_once()
        call_kwargs = mock_client.create_note.call_args
        assert call_kwargs.kwargs.get("title") == _TODAY_STEM or call_kwargs.args[0] == _TODAY_STEM

        assert local_path.exists(), "Local file should have been written"
        content = local_path.read_text()
        assert f'piper_vault_id: "{_NOTE_ID}"' in content

        mock_popen.assert_called_once_with(["code", str(local_path)])

    def test_piper_vault_id_matches_returned_note_id(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        local_path = tmp_path / "journal" / _TODAY_FILENAME
        unique_id = "unique-vault-id-999"

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note(unique_id)
        mock_client.list_notes.return_value = []

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=None),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert f'piper_vault_id: "{unique_id}"' in content


# ---------------------------------------------------------------------------
# Test 2: Idempotent — today's file already exists locally
# ---------------------------------------------------------------------------


class TestTodayIdempotent:
    def test_opens_existing_file_no_create(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)
        local_path = journal_dir / _TODAY_FILENAME
        local_path.write_text("existing content")

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        mock_client.create_note.assert_not_called()
        mock_popen.assert_called_once_with(["code", str(local_path)])


# ---------------------------------------------------------------------------
# Test 3: Carry-over from local file
# ---------------------------------------------------------------------------


class TestCarryOverFromLocalFile:
    def test_incomplete_task_appears_in_carried_over_section(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)

        # Write yesterday's note with an incomplete task
        yesterday_content = textwrap.dedent("""\
            ---
            tags: ["#daily_note"]
            piper_vault_id: "old-id"
            ---

            ### Journal:
            -

            ### Tasks:
            - [ ] Buy groceries
            - [x] Done task
        """)
        yesterday_path = journal_dir / _YESTERDAY_FILENAME
        yesterday_path.write_text(yesterday_content)

        local_path = journal_dir / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=yesterday_path),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert "**Carried over:**" in content
        assert "- [ ] Buy groceries" in content


# ---------------------------------------------------------------------------
# Test 4: Blank placeholder tasks NOT carried over
# ---------------------------------------------------------------------------


class TestBlankTasksNotCarriedOver:
    def test_bare_checkboxes_not_in_carryover(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)

        yesterday_content = textwrap.dedent("""\
            ### Tasks:
            - [ ]
            - [ ]
        """)
        yesterday_path = journal_dir / _YESTERDAY_FILENAME
        yesterday_path.write_text(yesterday_content)

        local_path = journal_dir / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=yesterday_path),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert "**Carried over:**" not in content


# ---------------------------------------------------------------------------
# Test 5: No prior note — API returns empty list → note created without carry-over
# ---------------------------------------------------------------------------


class TestNoPriorNote:
    def test_no_carryover_block_when_no_prior_note(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        local_path = tmp_path / "journal" / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note()
        mock_client.list_notes.return_value = []

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=None),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert "**Carried over:**" not in content
        mock_client.create_note.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: API create failure
# ---------------------------------------------------------------------------


class TestApiCreateFailure:
    def test_error_printed_no_local_file_exit_1(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        local_path = tmp_path / "journal" / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.side_effect = NotesClientError("API error 500: Internal Server Error", 500)
        mock_client.list_notes.return_value = []

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
            patch("notes.cli.find_most_recent_daily_note", return_value=None),
            patch("notes.cli.sys.exit") as mock_exit,
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        mock_exit.assert_called_once_with(1)
        assert not local_path.exists(), "Local file must NOT be written on API error"
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: Weekend gap — prior note from 3 days ago
# ---------------------------------------------------------------------------


class TestWeekendGap:
    def test_tasks_from_three_days_ago_used_for_carryover(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)

        # Simulate Friday -> Monday (3 days gap)
        friday = _TODAY - timedelta(days=3)
        friday_filename = get_daily_filename(friday)
        friday_content = textwrap.dedent("""\
            ### Tasks:
            - [ ] Deploy on Monday
            - [x] Finished Friday task
        """)
        friday_path = journal_dir / friday_filename
        friday_path.write_text(friday_content)

        local_path = journal_dir / _TODAY_FILENAME

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=friday_path),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert "**Carried over:**" in content
        assert "- [ ] Deploy on Monday" in content
        assert "Finished Friday task" not in content


# ---------------------------------------------------------------------------
# Test 8: Carry-over from API (prior note not local)
# ---------------------------------------------------------------------------


class TestCarryOverFromApi:
    def test_prior_note_fetched_from_api(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        local_path = tmp_path / "journal" / _TODAY_FILENAME

        api_prior_content = textwrap.dedent("""\
            ### Tasks:
            - [ ] API task to carry over
            - [x] API done task
        """)

        # list_notes returns a match for the prior note title
        prior_note_list_result = [{"id": "prior-note-id", "title": _YESTERDAY_STEM}]
        prior_note_full = {"id": "prior-note-id", "title": _YESTERDAY_STEM, "content": api_prior_content}

        mock_client = MagicMock()
        mock_client.list_notes.return_value = prior_note_list_result
        mock_client.get_note.return_value = prior_note_full
        mock_client.create_note.return_value = _created_note()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.date") as mock_date,
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.find_most_recent_daily_note", return_value=None),
        ):
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            from notes.cli import _today_impl
            _today_impl()

        content = local_path.read_text()
        assert "**Carried over:**" in content
        assert "- [ ] API task to carry over" in content

        # Verify the API calls were made correctly
        mock_client.list_notes.assert_called_once_with(q=_YESTERDAY_STEM)
        mock_client.get_note.assert_called_once_with("prior-note-id")
