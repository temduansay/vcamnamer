"""
mapping_store.py – Persist user-defined device-name mappings.

Mappings are stored as JSON under the XDG config directory:
  ~/.config/vcamnamer/mappings.json

Schema example::

    {
        "/dev/video0": "OBS Studio Camera",
        "/dev/video2": "Presentation Cam"
    }

Keys are canonical /dev/videoN paths; values are the user-chosen display names.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_MAX_NAME_LENGTH = 64
# Characters disallowed in display names (udev SYMLINK values must be safe for
# the file-system and shell; we keep it simple: only printable ASCII minus a
# few special chars).
_INVALID_CHAR_RE = re.compile(r'[/\\\x00-\x1f<>"|?*]')
_RESERVED_NAMES = frozenset(
    {"", ".", "..", "con", "prn", "aux", "nul"}  # Windows-safe; harmless on Linux
)


def validate_name(name: str) -> None:
    """
    Raise ValueError if *name* is not a valid display name.

    Rules:
    - Must be a non-empty string.
    - Must not exceed 64 characters.
    - Must not contain control characters or ``/ \\ < > " | ? *``.
    - Must not be a reserved token (., ..).
    """
    if not isinstance(name, str):
        raise ValueError("Name must be a string.")
    stripped = name.strip()
    if not stripped:
        raise ValueError("Name must not be empty or whitespace-only.")
    if len(stripped) > _MAX_NAME_LENGTH:
        raise ValueError(f"Name exceeds maximum length of {_MAX_NAME_LENGTH} characters.")
    if _INVALID_CHAR_RE.search(stripped):
        raise ValueError(
            "Name contains invalid characters (/, \\, control chars, <, >, \", |, ?, *)."
        )
    if stripped.lower() in _RESERVED_NAMES:
        raise ValueError(f"'{stripped}' is a reserved name.")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Return the XDG config dir for vcamnamer, creating it if needed."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    config_dir = base / "vcamnamer"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _mappings_path() -> Path:
    return _config_dir() / "mappings.json"


class MappingStore:
    """
    Manages the persistent mapping from device node → custom display name.

    Usage::

        store = MappingStore()
        store.set("/dev/video0", "My OBS Cam")
        store.save()
        store.load()
        store.get("/dev/video0")  # -> "My OBS Cam"
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path: Path = path or _mappings_path()
        self._mappings: Dict[str, str] = {}
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load mappings from disk; silently starts fresh if file missing/corrupt."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._mappings = {str(k): str(v) for k, v in data.items()}
            else:
                self._mappings = {}
        except (FileNotFoundError, json.JSONDecodeError):
            self._mappings = {}

    def save(self) -> None:
        """Persist current mappings to disk (atomic write via temp file)."""
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._mappings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def get(self, node: str) -> Optional[str]:
        """Return the custom name for *node*, or None if not set."""
        return self._mappings.get(node)

    def set(self, node: str, name: str) -> None:
        """
        Set a custom display name for *node*.

        Raises ValueError for invalid names or duplicate values (two different
        nodes cannot have the same custom name).
        """
        validate_name(name)
        stripped = name.strip()
        # Duplicate check across other nodes
        for existing_node, existing_name in self._mappings.items():
            if existing_node != node and existing_name == stripped:
                raise ValueError(
                    f"Name '{stripped}' is already assigned to {existing_node}."
                )
        self._mappings[node] = stripped

    def remove(self, node: str) -> None:
        """Remove the mapping for *node* (no-op if not present)."""
        self._mappings.pop(node, None)

    def clear(self) -> None:
        """Remove all mappings."""
        self._mappings.clear()

    def all(self) -> Dict[str, str]:
        """Return a shallow copy of all current mappings."""
        return dict(self._mappings)

    def __len__(self) -> int:
        return len(self._mappings)
