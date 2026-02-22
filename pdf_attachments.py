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


class CorruptAttachmentError(Exception):
    """Raised when an attachment exists but its data cannot be decoded."""


def _stream_data(ef: dict) -> bytes | None:
    """Extract raw bytes from an embedded file stream.

    Raises:
        CorruptAttachmentError: If the stream exists but cannot be decoded.
    """
    stream = ef.get("/F")
    if stream is None:
        return None
    try:
        return stream.get_object().get_data()
    except Exception as exc:
        raise CorruptAttachmentError(f"Failed to decode attachment stream: {exc}") from exc


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


def add_attachment(
    pdf_path: str,
    files: list[Path],
    output_path: str,
    *,
    renames: dict[str, str] | None = None,
) -> int:
    """Add one or more file attachments to a PDF and write the result.

    Args:
        pdf_path: Path to the input PDF.
        files: Files to embed.
        output_path: Where to write the resulting PDF.
        renames: Optional mapping of original filename → new attachment name.

    Raises:
        ValueError: If a resulting attachment name duplicates an existing one
            in the PDF, or if two input files resolve to the same name.
    """
    renames = renames or {}

    # Resolve final names for each input file.
    resolved: list[tuple[Path, str]] = []
    for file in files:
        resolved.append((file, renames.get(file.name, file.name)))

    # Check for duplicates among the input files themselves.
    seen: dict[str, Path] = {}
    for file, name in resolved:
        if name in seen:
            raise ValueError(
                f"Duplicate input name '{name}' "
                f"(from '{file}' and '{seen[name]}'). "
                f"Use --name to rename one of them."
            )
        seen[name] = file

    # Check for collisions with existing attachments in the PDF.
    existing = {a.name for a in list_attachments(pdf_path)}
    collisions = [name for _, name in resolved if name in existing]
    if collisions:
        names = ", ".join(f"'{n}'" for n in collisions)
        raise ValueError(
            f"Attachment(s) already exist in the PDF: {names}. Use --name to rename them."
        )

    writer = PdfWriter(clone_from=pdf_path)

    for file, name in resolved:
        writer.add_attachment(name, file.read_bytes())

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

    try:
        att = get_attachment(str(pdf), name)
    except CorruptAttachmentError as e:
        typer.echo(f"Error: attachment '{name}' is corrupt: {e}", err=True)
        raise typer.Exit(1) from None
    if att is None or att.data is None:
        typer.echo(f"Error: attachment '{name}' not found in {pdf}.", err=True)
        raise typer.Exit(1)

    out = output if output else Path(att.name)
    out.write_bytes(att.data)
    typer.echo(f"Extracted: {att.name} → {out}  ({len(att.data)} bytes)")


def _parse_renames(raw: list[str] | None) -> dict[str, str]:
    """Parse a list of 'old:new' rename strings into a dict."""
    if not raw:
        return {}
    renames: dict[str, str] = {}
    for item in raw:
        if ":" not in item:
            typer.echo(
                f"Error: invalid --name format '{item}'. Expected 'original:newname'.",
                err=True,
            )
            raise typer.Exit(1)
        old, new = item.split(":", 1)
        if not old or not new:
            typer.echo(
                f"Error: invalid --name format '{item}'. "
                f"Both original and new name must be non-empty.",
                err=True,
            )
            raise typer.Exit(1)
        renames[old] = new
    return renames


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
            help="Output PDF path. Required unless --in-place is set.",
        ),
    ] = None,
    in_place: Annotated[
        bool,
        typer.Option(
            "--in-place",
            "-i",
            help="Overwrite the input PDF in place.",
        ),
    ] = False,
    name: Annotated[
        list[str] | None,
        typer.Option(
            "--name",
            "-n",
            help=("Rename an attachment: 'original:newname'. Repeatable for multiple files."),
        ),
    ] = None,
) -> None:
    """Clones the input PDF, embeds the given files, and writes the result.

    Prints: "Added <N> attachment(s) → <path>" on success.
    Exit code 1 if any input file is missing or names collide.
    """
    if not pdf.is_file():
        typer.echo(f"Error: PDF file not found: {pdf}", err=True)
        raise typer.Exit(1)

    for f in files:
        if not f.is_file():
            typer.echo(f"Error: file not found: {f}", err=True)
            raise typer.Exit(1)

    renames = _parse_renames(name)

    # Validate that --name keys match actual input files.
    input_names = {f.name for f in files}
    unknown = set(renames.keys()) - input_names
    if unknown:
        typer.echo(
            f"Error: --name key(s) don't match any input file: {', '.join(sorted(unknown))}",
            err=True,
        )
        raise typer.Exit(1)

    if output and in_place:
        typer.echo("Error: --output and --in-place are mutually exclusive.", err=True)
        raise typer.Exit(1)
    if not output and not in_place:
        typer.echo(
            "Error: specify --output/-o or --in-place/-i. "
            "Refusing to overwrite input PDF without explicit --in-place.",
            err=True,
        )
        raise typer.Exit(1)

    out = str(output) if output else str(pdf)
    try:
        count = add_attachment(str(pdf), files, out, renames=renames)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Added {count} attachment(s) → {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
