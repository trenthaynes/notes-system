"""Tests for `notes push` CLI command."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from notes.cli import _push_impl
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


def _write_note(directory: Path, filename: str, vault_id: str | None = "abc-123") -> Path:
    """Write a minimal .md file with optional piper_vault_id frontmatter."""
    if vault_id is not None:
        content = (
            "---\n"
            f'title: "Test Note"\n'
            f'piper_vault_id: "{vault_id}"\n'
            "---\n\n"
            "Body text.\n"
        )
    else:
        content = (
            "---\n"
            'title: "No ID Note"\n'
            "---\n\n"
            "Body text.\n"
        )
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Test 1: Happy path — one file with valid piper_vault_id
# ---------------------------------------------------------------------------


class TestPushHappyPath:
    def test_calls_update_note_and_prints_summary(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "note1.md", vault_id="id-001")

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=False)

        mock_client.update_note.assert_called_once_with("id-001", (tmp_path / "note1.md").read_text())
        out = capsys.readouterr().out
        assert "✓ Pushed: note1.md" in out
        assert "1 updated, 0 skipped, 0 errors" in out


# ---------------------------------------------------------------------------
# Test 2: Missing piper_vault_id — file is skipped with warning
# ---------------------------------------------------------------------------


class TestPushMissingId:
    def test_skips_file_without_piper_vault_id(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "no-id.md", vault_id=None)

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=False)

        mock_client.update_note.assert_not_called()
        out = capsys.readouterr().out
        assert "⚠ Skipping no-id.md (no piper_vault_id)" in out
        assert "0 updated, 1 skipped" in out


# ---------------------------------------------------------------------------
# Test 3: Empty piper_vault_id — treated as missing
# ---------------------------------------------------------------------------


class TestPushEmptyId:
    def test_skips_file_with_empty_piper_vault_id(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "empty-id.md", vault_id="")

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=False)

        mock_client.update_note.assert_not_called()
        out = capsys.readouterr().out
        assert "⚠ Skipping empty-id.md (no piper_vault_id)" in out
        assert "0 updated, 1 skipped" in out


# ---------------------------------------------------------------------------
# Test 4: dry-run — prints "Would push", does NOT call update_note
# ---------------------------------------------------------------------------


class TestPushDryRun:
    def test_dry_run_prints_would_push_and_skips_api(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "note-dry.md", vault_id="id-dry")

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=True)

        mock_client.update_note.assert_not_called()
        out = capsys.readouterr().out
        assert "→ Would push: note-dry.md" in out
        assert "1 updated" in out


# ---------------------------------------------------------------------------
# Test 5: API failure — error printed, other files still processed, exit code 1
# ---------------------------------------------------------------------------


class TestPushApiFailure:
    def test_api_error_counts_and_continues(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "a-fail.md", vault_id="id-fail")
        _write_note(tmp_path, "b-ok.md", vault_id="id-ok")

        mock_client = MagicMock()
        mock_client.update_note.side_effect = [
            NotesClientError("Server error", 500),
            {"id": "id-ok"},
        ]

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
            pytest.raises(SystemExit) as exc_info,
        ):
            _push_impl(dry_run=False)

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "✗ Failed: a-fail.md" in out
        assert "✓ Pushed: b-ok.md" in out
        assert "1 updated, 0 skipped, 1 errors" in out


# ---------------------------------------------------------------------------
# Test 6: Empty notes dir — 0 files — summary "0 updated, 0 skipped, 0 errors"
# ---------------------------------------------------------------------------


class TestPushEmptyDir:
    def test_empty_directory_exits_zero(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=False)

        mock_client.update_note.assert_not_called()
        out = capsys.readouterr().out
        assert "0 updated, 0 skipped, 0 errors" in out


# ---------------------------------------------------------------------------
# Test 7: Multiple files — 2 valid + 1 missing id → 2 updated, 1 skipped
# ---------------------------------------------------------------------------


class TestPushMultipleFiles:
    def test_mixed_files_counts_correctly(self, tmp_path: Path, capsys) -> None:
        config = _make_config(tmp_path)
        _write_note(tmp_path, "a.md", vault_id="id-a")
        _write_note(tmp_path, "b.md", vault_id="id-b")
        _write_note(tmp_path, "c.md", vault_id=None)

        mock_client = MagicMock()

        with (
            patch("notes.cli.load_config", return_value=config),
            patch("notes.cli.NotesClient", return_value=mock_client),
        ):
            _push_impl(dry_run=False)

        assert mock_client.update_note.call_count == 2
        out = capsys.readouterr().out
        assert "2 updated, 1 skipped, 0 errors" in out
        assert "⚠ Skipping c.md (no piper_vault_id)" in out
