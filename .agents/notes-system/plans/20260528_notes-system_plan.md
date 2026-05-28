---
title: "feat: Self-hosted notes system (PiperVault + CLI + MCP)"
type: feat
status: completed
date: 2026-05-28
origin: .agents/notes-system/specification/20260528_notes-system_spec.md
---

<!-- markdownlint-disable-next-line MD025 -->
# feat: Self-hosted notes system (PiperVault + CLI + MCP)

## Overview

Build a self-hosted personal knowledge management system to replace Obsidian. The system has four components deployed across two environments:

- **Unraid home server**: PiperVault (core engine — web UI, local embeddings, RAG, storage) and an MCP server (agent memory layer)
- **Work MacBook**: `notes` CLI (daily note creation, standalone notes, local sync)

All notes are written locally first, stored in PiperVault for search and MCP recall, and accessible from any machine via the PiperVault web UI over Tailscale.

---

## Problem Frame

Obsidian is no longer approved for the work environment. 657 existing notes (482 daily journal entries + PARA-structured project/area/resource/reference notes) need a replacement that preserves the daily-note creation workflow, enables semantic search, and serves as long-term memory for Claude Code sessions. (see origin: `.agents/notes-system/specification/20260528_notes-system_spec.md`)

---

## Requirements Trace

- R1. Daily note creation: `notes today` renders Journal, Tasks, and Carry-Over sections from yesterday's incomplete tasks, in under 3 seconds
- R2. Standalone note creation: `notes new "<title>"` creates an inbox note in under 3 seconds
- R3. Note preservation: original markdown is retrievable verbatim on demand
- R4. Vault migration: all 657 existing notes ingested into PiperVault and searchable
- R5. Semantic search: vector search across all notes via PiperVault web UI, local embeddings, no data egress
- R6. MCP integration: `search_notes`, `get_note`, `get_daily_note`, `create_note` tools accessible from Claude Code
- R7. Multi-machine access: PiperVault web UI reachable from both work MacBook and home machine over Tailscale
- R8. Original markdown retrievable verbatim for any note

---

## Scope Boundaries

- **No concurrent editing** — single user, one machine at a time
- **No Obsidian plugin compatibility** — Templater, Excalibrain, Bases not replicated; carry-over logic reimplemented in Python
- **No public sharing** — self-hosted, private

### Planned Later (not in scope now)

- **Mobile quick capture** — PiperVault web UI is responsive and will be reachable over Tailscale; a dedicated capture flow is a future phase. Deployment must not block this: TLS via Traefik is required.
- **Voice memo ingestion** — deferred until mobile capture is established
- **Graph view** — PiperVault's built-in wiki-link tracking is sufficient; visual graph is deferred

---

## Context & Research

### PiperVault API Surface (verified against main branch, 2026-05-28)

All endpoints are under `/api/v1`:

- `POST /notes` — create a note (`title`, `content`, `parentPath`, `tags[]`)
- `GET /notes/:id` — retrieve full note; raw markdown in the `content` field (round-trip fidelity confirmed)
- `PATCH /notes/:id` — update title, content, path, tags
- `GET /notes?q=<query>` — list/filter notes; no direct title lookup endpoint — match client-side
- `POST /search` — semantic vector search; returns **chunks** not full notes; full content requires follow-up `GET /notes/:id`
- `POST /sources/bulk-import` — multi-file ingestion for non-note documents
- `GET /health` — health check

**Note data model:** `id` (UUID), `title`, `content` (raw markdown), `frontmatter` (parsed YAML), `parentPath` (folder hierarchy as string, e.g. `/journal`), `tags` (flat string array), `isNote: true`, `createdAt`, `updatedAt`.

**No direct title lookup:** `GET /notes?q=<title>` returns a list filtered by query — the caller must match client-side on title. For daily notes (predictable filename) this is deterministic.

**Search returns chunks:** `POST /search` returns `ChunkSearchResult[]` with `chunk.content`, `score`, and `source.id`. To get the full note from a search result: `GET /notes/:source.id`.

