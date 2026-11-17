import csv
import io

from api.parsers.base import ParsedDocument, ParsedSection, Parser, ParsingError, decode_text

ROWS_PER_SECTION = 20
MAX_ROWS = 50_000
MAX_COLUMNS = 200


class CsvParser(Parser):
  """
  Turns rows into readable text ("Row 3: Name: Alice; Dept: HR") grouped into sections of
  ROWS_PER_SECTION rows, so the content is searchable. The first row is treated as the header.

  This makes CSVs findable via semantic search. Exact questions over them ("total sales
  in Q3") will need the structured-data querying feature later.
  """

  extensions = (".csv",)

  def parse(self, data: bytes) -> ParsedDocument:
      text = decode_text(data).replace("\x00", "")
      if not text.strip():
          raise ParsingError("CSV is empty")

      try:
          dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
      except csv.Error:
          dialect = csv.excel

      reader = csv.reader(io.StringIO(text, newline=""), dialect)
      try:
          header_row = next(reader)
      except StopIteration:
          raise ParsingError("CSV is empty")
      except csv.Error as exc:
          raise ParsingError(f"CSV could not be parsed: {exc}")

      if len(header_row) > MAX_COLUMNS:
          raise ParsingError(f"CSV has more than {MAX_COLUMNS} columns")
      header = [
          (name.strip() or f"column_{i + 1}") for i, name in enumerate(header_row)
      ]

      sections: list[ParsedSection] = []
      lines: list[str] = []
      first_row = 0
      row_count = 0

      def flush(last_row: int) -> None:
          if lines:
              sections.append(
                  ParsedSection(
                      text="\n".join(lines),
                      kind="table",
                      metadata={"row_start": first_row, "row_end": last_row, "columns": header},
                  )
              )
              lines.clear()

      try:
          for row in reader:
              row_count += 1
              if row_count > MAX_ROWS:
                  raise ParsingError(f"CSV has more than {MAX_ROWS:,} rows")
              cells = []
              for i, value in enumerate(row):
                  value = value.strip()
                  if value:
                      name = header[i] if i < len(header) else f"column_{i + 1}"
                      cells.append(f"{name}: {value}")
              if not cells:
                  continue  # skip blank rows
              if not lines:
                  first_row = row_count
              lines.append(f"Row {row_count}: " + "; ".join(cells))
              if len(lines) >= ROWS_PER_SECTION:
                  flush(row_count)
      except csv.Error as exc:
          raise ParsingError(f"CSV could not be parsed: {exc}")
      flush(row_count)

      if not sections:
          raise ParsingError("CSV has a header but no data rows")
      return ParsedDocument(
          sections=sections,
          metadata={"columns": header, "row_count": row_count, "delimiter": dialect.delimiter},
      )