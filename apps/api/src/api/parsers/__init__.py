"""
Document parsers: bytes in, structured text out.

    parsed = parse_document("policy.pdf", data)
    for section in parsed.sections:
        section.text, section.page_number, section.heading_path, section.kind

To add a format: write a Parser subclass with `extensions`, and add it to _PARSERS below.
"""

from pathlib import PurePath

from api.parsers.base import ParsedDocument, ParsedSection, Parser, ParsingError
from api.parsers.csv_parser import CsvParser
from api.parsers.docx_parser import DocxParser
from api.parsers.markdown_parser import MarkdownParser
from api.parsers.pdf_parser import PdfParser
from api.parsers.text_parser import TextParser

_PARSERS: dict[str, Parser] = {}
for _parser in (PdfParser(), DocxParser(), TextParser(), MarkdownParser(), CsvParser()):
    for _ext in _parser.extensions:
        _PARSERS[_ext] = _parser


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    extension = PurePath(filename).suffix.lower()
    parser = _PARSERS.get(extension)
    if parser is None:
        raise ParsingError(f"No parser available for '{extension}' files")
    return parser.parse(data)


__all__ = ["ParsedDocument", "ParsedSection", "Parser", "ParsingError", "parse_document"]