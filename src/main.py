"""Convert PDF files into RAG-friendly Markdown with PyMuPDF4LLM."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf4llm

PAGE_RANGE_PATTERN = re.compile(r'_p(?P<start>\d+)-(?P<end>\d+)\.pdf$', re.IGNORECASE)
TITLE_PREFIX_PATTERN = re.compile(r'^(?:\d{2}(?:-\d{2})*_)?')


@dataclass(frozen=True)
class ConvertOptions:
    """Options for Markdown conversion."""

    include_frontmatter: bool = True
    include_page_comments: bool = True
    overwrite: bool = True
    show_progress: bool = False


@dataclass(frozen=True)
class PdfMetadata:
    """Metadata inferred from a source PDF path."""

    title: str
    original_page_start: int | None
    original_page_end: int | None


def infer_metadata(pdf_path: Path) -> PdfMetadata:
    """Infer title and original page range from a split PDF filename.

    Args:
        pdf_path: Source PDF path.

    Returns:
        Metadata inferred from the filename.
    """
    match = PAGE_RANGE_PATTERN.search(pdf_path.name)
    page_start = int(match.group('start')) if match else None
    page_end = int(match.group('end')) if match else None

    title = TITLE_PREFIX_PATTERN.sub('', pdf_path.stem)
    title = re.sub(r'_p\d+-\d+$', '', title)
    title = re.sub(r'\s+', ' ', title.replace('_', ' ')).strip()

    return PdfMetadata(title=title or pdf_path.stem, original_page_start=page_start, original_page_end=page_end)


def yaml_string(value: str) -> str:
    """Return a minimal double-quoted YAML scalar."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def build_frontmatter(pdf_path: Path, metadata: PdfMetadata) -> str:
    """Build Markdown frontmatter for RAG ingestion."""
    lines = [
        '---',
        f'title: {yaml_string(metadata.title)}',
        f'source_pdf: {yaml_string(str(pdf_path))}',
        f'source_file: {yaml_string(pdf_path.name)}',
        'converter: "pymupdf4llm"',
        'rag_ready: true',
    ]
    if metadata.original_page_start is not None and metadata.original_page_end is not None:
        lines.extend(
            [
                f'original_page_start: {metadata.original_page_start}',
                f'original_page_end: {metadata.original_page_end}',
            ],
        )
    lines.append('---')
    return '\n'.join(lines)


def extract_chunk_text(chunk: Any) -> str:
    """Extract Markdown text from a PyMuPDF4LLM page chunk."""
    if isinstance(chunk, dict):
        return str(chunk.get('text', '')).strip()
    return str(chunk).strip()


def extract_chunk_page_number(chunk: Any, fallback: int) -> int:
    """Extract the 1-based page number from a PyMuPDF4LLM page chunk."""
    if not isinstance(chunk, dict):
        return fallback

    metadata = chunk.get('metadata')
    if not isinstance(metadata, dict):
        return fallback

    page_number = metadata.get('page_number')
    if isinstance(page_number, int):
        return page_number
    return fallback


def convert_pdf_to_markdown(pdf_path: Path, options: ConvertOptions) -> str:
    """Convert a PDF file to a Markdown string."""
    metadata = infer_metadata(pdf_path)
    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True, show_progress=options.show_progress)

    body_parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        source_page = extract_chunk_page_number(chunk, fallback=index)
        original_page = source_page
        if metadata.original_page_start is not None:
            original_page = metadata.original_page_start + source_page - 1

        text = extract_chunk_text(chunk)
        if options.include_page_comments:
            body_parts.append(f'<!-- page: {original_page}; source_page: {source_page} -->\n\n{text}')
        else:
            body_parts.append(text)

    sections: list[str] = []
    if options.include_frontmatter:
        sections.append(build_frontmatter(pdf_path, metadata))
    sections.append(f'# {metadata.title}')
    sections.append('\n\n'.join(part for part in body_parts if part).strip())

    return '\n\n'.join(section for section in sections if section).strip() + '\n'


def collect_pdf_paths(input_path: Path, recursive: bool) -> list[Path]:
    """Collect PDF paths from a file or directory."""
    if input_path.is_file():
        if input_path.suffix.lower() != '.pdf':
            raise ValueError(f'Input file is not a PDF: {input_path}')
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f'Input path does not exist: {input_path}')

    pattern = '**/*.pdf' if recursive else '*.pdf'
    return sorted(input_path.glob(pattern))


def convert_path(input_path: Path, output_dir: Path, options: ConvertOptions, recursive: bool = False) -> list[Path]:
    """Convert one PDF or every PDF in a directory."""
    pdf_paths = collect_pdf_paths(input_path, recursive=recursive)
    if not pdf_paths:
        raise ValueError(f'No PDF files found: {input_path}')

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    for pdf_path in pdf_paths:
        output_path = output_dir / f'{pdf_path.stem}.md'
        if output_path.exists() and not options.overwrite:
            continue

        markdown = convert_pdf_to_markdown(pdf_path, options)
        output_path.write_text(markdown, encoding='utf-8')
        output_paths.append(output_path)

    return output_paths


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Convert PDF files into RAG-friendly Markdown.')
    parser.add_argument('input_path', type=Path, help='PDF file or directory containing split PDF files.')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path('markdown'), help='Directory for generated Markdown files.')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search input directories recursively.')
    parser.add_argument('--skip-existing', action='store_true', help='Do not overwrite existing Markdown files.')
    parser.add_argument('--no-frontmatter', action='store_true', help='Do not include YAML frontmatter.')
    parser.add_argument('--no-page-comments', action='store_true', help='Do not include page source comments.')
    parser.add_argument('--show-progress', action='store_true', help='Show PyMuPDF4LLM page processing progress.')
    return parser.parse_args()


def main() -> None:
    """Run the command-line interface."""
    args = parse_args()
    options = ConvertOptions(
        include_frontmatter=not args.no_frontmatter,
        include_page_comments=not args.no_page_comments,
        overwrite=not args.skip_existing,
        show_progress=args.show_progress,
    )
    output_paths = convert_path(args.input_path, args.output_dir, options, recursive=args.recursive)
    for output_path in output_paths:
        print(output_path)


if __name__ == '__main__':
    main()
