"""Tests for the PDF to Markdown command-line helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as pdf_to_markdown


def test_infer_metadata_from_split_filename() -> None:
    """It should infer a clean title and original page range."""
    metadata = pdf_to_markdown.infer_metadata(Path('08-03-02_Load_and_run_Blink_p36-37.pdf'))

    assert metadata.title == 'Load and run Blink'
    assert metadata.original_page_start == 36
    assert metadata.original_page_end == 37


def test_convert_pdf_to_markdown_adds_rag_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should add frontmatter and page comments around Docling pages."""
    source_pdf = tmp_path / '01_1._Introduction_p5-5.pdf'
    source_pdf.write_bytes(b'%PDF-1.5')

    def fake_convert_pdf_with_docling(pdf_path: Path) -> list[pdf_to_markdown.MarkdownPage]:
        assert pdf_path == source_pdf
        return [
            pdf_to_markdown.MarkdownPage(source_page=1, text='Chapter body'),
        ]

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    markdown, warnings = pdf_to_markdown.convert_pdf_to_markdown(source_pdf, pdf_to_markdown.ConvertOptions())

    assert 'title: "1. Introduction"' in markdown
    assert 'source_file: "01_1._Introduction_p5-5.pdf"' in markdown
    assert 'converter_version:' in markdown
    assert 'source_sha256:' in markdown
    assert 'original_page_start: 5' in markdown
    assert '# 1. Introduction' in markdown
    assert '<!-- page: 5; source_page: 1 -->' in markdown
    assert '## Page 5' in markdown
    assert 'Chapter body' in markdown
    assert warnings == []


def test_convert_pdf_to_markdown_warns_when_page_range_does_not_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should warn when inferred page range and converted chunks differ."""
    source_pdf = tmp_path / '08-03-02_Load_and_run_Blink_p36-37.pdf'
    source_pdf.write_bytes(b'%PDF-1.5')

    def fake_convert_pdf_with_docling(pdf_path: Path) -> list[pdf_to_markdown.MarkdownPage]:
        assert pdf_path == source_pdf
        return [
            pdf_to_markdown.MarkdownPage(source_page=1, text='Only one chunk'),
        ]

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    markdown, warnings = pdf_to_markdown.convert_pdf_to_markdown(source_pdf, pdf_to_markdown.ConvertOptions())

    assert '<!-- page: 36; source_page: 1 -->' in markdown
    assert len(warnings) == 1
    assert 'expects 2 page(s)' in warnings[0].message


def test_convert_pdf_to_markdown_strips_duplicate_title_heading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should avoid duplicating a heading already emitted by Docling."""
    source_pdf = tmp_path / '08-03-02_Load_and_run_Blink_p36-37.pdf'
    source_pdf.write_bytes(b'%PDF-1.5')

    def fake_convert_pdf_with_docling(pdf_path: Path) -> list[pdf_to_markdown.MarkdownPage]:
        assert pdf_path == source_pdf
        return [
            pdf_to_markdown.MarkdownPage(source_page=1, text='# Load and run Blink\n\nSecond page'),
            pdf_to_markdown.MarkdownPage(source_page=2, text='Fallback page'),
        ]

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    markdown, warnings = pdf_to_markdown.convert_pdf_to_markdown(source_pdf, pdf_to_markdown.ConvertOptions(page_marker='comment'))

    assert markdown.count('# Load and run Blink') == 1
    assert '<!-- page: 37; source_page: 2 -->' in markdown
    assert warnings == []


