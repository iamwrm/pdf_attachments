#!/usr/bin/env python3
"""Manage PDF attachments: list, extract (get), and add."""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf"]
# ///

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

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
# CLI
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> None:
    attachments = list_attachments(args.pdf)
    print(f"PDF: {args.pdf}")
    print(f"Attachments: {len(attachments)}")
    print("-" * 50)
    if attachments:
        print("\n".join(str(a) for a in attachments))
    else:
        print("  (none)")


def _cmd_get(args: argparse.Namespace) -> None:
    att = get_attachment(args.pdf, args.name)
    if att is None or att.data is None:
        print(f"Attachment '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output) if args.output else Path(att.name)
    out.write_bytes(att.data)
    print(f"Extracted: {att.name} → {out}  ({len(att.data)} bytes)")


def _cmd_add(args: argparse.Namespace) -> None:
    files = [Path(f) for f in args.files]
    for f in files:
        if not f.is_file():
            print(f"File not found: {f}", file=sys.stderr)
            sys.exit(1)

    output = args.output or args.pdf
    count = add_attachment(args.pdf, files, output)
    print(f"Added {count} attachment(s) → {output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf_attachments",
        description="List, extract, and add PDF attachments.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List attachments in a PDF")
    p_list.add_argument("pdf", help="Input PDF file")

    # get
    p_get = sub.add_parser("get", help="Extract an attachment by name")
    p_get.add_argument("pdf", help="Input PDF file")
    p_get.add_argument("name", help="Attachment filename to extract")
    p_get.add_argument("-o", "--output", help="Output path (default: attachment name)")

    # add
    p_add = sub.add_parser("add", help="Add file(s) as attachments to a PDF")
    p_add.add_argument("pdf", help="Input PDF file")
    p_add.add_argument("files", nargs="+", help="File(s) to attach")
    p_add.add_argument("-o", "--output", help="Output PDF path (default: overwrite input)")

    args = parser.parse_args()
    {"list": _cmd_list, "get": _cmd_get, "add": _cmd_add}[args.command](args)


if __name__ == "__main__":
    main()
