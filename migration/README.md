# Migration

This directory contains a one-time script for importing your existing Obsidian vault into PiperVault. Each markdown file is posted to PiperVault's API as a note, preserving the original content verbatim. Progress is tracked in `state.json` so you can interrupt and resume without creating duplicates.

Run the migration after PiperVault is deployed and you have an API token.

## What the script does

For each `.md` file in your vault:

1. Skips files in directories that contain Obsidian internals: `.obsidian`, `.notecompanion`, `_assets`, `_bases`.
2. Parses the YAML frontmatter to extract tags.
3. Maps the file's top-level folder to a PiperVault folder path (see the table below).
4. Posts the file to PiperVault using the filename (without `.md`) as the note title and the full file content as the note body — no transformation, no stripping of Obsidian-specific syntax.
5. Records the returned PiperVault note ID in `state.json` under the file's vault-relative path.

On subsequent runs, any file already in `state.json` is skipped. This makes the script safe to re-run after interruptions.

## Folder mapping

Your vault's top-level folders are mapped to PiperVault folder paths as follows:

| Obsidian folder | PiperVault path |
| --- | --- |
| `01 inbox` | `/inbox` |
| `02 projects` | `/projects` |
| `03 areas` | `/areas` |
| `04 resources` | `/resources` |
| `05 journal` | `/journal` |
| `06 input` | `/input` |
| `07 output` | `/output` |
| `zettelkasten` | `/zettelkasten` |
| `_templates` | `/templates` |
| (anything else) | `/inbox` + a warning |

For files nested more than one level deep, the sub-path is appended. For example, a file at `03 areas/work/kubernetes.md` goes to `/areas/work`.

If the script prints a warning about an unknown folder, the affected files end up in `/inbox`. You can reorganise them in PiperVault's web UI after migration, or add the folder to `FOLDER_MAP` in `migrate.py` and re-run (the script will only process files not already in `state.json`).

## Prerequisites

The migration script is standalone — it does not use the `notes` package. Install its dependencies separately using either pip or uv.

Python 3.11 or later is required.

**Using pip (inside a virtual environment):**

```sh
cd migration/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Using uv (no virtual environment needed):**

```sh
cd migration/
uv pip install --system -r requirements.txt
```

## Step 1: Dry run

Before importing anything, run the script with `--dry-run` to see what it will process and how it will map each file:

```sh
python migrate.py \
  --vault ~/obsidian/trent \
  --server https://vault.yourdomain.com \
  --token placeholder \
  --dry-run
```

In dry-run mode the `--token` is not used (no API calls are made), so a placeholder value is fine. The output looks like:

```
Found 657 markdown files in /Users/you/obsidian/trent
DRY RUN — no notes will be created

  → [1/657] Would migrate: 01 inbox/quick-capture.md → /inbox
  → [2/657] Would migrate: 02 projects/home-lab.md → /projects
  → [3/657] Would migrate: 05 journal/2026-05-28 Week 22 Day 148 - Thursday.md → /journal
  ...
  ⚠ Unknown folder 'scratchpad' → defaulting to /inbox
  → [412/657] Would migrate: scratchpad/rough-notes.md → /inbox
  ...

Migration complete: 657 migrated, 0 skipped, 0 errors
```

Review the output for:
- Folders mapped unexpectedly to `/inbox` — add them to `FOLDER_MAP` in `migrate.py` if you want them elsewhere.
- Files you do not want to import — you can delete them from the vault directory before running the real migration, or move them to a folder in `SKIP_DIRS`.

## Step 2: Run the migration

Once you are satisfied with the dry-run output, run the real migration. Replace the values with your actual server URL and API token:

```sh
python migrate.py \
  --vault ~/obsidian/trent \
  --server https://vault.yourdomain.com \
  --token pv_live_abc123...
```

The script processes files sequentially with a 0.1-second pause between API calls (configurable with `--delay`). For 657 files at the default delay, expect the migration to take about two minutes.

Output during migration:

```
Found 657 markdown files in /Users/you/obsidian/trent

  ✓ [1/657] 01 inbox/quick-capture.md → /inbox (id: a1b2c3d4-...)
  ✓ [2/657] 02 projects/home-lab.md → /projects (id: b2c3d4e5-...)
  ...

Migration complete: 657 migrated, 0 skipped, 0 errors
```

State is written to `state.json` after each successful note, not at the end. If the script is interrupted, run it again with the same arguments — already-migrated files will be skipped.

## Step 3: Verify the results

After migration, open PiperVault in your browser and check that your notes are present and correctly organised:

1. Browse the folder tree — confirm `/journal`, `/projects`, `/areas`, etc. are populated.
2. Open a daily note and verify the original markdown content is intact (including any `![[...]]` embeds and `[[wikilinks]]` — these are stored as plain text and do not need to render).
3. Run a semantic search for a term you know exists in your notes. Results should appear.

You can also check the count via the API:

```sh
curl -H "Authorization: Bearer pv_live_abc123..." \
  "https://vault.yourdomain.com/api/v1/notes?limit=1" | python3 -m json.tool
```

The response will include a total count field.

## Preserving state.json

`state.json` maps each vault-relative file path to its PiperVault note ID:

```json
{
  "05 journal/2026-05-28 Week 22 Day 148 - Thursday.md": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "02 projects/home-lab.md": "b2c3d4e5-f6a7-8901-bcde-f12345678901"
}
```

Do not delete this file after migration. If you re-run the script later (for example, to import new notes you added to the vault directory), the existing entries are skipped and only new files are imported.

`state.json` is excluded from git by the root `.gitignore`.

## Re-running for new files

If you add new `.md` files to the vault directory after the initial migration, you can import just the new files by running the script again with the same arguments. Files already in `state.json` are skipped automatically.

## Options reference

| Option | Default | Description |
| --- | --- | --- |
| `--vault PATH` | (required) | Path to the Obsidian vault root directory |
| `--server URL` | (required) | PiperVault base URL, e.g. `https://vault.yourdomain.com` |
| `--token TOKEN` | (required) | PiperVault API bearer token |
| `--state PATH` | `state.json` next to the script | Path to the state tracking file |
| `--delay SECONDS` | `0.1` | Pause between API calls; increase if you see rate-limit errors |
| `--dry-run` | off | Print what would be imported without making any API calls |

## Troubleshooting

**HTTP 401 errors**

The token is wrong or has been deleted. Create a new API token in PiperVault's **Settings → API Keys** and use it for `--token`.

**HTTP 413 or timeout errors on large files**

Some files may be very large. Try `--delay 0.5` to give PiperVault more time between requests. If a specific file consistently fails, check its size — PiperVault's upload limit is 500 MB per file, which no markdown note should approach.

**Parse error on a file**

The script logs `✗ Parse error <file>: <message>` and continues. Most parse errors come from malformed YAML frontmatter. Open the file, fix the frontmatter (or remove it), and re-run — the file is not in `state.json` so it will be retried.

**`state.json` was lost**

If you lose `state.json` and re-run the migration, you will create duplicate notes in PiperVault for every previously imported file. Before re-running, delete all notes in PiperVault through the web UI or API, then start fresh. This is the only scenario where duplicates can occur.
