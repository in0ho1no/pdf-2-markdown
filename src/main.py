"""Convert PDF files into RAG-friendly Markdown with PyMuPDF4LLM."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf4llm

PAGE_RANGE_PATTERN = re.compile(r'_p(?P<start>\d+)-(?P<end>\d+)\.pdf$', re.IGNORECASE)
TITLE_PREFIX_PATTERN = re.compile(r'^(?:\d{2}(?:-\d{2})*_)?')
PAGE_MARKER_CHOICES = ('comment', 'heading', 'both', 'none')


class ConversionError(Exception):
    """Raised when a PDF cannot be converted safely."""


@dataclass(frozen=True)
class ConvertOptions:
    """Options for Markdown conversion."""

    include_frontmatter: bool = True
    page_marker: str = 'both'
    overwrite: bool = True
    show_progress: bool = False


@dataclass(frozen=True)
class PdfMetadata:
    """Metadata inferred from a source PDF path."""

    title: str
    original_page_start: int | None
    original_page_end: int | None


@dataclass(frozen=True)
class ConversionWarning:
    """A non-fatal warning generated while converting a PDF."""

    pdf_path: Path
    message: str


@dataclass(frozen=True)
class ConvertResult:
    """Result of converting one or more PDF files."""

    output_paths: list[Path]
    warnings: list[ConversionWarning]


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
    import json

    return json.dumps(value, ensure_ascii=False)


def file_sha256(path: Path) -> str:
    """Calculate a SHA-256 digest for an input file."""
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_frontmatter(pdf_path: Path, metadata: PdfMetadata) -> str:
    """Build Markdown frontmatter for RAG ingestion."""
    converter_version = importlib.metadata.version('pymupdf4llm')
    lines = [
        '---',
        f'title: {yaml_string(metadata.title)}',
        f'source_pdf: {yaml_string(str(pdf_path))}',
        f'source_file: {yaml_string(pdf_path.name)}',
        'converter: "pymupdf4llm"',
        f'converter_version: {yaml_string(converter_version)}',
        f'source_sha256: {yaml_string(file_sha256(pdf_path))}',
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
    if isinstance(page_number, str) and page_number.isdecimal():
        return int(page_number)
    return fallback


def expected_page_count(metadata: PdfMetadata) -> int | None:
    """Return expected page count from metadata when available."""
    if metadata.original_page_start is None or metadata.original_page_end is None:
        return None
    return metadata.original_page_end - metadata.original_page_start + 1


def build_page_marker(original_page: int, source_page: int, marker_style: str) -> str:
    """Build a page marker that can survive different Markdown loaders."""
    comment = f'<!-- page: {original_page}; source_page: {source_page} -->'
    heading = f'## Page {original_page}'
    if marker_style == 'comment':
        return comment
    if marker_style == 'heading':
        return heading
    if marker_style == 'both':
        return f'{comment}\n\n{heading}'
    if marker_style == 'none':
        return ''
    raise ValueError(f'Unsupported page marker style: {marker_style}')


def convert_pdf_to_markdown(pdf_path: Path, options: ConvertOptions) -> tuple[str, list[ConversionWarning]]:
    """Convert a PDF file to a Markdown string."""
    metadata = infer_metadata(pdf_path)
    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True, show_progress=options.show_progress)
    if isinstance(chunks, str):
        chunks = [{'metadata': {'page_number': 1}, 'text': chunks}]

    warnings: list[ConversionWarning] = []
    expected_pages = expected_page_count(metadata)
    if expected_pages is not None and expected_pages != len(chunks):
        warnings.append(
            ConversionWarning(
                pdf_path=pdf_path,
                message=f'Filename page range expects {expected_pages} page(s), but converter returned {len(chunks)} chunk(s).',
            ),
        )

    body_parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        source_page = extract_chunk_page_number(chunk, fallback=index)
        original_page = source_page
        if metadata.original_page_start is not None:
            original_page = metadata.original_page_start + source_page - 1

        text = extract_chunk_text(chunk)
        page_marker = build_page_marker(original_page, source_page, options.page_marker)
        if page_marker:
            body_parts.append(f'{page_marker}\n\n{text}')
        elif text:
            body_parts.append(text)

    sections: list[str] = []
    if options.include_frontmatter:
        sections.append(build_frontmatter(pdf_path, metadata))
    sections.append(f'# {metadata.title}')
    sections.append('\n\n'.join(part for part in body_parts if part).strip())

    return '\n\n'.join(section for section in sections if section).strip() + '\n', warnings


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


def output_path_for(pdf_path: Path, input_path: Path, output_dir: Path, recursive: bool) -> Path:
    """Return an output Markdown path for a source PDF."""
    if recursive and input_path.is_dir():
        return output_dir / pdf_path.relative_to(input_path).with_suffix('.md')
    return output_dir / f'{pdf_path.stem}.md'


def convert_path(input_path: Path, output_dir: Path, options: ConvertOptions, recursive: bool = False) -> ConvertResult:
    """Convert one PDF or every PDF in a directory."""
    pdf_paths = collect_pdf_paths(input_path, recursive=recursive)
    if not pdf_paths:
        raise ValueError(f'No PDF files found: {input_path}')

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    warnings: list[ConversionWarning] = []
    for pdf_path in pdf_paths:
        output_path = output_path_for(pdf_path, input_path, output_dir, recursive)
        if output_path.exists() and not options.overwrite:
            continue

        markdown, conversion_warnings = convert_pdf_to_markdown(pdf_path, options)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding='utf-8')
        output_paths.append(output_path)
        warnings.extend(conversion_warnings)

    return ConvertResult(output_paths=output_paths, warnings=warnings)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Convert PDF files into RAG-friendly Markdown.')
    parser.add_argument('input_path', type=Path, help='PDF file or directory containing split PDF files.')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path('markdown'), help='Directory for generated Markdown files.')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search input directories recursively.')
    parser.add_argument('--skip-existing', action='store_true', help='Do not overwrite existing Markdown files.')
    parser.add_argument('--no-frontmatter', action='store_true', help='Do not include YAML frontmatter.')
    parser.add_argument(
        '--page-marker',
        choices=PAGE_MARKER_CHOICES,
        default='both',
        help='Page marker style. "both" keeps source pages even if HTML comments are removed by a Markdown loader.',
    )
    parser.add_argument('--show-progress', action='store_true', help='Show PyMuPDF4LLM page processing progress.')
    return parser.parse_args()


def run_cli() -> int:
    """Run the command-line interface."""
    args = parse_args()
    options = ConvertOptions(
        include_frontmatter=not args.no_frontmatter,
        page_marker=args.page_marker,
        overwrite=not args.skip_existing,
        show_progress=args.show_progress,
    )
    try:
        result = convert_path(args.input_path, args.output_dir, options, recursive=args.recursive)
    except (OSError, ValueError, ConversionError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f'warning: {warning.pdf_path}: {warning.message}', file=sys.stderr)
    for output_path in result.output_paths:
        print(output_path)
    return 0


def main() -> None:
    """Run the command-line interface and exit with its status code."""
    raise SystemExit(run_cli())


if __name__ == '__main__':
    main()
