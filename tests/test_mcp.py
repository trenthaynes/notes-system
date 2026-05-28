"""Tests for the MCP server tools in notes.server."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from notes.client import NotesClientError
import notes.server as server_module
from notes.server import (
    search_notes,
    get_note,
    get_daily_note,
    create_note,
)
from notes.core import get_daily_filename
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk_result(
    source_id: str,
    filename: str,
    content: str,
    score: float = 0.9,
) -> dict:
    return {
        "score": score,
        "chunk": {"content": content, "sourceId": source_id},
        "source": {"id": source_id, "filename": filename},
    }


def _patch_client(mock_client: MagicMock):
    """Context manager: patch _get_client() to return mock_client."""
    return patch.object(server_module, "_get_client", return_value=mock_client)


# ---------------------------------------------------------------------------
# search_notes
# ---------------------------------------------------------------------------


class TestSearchNotes:
    def test_two_results_returns_two_sections(self):
        mock_client = MagicMock()
        mock_client.search.return_value = [
            _make_chunk_result("id-1", "docker-notes.md", "Docker is a container runtime.", score=0.95),
            _make_chunk_result("id-2", "docker-compose.md", "Compose orchestrates containers.", score=0.85),
        ]
        mock_client.get_note.side_effect = [
            {"title": "Docker Notes", "content": "..."},
            {"title": "Docker Compose", "content": "..."},
        ]

        with _patch_client(mock_client):
            result = search_notes("docker")

        assert result.count("##") == 2
        assert "Docker Notes" in result
        assert "Docker Compose" in result
        assert "Docker is a container runtime." in result
        assert "Compose orchestrates containers." in result

    def test_deduplication_keeps_highest_score(self):
        """Two chunks from same source → only one result returned."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            _make_chunk_result("id-1", "docker-notes.md", "First chunk.", score=0.95),
            _make_chunk_result("id-1", "docker-notes.md", "Second chunk.", score=0.80),
        ]
        mock_client.get_note.return_value = {"title": "Docker Notes", "content": "..."}

        with _patch_client(mock_client):
            result = search_notes("docker", top_k=1)

        assert result.count("##") == 1
        # Highest-score chunk content should be present
        assert "First chunk." in result

    def test_no_results_returns_no_notes_message(self):
        mock_client = MagicMock()
        mock_client.search.return_value = []

        with _patch_client(mock_client):
            result = search_notes("docker")

        assert "No notes found matching 'docker'." == result

    def test_client_error_returns_error_message(self):
        mock_client = MagicMock()
        mock_client.search.side_effect = NotesClientError("connection refused", 503)

        with _patch_client(mock_client):
            result = search_notes("docker")

        assert result.startswith("Search failed:")
        assert "connection refused" in result


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------


class TestGetNote:
    def test_exact_match_returns_content(self):
        mock_client = MagicMock()
        mock_client.list_notes.return_value = [
            {"id": "note-42", "title": "Kubernetes", "content": ""},
        ]
        mock_client.get_note.return_value = {"id": "note-42", "title": "Kubernetes", "content": "# Kubernetes\nContent here."}

        with _patch_client(mock_client):
            result = get_note("kubernetes")

        assert result == "# Kubernetes\nContent here."
        mock_client.get_note.assert_called_once_with("note-42")

    def test_nonexistent_note_returns_not_found(self):
        mock_client = MagicMock()
        mock_client.list_notes.return_value = []

        with _patch_client(mock_client):
            result = get_note("nonexistent")

        assert "No note found matching 'nonexistent'." == result

    def test_substring_match_used_when_no_exact_match(self):
        mock_client = MagicMock()
        mock_client.list_notes.return_value = [
            {"id": "note-7", "title": "Kubernetes Deployment Guide", "content": ""},
        ]
        mock_client.get_note.return_value = {"id": "note-7", "title": "Kubernetes Deployment Guide", "content": "Guide content."}

        with _patch_client(mock_client):
            result = get_note("kubernetes")

        assert result == "Guide content."

    def test_list_notes_error_returns_error_message(self):
        mock_client = MagicMock()
        mock_client.list_notes.side_effect = NotesClientError("server error", 500)

        with _patch_client(mock_client):
            result = get_note("kubernetes")

        assert result.startswith("Error retrieving note:")


# ---------------------------------------------------------------------------
# get_daily_note
# ---------------------------------------------------------------------------


class TestGetDailyNote:
    def _stem_for(self, d: datetime.date) -> str:
        return Path(get_daily_filename(d)).stem

    def test_no_date_uses_today(self):
        today = datetime.date.today()
        expected_stem = self._stem_for(today)

        mock_client = MagicMock()
        mock_client.list_notes.return_value = [
            {"id": "daily-1", "title": expected_stem},
        ]
        mock_client.get_note.return_value = {"id": "daily-1", "title": expected_stem, "content": "Today's note."}

        with _patch_client(mock_client):
            result = get_daily_note()

        assert result == "Today's note."
        call_args = mock_client.list_notes.call_args
        assert call_args.kwargs.get("q") == expected_stem or call_args.args[0] == expected_stem

    def test_specific_date_constructs_correct_stem(self):
        d = datetime.date(2026, 5, 27)
        expected_stem = self._stem_for(d)

        mock_client = MagicMock()
        mock_client.list_notes.return_value = [
            {"id": "daily-2", "title": expected_stem},
        ]
        mock_client.get_note.return_value = {"id": "daily-2", "title": expected_stem, "content": "May 27 note."}

        with _patch_client(mock_client):
            result = get_daily_note("2026-05-27")

        assert result == "May 27 note."
        call_args = mock_client.list_notes.call_args
        q_used = call_args.kwargs.get("q") or (call_args.args[0] if call_args.args else None)
        assert q_used == expected_stem

    def test_date_not_found_returns_not_found_message(self):
        mock_client = MagicMock()
        mock_client.list_notes.return_value = []

        with _patch_client(mock_client):
            result = get_daily_note("2099-01-01")

        assert "No daily note found for 2099-01-01." == result

    def test_invalid_date_returns_format_error(self):
        mock_client = MagicMock()

        with _patch_client(mock_client):
            result = get_daily_note("not-a-date")

        assert "Invalid date format. Use YYYY-MM-DD." == result
        mock_client.list_notes.assert_not_called()


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------


class TestCreateNote:
    def test_create_note_returns_confirmation_with_id(self):
        mock_client = MagicMock()
        mock_client.create_note.return_value = {"id": "new-99", "title": "Test", "content": "content"}

        with _patch_client(mock_client):
            result = create_note("Test", "content", ["tag1"])

        assert result == "Created note 'Test' with ID new-99."
        mock_client.create_note.assert_called_once_with(
            title="Test",
            content="content",
            parent_path="/inbox",
            tags=["tag1"],
        )

    def test_create_note_error_returns_failure_message(self):
        mock_client = MagicMock()
        mock_client.create_note.side_effect = NotesClientError("quota exceeded", 429)

        with _patch_client(mock_client):
            result = create_note("Test", "content", [])

        assert result.startswith("Failed to create note:")
        assert "quota exceeded" in result
