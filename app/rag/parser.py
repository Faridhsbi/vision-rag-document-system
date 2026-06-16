import logging
import re
from collections.abc import Callable
from pathlib import Path

from app.rag.schemas import DocumentChunk

logger = logging.getLogger(__name__)


def make_document_id(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "document"


def normalize_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "\\|")


def table_to_markdown(table: list[list[object]]) -> str:
    rows = [[normalize_cell(cell) for cell in row] for row in table if row]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def infer_table_title(page_text: str, page_number: int, table_index: int) -> str:
    keywords = ("tabel", "kredit", "sektor", "dpk", "dana pihak", "komposisi")
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in keywords) and len(line) <= 140:
            return line
    return f"Table {table_index} on page {page_number}"


class PDFParser:
    def __init__(self, processed_dir: Path):
        self.processed_dir = processed_dir

    def parse(
        self,
        pdf_path: Path,
        document_id: str,
        source_filename: str,
        visual_page_numbers: set[int] | None = None,
        visual_describer: Callable[[Path, int], str] | None = None,
    ) -> tuple[list[DocumentChunk], int, int, int]:
        text_chunks, page_texts, page_count = self._extract_text_chunks(
            pdf_path, document_id, source_filename
        )
        table_chunks = self._extract_table_chunks(
            pdf_path, document_id, source_filename, page_texts
        )
        visual_chunks = self._extract_visual_chunks(
            pdf_path=pdf_path,
            document_id=document_id,
            source_filename=source_filename,
            page_count=page_count,
            visual_page_numbers=visual_page_numbers,
            visual_describer=visual_describer,
        )
        chunks = text_chunks + table_chunks + visual_chunks
        return chunks, page_count, len(table_chunks), len(visual_chunks)

    def _extract_text_chunks(
        self, pdf_path: Path, document_id: str, source_filename: str
    ) -> tuple[list[DocumentChunk], dict[int, str], int]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF text extraction.") from exc

        chunks: list[DocumentChunk] = []
        page_texts: dict[int, str] = {}

        with fitz.open(pdf_path) as document:
            page_count = len(document)
            for index, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                page_texts[index] = text
                if not text:
                    continue
                chunks.append(
                    DocumentChunk(
                        id=f"{document_id}_page_{index:03d}_text",
                        document_id=document_id,
                        page=index,
                        type="text",
                        source=source_filename,
                        title=f"Page {index} text",
                        content=text,
                        metadata={"parser": "pymupdf"},
                    )
                )
        return chunks, page_texts, page_count

    def _extract_table_chunks(
        self,
        pdf_path: Path,
        document_id: str,
        source_filename: str,
        page_texts: dict[int, str],
    ) -> list[DocumentChunk]:
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber is not installed; table extraction skipped.")
            return []

        chunks: list[DocumentChunk] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    tables = page.extract_tables() or []
                except Exception as exc:  # pragma: no cover - parser-specific failures
                    logger.warning("Table extraction failed on page %s: %s", page_number, exc)
                    continue

                for table_index, table in enumerate(tables, start=1):
                    markdown = table_to_markdown(table)
                    if not markdown:
                        continue
                    title = infer_table_title(
                        page_texts.get(page_number, ""), page_number, table_index
                    )
                    chunks.append(
                        DocumentChunk(
                            id=(
                                f"{document_id}_page_{page_number:03d}_"
                                f"table_{table_index:02d}"
                            ),
                            document_id=document_id,
                            page=page_number,
                            type="table",
                            source=source_filename,
                            title=title,
                            content=f"{title}\n\n{markdown}",
                            metadata={"parser": "pdfplumber", "table_index": table_index},
                        )
                    )
        return chunks

    def _extract_visual_chunks(
        self,
        pdf_path: Path,
        document_id: str,
        source_filename: str,
        page_count: int,
        visual_page_numbers: set[int] | None,
        visual_describer: Callable[[Path, int], str] | None,
    ) -> list[DocumentChunk]:
        if visual_describer is None:
            return []

        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF page rendering.") from exc

        output_dir = self.processed_dir / document_id / "rendered_pages"
        output_dir.mkdir(parents=True, exist_ok=True)
        chunks: list[DocumentChunk] = []

        with fitz.open(pdf_path) as document:
            for page_number in range(1, page_count + 1):
                if visual_page_numbers is not None and page_number not in visual_page_numbers:
                    continue
                page = document[page_number - 1]
                image_path = output_dir / f"page_{page_number:03d}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(image_path)

                try:
                    caption = visual_describer(image_path, page_number).strip()
                except Exception as exc:  # pragma: no cover - external API failure
                    logger.warning("Visual captioning failed on page %s: %s", page_number, exc)
                    caption = ""

                if not caption:
                    continue
                chunks.append(
                    DocumentChunk(
                        id=f"{document_id}_page_{page_number:03d}_visual",
                        document_id=document_id,
                        page=page_number,
                        type="visual",
                        source=source_filename,
                        title=f"Visual interpretation page {page_number}",
                        content=caption,
                        metadata={
                            "parser": "gemini_vision",
                            "rendered_image": str(image_path.as_posix()),
                        },
                    )
                )
        return chunks

