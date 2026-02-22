"""Tests for add command: duplicate detection, --name rename, --in-place, error handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pdf_attachments import (
    CorruptAttachmentError,
    add_attachment,
    app,
    get_attachment,
    list_attachments,
)

runner = CliRunner()


@pytest.fixture()
def minimal_pdf(tmp_path: Path) -> Path:
    """Create a minimal valid PDF with no attachments."""
    from pypdf import PdfWriter

    pdf = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf, "wb") as f:
        writer.write(f)
    return pdf


@pytest.fixture()
def pdf_with_attachment(minimal_pdf: Path, tmp_path: Path) -> Path:
    """Create a PDF that already has 'existing.txt' attached."""
    txt = tmp_path / "existing.txt"
    txt.write_text("hello")
    add_attachment(str(minimal_pdf), [txt], str(minimal_pdf))
    return minimal_pdf


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    txt = tmp_path / "data.csv"
    txt.write_text("a,b,c")
    return txt


# ── API-level tests ──────────────────────────────────────────────────


class TestAddAttachmentAPI:
    def test_basic_add(self, minimal_pdf: Path, sample_file: Path) -> None:
        out = minimal_pdf.parent / "out.pdf"
        count = add_attachment(str(minimal_pdf), [sample_file], str(out))
        assert count == 1
        atts = list_attachments(str(out))
        assert len(atts) == 1
        assert atts[0].name == "data.csv"

    def test_add_with_rename(self, minimal_pdf: Path, sample_file: Path) -> None:
        out = minimal_pdf.parent / "out.pdf"
        count = add_attachment(
            str(minimal_pdf), [sample_file], str(out), renames={"data.csv": "renamed.csv"}
        )
        assert count == 1
        atts = list_attachments(str(out))
        assert atts[0].name == "renamed.csv"

    def test_duplicate_with_existing(self, pdf_with_attachment: Path, tmp_path: Path) -> None:
        """Adding a file whose name matches an existing attachment should raise."""
        new_file = tmp_path / "existing.txt"
        new_file.write_text("different content")
        with pytest.raises(ValueError, match="already exist"):
            add_attachment(str(pdf_with_attachment), [new_file], str(pdf_with_attachment))

    def test_duplicate_among_inputs(self, minimal_pdf: Path, tmp_path: Path) -> None:
        """Two input files resolving to the same name should raise."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "same.txt").write_text("aaa")
        (dir_b / "same.txt").write_text("bbb")
        with pytest.raises(ValueError, match="Duplicate input name"):
            add_attachment(
                str(minimal_pdf),
                [dir_a / "same.txt", dir_b / "same.txt"],
                str(minimal_pdf),
            )

    def test_rename_avoids_existing_collision(
        self, pdf_with_attachment: Path, tmp_path: Path
    ) -> None:
        """Renaming away from the collision should succeed."""
        new_file = tmp_path / "existing.txt"
        new_file.write_text("new content")
        out = tmp_path / "out.pdf"
        count = add_attachment(
            str(pdf_with_attachment),
            [new_file],
            str(out),
            renames={"existing.txt": "existing_v2.txt"},
        )
        assert count == 1
        atts = list_attachments(str(out))
        names = {a.name for a in atts}
        assert names == {"existing.txt", "existing_v2.txt"}

    def test_rename_avoids_input_collision(self, minimal_pdf: Path, tmp_path: Path) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "data.txt").write_text("aaa")
        (dir_b / "other.txt").write_text("bbb")
        out = tmp_path / "out.pdf"
        count = add_attachment(
            str(minimal_pdf),
            [dir_a / "data.txt", dir_b / "other.txt"],
            str(out),
        )
        assert count == 2

    def test_roundtrip_data_integrity(self, minimal_pdf: Path, tmp_path: Path) -> None:
        """Add a file, extract it, verify bytes match."""
        content = b"\x00\x01\x02\xff" * 100
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(content)
        out = tmp_path / "out.pdf"
        add_attachment(str(minimal_pdf), [binary_file], str(out))
        att = get_attachment(str(out), "binary.bin")
        assert att is not None
        assert att.data == content


# ── --in-place CLI tests ─────────────────────────────────────────────


