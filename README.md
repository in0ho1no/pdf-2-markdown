# pdf_2_markdown

PDF files split by chapter or section into Markdown files for RAG pipelines.

This tool is designed to be used after a PDF has already been split into smaller PDF files, such as files created by `pdf-toc-splitter` / `split-pdf-by-toc`. It uses PyMuPDF4LLM as the conversion engine and adds lightweight metadata that is useful when indexing Markdown chunks.

## Features

- Convert one PDF file or every PDF in a directory.
- Keep one Markdown file per source PDF.
- Add YAML frontmatter with source filename, source path, converter name, and original page range.
- Add page comments such as `<!-- page: 36; source_page: 1 -->` before each converted page.
- Infer titles and original page ranges from split filenames like `08-03-02_Load_and_run_Blink_p36-37.pdf`.

## Non-features

- No OCR for scanned PDFs.
- No PDF splitting.
- No automatic cleanup of PDF-specific mojibake or command-line examples yet.
- No embedding or vector database indexing.

## Installation

Use `uv` from the project root.

```powershell
uv sync
```

## Usage

Convert a directory of split PDFs:

```powershell
uv run python src/main.py D:\work\14_pdf-toc-splitter\RP-008276-DS-1-getting-started-with-pico\chapters -o outputs\RP-008276-DS-1-getting-started-with-pico\chapters_md
```

Convert one PDF:

```powershell
uv run python src/main.py path\to\chapter.pdf -o markdown
```

Search directories recursively:

```powershell
uv run python src/main.py path\to\chapters -o markdown --recursive
```

Avoid overwriting existing Markdown files:

```powershell
uv run python src/main.py path\to\chapters -o markdown --skip-existing
```

Disable metadata sections:

```powershell
uv run python src/main.py path\to\chapters -o markdown --no-frontmatter --no-page-comments
```

## Output

Each Markdown file starts with frontmatter:

```markdown
---
title: "Load and run Blink"
source_pdf: "D:\\work\\14_pdf-toc-splitter\\...\08-03-02_Load_and_run_Blink_p36-37.pdf"
source_file: "08-03-02_Load_and_run_Blink_p36-37.pdf"
converter: "pymupdf4llm"
rag_ready: true
original_page_start: 36
original_page_end: 37
---
```

Each page starts with a source comment:

```markdown
<!-- page: 36; source_page: 1 -->
```

`page` is the original PDF page number inferred from the filename. `source_page` is the page number inside the split PDF.

## Quality Notes

PyMuPDF4LLM works well for this repository's target flow because it can return page chunks and Markdown-like structure directly. The current script intentionally keeps the first conversion pass conservative. Some PDFs may still need later cleanup for:

- PDF font encoding artifacts such as mojibake symbols.
- Shell command examples that are collapsed into one line.
- Repeated headers and footers.

Those cleanup passes should be added after reviewing actual RAG retrieval quality.

## Development

Run checks after changing code:

```powershell
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
uv run pytest
```
