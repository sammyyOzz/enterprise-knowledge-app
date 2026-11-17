import re

from api.parsers.base import (
    ParsedDocument,
    ParsedSection,
    Parser,
    ParsingError,
    decode_text,
    heading_path,
    normalize_text,
    push_heading,
)

_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


class MarkdownParser(Parser):
    """Splits on ATX headings (# ... ######), ignoring '#' lines inside fenced code blocks."""

    extensions = (".md",)

    def parse(self, data: bytes) -> ParsedDocument:
        text = normalize_text(decode_text(data))

        # Drop YAML front matter (--- key: value --- at the very top).
        match = _FRONT_MATTER.match(text)
        if match and re.match(r"[\w-]+\s*:", match.group(1)):
            text = text[match.end():]

        sections: list[ParsedSection] = []
        stack: list[tuple[int, str]] = []
        buffer: list[str] = []
        title: str | None = None
        fence: str | None = None

        def flush() -> None:
            body = "\n".join(buffer).strip()
            buffer.clear()
            if body:
                sections.append(ParsedSection(text=body, heading_path=heading_path(stack)))

        for line in text.split("\n"):
            fence_match = _FENCE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if fence is None:
                    fence = marker[:3]
                elif line.strip().startswith(fence):
                    fence = None
                buffer.append(line)
                continue

            heading = None if fence else _HEADING.match(line)
            if heading:
                flush()
                level, heading_text = len(heading.group(1)), heading.group(2).strip()
                push_heading(stack, level, heading_text)
                if title is None and level == 1:
                    title = heading_text
            else:
                buffer.append(line)
        flush()

        if not sections:
            raise ParsingError("File contains no text")
        return ParsedDocument(sections=sections, metadata={"title": title} if title else {})