class TestInPlace:
    def test_cli_no_output_no_inplace_errors(self, minimal_pdf: Path, sample_file: Path) -> None:
        """Without --output or --in-place, the CLI should refuse."""
        result = runner.invoke(app, ["add", str(minimal_pdf), str(sample_file)])
        assert result.exit_code == 1
        assert "--in-place" in result.stderr

    def test_cli_output_and_inplace_errors(
        self, minimal_pdf: Path, sample_file: Path, tmp_path: Path
    ) -> None:
        """--output and --in-place are mutually exclusive."""
        out = tmp_path / "out.pdf"
        result = runner.invoke(
            app,
            ["add", str(minimal_pdf), str(sample_file), "-o", str(out), "--in-place"],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.stderr

    def test_cli_inplace_works(self, minimal_pdf: Path, sample_file: Path) -> None:
        """--in-place should overwrite the input PDF."""
        result = runner.invoke(app, ["add", str(minimal_pdf), str(sample_file), "--in-place"])
        assert result.exit_code == 0
        assert "Added 1" in result.stdout
        atts = list_attachments(str(minimal_pdf))
        assert len(atts) == 1
        assert atts[0].name == "data.csv"

    def test_cli_inplace_short_flag(self, minimal_pdf: Path, sample_file: Path) -> None:
        """-i should work as short form of --in-place."""
        result = runner.invoke(app, ["add", str(minimal_pdf), str(sample_file), "-i"])
        assert result.exit_code == 0
        assert "Added 1" in result.stdout

    def test_cli_output_works(self, minimal_pdf: Path, sample_file: Path, tmp_path: Path) -> None:
        """--output should write to a different file."""
        out = tmp_path / "out.pdf"
        result = runner.invoke(app, ["add", str(minimal_pdf), str(sample_file), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        # Original should be unchanged (no attachments).
        assert len(list_attachments(str(minimal_pdf))) == 0
        assert len(list_attachments(str(out))) == 1


# ── Error handling tests ─────────────────────────────────────────────


class TestErrorHandling:
    def test_corrupt_attachment_error_type(self) -> None:
        """CorruptAttachmentError is a distinct exception."""
        exc = CorruptAttachmentError("bad stream")
        assert isinstance(exc, Exception)
        assert "bad stream" in str(exc)

    def test_cli_get_missing_attachment(self, minimal_pdf: Path) -> None:
        result = runner.invoke(app, ["get", str(minimal_pdf), "nonexistent.txt"])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_cli_get_missing_pdf(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["get", str(tmp_path / "nope.pdf"), "x.txt"])
        assert result.exit_code == 1
        assert "file not found" in result.stderr

    def test_cli_add_missing_pdf(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("x")
        result = runner.invoke(app, ["add", str(tmp_path / "nope.pdf"), str(f), "-i"])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_cli_add_missing_input_file(self, minimal_pdf: Path, tmp_path: Path) -> None:
        result = runner.invoke(app, ["add", str(minimal_pdf), str(tmp_path / "ghost.txt"), "-i"])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_cli_list_missing_pdf(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["list", str(tmp_path / "nope.pdf")])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_cli_list_empty_pdf(self, minimal_pdf: Path) -> None:
        result = runner.invoke(app, ["list", str(minimal_pdf)])
        assert result.exit_code == 0
        assert "Attachments: 0" in result.stdout
        assert "(none)" in result.stdout


# ── --name CLI tests ─────────────────────────────────────────────────


class TestNameCLI:
    def test_cli_duplicate_errors(self, pdf_with_attachment: Path, tmp_path: Path) -> None:
        dup = tmp_path / "existing.txt"
        dup.write_text("dup")
        result = runner.invoke(app, ["add", str(pdf_with_attachment), str(dup), "-i"])
        assert result.exit_code == 1
        assert "already exist" in result.stderr

    def test_cli_name_resolves_collision(self, pdf_with_attachment: Path, tmp_path: Path) -> None:
        dup = tmp_path / "existing.txt"
        dup.write_text("dup")
        out = tmp_path / "out.pdf"
        result = runner.invoke(
            app,
            [
                "add",
                str(pdf_with_attachment),
                str(dup),
                "--name",
                "existing.txt:existing_v2.txt",
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert "Added 1" in result.stdout

    def test_cli_name_bad_format(self, minimal_pdf: Path, sample_file: Path) -> None:
        result = runner.invoke(
            app, ["add", str(minimal_pdf), str(sample_file), "-i", "--name", "nocolon"]
        )
        assert result.exit_code == 1
        assert "invalid --name format" in result.stderr

    def test_cli_name_unknown_key(self, minimal_pdf: Path, sample_file: Path) -> None:
        result = runner.invoke(
            app,
            ["add", str(minimal_pdf), str(sample_file), "-i", "--name", "nope.txt:x.txt"],
        )
        assert result.exit_code == 1
        assert "don't match" in result.stderr

    def test_cli_name_empty_parts(self, minimal_pdf: Path, sample_file: Path) -> None:
        result = runner.invoke(
            app, ["add", str(minimal_pdf), str(sample_file), "-i", "--name", ":empty"]
        )
        assert result.exit_code == 1
        assert "non-empty" in result.stderr

    def test_cli_multiple_renames(self, minimal_pdf: Path, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("aaa")
        b.write_text("bbb")
        out = tmp_path / "out.pdf"
        result = runner.invoke(
            app,
            [
                "add",
                str(minimal_pdf),
                str(a),
                str(b),
                "--name",
                "a.txt:alpha.txt",
                "--name",
                "b.txt:beta.txt",
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0
        atts = list_attachments(str(out))
        names = {att.name for att in atts}
        assert names == {"alpha.txt", "beta.txt"}
