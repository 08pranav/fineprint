"""Turn an upload (PDF or text) into plain text. Pages are separated by a form feed (\f)."""
from __future__ import annotations

import io
import unicodedata

PAGE_BREAK = "\f"


class LoadError(ValueError):
    """Raised with a message that is safe to show to the user."""


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("​", "")
    # Common PDF ligatures and quote marks
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return text.strip()


def load_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise LoadError("PDF support is not installed on the server.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise LoadError("This file could not be opened as a PDF. Try exporting it again, or paste the text.") from exc
    if reader.is_encrypted:
        # Bank PDFs are often AES-encrypted with an empty password just to block editing.
        # decrypt() reports a wrong password by returning 0, not by raising.
        try:
            opened = reader.decrypt("")
        except Exception as exc:
            raise LoadError("This PDF's encryption could not be read. Paste the text instead.") from exc
        if not opened:
            raise LoadError("This PDF is password-protected. Remove the password, or paste the text instead.")
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = PAGE_BREAK.join(p.strip() for p in pages)
    if len(text.replace(PAGE_BREAK, "").strip()) < 40:
        raise LoadError(
            "No readable text was found in this PDF. It may be a scanned image. "
            "Copy the text from the document and paste it instead."
        )
    return clean_text(text)


def load_upload(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return load_pdf(data)
    if name.endswith((".txt", ".md")) or not name:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return clean_text(data.decode(encoding))
            except UnicodeDecodeError:
                continue
    raise LoadError("Only PDF and plain-text (.txt) files can be read. Paste the text if your file is in another format.")
