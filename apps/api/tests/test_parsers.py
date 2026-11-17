import io

import pymupdf
import pytest
from docx import Document as DocxDocument

from api.parsers import ParsingError, parse_document


# ----------------------------- text ----------------------------- #
def test_txt_utf8_and_cp1252():
    assert parse_document("a.txt", "héllo wörld".encode("utf-8")).sections[0].text == "héllo wörld"
    assert parse_document("a.txt", "café".encode("cp1252")).sections[0].text == "café"


def test_txt_empty_raises():
    with pytest.raises(ParsingError):
        parse_document("a.txt", b"   \n  ")


def test_unknown_extension_raises():
    with pytest.raises(ParsingError):
        parse_document("a.xyz", b"data")


# --------------------------- markdown --------------------------- #
def test_markdown_heading_paths_and_code_fences():
    md = (
        b"---\ntitle: x\n---\n"
        b"# Leave Policy\nIntro text.\n\n"
        b"## Annual Leave\n20 days.\n\n"
        b"```\n# not a heading\n```\n\n"
        b"## Sick Leave\n10 days.\n"
    )
    parsed = parse_document("p.md", md)
    paths = [s.heading_path for s in parsed.sections]
    assert paths == ["Leave Policy", "Leave Policy > Annual Leave", "Leave Policy > Sick Leave"]
    assert "# not a heading" in parsed.sections[1].text  # stayed inside its section
    assert "title: x" not in parsed.sections[0].text  # front matter removed
    assert parsed.metadata["title"] == "Leave Policy"


# ----------------------------- csv ------------------------------ #
def test_csv_rows_and_grouping():
    rows = "\n".join(f"{i},Name{i},HR" for i in range(1, 46))
    parsed = parse_document("e.csv", f"id,name,dept\n{rows}\n".encode())
    assert len(parsed.sections) == 3  # 45 rows / 20 per section
    assert parsed.sections[0].text.startswith("Row 1: id: 1; name: Name1; dept: HR")
    assert parsed.sections[2].metadata["row_end"] == 45
    assert parsed.sections[0].kind == "table"


def test_csv_semicolon_delimiter_and_blank_cells():
    parsed = parse_document("e.csv", b"a;b;c\n1;;3\n")
    assert parsed.sections[0].text == "Row 1: a: 1; c: 3"


def test_csv_header_only_raises():
    with pytest.raises(ParsingError):
        parse_document("e.csv", b"a,b,c\n")


# ----------------------------- docx ----------------------------- #
def _make_docx() -> bytes:
    doc = DocxDocument()
    doc.add_heading("Leave Policy", level=1)
    doc.add_paragraph("Applies to all staff.")
    doc.add_heading("Annual Leave", level=2)
    doc.add_paragraph("20 days per year.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Tenure", "Days"
    table.cell(1, 0).text, table.cell(1, 1).text = "0-2 years", "20"
    doc.add_heading("Sick Leave", level=2)
    doc.add_paragraph("10 days per year.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_headings_and_tables():
    parsed = parse_document("p.docx", _make_docx())
    by_path = [(s.heading_path, s.kind) for s in parsed.sections]
    assert by_path == [
        ("Leave Policy", "text"),
        ("Leave Policy > Annual Leave", "text"),
        ("Leave Policy > Annual Leave", "table"),
        ("Leave Policy > Sick Leave", "text"),
    ]
    assert "Tenure | Days" in parsed.sections[2].text
    assert parsed.page_count is None


def test_docx_garbage_raises():
    with pytest.raises(ParsingError):
        parse_document("p.docx", b"PK\x03\x04 not really a docx")


# ------------------------------ pdf ----------------------------- #
def _make_pdf(with_outline: bool = True) -> bytes:
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Introduction to the leave policy of the company.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Annual leave is twenty days per year for all staff.")
    if with_outline:
        doc.set_toc([[1, "Introduction", 1], [2, "Annual Leave", 2]])
    return doc.tobytes()


def test_pdf_pages_and_outline_headings():
    parsed = parse_document("p.pdf", _make_pdf())
    assert parsed.page_count == 2
    assert [s.page_number for s in parsed.sections] == [1, 2]
    assert parsed.sections[0].heading_path == "Introduction"
    assert parsed.sections[1].heading_path == "Introduction > Annual Leave"
    assert "twenty days" in parsed.sections[1].text


def test_pdf_without_outline_still_parses():
    parsed = parse_document("p.pdf", _make_pdf(with_outline=False))
    assert parsed.sections[0].heading_path is None


def test_pdf_scanned_like_raises():
    doc = pymupdf.open()
    doc.new_page()  # blank page: no extractable text
    with pytest.raises(ParsingError, match="scanned"):
        parse_document("p.pdf", doc.tobytes())


def test_pdf_garbage_raises():
    with pytest.raises(ParsingError):
        parse_document("p.pdf", b"%PDF-1.4 this is not a real pdf")