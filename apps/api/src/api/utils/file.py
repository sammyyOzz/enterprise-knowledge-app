import re
from pathlib import PurePath

from api.core.config import app_config
from api.exceptions import InvalidFileContent, UnsupportedFileType



def sanitize_filename(name: str | None) -> str:
  # Browsers should send a bare name, but strip any path (incl. Windows-style).
  base = PurePath((name or "").replace("\\", "/")).name.strip()
  # \w keeps letters/digits from ANY language, so "报告.pdf" and "résumé.pdf" stay
  # distinct instead of collapsing into the same "__.pdf".
  base = re.sub(r"[^\w.\- ]", "_", base)
  base = re.sub(r"\s+", " ", base).lstrip(". ")
  if len(base) > app_config.MAX_FILENAME_LENGTH:
      suffix = PurePath(base).suffix
      base = PurePath(base).stem[: app_config.MAX_FILENAME_LENGTH - len(suffix)] + suffix
  return base or "file"


def resolve_mime(filename: str) -> str:
  ext = PurePath(filename).suffix.lower()
  if ext not in app_config.ALLOWED_TYPES:
      allowed = ", ".join(sorted(app_config.ALLOWED_TYPES))
      raise UnsupportedFileType(f"Unsupported file type '{ext}'. Allowed: {allowed}")
  return app_config.ALLOWED_TYPES[ext]


def validate_content(filename: str, data: bytes) -> None:
  """Cheap sanity check that the bytes match the extension (not a full scan)."""
  ext = PurePath(filename).suffix.lower()
  if ext == ".pdf" and b"%PDF-" not in data[:1024]:
      raise InvalidFileContent("File does not look like a valid PDF")
  if ext == ".docx" and not data.startswith(b"PK\x03\x04"):
      raise InvalidFileContent("File does not look like a valid DOCX")
  if ext in (".txt", ".md", ".csv") and b"\x00" in data[:8192]:
      raise InvalidFileContent("File looks binary, expected text")

