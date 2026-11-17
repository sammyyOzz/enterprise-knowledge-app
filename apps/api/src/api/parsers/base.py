"""
Common types and helpers for document parsers.

This package deliberately imports nothing from api.core / the database, so parsers
can be unit-tested without environment variables or running services.
"""

import codecs
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ParsingError(Exception):
    """The file can't be parsed. The message is written to be safe to show to users."""


@dataclass
class ParsedSection:
    """A block of text plus where it came from (used later for chunking and citations)."""

    text: str
    page_number: int | None = None  # PDFs only; DOCX/MD/TXT/CSV have no reliable pages
    heading_path: str | None = None  # e.g. "Leave Policy > Annual Leave"
    kind: str = "text"  # "text" | "table"
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    sections: list[ParsedSection]
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)  # title, author, columns, ...

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.sections)


class Parser(ABC):
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, data: bytes) -> ParsedDocument: ...


# --------------------------------------------------------------------------- #
# Helpers shared by parsers
# --------------------------------------------------------------------------- #
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def decode_text(data: bytes) -> str:
    """Best-effort decode: UTF-8 (with/without BOM), UTF-16 with BOM, then Windows-1252, then Latin-1."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails


def normalize_text(text: str, *, compat: bool = False) -> str:
    """
    Unicode-normalise and tidy whitespace.
    compat=True (NFKC) also expands ligatures such as "ﬁ" -> "fi", which PDFs often contain.
    """
    text = unicodedata.normalize("NFKC" if compat else "NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def push_heading(stack: list[tuple[int, str]], level: int, title: str) -> None:
    """Maintain a heading stack: a new heading closes every heading at the same or deeper level."""
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))


def heading_path(stack: list[tuple[int, str]]) -> str | None:
    return " > ".join(title for _, title in stack) or None