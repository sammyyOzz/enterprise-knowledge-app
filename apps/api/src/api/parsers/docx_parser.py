import io
import re
import zipfile

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from api.parsers.base import (
    ParsedDocument,
    ParsedSection,
    Parser,
    ParsingError,
    heading_path,
    normalize_text,
    push_heading,
)

MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # guards against zip bombs
_HEADING_STYLE = re.compile(r"heading\s*(\d)", re.IGNORECASE)


def _heading_level(style_name: str) -> int | None:
    if style_name.strip().lower() == "title":
        return 1
    match = _HEADING_STYLE.match(style_name.strip())
    return int(match.group(1)) if match else None


def _table_text(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells, previous = [], None
        for cell in row.cells:
            if cell._tc is previous:  # merged cells repeat; skip the duplicates
                continue
            previous = cell._tc
            cells.append(" ".join(cell.text.split()))
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


class DocxParser(Parser):
    """Walks the body in order, splitting on Heading styles; tables become their own sections."""

    extensions = (".docx",)

    def parse(self, data: bytes) -> ParsedDocument:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                total = sum(info.file_size for info in archive.infolist())
        except zipfile.BadZipFile:
            raise ParsingError("DOCX file is corrupt or not a valid Word document")
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ParsingError("DOCX expands to an unreasonable size")

        try:
            doc = DocxDocument(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            raise ParsingError("DOCX file is corrupt or not a valid Word document") from exc

        sections: list[ParsedSection] = []
        stack: list[tuple[int, str]] = []
        buffer: list[str] = []

        def flush() -> None:
            body = normalize_text("\n\n".join(buffer))
            buffer.clear()
            if body:
                sections.append(ParsedSection(text=body, heading_path=heading_path(stack)))

        for child in doc.element.body.iterchildren():
            if child.tag == qn("w:p"):
                paragraph = Paragraph(child, doc)
                text = paragraph.text.strip()
                if not text:
                    continue
                style_name = paragraph.style.name if paragraph.style is not None else ""
                level = _heading_level(style_name or "")
                if level:
                    flush()
                    push_heading(stack, level, text)
                else:
                    prefix = "- " if (style_name or "").lower().startswith("list") else ""
                    buffer.append(prefix + text)
            elif child.tag == qn("w:tbl"):
                flush()
                table_text = _table_text(Table(child, doc))
                if table_text:
                    sections.append(
                        ParsedSection(text=table_text, heading_path=heading_path(stack), kind="table")
                    )
        flush()

        if not sections:
            raise ParsingError("Document contains no extractable text")

        props = doc.core_properties
        metadata = {k: v for k, v in {"title": props.title, "author": props.author}.items() if v}
        return ParsedDocument(sections=sections, metadata=metadata)