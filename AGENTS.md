# AGENTS.md — Maintenance Guide for pdf_attachments

## Project Overview

Single-file Python CLI tool (`pdf_attachments.py`) that lists, extracts, and adds file attachments in PDFs. Uses `pypdf` for PDF manipulation and `typer` for CLI.

**This is a single-module project — there is no `src/` directory or package folder.** The entire codebase lives in `pdf_attachments.py` at the repo root.

## Architecture

```
pdf_attachments.py   ← Everything: data model, PDF helpers, public API, CLI
pyproject.toml       ← Build config (hatchling), dependencies, ruff, entry point
.github/workflows/   ← CI (ruff lint + format)
```

### Key sections inside `pdf_attachments.py`

1. **Data model** — `Attachment` dataclass
2. **Internal helpers** — `_stream_size()`, `_stream_data()`, `_get_document_attachments()`, `_get_page_attachments()`
3. **Public API** — `list_attachments()`, `get_attachment()`, `add_attachment()`
4. **CLI** — typer app with `list`, `get`, `add` commands

### Two types of PDF attachments

- **Document-level**: stored in `/Root → /Names → /EmbeddedFiles`. Most common.
- **Page-level**: `/FileAttachment` annotations on individual pages. Less common but must be supported.

Both types are collected by `list_attachments()` and `get_attachment()`. The `add` command only creates document-level attachments (via `PdfWriter.add_attachment()`).

## Tool Versions & Commands

| Task | Command |
|---|---|
| Install deps | `uv sync` |
| Run CLI | `uv run pdf-attachments <command>` |
| Lint | `uv run ruff check .` |
| Auto-fix lint | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Format check | `uv run ruff format --check .` |
| Build wheel | `uv build` |
| Run from GitHub | `uvx --from git+https://github.com/iamwrm/pdf_attachments pdf-attachments --help` |

## Common Pitfalls

### 1. Do NOT create a package directory

This project uses a **single-file module** (`pdf_attachments.py`). Hatchling is configured with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["pdf_attachments.py"]
```

If you move the code into `src/pdf_attachments/` or `pdf_attachments/`, you must update both `pyproject.toml` (hatch config and entry point) and the inline script metadata at the top of the file.

### 2. Keep the inline script metadata in sync

The file has PEP 723 inline script metadata at the top:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf", "typer"]
# ///
```

This allows `uv run pdf_attachments.py` without installation. **If you add a dependency to `pyproject.toml`, also add it here** (and vice versa).

### 3. Ruff line length is 100, not 80

```toml
[tool.ruff]
line-length = 100
```

Typer help strings and `typer.Option()`/`typer.Argument()` calls tend to be long. Break them across multiple lines to stay under 100 chars. Example:

```python
# Bad — will fail ruff
typer.Option("--output", "-o", help="Very long description that exceeds one hundred characters limit easily.")

# Good
typer.Option(
    "--output", "-o",
    help="Shorter description broken across lines.",
)
```

### 4. Use `typer.echo()` and `typer.Exit()`, not `print()`/`sys.exit()`

For consistency and testability:
- Output: `typer.echo(...)` (stdout) or `typer.echo(..., err=True)` (stderr)
- Errors: `raise typer.Exit(1)` instead of `sys.exit(1)`

### 5. PDF key strings are literal — don't strip the slash

pypdf uses literal PDF name strings like `"/F"`, `"/EF"`, `"/Subtype"`. These are **not** Python conventions — they match the PDF spec. Don't "clean them up".

### 6. `get_object()` calls are necessary

pypdf returns indirect references (`IndirectObject`) in many places. Always call `.get_object()` when traversing PDF structures, especially for annotation `/FS` entries and file specs.

### 7. The `add` command overwrites by default

`pdf-attachments add doc.pdf file.txt` writes back to `doc.pdf`. This is intentional but destructive. The `--output` flag exists for non-destructive use. Don't change this default without updating help text.

### 8. CI only runs ruff — there are no tests yet

The GitHub Actions workflow (`.github/workflows/ci.yml`) only checks:
- `ruff check .` (lint)
- `ruff format --check .` (formatting)

If you add tests, add a test step to the CI workflow and include `pytest` in `[dependency-groups] dev`.

## Making Changes

### Adding a new CLI command

1. Write the business logic function in the "Public API" section
2. Add a `@app.command()` function in the "CLI" section
3. Use `Annotated[..., typer.Argument/Option(...)]` for all parameters with descriptive help text
4. Validate inputs early, use `typer.echo(..., err=True)` + `raise typer.Exit(1)` for errors
5. Run `uv run ruff check --fix . && uv run ruff format .` before committing

### Adding a dependency

1. `uv add <package>` (updates `pyproject.toml` and `uv.lock`)
2. Update the inline script metadata (`# dependencies = [...]`) at the top of `pdf_attachments.py`
3. Verify build still works: `uv build`

### Bumping version

Edit `version` in `pyproject.toml`. There is only one place — no `__version__` variable in the Python file.
