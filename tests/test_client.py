"""Unit tests for notes.client — NotesClient against a mock HTTP transport."""

from __future__ import annotations

import json

import httpx
import pytest

from notes.client import NotesClient, NotesClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(
    *,
    status_code: int = 200,
    response_body: object = None,
) -> httpx.MockTransport:
    """Build an httpx.MockTransport that always returns the given response."""
    encoded = json.dumps(response_body or {}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            headers={"Content-Type": "application/json"},
            content=encoded,
        )

    return httpx.MockTransport(handler)


def _client_with_transport(transport: httpx.MockTransport) -> NotesClient:
    nc = NotesClient("https://vault.example.com", "test-token")
    nc._client = httpx.Client(
        base_url="https://vault.example.com",
        headers={"Authorization": "Bearer test-token"},
        transport=transport,
    )
    return nc


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------


class TestCreateNote:
    def test_sends_post_with_correct_body(self) -> None:
        captured: list[httpx.Request] = []
        note_response = {"id": "n1", "title": "My Note", "content": "Hello"}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=json.dumps(note_response).encode(),
            )

        nc = _client_with_transport(httpx.MockTransport(handler))
        result = nc.create_note("My Note", "Hello", parent_path="/inbox", tags=["daily"])

        assert len(captured) == 1
        req = captured[0]
        assert req.method == "POST"
        assert req.url.path == "/api/v1/notes"

        body = json.loads(req.content)
        assert body["title"] == "My Note"
        assert body["content"] == "Hello"
        assert body["parent_path"] == "/inbox"
        assert body["tags"] == ["daily"]

    def test_sends_authorization_header(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=json.dumps({"id": "n1"}).encode(),
            )

        nc = _client_with_transport(httpx.MockTransport(handler))
        nc.create_note("T", "C")

        assert captured[0].headers["Authorization"] == "Bearer test-token"

    def test_returns_note_dict(self) -> None:
        expected = {"id": "n1", "title": "My Note", "content": "Hello"}
        nc = _client_with_transport(_make_transport(response_body=expected))
        result = nc.create_note("My Note", "Hello")
        assert result == expected


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------


class TestListNotes:
    def test_sends_query_param(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b"[]",
            )

        nc = _client_with_transport(httpx.MockTransport(handler))
        nc.list_notes(q="test")

        req = captured[0]
        assert req.url.params["q"] == "test"

    def test_path_is_correct(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b"[]",
            )

        nc = _client_with_transport(httpx.MockTransport(handler))
        nc.list_notes()

        assert captured[0].url.path == "/api/v1/notes"


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------


class TestGetNote:
    def test_sends_get_to_correct_url(self) -> None:
        captured: list[httpx.Request] = []
        note = {"id": "abc-123", "title": "Test"}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=json.dumps(note).encode(),
            )

        nc = _client_with_transport(httpx.MockTransport(handler))
        result = nc.get_note("abc-123")

        req = captured[0]
        assert req.method == "GET"
        assert req.url.path == "/api/v1/notes/abc-123"
        assert result == note


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500])
    def test_non_200_raises_notes_client_error(self, status_code: int) -> None:
        transport = _make_transport(status_code=status_code, response_body={"error": "bad"})
        nc = _client_with_transport(transport)

        with pytest.raises(NotesClientError) as exc_info:
            nc.get_note("any-id")

        assert exc_info.value.status_code == status_code

    def test_error_message_contains_status_code(self) -> None:
        transport = _make_transport(status_code=404, response_body={"detail": "not found"})
        nc = _client_with_transport(transport)

        with pytest.raises(NotesClientError) as exc_info:
            nc.get_note("missing")

        assert "404" in str(exc_info.value)