def test_convert_pdf_with_docling_stages_non_ascii_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should copy a non-ASCII-path PDF to a temp ASCII location before passing to Docling."""
    source_pdf = tmp_path / '日本語_p1-2.pdf'
    source_pdf.write_bytes(b'%PDF-1.5')

    captured_paths: list[Path] = []

    class FakeDocument:
        def export_to_markdown(self, *, page_no: int) -> str:
            return f'page {page_no}'

    class FakeConversionResult:
        def __init__(self) -> None:
            self.pages: list[object] = [object()]
            self.document = FakeDocument()

    class FakeConverter:
        def convert(self, path: Path) -> FakeConversionResult:
            captured_paths.append(path)
            return FakeConversionResult()

    monkeypatch.setattr(pdf_to_markdown, 'get_document_converter', lambda: FakeConverter())

    pages = pdf_to_markdown.convert_pdf_with_docling(source_pdf)

    assert len(pages) == 1
    assert len(captured_paths) == 1
    staged_path = captured_paths[0]
    assert str(staged_path).isascii()
    assert staged_path.name == 'input_staging_docling.pdf'
    assert staged_path != source_pdf


def test_convert_path_converts_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should convert every PDF in a directory to Markdown files."""
    input_dir = tmp_path / 'chapters'
    output_dir = tmp_path / 'markdown'
    input_dir.mkdir()
    (input_dir / '02_Install_p6-6.pdf').write_bytes(b'%PDF-1.5')
    (input_dir / 'notes.txt').write_text('ignored', encoding='utf-8')

    def fake_convert_pdf_with_docling(pdf_path: Path) -> list[pdf_to_markdown.MarkdownPage]:
        return [
            pdf_to_markdown.MarkdownPage(source_page=1, text=f'converted from {pdf_path.name}'),
        ]

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    result = pdf_to_markdown.convert_path(input_dir, output_dir, pdf_to_markdown.ConvertOptions())

    assert result.output_paths == [output_dir / '02_Install_p6-6.md']
    assert 'converted from 02_Install_p6-6.pdf' in result.output_paths[0].read_text(encoding='utf-8')


def test_convert_path_preserves_relative_paths_when_recursive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should avoid overwriting same-stem files during recursive conversion."""
    input_dir = tmp_path / 'chapters'
    output_dir = tmp_path / 'markdown'
    (input_dir / 'a').mkdir(parents=True)
    (input_dir / 'b').mkdir()
    (input_dir / 'a' / 'same_p1-1.pdf').write_bytes(b'%PDF-1.5')
    (input_dir / 'b' / 'same_p2-2.pdf').write_bytes(b'%PDF-1.5')

    def fake_convert_pdf_with_docling(pdf_path: Path) -> list[pdf_to_markdown.MarkdownPage]:
        return [
            pdf_to_markdown.MarkdownPage(source_page=1, text=f'converted from {pdf_path.parent.name}'),
        ]

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    result = pdf_to_markdown.convert_path(input_dir, output_dir, pdf_to_markdown.ConvertOptions(), recursive=True)

    assert result.output_paths == [
        output_dir / 'a' / 'same_p1-1.md',
        output_dir / 'b' / 'same_p2-2.md',
    ]
    assert (output_dir / 'a' / 'same_p1-1.md').is_file()
    assert (output_dir / 'b' / 'same_p2-2.md').is_file()


def test_convert_path_skips_existing_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should leave existing files untouched when overwrite is disabled."""
    input_dir = tmp_path / 'chapters'
    output_dir = tmp_path / 'markdown'
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / '02_Install_p6-6.pdf').write_bytes(b'%PDF-1.5')
    existing = output_dir / '02_Install_p6-6.md'
    existing.write_text('existing', encoding='utf-8')

    def fake_convert_pdf_with_docling(*args: Any, **kwargs: Any) -> list[pdf_to_markdown.MarkdownPage]:
        pytest.fail('converter should not be called for existing files')

    monkeypatch.setattr(pdf_to_markdown, 'convert_pdf_with_docling', fake_convert_pdf_with_docling)

    result = pdf_to_markdown.convert_path(input_dir, output_dir, pdf_to_markdown.ConvertOptions(overwrite=False))

    assert result.output_paths == []
    assert existing.read_text(encoding='utf-8') == 'existing'


def test_collect_pdf_paths_rejects_non_pdf_file(tmp_path: Path) -> None:
    """It should reject non-PDF input files."""
    text_file = tmp_path / 'input.txt'
    text_file.write_text('not a pdf', encoding='utf-8')

    with pytest.raises(ValueError, match='not a PDF'):
        pdf_to_markdown.collect_pdf_paths(text_file, recursive=False)


def test_run_cli_reports_expected_errors(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """It should report expected CLI errors without a traceback."""
    missing_path = tmp_path / 'missing'
    monkeypatch.setattr(
        'sys.argv',
        ['main.py', str(missing_path), '-o', str(tmp_path / 'markdown')],
    )

    exit_code = pdf_to_markdown.run_cli()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ''
    assert 'error:' in captured.err
    assert 'Traceback' not in captured.err