### Deployment

PiperVault ships as a single Docker container (`pipervault/piper-vault:latest`) bundling PostgreSQL 16, NestJS API, ONNX embedding model (all-MiniLM-L6-v2, 384-dim), and Nginx. One port (8080) exposed. Volume mounts: `pgdata:/var/lib/postgresql/data`, `config:/root/.delve`, `watched:/app/watched`. Memory limit: 2 GB.

**Authentication:** `AUTH_ENABLED` defaults to `false`. Set to `true` with a strong `JWT_SECRET` for any externally-reachable deployment.

**Traefik:** No official support; standard Docker provider labels on port 8080 work without modification.

**MCP:** PiperVault's `.mcp.json` is empty — MCP is a future roadmap item. We build our own adapter.

### Python Tooling

- **Python version:** 3.11+ required (`tomllib` is stdlib from 3.11)
- **Environment manager:** `uv` — handles virtual environments, lockfiles, and Python version pinning in one tool; used by the MCP SDK docs throughout
- **CLI framework:** Typer (built on Click, type-hint driven, `no_args_is_help=True`)
- **HTTP client:** httpx (sync, for CLI and MCP server's PiperVault calls)
- **MCP server:** `mcp` package v1.27.1; `FastMCP` with `@mcp.tool()` decorator; streamable-http transport for network-accessible server
- **Config:** `tomllib` (stdlib) reading `~/.config/notes/config.toml`
- **Entry points:** both `notes` (CLI) and `notes-mcp` (server) declared in `pyproject.toml [project.scripts]`

### Relevant Patterns

- Existing daily note filenames: `YYYY-MM-DD Week WW Day DDD - dddd.md` (e.g. `2026-05-28 Week 22 Day 148 - Thursday.md`); use `datetime.isocalendar()` for week number, `timetuple().tm_yday` for day-of-year
- Carry-over JavaScript logic (Templater): scan lines for `^#{1,6}\s+Tasks` heading, collect `- [ ]` lines that are not blank placeholders, stop at next heading — reproduce in Python
- Existing vault structure: `05 journal/` → parentPath `/journal`, `01 inbox/` → `/inbox`, `02 projects/` → `/projects`, `03 areas/` → `/areas`, `04 resources/` → `/resources`, `06 input/` → `/input`, `07 output/` → `/output`, `zettelkasten/` → `/zettelkasten`

---

## Key Technical Decisions

- **`uv` as the Python toolchain.** `uv tool install .` installs both `notes` and `notes-mcp` as globally available commands on the work machine. `uv.lock` is committed for reproducible installs. The `Dockerfile.mcp` uses `uv pip install` for consistency. This matches the MCP SDK's own documentation and avoids the `pip` + `venv` two-step.
- **Local file is the editing surface.** `notes today` writes a local `.md` file to a configured notes directory and opens it in the user's editor. PiperVault receives the note at creation time and again on `notes push`. This avoids a background daemon and keeps VS Code as the primary editing experience.
- **Note ID in YAML frontmatter.** When a note is created in PiperVault, its UUID is written into the local file's frontmatter as `piper_vault_id`. `notes push` reads this field to PATCH the correct note without a lookup.
- **Single Python package, two executables.** The CLI (`notes`) and MCP server (`notes-mcp`) share `core.py`, `client.py`, and `config.py`. No duplication of business logic. Both declared in `pyproject.toml [project.scripts]`.
- **MCP transport: streamable-http.** The MCP server runs on Unraid and is accessed over the network. Stdio is only appropriate for local subprocess invocation; streamable-http is correct for a remote, always-on server.
- **Migration via API, not watched folder.** Using `POST /api/v1/notes` per file creates proper notes with `isNote: true`, enabling wiki-link tracking and backlinks. State tracked in `migration/state.json` (filename → note ID) for idempotency.
- **Carry-over searches backward up to 7 days.** If yesterday has no note (weekend, holiday), the CLI walks back to find the most recent daily note. This avoids empty carry-over on Monday mornings.
- **PiperVault auth enabled from day one.** The Unraid deployment sets `AUTH_ENABLED=true` and a strong `JWT_SECRET`. The `notes` CLI and MCP server use a configured API token. This ensures the TLS+auth posture required for future mobile access is in place from the start.

---

## Open Questions

### Resolved During Planning

- **MCP transport choice:** streamable-http (not stdio) — server runs on Unraid, accessed over network
- **Python toolchain:** `uv` — install with `uv tool install .`; lockfile committed as `uv.lock`
- **Editor invocation:** `subprocess.Popen([editor_cmd, str(local_path)])` where `editor_cmd` defaults to `code`; configurable in `~/.config/notes/config.toml`
- **Carry-over source:** local file first, then PiperVault API; avoids API call when note is already local
- **Search returns chunks not notes:** `get_note` and `get_daily_note` MCP tools use `GET /notes?q=` (list endpoint) for title-based lookup, not the search endpoint; search endpoint is used for `search_notes` only
- **Folder mapping for migration:** hard-coded map of Obsidian folder names to PiperVault `parentPath` values (see Relevant Patterns above); unknown folders default to `/inbox`

### Deferred to Implementation

- **PiperVault API key format:** whether `AUTH_ENABLED=true` uses Bearer token or another header format — confirm from PiperVault docs or source during U1 deployment
- **`notes open` when multiple matches:** exact disambiguation UX (numbered list, fuzzy select) — implement using `typer.prompt` or `questionary` depending on what's already in the dependency tree
- **`notes push` change detection:** simple mtime comparison vs always-PATCH — implement always-PATCH first and add mtime optimization only if it proves slow in practice

---

## Output Structure

    notes-system/
    ├── deployment/
    │   ├── docker-compose.yml        # PiperVault + MCP server services
    │   └── .env.example              # Required env vars with descriptions
    ├── migration/
    │   ├── migrate.py                # Bulk import script (standalone, not part of the package)
    │   ├── requirements.txt          # httpx, python-frontmatter
    │   └── state.json.example        # Documents the state file format
    ├── src/
    │   └── notes/
    │       ├── __init__.py
    │       ├── cli.py                # Typer app, registers all subcommands
    │       ├── server.py             # FastMCP server, registers all tools
    │       ├── core.py               # Filename logic, template rendering, carry-over parsing
    │       ├── client.py             # PiperVault REST client (httpx)
    │       └── config.py             # TOML config loading
    ├── tests/
    │   ├── test_core.py              # Unit tests for filename/template/carry-over logic
    │   ├── test_client.py            # Client tests with httpx mock
    │   └── test_mcp.py              # MCP tool tests with mocked client
    ├── pyproject.toml                # Package metadata, dependencies, both entry points
    ├── uv.lock                       # Committed lockfile for reproducible installs
    └── Dockerfile.mcp                # Container for the MCP server on Unraid

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification.*

    ┌─────────────────────────── Work MacBook ───────────────────────────────┐
    │                                                                         │
    │   notes today / new / open / push                                       │
    │        │                                                                │
    │        ▼                                                                │
    │   [notes CLI]──writes──▶ ~/.notes/{journal,inbox,...}/<filename>.md    │
    │        │                   (piper_vault_id in YAML frontmatter)        │
    │        │                                                                │
    │        └──REST──▶ (Tailscale / local network)                          │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
                                      │
                       ┌──────────────▼──────────────────┐
                       │       Unraid Home Server         │
                       │                                  │
                       │  [Traefik] ──────────────────┐  │
                       │     │                         │  │
                       │     ▼                         ▼  │
                       │  [PiperVault :8080]  [MCP Server :8000]
                       │     │ PostgreSQL+ONNX          │  │
                       │     │ (local, no egress)       │  │
                       │     └──REST◀────────────────── ┘  │
                       │     └──Anthropic API (RAG only)──▶ internet
                       └──────────────────────────────────┘
                                      ▲
                                      │ MCP protocol (streamable-http)
                               [Claude Code]

Data flow for `notes today`:

1. CLI computes today's filename + yesterday's filename
2. Checks local `~/.notes/journal/` for yesterday's file (carry-over source)
3. If missing: `GET /api/v1/notes?q=<yesterday_filename>` → client-side title match → `GET /api/v1/notes/:id` for full content
4. Parses `### Tasks:` section for incomplete `- [ ]` items (skip blank placeholders)
5. Renders today's note (Journal, Tasks, Carry-Over)
6. `POST /api/v1/notes` → receives UUID → embeds as `piper_vault_id` in frontmatter
7. Writes local file to `~/.notes/journal/<filename>.md`
8. Invokes configured editor (`code <path>`) via `Popen` (non-blocking)

---

## Implementation Units

- U1. **PiperVault deployment on Unraid**

**Goal:** PiperVault running in Docker on Unraid, accessible at a stable internal address via Traefik, with auth enabled and TLS terminated.

**Requirements:** R7

**Dependencies:** None (prerequisite for all other units)

**Files:**

- Create: `deployment/docker-compose.yml`
- Create: `deployment/.env.example`

**Approach:**

- Use the single-container image `pipervault/piper-vault:latest`
- Mount four named volumes: `pgdata`, `config`, `plugins`, `watched`
- Add standard Traefik Docker provider labels for the configured domain and `websecure` entrypoint with a Let's Encrypt cert resolver
- Set `AUTH_ENABLED=true`, `JWT_SECRET` (from `.env`), `ANTHROPIC_API_KEY` (from `.env`), `CORS_ORIGIN` matching the Traefik domain
- Cap memory at 2 GB (PiperVault recommendation)
- Document in `.env.example`: all required variables, their purpose, and whether they have defaults

**Test scenarios:**

- Happy path: `GET /api/v1/health` returns 200 from work machine over Tailscale
- Auth: unauthenticated `GET /api/v1/notes` returns 401
- Web UI: browser navigates to the configured domain and renders the PiperVault UI

**Verification:** PiperVault web UI loads from work machine browser; API health check passes; unauthenticated requests are rejected.

---

- U2. **Vault migration script**

**Goal:** All 657 notes from `~/obsidian/trent/` ingested into PiperVault as notes (not sources), preserving folder structure as `parentPath` and YAML frontmatter tags. Idempotent.

**Requirements:** R4, R8

**Dependencies:** U1

**Files:**

- Create: `migration/migrate.py`
- Create: `migration/requirements.txt`
- Create: `migration/state.json.example`

**Approach:**

- Walk the vault directory recursively; skip `.obsidian/`, `.notecompanion/`, `_assets/`, `_bases/`
- For each `.md` file: parse YAML frontmatter with `python-frontmatter`, map folder path to `parentPath` using the known Obsidian-to-PiperVault folder map (e.g. `05 journal` → `/journal`)
- Call `POST /api/v1/notes` with `title` (filename without extension), `content` (full raw markdown), `tags` (from frontmatter + folder-derived tag), `parentPath`
- Persist returned UUID to `migration/state.json` as `{relative_path: note_uuid}`; on re-run, skip files already in state (idempotency)
- Print progress: files processed, skipped (already migrated), errors
- Unknown folder paths default to `/inbox` with a warning printed
- Obsidian-specific syntax (`![[...base.base]]`, `[[wikilinks]]`) left in the markdown as-is — no transformation

**Test scenarios:**

- Happy path: single `.md` file POSTed, UUID recorded in `state.json`
- Idempotency: re-running skips already-migrated files (no duplicates)
- Folder mapping: `05 journal/2026-05-28...md` gets `parentPath=/journal`
- Frontmatter tags: `tags: ["#daily_note"]` from frontmatter carried to PiperVault tags
- Unknown folder: falls back to `/inbox`, prints warning
- Error handling: API failure on one file logs the error and continues (no abort)

**Verification:** After migration, `GET /api/v1/notes?limit=100` returns at least 657 notes; spot-check 5 notes across different folders for correct `parentPath` and `content` fidelity; semantic search for a known term from the vault returns relevant results.

---

- U3. **`notes` package foundation (config, client, core logic)**

**Goal:** An installable Python package providing shared infrastructure: config loading, PiperVault REST client, and the core business logic (filename generation, template rendering, carry-over parsing).

**Requirements:** R1, R2, R3 (prerequisite logic)

**Dependencies:** U1 (server must be running for client integration tests)

**Files:**

- Create: `pyproject.toml`
- Create: `uv.lock` (generated, committed)
- Create: `src/notes/__init__.py`
- Create: `src/notes/config.py`
- Create: `src/notes/client.py`
- Create: `src/notes/core.py`
- Create: `src/notes/cli.py` (Typer app skeleton, no commands yet)
- Create: `src/notes/server.py` (FastMCP skeleton, no tools yet)
- Test: `tests/test_core.py`
- Test: `tests/test_client.py`

**Approach:**

- `pyproject.toml`: `requires-python = ">=3.11"`; dependencies: `typer`, `httpx`, `mcp`, `python-frontmatter`; `[project.scripts]`: `notes = "notes.cli:app"` and `notes-mcp = "notes.server:main"`
- `config.py`: load `~/.config/notes/config.toml` using `tomllib`; required keys: `server.url`, `server.api_token`; optional: `local.notes_dir` (default `~/.notes`), `local.editor` (default `code`)
- `client.py`: `NotesClient(base_url, api_token)` wrapping `httpx.Client`; methods: `create_note`, `get_note`, `list_notes`, `update_note`, `search` — each raises `NotesClientError` on non-200 response
- `core.py` functions:
  - `get_daily_filename(date)` → e.g. `2026-05-28 Week 22 Day 148 - Thursday.md`; use `date.isocalendar()` for week number (ISO 8601, zero-padded to 2 digits), `date.timetuple().tm_yday` for day-of-year
  - `find_incomplete_tasks(content)` → list of strings; scan for `^#{1,6}\s+Tasks` heading, collect `- [ ]` lines that are not blank, stop at next heading; preserve leading whitespace for nested sub-tasks
  - `render_daily_note(carryover_tasks, date)` → rendered markdown string with Journal, Tasks, Carry-Over sections and YAML frontmatter
  - `find_most_recent_daily_note(notes_dir, from_date)` → Path or None; walk back up to 7 days

**Patterns to follow:**

- `tomllib` stdlib pattern (Python 3.11+)
- httpx sync client with `with` context manager

**Test scenarios:**

- `get_daily_filename`: correct week number, day-of-year, weekday name for 2026-05-28 → "Week 22, Day 148, Thursday"
- `get_daily_filename`: ISO week boundary — 2027-01-01 is in Week 52 of 2026, not Week 1 of 2027
- `find_incomplete_tasks`: returns only tasks under `### Tasks:` heading
- `find_incomplete_tasks`: skips blank `- [ ]` placeholder lines with no text after the checkbox
- `find_incomplete_tasks`: stops at the next heading after the Tasks section
- `find_incomplete_tasks`: preserves two-space-indented sub-task lines (nested tasks)
- `find_incomplete_tasks`: returns empty list when Tasks section is absent
- `find_incomplete_tasks`: returns empty list when all tasks are blank placeholders
- `render_daily_note`: output contains `### Journal:`, `### Tasks:`, `**Carried over:**` sections
- `render_daily_note`: `piper_vault_id` is empty string in frontmatter (filled in after API call)
- Client: `create_note` sends correct JSON body and returns note dict
- Client: `list_notes(q=...)` passes query param correctly
- Client: non-200 response raises `NotesClientError`

**Verification:** `uv run pytest tests/test_core.py` passes; `uv tool install .` makes `notes --help` available system-wide.

---

- U4. **`notes today` command**

**Goal:** `notes today` creates today's daily note (with carry-over from the most recent prior note), writes it locally, stores it in PiperVault, and opens it in the configured editor. Idempotent.

**Requirements:** R1, R3 (success criteria 1, 2)

**Dependencies:** U3

**Files:**

- Modify: `src/notes/cli.py` (add `today` command)
- Test: `tests/test_today.py`

**Approach:**

1. Compute today's filename via `get_daily_filename(today)`
2. Compute local path: `<notes_dir>/journal/<filename>.md`
3. If local file exists: open in editor and exit (idempotent)
4. Find carry-over source: `find_most_recent_daily_note(notes_dir, today - 1 day)` (up to 7 days back)
5. If found locally: read and parse; if not found locally: `GET /notes?q=<prior_filename>` → title match → `GET /notes/:id` for content
6. Call `find_incomplete_tasks(prior_content)` → carry-over list
7. Call `render_daily_note(carryover_tasks, today)` → note content string
8. `client.create_note(...)` → note dict with `id`; embed UUID as `piper_vault_id` in frontmatter
9. Write rendered content (with `piper_vault_id`) to local path
10. `subprocess.Popen([config.editor, str(local_path)])` — non-blocking, terminal returns immediately

**Test scenarios:**

- Happy path: creates local file with correct filename and Journal/Tasks sections, opens editor
- Carry-over: yesterday's incomplete task appears in `**Carried over:**` block
- Carry-over: blank `- [ ]` placeholder lines are not carried over
- Carry-over: two-space-indented sub-tasks are preserved with their indentation
- Idempotency: if local file already exists for today, opens it without calling the API
- No prior note found: note is created without carry-over block (no error, no crash)
- Weekend gap: Friday's tasks are carried over on Monday (7-day lookback)
- API failure on create: clear error message, no local file written, editor not opened
- `piper_vault_id` is present in the local file's YAML frontmatter after creation

**Verification:** Running `notes today` on a machine with the vault migrated creates the note in under 3 seconds; local file contains correct carry-over from the most recent daily note.

---

- U5. **`notes new` and `notes open` commands**

**Goal:** `notes new "<title>"` creates a titled note in the inbox and opens it for editing. `notes open "<partial>"` reopens an existing note by fuzzy title match.

**Requirements:** R2 (success criteria 3)

**Dependencies:** U3

**Files:**

- Modify: `src/notes/cli.py` (add `new` and `open_` commands)
- Test: `tests/test_commands.py`

**Approach:**

`notes new "<title>"`:

1. Derive filename from title (lowercase, spaces to hyphens, strip special chars)
2. Render minimal template: YAML frontmatter (`title`, `creation date`, `tags: []`, `piper_vault_id: ""`) + blank body
3. `client.create_note(title=title, content=..., parent_path="/inbox")` → note dict
4. Embed returned UUID as `piper_vault_id` in frontmatter; write to `<notes_dir>/inbox/<filename>.md`
5. Open in editor

`notes open "<partial>"`:

1. Search local `<notes_dir>` recursively for `.md` files whose filename contains the query (case-insensitive substring)
2. Exactly one match: open in editor
3. Multiple matches: print numbered list, prompt user to select
4. No local match: `client.list_notes(q=partial, limit=10)` → user selects → `client.get_note(id)` → write local copy with `piper_vault_id` → open in editor
5. No match anywhere: suggest `notes new "<partial>"`, exit non-zero

**Test scenarios:**

- `new`: file created at `inbox/<slug>.md` with correct YAML frontmatter
- `new`: title with spaces slugified correctly (`"My New Note"` → `my-new-note.md`)
- `new`: `piper_vault_id` present in frontmatter after creation
- `open` — single local match: opens correct file
- `open` — multiple local matches: numbered list printed (assert on stdout, not editor invocation)
- `open` — no local match, API match found: note content pulled and written to local dir
- `open` — no match anywhere: exits with non-zero code and helpful message

**Verification:** `notes new "Test Note"` creates `inbox/test-note.md` in under 3 seconds with `piper_vault_id` in frontmatter.

---

- U6. **`notes push` sync command**

**Goal:** `notes push` syncs locally modified notes back to PiperVault by PATCHing their content using the stored `piper_vault_id`.

**Requirements:** R3 (note preservation — keeps PiperVault current after local editing)

**Dependencies:** U3, U4, U5

**Files:**

- Modify: `src/notes/cli.py` (add `push` command)
- Test: `tests/test_push.py`

**Approach:**

1. Walk all `.md` files in `<notes_dir>` recursively
2. For each file: parse YAML frontmatter; if `piper_vault_id` absent or empty, warn and skip
3. Call `client.update_note(note_id, content=full_file_content)` for each file with a valid ID
4. Print a summary: N updated, M skipped, K errors
5. `--dry-run` flag shows what would be pushed without sending requests

Implementation note: always-PATCH for simplicity (no mtime comparison); add `last_synced_at` frontmatter field as an optimization in a follow-up if latency becomes a problem.

**Test scenarios:**

- Happy path: file with `piper_vault_id` is PATCHed; summary reports 1 updated
- Missing ID: file without `piper_vault_id` is skipped with a warning
- `--dry-run`: shows files that would be pushed, sends no requests
- API failure on one file: error logged, other files still processed, exit code non-zero
- Empty notes dir: reports 0 updated, exits 0

**Verification:** After editing a local daily note and running `notes push`, `GET /api/v1/notes/:id` from PiperVault returns the updated content.

---

- U7. **MCP server (FastMCP) and Unraid deployment**

**Goal:** A FastMCP server running on Unraid exposes four tools to Claude Code: `search_notes`, `get_note`, `get_daily_note`, `create_note`. Deployed as a Docker container alongside PiperVault.

**Requirements:** R6 (success criteria 5)

**Dependencies:** U1, U3

**Files:**

- Modify: `src/notes/server.py` (implement all four tools)
- Create: `Dockerfile.mcp`
- Modify: `deployment/docker-compose.yml` (add `notes-mcp` service)
- Test: `tests/test_mcp.py`

**Approach:**

Server setup:

- `FastMCP("notes-mcp")` with `transport="streamable-http"`, `host="0.0.0.0"`, `port=8000`
- `NotesClient` initialized from environment variables (`PIPERVAULT_URL`, `PIPERVAULT_API_TOKEN`)
- Traefik labels on port 8000 in `docker-compose.yml`

Tool implementations:

- `search_notes(query, top_k=5)`: `POST /search` → deduplicate by `source.id` → `GET /notes/:id` for each unique source → return formatted list of title + excerpt
- `get_note(title)`: `GET /notes?q=<title>&limit=10` → case-insensitive title match client-side → `GET /notes/:id` for full content → return raw markdown; return "No note found" if no match
- `get_daily_note(date="")`: construct expected filename via `get_daily_filename()`; `GET /notes?q=<filename>&limit=5` → title match → `GET /notes/:id`; return "No daily note found for {date}" if absent
- `create_note(title, content, tags=[])`: `POST /notes` with `parent_path="/inbox"` → return confirmation string with note ID

Docker and deployment:

- `Dockerfile.mcp`: Python 3.12 slim image; `uv pip install` the package from source; entrypoint `notes-mcp`
- `deployment/docker-compose.yml`: add `notes-mcp` service; `PIPERVAULT_URL=http://delve:8080`, `PIPERVAULT_API_TOKEN` from `.env`, Traefik labels for the MCP endpoint, `depends_on: [delve]`

Claude Code integration: user adds the MCP server URL to `~/.claude/settings.json` under `mcpServers`.

**Patterns to follow:**

- FastMCP tool signature pattern: type-annotated parameters; docstring written for the model, not a human reader

**Test scenarios:**

- `search_notes("docker deployment")`: returns at least one result with title and excerpt (mocked client)
- `search_notes` with `top_k=1`: returns exactly one deduplicated result
- `get_note("non-existent title")`: returns "No note found" string, no exception raised
- `get_note("kubernetes")`: returns markdown content of matching note
- `get_daily_note()` with today's note present: returns full markdown content
- `get_daily_note("2026-05-27")`: returns Wednesday's note content
- `get_daily_note("2099-01-01")`: returns "No daily note found" message
- `create_note("Test", "content", ["tag1"])`: returns confirmation string with note ID
- Server health: HTTP GET to the server returns 200

**Verification:** After deploying, a Claude Code session with the MCP server configured can call `get_daily_note()` and receive today's note content; `search_notes("kubernetes")` returns relevant results from the migrated vault.

---

## System-Wide Impact

- **Interaction graph:** All four components (CLI, migration script, MCP server, PiperVault) share the same REST API surface. Any breaking PiperVault API change (image upgrade) affects CLI and MCP server equally.
- **Error propagation:** PiperVault API errors surface as `NotesClientError` in `client.py`; CLI commands catch and print a human-readable message and exit non-zero; MCP tools return error strings rather than raising exceptions (the model handles a string response, not a Python traceback).
- **State lifecycle risks:** The `piper_vault_id` in local frontmatter is the sync anchor. If PiperVault volumes are lost and the service is reinstalled, all local IDs become stale. Recovery requires re-running migration and updating frontmatter IDs — document this in operational notes.
- **API surface parity:** `notes push` assumes locally written files have `piper_vault_id`. Notes created directly in the PiperVault web UI and pulled via `notes open` will have IDs; any files created manually outside the CLI will be skipped by `push` with a warning.
- **Integration coverage:** The end-to-end flow (CLI creates note → PiperVault stores it → MCP retrieves it) must be verified manually after U7 is deployed; unit tests with mocked clients cannot prove this path.
- **Unchanged invariants:** PiperVault's web UI, wiki-link tracking, backlinks, and RAG chat are used as-is. The CLI and MCP server are purely additive.

---

## Risks & Dependencies

| Risk | Mitigation |
| --- | --- |
| PiperVault API changes on image update (no versioned releases observed) | Pin the Docker image to a specific digest; review changelog before updating |
| `AUTH_ENABLED=true` JWT token format not confirmed from source | Verify during U1 deployment; fall back to `AUTH_ENABLED=false` behind Tailscale if JWT mode is complex |
| 657-file migration causes rate-limiting or memory pressure on PiperVault | Run with configurable concurrency limit (default: sequential); monitor PiperVault logs |
| Carry-over relies on PiperVault API when note is not cached locally | If API is unreachable, create note without carry-over and print a warning |
| `search_notes` MCP tool makes N+1 API calls (one search + one GET per unique source) | Cap `top_k` at 5 by default; deduplicate source IDs before fetching; acceptable at personal-use scale |
| MCP streamable-http transport under Traefik TLS termination unverified | Test MCP endpoint from Claude Code before declaring U7 complete; SSE transport is a fallback |

---

## Documentation / Operational Notes

- **First-run setup:** After U1, access PiperVault web UI to complete initial configuration (LLM model selection, collection setup) before running migration
- **CLI installation:** `uv tool install .` from repo root; installs both `notes` and `notes-mcp` globally. On a second machine: `uv tool install git+<repo-url>` or clone and re-run.
- **Config file:** `~/.config/notes/config.toml` — document all keys and defaults in a top-level `README.md`
- **Data volume backup:** PiperVault's `pgdata` volume contains all notes and embeddings; back up before any image updates via Unraid's backup tooling
- **Claude Code MCP config:** add `notes-mcp` server URL to `~/.claude/settings.json` on each machine that needs agent memory access
- **Mobile TLS:** Traefik Let's Encrypt cert resolver must be configured (not self-signed) for mobile browsers to trust the domain
- **Migration state:** preserve `migration/state.json` after the initial migration run to prevent duplicate notes if the script is re-run
