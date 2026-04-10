"""Doc manager — marker-based section management for Markdown files.

Uses HTML comment markers (<!-- forge:name:start --> / <!-- forge:name:end -->)
to manage fenced regions in Markdown files without touching surrounding content.
"""

from __future__ import annotations

import re
from pathlib import Path


def find_section(doc: str, section_name: str) -> str | None:
    """Find the content between forge markers for the given section name.

    Returns the content string (may be empty), or None if markers not found.
    """
    pattern = re.compile(
        rf"<!-- forge:{re.escape(section_name)}:start -->\n"
        rf"(?P<content>.*?)"
        rf"<!-- forge:{re.escape(section_name)}:end -->\n",
        re.DOTALL,
    )
    match = pattern.search(doc)
    if match:
        return match.group("content")
    return None


def upsert_section(doc: str, section_name: str, content: str) -> str:
    """Insert or update a marker-bounded section in a document.

    If markers exist, replaces the content between them.
    If markers don't exist, appends the section at the end.
    """
    marker_start = f"<!-- forge:{section_name}:start -->"
    marker_end = f"<!-- forge:{section_name}:end -->"

    existing = find_section(doc, section_name)
    if existing is not None:
        # Replace existing content between markers
        pattern = re.compile(
            rf"<!-- forge:{re.escape(section_name)}:start -->\n"
            rf".*?"
            rf"<!-- forge:{re.escape(section_name)}:end -->\n",
            re.DOTALL,
        )
        replacement = f"{marker_start}\n{content}{marker_end}\n"
        return pattern.sub(replacement, doc, count=1)
    else:
        # Append new section
        if not doc or doc.endswith("\n\n"):
            separator = ""
        elif doc.endswith("\n"):
            separator = "\n"
        else:
            separator = "\n\n"
        return f"{doc}{separator}{marker_start}\n{content}{marker_end}\n"


def upsert_doc_sections(
    file_path: Path,
    sections: dict[str, str],
) -> bool:
    """Update multiple managed sections in a Markdown file.

    Args:
        file_path: Path to the Markdown file (must exist)
        sections: Dict of section_name -> content to upsert

    Returns True if file was modified, False if unchanged or file doesn't exist.
    """
    if not file_path.is_file():
        return False

    original = file_path.read_text()
    doc = original

    for section_name, content in sections.items():
        doc = upsert_section(doc, section_name, content)

    if doc != original:
        file_path.write_text(doc)
        return True
    return False
