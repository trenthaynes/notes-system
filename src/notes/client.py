"""PiperVault REST client for the notes system."""

from __future__ import annotations

from typing import Any

import httpx


_API_PREFIX = "/api/v1"


class NotesClientError(Exception):
    """Raised when the PiperVault API returns a non-200 response."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class NotesClient:
    """Synchronous HTTP client for the PiperVault REST API."""

    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_token}"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{_API_PREFIX}/{path.lstrip('/')}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise NotesClientError(
                f"API error {response.status_code}: {detail}",
                status_code=response.status_code,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_note(
        self,
        title: str,
        content: str,
        parent_path: str = "/inbox",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new note and return the created note dict (with ``id``)."""
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "parent_path": parent_path,
        }
        if tags is not None:
            payload["tags"] = tags

        response = self._client.post(self._url("/notes"), json=payload)
        self._raise_for_status(response)
        return response.json()

    def get_note(self, note_id: str) -> dict[str, Any]:
        """Fetch a single note by ID."""
        response = self._client.get(self._url(f"/notes/{note_id}"))
        self._raise_for_status(response)
        return response.json()

    def list_notes(self, q: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List notes, optionally filtered by a search query."""
        params: dict[str, Any] = {"limit": limit}
        if q is not None:
            params["q"] = q

        response = self._client.get(self._url("/notes"), params=params)
        self._raise_for_status(response)
        return response.json()

    def update_note(self, note_id: str, content: str) -> dict[str, Any]:
        """Update the content of an existing note."""
        response = self._client.patch(
            self._url(f"/notes/{note_id}"),
            json={"content": content},
        )
        self._raise_for_status(response)
        return response.json()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search; returns a list of chunk result dicts."""
        response = self._client.get(
            self._url("/search"),
            params={"q": query, "top_k": top_k},
        )
        self._raise_for_status(response)
        return response.json()

    def close(self) -> None:
        self._client.close()

    # Context-manager support
    def __enter__(self) -> "NotesClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
