#!/usr/bin/env python3
"""placeholder_scan.py — cheap text-extraction sweep for placeholder strings.

Runs BEFORE the vision audit. PyMuPDF's text extraction is free (no API cost),
so we use it to catch the cheapest, highest-frequency defect class:
placeholder text Claude (or a template) left in the document.

Calibrated against patterns extracted from real Pedro sessions where final
documents shipped with `FALAR DE PRAL AQUI`, `CITATION`, `SINTETIZAR
EXTREMAMENTE BEM`, `Absctract`, etc.

Reads env: RENDER_DIR, INPUT, OUT_PATH.
Writes a JSON list of findings to OUT_PATH (one entry per match) — the
aggregator can merge these with vision findings.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


# Calibrated against real Pedro session failures + standard placeholder lexicon.
# Each regex is matched case-INSENSITIVELY against per-page text.
PLACEHOLDER_PATTERNS = [
    (r"\bTODO\b",                          "TODO marker"),
    (r"\bFIXME\b",                         "FIXME marker"),
    (r"\bTBD\b",                           "TBD marker"),
    (r"\bXXX\b",                           "XXX marker"),
    (r"\bNOCOMMIT\b",                      "NOCOMMIT marker"),
    (r"\bCITATION\b",                      "literal 'CITATION' placeholder"),
    (r"\bCITAÇ[ÃA]O\b",                    "literal 'CITAÇÃO' placeholder"),
    (r"\bFALAR DE\b",                      "PT placeholder 'FALAR DE'"),
    (r"\bSINTETIZAR\b",                    "PT placeholder 'SINTETIZAR'"),
    (r"\blorem ipsum\b",                   "lorem ipsum"),
    (r"\[insert[^\]]*\]",                  "[insert ...] placeholder"),
    (r"\[your[^\]]*\]",                    "[your ...] placeholder"),
    (r"\[name\]|\[date\]|\[address\]",     "[name]/[date]/[address] placeholder"),
    (r"\{\{[^}]+\}\}",                     "{{template variable}} not rendered"),
    (r"\{[A-Z_ ]{4,}\}",                   "{TEMPLATE_VAR} not rendered"),
    (r"\bplaceholder\b",                   "literal 'placeholder' word"),
    (r"^\s*\[\s*\]\s*$",                   "empty [ ] field"),
    # Typo-frozen-in-headings (Pedro example: "Absctract" — capture mirror typos
    # via the heuristic: words that contain unusual consonant clusters AND are
    # near-misses to known section names)
    (r"\bAbsctract\b",                     "typo: 'Absctract' (should be 'Abstract')"),
    (r"\bIntroducti?on\s*[?:]?\s*$",       "heading 'Introduction' on its own line — possibly stub"),
]


def find_placeholder_matches(text: str) -> list[dict]:
    """Return one finding per (pattern, line) match."""
    findings = []
    if not text:
        return findings
    lines = text.splitlines()
    for line_num, line in enumerate(lines, start=1):
        for pattern, label in PLACEHOLDER_PATTERNS:
            for m in re.finditer(pattern, line, flags=re.IGNORECASE | re.MULTILINE):
                findings.append({
                    "category": "CONTENT",
                    "subcategory": "placeholder-leftover",
                    "severity": "critical" if "TODO" in label or "CITATION" in label or "FALAR" in label or "SINTETIZAR" in label else "warning",
                    "description": f"{label} on this page",
                    "quoted_text": line.strip()[:160],
                    "line": line_num,
                    "match": m.group(0)[:80],
                })
    return findings


def extract_page_text(pdf_path: Path) -> list[str]:
    """Extract per-page text from a PDF via PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"placeholder_scan: failed to open {pdf_path}: {e}", file=sys.stderr)
        return []
    out = []
    for page in doc:
        try:
            out.append(page.get_text("text"))
        except Exception:
            out.append("")
    doc.close()
    return out


def main() -> None:
    input_path = os.environ.get("INPUT")
    render_dir = os.environ.get("RENDER_DIR", "")
    out_path = os.environ.get("OUT_PATH")
    if not input_path or not out_path:
        print("placeholder_scan: missing INPUT or OUT_PATH env vars", file=sys.stderr)
        sys.exit(1)

    input_path = Path(input_path)
    ext = input_path.suffix.lower()

    # We only run the cheap text extraction on the PDF (either the original or
    # the soffice-rendered one). If the source is .docx/.pptx and we have a
    # render dir, prefer the PDF that should be alongside the PNGs (parent of
    # render dir / sibling).
    pdf_to_scan: Path | None = None
    if ext == ".pdf":
        pdf_to_scan = input_path
    else:
        # The render.py path puts the converted PDF in a tempdir; we don't have
        # easy access to it post-render. Fall back to converting again ourselves
        # ONLY if asked. For now, skip non-PDF placeholder scans — the vision
        # pass picks them up at higher cost.
        print(
            f"placeholder_scan: skipping non-PDF input ({ext}); vision pass will catch placeholders.",
            file=sys.stderr,
        )
        Path(out_path).write_text("[]", encoding="utf-8")
        return

    page_texts = extract_page_text(pdf_to_scan)
    all_findings = []
    for i, text in enumerate(page_texts, start=1):
        for f in find_placeholder_matches(text):
            f["page"] = i
            all_findings.append(f)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
    print(
        f"placeholder_scan: {len(all_findings)} placeholder match(es) across {len(page_texts)} page(s)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
