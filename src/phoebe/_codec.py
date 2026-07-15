# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Phoebe's content codec — the single source of truth for the ``JSON:``
tagged-string wire format and the read-side memory-content view.

# Why this module exists

Phoebe stores polymorphic fields (memory ``content``, ``*.data``, story
``input_context`` / ``output``) as Kuzu ``STRING`` columns holding JSON. The
``real_ladybug`` driver auto-detects JSON inside a STRING parameter by
inspecting the first byte: a leading ``{`` or ``[`` makes it try (and fail)
to infer a nested-vector type. :func:`json_encode` prepends the tag
``JSON:`` so that first-byte heuristic never fires; :func:`json_decode` is
the strict inverse.

# CROSS-FIREWALL MIRROR — keep byte-compatible with ``othrys/_db.py``

``othrys._db.json_encode`` / ``json_decode`` implement the EXACT same wire
format. They cannot be a single shared module: Titan tool source is compiled
in a sandbox that forbids importing ``othrys.*`` (see
``othrys.query_tool._ALLOWED_TITAN_PACKAGES``), and ``othrys`` is not even
importable at Phoebe standalone time. So the format lives in two places by
necessity. If you change the tag or the encode/decode contract HERE, change
``othrys/_db.py`` in lockstep — a drift silently corrupts every value that
crosses between the importer (Othrys) and the tools (Phoebe).
"""

from __future__ import annotations

import json
import re
from typing import Any

JSON_PREFIX = "JSON:"
"""Tag-prefix for encoded JSON strings. The leading 'J' is alphabetic, never
matches the driver's ``{``/``[`` first-byte heuristic, and self-documents the
value as machine-readable JSON. Mirror of ``othrys._db.JSON_PREFIX``."""


def json_encode(obj: Any) -> str:
    """Serialize ``obj`` as tagged JSON safe for binding into a Kuzu STRING.

    The returned string always begins with :data:`JSON_PREFIX`. Byte-identical
    to ``othrys._db.json_encode`` (``"JSON:" + json.dumps(obj)``).
    """
    return JSON_PREFIX + json.dumps(obj)


def json_decode(value: Any) -> Any:
    """Strict inverse of :func:`json_encode` for a Kuzu column value.

    Accepts exactly two shapes:

    * ``str`` beginning with :data:`JSON_PREFIX` (tagged JSON) -> parsed.
    * Native ``list`` / ``dict`` (the driver returns these directly for
      ``STRING[]`` / ``STRUCT`` columns) -> passed through unchanged.

    Returns ``None`` for ``None``, the empty string, and any UNTAGGED string —
    the reader refuses to guess the type of an untagged value rather than
    silently mis-decode. Mirror of ``othrys._db.json_decode``.

    NOTE: memory ``content`` is NOT always tagged (e.g. council-decision
    memories store a bare string). Use :func:`decode_memory_content` for that
    field — it treats an untagged string as literal text.
    """
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value:
        return None
    if not value.startswith(JSON_PREFIX):
        return None
    body = value[len(JSON_PREFIX):]
    if not body:
        return None
    return json.loads(body)


# ---------------------------------------------------------------------------
# Memory-content view (read side)
# ---------------------------------------------------------------------------

def decode_memory_content(value: Any) -> Any:
    """Decode a memory ``content`` column to its Python view.

    Unlike the strict :func:`json_decode`, an UNTAGGED string is legitimate
    memory content (council decisions and imported rows store bare text), so
    it is returned verbatim rather than nulled.

    ``remember()`` wraps a plain user string as ``{"description": <str>}`` — an
    informationless envelope. A LONE-``description`` dict is unwrapped back to
    the bare string so readers see exactly what the author wrote. Richer dicts
    (``{"story", "artifact"}``, ``{"description", "delta", "file"}``, ...) are
    returned WHOLE.
    """
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        decoded: Any = value
    elif isinstance(value, str):
        decoded = json_decode(value) if value.startswith(JSON_PREFIX) else value
    else:
        return value
    if (
        isinstance(decoded, dict)
        and set(decoded) == {"description"}
        and isinstance(decoded["description"], str)
    ):
        return decoded["description"]
    return decoded


# Full ANSI/CSI escape sequences (ESC [ ... final-byte). Stripped whole so a
# title never carries a terminal control sequence — nor its inert printable
# tail (``[31m``) — into GUIs or logs. Terminal/log-injection defense.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Residual control chars that are NOT ordinary whitespace (C0 minus \t\n\r,
# plus DEL and C1) — e.g. a lone ESC, NUL, backspace.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WS_RE = re.compile(r"\s+")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")   # [text](url) -> text
_MD_EMPHASIS_RE = re.compile(r"[*_`~]+")             # ** __ ` ~~ markers
_MD_LEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+|>+\s*|[-*+]\s+|\d+[.)]\s+)")
_SENTENCE_RE = re.compile(r"^(.*?[.!?])(?:\s|$)")


def _title_text(content: Any) -> str:
    """Coerce decoded memory content to the string a title is derived from."""
    decoded = decode_memory_content(content)
    if decoded is None:
        return ""
    if isinstance(decoded, str):
        return decoded
    if isinstance(decoded, dict):
        for key in ("description", "story", "summary", "title", "content", "text"):
            v = decoded.get(key)
            if isinstance(v, str) and v.strip():
                return v
        return " ".join(
            v for v in decoded.values() if isinstance(v, str) and v.strip()
        )
    return str(decoded)


def derive_title(content: Any) -> str:
    """Derive a short, human, sanitized title from memory ``content`` at READ
    time (index tier only). NOT a byte-slice of content.

    Rule: decode content -> take the FIRST sentence (up to the first ``.``/
    ``!``/``?`` boundary) of the FIRST non-empty line -> strip ANSI/terminal
    control sequences -> strip markdown (leading heading/list/quote markers,
    inline emphasis/code markers, links reduced to their visible text) ->
    collapse whitespace -> trim. No length cap (the standing no-truncation
    rule: the first sentence is returned whole).
    """
    text = _title_text(content)
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    first_line = ""
    for line in normalized.split("\n"):
        if line.strip():
            first_line = line
            break
    if not first_line:
        return ""
    first_line = _MD_LEADING_RE.sub("", first_line)
    m = _SENTENCE_RE.match(first_line.strip())
    candidate = m.group(1) if m else first_line
    # ANSI/control FIRST: the CSI introducer ``\x1b[`` contains a ``[`` that the
    # markdown-link regex would otherwise latch onto as a link's opening
    # bracket, splicing the escape's parameter bytes (``31m``) into the title.
    # Strip terminal sequences before markdown so the two never interleave.
    candidate = _ANSI_RE.sub("", candidate)
    candidate = _CONTROL_RE.sub("", candidate)
    candidate = _MD_LINK_RE.sub(r"\1", candidate)
    candidate = _MD_EMPHASIS_RE.sub("", candidate)
    candidate = _WS_RE.sub(" ", candidate).strip()
    return candidate
