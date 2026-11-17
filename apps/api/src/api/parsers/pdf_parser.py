import re

import pymupdf

from api.parsers.base import (
    ParsedDocument,
    ParsedSection,
    Parser,
    ParsingError,
    heading_path,
    normalize_text,
    push_heading,
)

MAX_PAGES = 1000
MIN_AVG_CHARS_PER_PAGE = 10  # below this we assume the PDF is scanned images


def _clean_block(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)  # re-join words hyphenated across lines
    return re.sub(r"\s*\n\s*", " ", text).strip()  # PDF line breaks are layout, not meaning


class PdfParser(Parser):
    """
    One section per page, with the page number kept for citations. Heading paths come from the
    PDF's outline (bookmarks) when it has one, at page granularity.

    Not supported (reported as clear errors where detectable): scanned PDFs (needs OCR) and
    password-protected files. Tables are extracted as plain text, not structure.
    """

    extensions = (".pdf",)

    def parse(self, data: bytes) -> ParsedDocument:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise ParsingError("PDF could not be opened (file may be corrupt)") from exc

        with doc:
            if doc.needs_pass:
                raise ParsingError("PDF is password-protected")
            page_count = doc.page_count
            if page_count == 0:
                raise ParsingError("PDF has no pages")
            if page_count > MAX_PAGES:
                raise ParsingError(f"PDF has more than {MAX_PAGES} pages")

            try:
                outline = [
                    (level, title.strip(), page)
                    for level, title, page in doc.get_toc(simple=True)
                    if title.strip() and page >= 1
                ]
            except Exception:  # noqa: BLE001  (a broken outline shouldn't fail the whole file)
                outline = []
            outline.sort(key=lambda entry: entry[2])  # stable: keeps order within a page

            sections: list[ParsedSection] = []
            stack: list[tuple[int, str]] = []
            next_entry = 0

            for page_number, page in enumerate(doc, start=1):
                while next_entry < len(outline) and outline[next_entry][2] <= page_number:
                    level, title, _ = outline[next_entry]
                    push_heading(stack, level, title)
                    next_entry += 1

                paragraphs = []
                for block in page.get_text("blocks", sort=True):
                    if block[6] != 0:  # 0 = text block, 1 = image
                        continue
                    cleaned = _clean_block(block[4])
                    if cleaned:
                        paragraphs.append(cleaned)

                text = normalize_text("\n\n".join(paragraphs), compat=True)
                if text:
                    sections.append(
                        ParsedSection(
                            text=text, page_number=page_number, heading_path=heading_path(stack)
                        )
                    )

            total_chars = sum(len(s.text) for s in sections)
            if total_chars == 0 or total_chars / page_count < MIN_AVG_CHARS_PER_PAGE:
                raise ParsingError(
                    "No extractable text found. This looks like a scanned PDF, "
                    "which isn't supported yet (OCR is not available)."
                )

            meta = doc.metadata or {}
            metadata = {
                k: v for k, v in {"title": meta.get("title"), "author": meta.get("author")}.items() if v
            }
            return ParsedDocument(sections=sections, page_count=page_count, metadata=metadata)