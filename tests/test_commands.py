"""Tests for `notes new` and `notes open` CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from notes.client import NotesClientError
from notes.config import NotesConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> NotesConfig:
    return NotesConfig(
        server_url="https://vault.example.com",
        api_token="token123",
        notes_dir=tmp_path,
        editor="code",
    )


def _created_note(note_id: str = "note-uuid-1234", title: str = "My Note") -> dict:
    return {"id": note_id, "title": title}


# ---------------------------------------------------------------------------
# notes new — Test 1: Happy path
# ---------------------------------------------------------------------------


class TestNewHappyPath:
    def test_creates_note_and_opens_editor(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title = "My Note"
        note_id = "note-uuid-1234"
        local_path = tmp_path / "inbox" / "my-note.md"

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note(note_id, title)

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
        ):
            from notes.cli import _new_impl
            _new_impl(title)

        # create_note called with correct title and parent_path
        mock_client.create_note.assert_called_once()
        call_kwargs = mock_client.create_note.call_args
        assert call_kwargs.kwargs.get("title") == title or call_kwargs.args[0] == title
        assert call_kwargs.kwargs.get("parent_path") == "/inbox"

        # Local file written at inbox/<slug>.md
        assert local_path.exists(), "Local file should have been written"
        content = local_path.read_text()

        # piper_vault_id injected into frontmatter
        assert f'piper_vault_id: "{note_id}"' in content

        # Editor opened
        mock_popen.assert_called_once_with(["code", str(local_path)])


# ---------------------------------------------------------------------------
# notes new — Test 2: Title with spaces slugified correctly
# ---------------------------------------------------------------------------


class TestNewSlugify:
    def test_spaces_become_hyphens_in_filename(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title = "My New Note"
        expected_path = tmp_path / "inbox" / "my-new-note.md"

        mock_client = MagicMock()
        mock_client.create_note.return_value = _created_note(title=title)

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
        ):
            from notes.cli import _new_impl
            _new_impl(title)

        assert expected_path.exists(), f"Expected file at {expected_path}"


# ---------------------------------------------------------------------------
# notes new — Test 3: File already exists — open without create_note
# ---------------------------------------------------------------------------


class TestNewFileAlreadyExists:
    def test_opens_existing_file_without_api_call(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title = "Existing Note"
        inbox_dir = tmp_path / "inbox"
        inbox_dir.mkdir(parents=True)
        local_path = inbox_dir / "existing-note.md"
        local_path.write_text("already here")

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
        ):
            from notes.cli import _new_impl
            _new_impl(title)

        mock_client.create_note.assert_not_called()
        mock_popen.assert_called_once_with(["code", str(local_path)])


# ---------------------------------------------------------------------------
# notes new — Test 4: API failure → error printed, no file written, exit 1
# ---------------------------------------------------------------------------


class TestNewApiFailure:
    def test_error_printed_no_file_exit_1(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title = "Failed Note"
        local_path = tmp_path / "inbox" / "failed-note.md"

        mock_client = MagicMock()
        mock_client.create_note.side_effect = NotesClientError("API error 500: Server Error", 500)

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
            patch("notes.cli.sys.exit") as mock_exit,
        ):
            from notes.cli import _new_impl
            _new_impl(title)

        mock_exit.assert_called_once_with(1)
        assert not local_path.exists(), "File must NOT be written on API error"
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# notes open — Test 5: Single local match → editor opened
# ---------------------------------------------------------------------------


class TestOpenSingleLocalMatch:
    def test_opens_matching_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)
        note_file = journal_dir / "my-project-notes.md"
        note_file.write_text("# My Project Notes")

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient") as mock_client_cls,
            patch("notes.cli.subprocess.Popen") as mock_popen,
        ):
            from notes.cli import _open_impl
            _open_impl("project")

        mock_popen.assert_called_once_with(["code", str(note_file)])
        # NotesClient should not be instantiated (local match found)
        mock_client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# notes open — Test 6: Multiple local matches → numbered list, user selects #1
# ---------------------------------------------------------------------------


class TestOpenMultipleLocalMatches:
    def test_numbered_list_and_correct_file_opened(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        inbox_dir = tmp_path / "inbox"
        inbox_dir.mkdir(parents=True)
        note1 = inbox_dir / "project-alpha.md"
        note2 = inbox_dir / "project-beta.md"
        note1.write_text("Alpha")
        note2.write_text("Beta")

        # Sort order is from rglob; we need to know which is first
        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient") as mock_client_cls,
            patch("notes.cli.subprocess.Popen") as mock_popen,
            patch("notes.cli.typer.prompt", return_value=1),
        ):
            from notes.cli import _open_impl
            _open_impl("project")

        # The first item in the numbered list should be opened
        mock_popen.assert_called_once()
        opened_path = Path(mock_popen.call_args[0][0][1])
        assert opened_path.suffix == ".md"
        assert "project" in opened_path.stem
        mock_client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# notes open — Test 7: No local match, API returns results → note written and opened
# ---------------------------------------------------------------------------


class TestOpenNoLocalApiMatch:
    def test_api_note_written_locally_and_opened(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)

        api_note_content = (
            "---\n"
            'title: "Remote Note"\n'
            "creation date: 2026-01-01\n"
            "tags: []\n"
            'piper_vault_id: ""\n'
            "---\n\n"
            "Some content here.\n"
        )
        note_id = "remote-uuid-5678"
        note_title = "Remote Note"

        mock_client = MagicMock()
        mock_client.list_notes.return_value = [
            {"id": note_id, "title": note_title, "parentPath": "/inbox"},
        ]
        mock_client.get_note.return_value = {
            "id": note_id,
            "title": note_title,
            "parentPath": "/inbox",
            "content": api_note_content,
        }

        expected_local_path = tmp_path / "inbox" / "remote-note.md"

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen") as mock_popen,
            patch("notes.cli.typer.prompt", return_value=1),
        ):
            from notes.cli import _open_impl
            _open_impl("remote")

        mock_client.list_notes.assert_called_once_with(q="remote", limit=10)
        mock_client.get_note.assert_called_once_with(note_id)

        assert expected_local_path.exists(), "Note should be written locally"
        written = expected_local_path.read_text()
        assert f'piper_vault_id: "{note_id}"' in written

        mock_popen.assert_called_once_with(["code", str(expected_local_path)])


# ---------------------------------------------------------------------------
# notes open — Test 8: No match anywhere → exit 1, message contains "notes new"
# ---------------------------------------------------------------------------


class TestOpenNoMatchAnywhere:
    def test_no_match_exits_with_helpful_message(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        config = _make_config(tmp_path)

        mock_client = MagicMock()
        mock_client.list_notes.return_value = []

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            patch("notes.cli.subprocess.Popen"),
            patch("notes.cli.sys.exit") as mock_exit,
        ):
            from notes.cli import _open_impl
            _open_impl("nonexistent-xyz-query")

        mock_exit.assert_called_once_with(1)
        captured = capsys.readouterr()
        assert "notes new" in captured.out
