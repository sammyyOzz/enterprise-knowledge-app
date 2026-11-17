from api.parsers.base import ParsedDocument, ParsedSection, Parser, ParsingError, decode_text, normalize_text


class TextParser(Parser):
    extensions = (".txt",)

    def parse(self, data: bytes) -> ParsedDocument:
        text = normalize_text(decode_text(data))
        if not text:
            raise ParsingError("File contains no text")
        return ParsedDocument(sections=[ParsedSection(text=text)])