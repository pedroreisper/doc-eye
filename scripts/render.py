#!/usr/bin/env python3
"""render.py — convert a document to per-page PNGs.

Reads env vars: INPUT, RENDER_DIR, DPI.
For .docx/.pptx, first converts to PDF via `soffice --headless`, then
rasterises with PyMuPDF. For .pdf, rasterises directly.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def die(msg: str, code: int = 1) -> None:
    print(f"render.py: {msg}", file=sys.stderr)
    sys.exit(code)


def soffice_convert_to_pdf(input_path: Path, work_dir: Path) -> Path:
    """Convert DOCX/PPTX/ODT to PDF via headless LibreOffice."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        die(
            "soffice not found on PATH. Install LibreOffice "
            "(`brew install --cask libreoffice`) and retry."
        )
    # Per-process profile dir so concurrent invocations don't clash.
    profile = tempfile.mkdtemp(prefix="doc-eye-lo-")
    cmd = [
        soffice,
        f"-env:UserInstallation=file://{profile}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(work_dir),
        str(input_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        die("soffice conversion timed out after 120s.")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"soffice exit {r.returncode}: {r.stderr.strip()[:400]}")
    pdf = work_dir / (input_path.stem + ".pdf")
    if not pdf.exists():
        die(f"soffice produced no PDF for {input_path.name}")
    return pdf


def rasterise(pdf: Path, out_dir: Path, dpi: int) -> int:
    """Render every PDF page as PNG into out_dir using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        die("PyMuPDF not installed. Run `pip install pymupdf` and retry.")

    doc = fitz.open(str(pdf))
    if doc.is_encrypted:
        if doc.needs_pass:
            die(
                f"PDF is encrypted with a password. Provide a decrypted copy "
                f"(file: {pdf.name})."
            )
        # Read-only encryption — try to open anonymously
        if not doc.authenticate(""):
            die(f"PDF is encrypted; cannot open: {pdf.name}")

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out = out_dir / f"page-{i:03d}.png"
        pix.save(str(out))
    n = doc.page_count
    doc.close()
    return n


def main() -> None:
    input_str = os.environ.get("INPUT")
    render_dir_str = os.environ.get("RENDER_DIR")
    dpi_str = os.environ.get("DPI", "200")
    if not input_str or not render_dir_str:
        die("missing INPUT or RENDER_DIR env vars")
    try:
        dpi = int(dpi_str)
    except ValueError:
        die(f"invalid DPI: {dpi_str}")
    if dpi < 72 or dpi > 600:
        die(f"DPI out of range (72-600): {dpi}")

    input_path = Path(input_str).resolve()
    render_dir = Path(render_dir_str).resolve()
    render_dir.mkdir(parents=True, exist_ok=True)

    ext = input_path.suffix.lower()
    work = Path(tempfile.mkdtemp(prefix="doc-eye-render-"))
    try:
        if ext == ".pdf":
            pdf = input_path
        elif ext in (".docx", ".doc", ".pptx", ".ppt", ".odt", ".odp"):
            pdf = soffice_convert_to_pdf(input_path, work)
        else:
            die(f"unsupported format: {ext} (use .pdf, .docx, or .pptx)")
        n = rasterise(pdf, render_dir, dpi)
        print(f"rendered {n} page(s)", file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
