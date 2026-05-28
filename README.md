# notes-system

A self-hosted personal knowledge management system built to replace Obsidian. It preserves a daily-note workflow, stores everything in a searchable database, and exposes your notes as long-term memory for AI agent sessions.

## What it is

Four components, two environments:

**On your Unraid home server:**
- **PiperVault** — the storage and search engine. Stores every note as original markdown, generates local vector embeddings (no data leaves the server for search), and provides a web UI accessible from any machine on your network or via Tailscale.
- **notes-mcp** — an MCP server that exposes your notes to Claude Code and other AI agents. Wraps PiperVault's REST API and provides four tools: `search_notes`, `get_note`, `get_daily_note`, and `create_note`.

**On your work machine (and optionally other machines):**
- **`notes` CLI** — creates daily notes and standalone notes from the terminal, syncs them to PiperVault, and opens them in your editor.

**In this repo (run once):**
- **`migration/migrate.py`** — imports your existing Obsidian vault into PiperVault.

## Design

Notes are written locally first. The `notes` CLI creates a markdown file on disk, stores it in PiperVault, and embeds PiperVault's note ID in the file's YAML frontmatter as `piper_vault_id`. Later edits are synced back to PiperVault with `notes push`. This means:

- VS Code (or any text editor) remains the editing surface.
- The local file is the working copy; PiperVault is the index and search backend.
- If you ever need to export or back up raw notes, the local files are always there.

PiperVault stores the original markdown verbatim — it does not transform or extract text-only content. You can retrieve any note's full content at any time via the web UI or API.

```
Work MacBook
  notes CLI ──creates──► ~/.notes/journal/2026-05-28 Week 22 Day 148 - Thursday.md
             ──REST──────► Unraid: PiperVault  ◄──REST── notes-mcp ◄── Claude Code
                                  │
                            PostgreSQL + ONNX embeddings (local)
                                  │
                            AskSage API (RAG chat only)
```

The MCP server accesses PiperVault over the internal Docker network, so agent queries never leave your server. Only PiperVault's RAG chat feature calls the AskSage API — search and retrieval are fully local.

## Daily note workflow

Running `notes today` on your work machine:

1. Computes today's filename (`2026-05-28 Week 22 Day 148 - Thursday.md`).
2. Finds the most recent prior daily note — local file first, PiperVault API fallback — and extracts incomplete `- [ ]` tasks from the `### Tasks:` section.
3. Renders a new note with `### Journal:`, `### Tasks:`, and a `**Carried over:**` block containing those tasks.
4. Creates the note in PiperVault (receives a UUID back).
5. Writes the note to `~/.notes/journal/<filename>.md` with `piper_vault_id: <uuid>` in the frontmatter.
6. Opens the file in VS Code.

If you run `notes today` again later the same day, it detects the local file and just opens it — no duplicate is created.

## Commands

```
notes today           Create or open today's daily note
notes today --web     Print the PiperVault URL instead of opening locally
notes new "Title"     Create a standalone note in the inbox folder
notes open "partial"  Open an existing note by partial title match
notes push            Sync all local notes back to PiperVault
notes push --dry-run  Show what would be pushed without sending anything
```

## External dependencies

| Dependency | Role | Required for |
| --- | --- | --- |
| **PiperVault** | Storage, embeddings, search, web UI | Everything |
| **Docker + Compose** | Runs PiperVault and notes-mcp on Unraid | Server deployment |
| **Traefik** | Reverse proxy + TLS for both services | HTTPS access |
| **AskSage** | LLM for PiperVault's RAG chat | Chat feature only — not search |
| **Tailscale** (or VPN) | Access from work machine to home server | Multi-machine access |
| **Python 3.11+** | Runs the `notes` CLI and notes-mcp | CLI install |
| **uv** | Python package manager | CLI install |

The AskSage token is used only by PiperVault's chat feature. Semantic search and embeddings run entirely locally inside the Docker container using an ONNX model (all-MiniLM-L6-v2, 384 dimensions). You can use PiperVault for search and note retrieval without an AskSage token — RAG chat will simply not work. PiperVault also supports Anthropic, OpenAI, and Ollama as alternative LLM providers if you ever switch.

## Repository layout

```
deployment/        Docker Compose config for Unraid + Traefik
migration/         One-time Obsidian vault import script
src/notes/         Python package (CLI + MCP server)
  cli.py           Typer app: today, new, open, push commands
  server.py        FastMCP app: search_notes, get_note, get_daily_note, create_note
  core.py          Pure functions: filename generation, carry-over parsing, rendering
  client.py        PiperVault REST client (httpx)
  config.py        Config loader (~/.config/notes/config.toml)
tests/             Pytest suite (77 tests)
Dockerfile.mcp     Container image for notes-mcp
pyproject.toml     Package definition and entry points
uv.lock            Locked dependencies
```

## Getting started

1. **Deploy PiperVault and notes-mcp on Unraid** — see `deployment/README.md`
2. **Import your existing vault** — see `migration/README.md`
3. **Install the CLI on your work machine:**

   ```sh
   cd /path/to/notes-system
   uv tool install .
   ```

4. **Create the CLI config file** at `~/.config/notes/config.toml`:

   ```toml
   [server]
   url = "https://vault.yourdomain.com"
   api_token = "the-token-you-created-in-pipervault"

   [local]
   notes_dir = "~/.notes"
   editor = "code"
   ```

5. **Add the MCP server to Claude Code** by adding an entry to `~/.claude/settings.json`:

   ```json
   {
     "mcpServers": {
       "notes": {
         "type": "url",
         "url": "https://mcp.yourdomain.com/mcp"
       }
     }
   }
   ```

6. **Run your first daily note:**

   ```sh
   notes today
   ```

## Syncing notes back to PiperVault

Edit notes in VS Code normally. When you want PiperVault's index to reflect your edits (for search and MCP recall), run:

```sh
notes push
```

This walks `~/.notes/` recursively, finds every `.md` file that has a `piper_vault_id` in its frontmatter, and PATCHes it to PiperVault. Files without a `piper_vault_id` are skipped with a warning — they were not created through the CLI.

## Backing up your data

PiperVault stores all notes in a named Docker volume (`pgdata`). Back this up before updating the PiperVault Docker image. On Unraid, use Unraid's built-in backup tooling or a plugin like CA Backup / Restore Appdata to snapshot the volume.

The local `~/.notes/` directory is also a complete copy of every note you have created through the CLI. Notes migrated from Obsidian live in PiperVault only unless you also pull them locally with `notes open`.
