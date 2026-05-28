"""Configuration loading for the notes system.

Reads ~/.config/notes/config.toml using the stdlib tomllib module.

TOML shape:
    [server]
    url = "https://vault.example.com"
    api_token = "..."

    [local]
    notes_dir = "~/.notes"   # optional, default ~/.notes
    editor = "code"           # optional, default "code"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


_CONFIG_PATH = Path("~/.config/notes/config.toml")


@dataclass
class NotesConfig:
    server_url: str
    api_token: str
    notes_dir: Path
    editor: str


class ConfigError(Exception):
    """Raised when the config file is missing or malformed."""


def load_config(config_path: Path | None = None) -> NotesConfig:
    """Load and return the notes configuration.

    Args:
        config_path: Override the default config path (~/.config/notes/config.toml).

    Raises:
        ConfigError: If the file is missing or required keys are absent.
    """
    path = (config_path or _CONFIG_PATH).expanduser()

    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            "Create it with:\n"
            "  [server]\n"
            "  url = \"https://vault.example.com\"\n"
            "  api_token = \"<your token>\"\n"
        )

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path}\n{exc}") from exc

    server = data.get("server", {})
    local = data.get("local", {})

    missing = [k for k in ("url", "api_token") if k not in server]
    if missing:
        raise ConfigError(
            f"Config file {path} is missing required [server] keys: {', '.join(missing)}"
        )

    notes_dir = Path(local.get("notes_dir", "~/.notes")).expanduser()
    editor = local.get("editor", "code")

    return NotesConfig(
        server_url=server["url"],
        api_token=server["api_token"],
        notes_dir=notes_dir,
        editor=editor,
    )
