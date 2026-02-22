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

## Quick Start

```bash
# Run directly from GitHub — no install needed
uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments list document.pdf
```

## Usage

### List attachments

```
$ uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments list test.pdf
PDF: test.pdf
Attachments: 1
--------------------------------------------------
  hello.txt  —  13 bytes
```

### Extract an attachment

```
$ uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments get test.pdf hello.txt -o /tmp/hello.txt
Extracted: hello.txt → /tmp/hello.txt  (13 bytes)
```

### Add attachments

```bash
# Add and write to a new file
uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments add document.pdf data.csv image.png -o document_with_attachments.pdf

# Add and overwrite in place
uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments add document.pdf data.csv --in-place

# Rename attachments to avoid collisions
uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments add document.pdf data.csv --name data.csv:data_v2.csv -o out.pdf
```

> **Tip:** To avoid typing the full `uvx --from ...` each time, install it as a tool:
> ```bash
> uv tool install git+https://github.com/iamwrm/pdf_attachments
> pdf-attachments list document.pdf
> ```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
```

## License

MIT
