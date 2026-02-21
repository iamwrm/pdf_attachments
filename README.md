# pdf_attachments

A CLI tool to **list**, **extract**, and **add** file attachments in PDF documents.

## Installation

Requires Python ≥ 3.10.

```bash
# Run directly from GitHub (no install needed)
uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments <command> ...

# Or install as a tool
uv tool install git+https://github.com/iamwrm/pdf_attachments
pdf-attachments <command> ...

# Or install into current environment
uv pip install git+https://github.com/iamwrm/pdf_attachments
```

## Usage

### List attachments

```bash
pdf-attachments list document.pdf
```

### Extract an attachment

```bash
pdf-attachments get document.pdf report.xlsx
pdf-attachments get document.pdf report.xlsx -o /tmp/report.xlsx
```

### Add attachments

```bash
pdf-attachments add document.pdf data.csv image.png
pdf-attachments add document.pdf data.csv -o document_with_attachments.pdf
```

## As a library

```python
from pdf_attachments import list_attachments, get_attachment, add_attachment
from pathlib import Path

# List
for att in list_attachments("doc.pdf"):
    print(att.name, att.size)

# Extract
att = get_attachment("doc.pdf", "data.csv")
if att and att.data:
    Path("data.csv").write_bytes(att.data)

# Add
add_attachment("doc.pdf", [Path("notes.txt")], "output.pdf")
```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
```

## License

MIT
