#!/usr/bin/env python3
"""Manage PDF attachments: list, extract (get), and add.

A CLI tool for working with file attachments embedded in PDF documents.
Supports document-level and page-level (annotation) attachments.

Commands:
  list  — Show all attachments in a PDF (name, size, page, description).
  get   — Extract a single attachment by exact filename.
  add   — Embed one or more files into a PDF as attachments.

Exit codes:
  0  Success.
  1  Error (file not found, attachment not found, invalid PDF).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf", "typer"]
# ///

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from pypdf import PdfReader, PdfWriter

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Attachment:
    name: str
    size: int | None = None
    description: str = ""
    page: int | None = None
    data: bytes | None = None

    def __str__(self) -> str:
        location = f" (page {self.page})" if self.page else ""
        size = f"{self.size} bytes" if self.size is not None else "unknown"
        lines = [f"  {self.name}{location}  —  {size}"]
        if self.description:
            lines.append(f"    {self.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stream_size(ef: dict) -> int | None:
    """Extract byte size from an embedded file stream."""
    stream = ef.get("/F")
    if stream is None:
        return None
    obj = stream.get_object()
    params = obj.get("/Params", {})
    if hasattr(params, "get") and "/Size" in params:
        return int(params["/Size"])
    try:
        return len(obj.get_data())
    except Exception:
        return None


def _stream_data(ef: dict) -> bytes | None:
    """Extract raw bytes from an embedded file stream."""
    stream = ef.get("/F")
    if stream is None:
        return None
    try:
        return stream.get_object().get_data()
    except Exception:
        return None


def _get_document_attachments(reader: PdfReader, *, with_data: bool = False) -> list[Attachment]:
    """Get attachments from the document-level /EmbeddedFiles catalog."""
    catalog = reader.trailer["/Root"]
    names = catalog.get("/Names", {}).get("/EmbeddedFiles", {}).get("/Names", [])
    attachments = []
    for i in range(0, len(names), 2):
        spec = names[i + 1].get_object()
        ef = spec.get("/EF", {})
        attachments.append(
            Attachment(
                name=str(names[i]),
                size=_stream_size(ef),
                description=str(spec.get("/Desc", "")),
                data=_stream_data(ef) if with_data else None,
            )
        )
    return attachments


def _get_page_attachments(reader: PdfReader, *, with_data: bool = False) -> list[Attachment]:
    """Get attachments from page-level /FileAttachment annotations."""
    attachments = []
    for page_num, page in enumerate(reader.pages, 1):
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/FileAttachment":
                continue
            fs = annot.get("/FS", {})
            if hasattr(fs, "get_object"):
                fs = fs.get_object()
            ef = fs.get("/EF", {})
            attachments.append(
                Attachment(
                    name=str(fs.get("/F", fs.get("/UF", "unknown"))),
                    size=_stream_size(ef),
                    description=str(fs.get("/Desc", annot.get("/Contents", ""))),
                    page=page_num,
                    data=_stream_data(ef) if with_data else None,
                )
            )
    return attachments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_attachments(pdf_path: str) -> list[Attachment]:
    """Return all attachments found in a PDF."""
    reader = PdfReader(pdf_path)
    return _get_document_attachments(reader) + _get_page_attachments(reader)


def get_attachment(pdf_path: str, name: str) -> Attachment | None:
    """Extract a single attachment by name, including its data."""
    reader = PdfReader(pdf_path)
    all_attachments = _get_document_attachments(reader, with_data=True) + _get_page_attachments(
        reader, with_data=True
    )
    for att in all_attachments:
        if att.name == name:
            return att
    return None


def add_attachment(pdf_path: str, files: list[Path], output_path: str) -> int:
    """Add one or more file attachments to a PDF and write the result."""
    writer = PdfWriter(clone_from=pdf_path)

    for file in files:
        writer.add_attachment(file.name, file.read_bytes())

    with open(output_path, "wb") as f:
        writer.write(f)

    return len(files)


# ---------------------------------------------------------------------------
# CLI (typer)
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="pdf-attachments",
    help=(
        "List, extract, and add file attachments in PDF documents.\n\n"
        "Supports both document-level embedded files and page-level "
        "FileAttachment annotations.\n\n"
        "EXAMPLES:\n\n"
        "  pdf-attachments list report.pdf\n\n"
        "  pdf-attachments get report.pdf data.csv\n\n"
        "  pdf-attachments get report.pdf data.csv --output /tmp/data.csv\n\n"
        "  pdf-attachments add report.pdf notes.txt image.png\n\n"
        "  pdf-attachments add report.pdf notes.txt --output report_new.pdf\n\n"
        "EXIT CODES:  0 = success, 1 = error (file/attachment not found, invalid PDF)."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command(
    "list",
    help="List all attachments in a PDF. Prints name, size, page, and description.",
)
def cmd_list(
    pdf: Annotated[
        Path,
        typer.Argument(help="Path to the input PDF file to inspect."),
    ],
) -> None:
    """Output format (stdout, one attachment per block):

      <filename> (page <N>)  —  <size> bytes
        <description>

    Returns exit code 0 even when there are no attachments.
    """
    if not pdf.is_file():
        typer.echo(f"Error: file not found: {pdf}", err=True)
        raise typer.Exit(1)

    attachments = list_attachments(str(pdf))
    typer.echo(f"PDF: {pdf}")
    typer.echo(f"Attachments: {len(attachments)}")
    typer.echo("-" * 50)
    if attachments:
        typer.echo("\n".join(str(a) for a in attachments))
    else:
        typer.echo("  (none)")


@app.command("get", help="Extract a single attachment by its exact filename and save it to disk.")
def cmd_get(
    pdf: Annotated[
        Path,
        typer.Argument(help="Path to the input PDF file containing the attachment."),
    ],
    name: Annotated[
        str,
        typer.Argument(
            help="Exact filename of the attachment to extract. Use 'list' to see names."
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path. Defaults to the attachment's filename in the CWD.",
        ),
    ] = None,
) -> None:
    """Writes the attachment bytes to the output path.

    Prints: "Extracted: <name> → <path>  (<size> bytes)" on success.
    Exit code 1 if the attachment is not found.
    """
    if not pdf.is_file():
        typer.echo(f"Error: file not found: {pdf}", err=True)
        raise typer.Exit(1)

    att = get_attachment(str(pdf), name)
    if att is None or att.data is None:
        typer.echo(f"Error: attachment '{name}' not found in {pdf}.", err=True)
        raise typer.Exit(1)

    out = output if output else Path(att.name)
    out.write_bytes(att.data)
    typer.echo(f"Extracted: {att.name} → {out}  ({len(att.data)} bytes)")


@app.command("add", help="Embed one or more files into a PDF as document-level attachments.")
def cmd_add(
    pdf: Annotated[
        Path,
        typer.Argument(help="Path to the input PDF file to add attachments to."),
    ],
    files: Annotated[
        list[Path],
        typer.Argument(help="One or more file paths to embed as attachments."),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output PDF path. Defaults to overwriting the input PDF in place.",
        ),
    ] = None,
) -> None:
    """Clones the input PDF, embeds the given files, and writes the result.

    Prints: "Added <N> attachment(s) → <path>" on success.
    Exit code 1 if any input file is missing.
    """
    if not pdf.is_file():
        typer.echo(f"Error: PDF file not found: {pdf}", err=True)
        raise typer.Exit(1)

    for f in files:
        if not f.is_file():
            typer.echo(f"Error: file not found: {f}", err=True)
            raise typer.Exit(1)

    out = str(output) if output else str(pdf)
    count = add_attachment(str(pdf), files, out)
    typer.echo(f"Added {count} attachment(s) → {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
