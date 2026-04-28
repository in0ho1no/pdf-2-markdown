# pdf_2_markdown

章・節単位に分割済みのPDFを、RAGで扱いやすいMarkdownへ変換するツールです。

このツールは、`pdf-toc-splitter` でPDFを先に分割しておき、その分割済みPDFを1ファイルずつMarkdown化する前提で作っています。変換エンジンには `PyMuPDF4LLM` を使用します。

## できること

- PDFファイル1件、またはディレクトリ内のPDFをまとめてMarkdown化する
- 入力PDFごとに1つのMarkdownファイルを出力する
- RAGの出典表示に使いやすいfrontmatterを付与する
- 分割PDFのファイル名からタイトルと元PDFのページ範囲を推定する
- ページごとに `page` と `source_page` を付与する
- `--recursive` 指定時は入力ディレクトリの相対構造を出力先にも保持する

## できないこと

- PDFの章・節分割
- スキャンPDFのOCR
- 表、コード例、ヘッダー/フッターの完全な整形
- ベクトルDBへの登録
- RAG用チャンク分割そのもの

## セットアップ

プロジェクトルートで以下を実行します。

```powershell
uv sync
```

## 使い方

分割済みPDFが入ったディレクトリを変換します。

```powershell
uv run python src/main.py D:\work\14_pdf-toc-splitter\RP-008276-DS-1-getting-started-with-pico\chapters -o outputs\RP-008276-DS-1-getting-started-with-pico\chapters_md
```

PDFファイルを1件だけ変換します。

```powershell
uv run python src/main.py path\to\chapter.pdf -o markdown
```

サブディレクトリも再帰的に変換します。

```powershell
uv run python src/main.py path\to\chapters -o markdown --recursive
```

既存のMarkdownを上書きしない場合:

```powershell
uv run python src/main.py path\to\chapters -o markdown --skip-existing
```

frontmatterを出力しない場合:

```powershell
uv run python src/main.py path\to\chapters -o markdown --no-frontmatter
```

ページマーカーの形式を変える場合:

```powershell
uv run python src/main.py path\to\chapters -o markdown --page-marker comment
```

`--page-marker` には以下を指定できます。

| 値 | 出力 |
|---|---|
| `both` | HTMLコメントと見出しを両方出力します。既定値です |
| `comment` | `<!-- page: ... -->` のみ出力します |
| `heading` | `## Page ...` のみ出力します |
| `none` | ページマーカーを出力しません |

RAG用のMarkdownローダーによってはHTMLコメントを削除することがあります。そのため既定値は `both` にしています。

## 出力形式

Markdownの先頭にはfrontmatterを付与します。

```markdown
---
title: "Load and run Blink"
source_pdf: "D:\\work\\14_pdf-toc-splitter\\...\08-03-02_Load_and_run_Blink_p36-37.pdf"
source_file: "08-03-02_Load_and_run_Blink_p36-37.pdf"
converter: "pymupdf4llm"
converter_version: "1.27.2.3"
source_sha256: "..."
rag_ready: true
original_page_start: 36
original_page_end: 37
---
```

本文にはページごとのマーカーを付与します。

```markdown
<!-- page: 36; source_page: 1 -->

## Page 36
```

`page` は元PDFにおける推定ページ番号です。`source_page` は分割PDF内のページ番号です。

## ファイル名の前提

ページ範囲は、ファイル名末尾の `_p開始-終了.pdf` から推定します。

例:

```text
08-03-02_Load_and_run_Blink_p36-37.pdf
```

この場合、以下のように推定します。

| 項目 | 値 |
|---|---|
| タイトル | `Load and run Blink` |
| 元PDFの開始ページ | `36` |
| 元PDFの終了ページ | `37` |

ファイル名のページ範囲と実際に変換されたページ数が一致しない場合、CLIは警告を表示します。出典ページの正確性はファイル名に依存するため、分割元ツールの出力名が正しいことを確認してください。

## RAG投入前の確認ポイント

PyMuPDF4LLMはRAG向けのMarkdown化に向いていますが、PDFの構造によっては変換結果の確認が必要です。

- 表がMarkdown表として扱いやすい形になっているか
- コマンド例やコードブロックの改行が崩れていないか
- 図のキャプションが本文と近い位置に残っているか
- ヘッダー/フッターが検索ノイズになっていないか
- PDF由来の文字化けが残っていないか
- 使用するMarkdownローダーがHTMLコメントを削除しないか

まずは代表的な数ファイルを変換し、RAG検索結果の出典表示と回答品質を確認することをおすすめします。

## 再現性について

出力には `converter_version` と `source_sha256` を入れています。再変換時の差分を追う場合は、入力PDF、依存バージョン、実行オプションを固定してください。

## 開発

コード変更後は以下を実行します。

```powershell
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
uv run pytest
```
