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
    """It should add frontmatter and page comments around PyMuPDF4LLM chunks."""
    source_pdf = tmp_path / '01_1._Introduction_p5-5.pdf'
    source_pdf.write_bytes(b'%PDF-1.5')

    def fake_to_markdown(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        assert args == (str(source_pdf),)
        assert kwargs == {'page_chunks': True, 'show_progress': False}
        return [
            {'metadata': {'page_number': 1}, 'text': 'Chapter body'},
        ]

    monkeypatch.setattr(pdf_to_markdown.pymupdf4llm, 'to_markdown', fake_to_markdown)

    markdown = pdf_to_markdown.convert_pdf_to_markdown(source_pdf, pdf_to_markdown.ConvertOptions())

    assert 'title: "1. Introduction"' in markdown
    assert 'source_file: "01_1._Introduction_p5-5.pdf"' in markdown
    assert 'original_page_start: 5' in markdown
    assert '# 1. Introduction' in markdown
    assert '<!-- page: 5; source_page: 1 -->' in markdown
    assert 'Chapter body' in markdown


def test_convert_path_converts_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It should convert every PDF in a directory to Markdown files."""
    input_dir = tmp_path / 'chapters'
    output_dir = tmp_path / 'markdown'
    input_dir.mkdir()
    (input_dir / '02_Install_p6-6.pdf').write_bytes(b'%PDF-1.5')
    (input_dir / 'notes.txt').write_text('ignored', encoding='utf-8')

    def fake_to_markdown(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {'metadata': {'page_number': 1}, 'text': f'converted from {Path(args[0]).name}'},
        ]

    monkeypatch.setattr(pdf_to_markdown.pymupdf4llm, 'to_markdown', fake_to_markdown)

    outputs = pdf_to_markdown.convert_path(input_dir, output_dir, pdf_to_markdown.ConvertOptions())

    assert outputs == [output_dir / '02_Install_p6-6.md']
    assert 'converted from 02_Install_p6-6.pdf' in outputs[0].read_text(encoding='utf-8')


def test_collect_pdf_paths_rejects_non_pdf_file(tmp_path: Path) -> None:
    """It should reject non-PDF input files."""
    text_file = tmp_path / 'input.txt'
    text_file.write_text('not a pdf', encoding='utf-8')

    with pytest.raises(ValueError, match='not a PDF'):
        pdf_to_markdown.collect_pdf_paths(text_file, recursive=False)
