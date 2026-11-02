"""Where a chat's history lives on disk."""
from __future__ import annotations

import unicodedata
from pathlib import Path


def _legacy_slug(contact: str) -> str:
    return contact.lower().replace(" ", "_")


def contact_slug(contact: str) -> str:
    """Folder name for CONTACT: lower case, spaces → _, accents dropped.

    "Data Lake - Técnico" and "DATA LAKE - Tecnico" are the same chat; keeping
    the accent made two folders, and a --newest on one never saw what the
    other had captured (DataLake, 2026-11-02).
    """
    s = unicodedata.normalize("NFKD", contact.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace(" ", "_")


def contact_dir(base: Path, contact: str) -> Path:
    """BASE/<slug>, reusing a folder an older wavi created with the accent
    when the accent-free one does not exist yet, so history is not orphaned."""
    new = base / contact_slug(contact)
    old = base / _legacy_slug(contact)
    if not new.exists() and old.exists():
        return old
    return new
