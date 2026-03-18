# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tome management — create, open, and initialize Phoebe's embedded Kuzu databases."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import kuzu
except ImportError:
    try:
        import ladybugdb as kuzu
    except ImportError:
        kuzu = None  # type: ignore[assignment]

from phoebe.schema import init_schema


def _default_tome_path() -> Path:
    """Return the default tome path, respecting PHOEBE_TOME env var."""
    env = os.environ.get("PHOEBE_TOME")
    if env:
        return Path(env)
    # Check for .phoebe config in cwd
    config = Path.cwd() / ".phoebe"
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if line.startswith("tome:"):
                tome_path = line.split(":", 1)[1].strip()
                return Path(tome_path).expanduser()
    # Look for any .tome file in cwd
    tomes = list(Path.cwd().glob("*.tome"))
    if len(tomes) == 1:
        return tomes[0]
    # Default
    return Path.cwd() / "project.tome"


class Tome:
    """A Phoebe knowledge tome — an embedded Kuzu database.

    Usage:
        tome = Tome("my-project.tome")
        conn = tome.connection()
        # ... use conn for queries
        tome.close()

    Or as context manager:
        with Tome("my-project.tome") as tome:
            conn = tome.connection()
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if kuzu is None:
            raise ImportError(
                "Phoebe requires kuzu or ladybugdb. "
                "Install with: pip install ladybugdb"
            )
        self._path = Path(path) if path else _default_tome_path()
        self._db: Any = None
        self._conn: Any = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.exists()

    def open(self) -> None:
        """Open (or create) the tome database and initialize schema."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._path))
        self._conn = kuzu.Connection(self._db)
        init_schema(self._conn)

    def connection(self) -> Any:
        """Return a connection to the tome. Opens if not already open."""
        if self._conn is None:
            self.open()
        return self._conn

    def close(self) -> None:
        """Close the tome database."""
        self._conn = None
        self._db = None

    def __enter__(self) -> Tome:
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def stats(self) -> dict[str, Any]:
        """Return high-level tome statistics."""
        conn = self.connection()
        counts = {}
        for table in ("memories", "sources", "entities", "milestones"):
            try:
                result = conn.execute(f"MATCH (n:{table}) RETURN COUNT(n) AS c")
                row = result.get_next()
                counts[table] = row[0] if row else 0
            except Exception:
                counts[table] = 0
        return counts
