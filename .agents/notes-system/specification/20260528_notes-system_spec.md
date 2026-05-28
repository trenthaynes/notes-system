# Notes System — Requirements

**Date:** 2026-05-28
**Status:** Draft — pending user approval before planning phase

---

## Problem

Obsidian is no longer approved for the work environment. ~657 existing markdown notes (482 daily journal entries + project, area, resource, and reference notes in a PARA-like structure) need a new home with:

- A preserved daily-note creation workflow (Journal, Tasks, Carry-Over are the essential parts)
- Access from both the work machine and the home machine without concurrent-access complexity
- Semantic search and AI-powered recall over the full note corpus
- A long-term memory layer for Claude Code and other AI agent sessions (MCP)

---

## What We're Building

A self-hosted personal knowledge management system with four components:

1. **PiperVault** — the core engine (web UI, local embeddings, RAG search, original file storage)
2. **`notes` CLI** — daily note creation, standalone note creation, template rendering, and task carry-over
3. **MCP server** — exposes notes and semantic search to Claude Code and other agents
4. **Migration script** — one-time import of the existing Obsidian vault

---

## Users and Access Model

- **Single user** — no multi-tenancy, no auth beyond basic access control
- **Two machines:** work MacBook (primary) + home machine (secondary)
- **One server:** Unraid home server (always on), hosts PiperVault and MCP server
- Both machines access the server over Tailscale or local network — no file sync or git sync needed
- Concurrent access between machines is not a hard requirement (occasional is fine)

---

## Core Requirements

### Daily Note Creation

The `notes today` command (run on either machine via the CLI or via the web UI) must:

1. Determine today's filename in the format: `YYYY-MM-DD Week WW Day DDD - dddd.md`
   - Example: `2026-05-28 Week 22 Day 148 - Thursday.md`
2. Render the note with:
   - **Journal section** with an empty bullet
   - **Tasks section** with two empty task lines
   - **Carry-Over block** — scan yesterday's note for incomplete `- [ ]` items under the `### Tasks:` heading and carry them forward (skip blank placeholder tasks)
3. Store the rendered note in PiperVault (which preserves the original markdown)
4. Open the note for editing (either in the PiperVault web editor or by opening the local file in VS Code — user preference at run time)

If today's note already exists, open it without recreating it.

### Standalone Note Creation

The `notes new "<title>"` command creates a focused note on a specific topic:

1. Create a new markdown file titled and named from the provided title
2. Apply a minimal template: YAML frontmatter (title, creation date, tags) + blank body
3. Store in PiperVault under the inbox folder (user organizes to the appropriate PARA folder later)
4. Open the note for editing (same editor preference as `notes today`)

Standalone notes are expected to be linked from a daily note entry (e.g., a journal bullet or task that references the note). The `notes new` command does not enforce this — it is a convention, not a constraint.

The CLI should also support `notes open "<title or partial title>"` to quickly reopen an existing standalone note without searching the web UI.

### Note Preservation

- PiperVault stores the **original markdown content** of every note, not just extracted/indexed text
- Notes must be **retrievable in full** on demand (via web UI or API)
- The source markdown format (YAML frontmatter, wiki-link syntax, task syntax) must be preserved as stored

### Vault Migration

- One-time import of all `~/obsidian/trent/` markdown files into PiperVault
- Preserve folder structure as note metadata (tags or folder path)
- Obsidian-specific syntax that won't render (e.g., `![[...base.base]]` embeds) can remain in the stored markdown as inert text — no transformation required
- Migration should be idempotent (safe to re-run)

### Semantic Search

- Semantic (vector) search across all notes via the PiperVault web UI
- Fully local embeddings — no data leaves the server (ONNX model bundled in PiperVault)
- RAG chat using the Anthropic Claude API (internet call is acceptable for LLM inference; embeddings remain local)

### MCP Integration

An MCP server running on Unraid exposes at minimum:

| Tool | Description |
| --- | --- |
| `search_notes` | Semantic search over the full note corpus, returns matching excerpts with note title and date |
| `get_note` | Retrieve a specific note by title or date |
| `create_note` | Create a new note (for agent-driven capture) |
| `get_daily_note` | Retrieve today's (or a given date's) daily note |

The MCP server connects to PiperVault's API — it is a thin adapter, not a separate data store.

### Multi-Machine Access

- PiperVault web UI accessible from both machines via Tailscale or local network
- `notes` CLI configurable with a server URL so it can run on either machine against the same Unraid instance
- Traefik (already running on Unraid) handles reverse proxying and TLS

---

## Planned Later (Not In Scope Now)

- **Mobile capture** — PiperVault's web UI is responsive and will be reachable over Tailscale, so basic mobile access may work without additional work. A dedicated mobile-optimized "quick capture" flow (inbox note from phone) is a future phase. The deployment should not block this: ensure PiperVault is accessible on port 443 via Traefik with a valid TLS cert.
- **Voice memo ingestion** — capturing audio on the go and transcribing to a note; defer until mobile capture workflow is established.
- **Graph view** — PiperVault's wiki-link tracking covers backlinks; a full visual graph is a nice-to-have for later.

## Out of Scope

- **No concurrent editing** — not needed; single user accessing from one machine at a time
- **No Obsidian plugin compatibility** — Templater macros, Bases embeds, and Excalibrain graph are not replicated; carry-over logic is reimplemented in the CLI
- **No public sharing** — self-hosted, private

---

## Template Elements: Priority

| Element | Priority | Notes |
| --- | --- | --- |
| Journal section | Must have | Empty bullet, free-form |
| Tasks section | Must have | Checkboxes |
| Carry-Over of incomplete tasks | Must have | Scan previous day's Tasks section |
| Filename format (long form) | Must have | Existing notes use this format; must stay consistent |
| YAML frontmatter | Should have | Tags, title, creation date — useful for search faceting |
| Prev/next day nav links | Nice to have | Obsidian wiki-link syntax; may not render in PiperVault |
| Habit tracking checkboxes | Nice to have | Workout, meditate |
| Bases embeds (`![[...base.base]]`) | Defer | Obsidian-specific; stored as inert text |

---

## Dependencies and Assumptions

- Unraid server is accessible from the work machine over Tailscale or VPN at a stable address
- Traefik is already deployed on Unraid and can be configured to route to PiperVault
- The Anthropic API key is available on the Unraid server for RAG queries
- PiperVault's REST API is sufficient for the MCP adapter (to be confirmed during planning)
- `notes` CLI will be installed on the work machine; home-machine access primarily via web UI

---

## Success Criteria

1. `notes today` creates and opens a correctly rendered daily note in under 3 seconds
2. Carry-over from yesterday works correctly, including nested task indentation
3. `notes new "<title>"` creates a new inbox note and opens it for editing in under 3 seconds
4. All 657 existing notes are searchable in PiperVault after migration
5. A Claude Code session can retrieve today's daily note via the MCP `get_daily_note` tool
6. PiperVault web UI is accessible from both work and home machines
7. Original markdown is retrievable verbatim for any note
