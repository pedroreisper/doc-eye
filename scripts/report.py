#!/usr/bin/env python3
"""report.py — render audit-report.json as a human-readable prose summary."""
from __future__ import annotations

import json
import sys
from pathlib import Path


GLYPH = {"critical": "❌", "warning": "⚠️ ", "info": "•"}
LINE = "─" * 60


def main(path: str) -> None:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    src = r.get("source_file", "?")
    out: list[str] = []
    out.append("DOC-EYE — visual audit report")
    out.append(LINE)
    out.append(f"Source:        {src}")
    out.append(f"Model:         {r.get('model', '?')}")
    out.append(f"Pages:         {r.get('audited_pages', 0)} audited / {r.get('rendered_pages', 0)} rendered")
    counts = r.get("summary_counts", {})
    out.append(f"Findings:      ❌ {counts.get('critical', 0)} critical   ⚠️  {counts.get('warning', 0)} warning   • {counts.get('info', 0)} info")
    usage = r.get("usage", {})
    if usage:
        out.append(f"Token usage:   {usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out")
    out.append("")

    # Document-level findings (multi-page patterns)
    doc_findings = r.get("document_findings", []) or []
    out.append(f"DOCUMENT-LEVEL FINDINGS ({len(doc_findings)})")
    out.append(LINE)
    if not doc_findings:
        out.append("  (none)")
    else:
        for f in doc_findings:
            glyph = GLYPH.get(f.get("severity", "warning"), "•")
            cat = f.get("category", "?")
            pages = f.get("pages", [])
            page_summary = (
                f"pp. {pages[0]}-{pages[-1]} ({len(pages)} occurrences)"
                if len(pages) > 3
                else "pp. " + ", ".join(str(p) for p in pages)
            )
            out.append(f"  {glyph} [{cat}] {page_summary}")
            out.append(f"      {f.get('description', '').strip()}")
            if f.get("location"):
                out.append(f"      location: {f['location']}")
            if f.get("quoted_text"):
                out.append(f"      text:     \"{f['quoted_text'][:120]}\"")
            out.append("")

    # Per-page findings (single-page only — multi-page already in doc-level)
    page_findings = r.get("page_findings", []) or []
    page_only: list[dict] = []
    doc_fingerprints = {
        (df.get("category"), df.get("description", "")[:60].lower())
        for df in doc_findings
    }
    for pf in page_findings:
        single = []
        for f in pf.get("findings", []) or []:
            fp = (f.get("category"), f.get("description", "")[:60].lower())
            if fp not in doc_fingerprints:
                single.append(f)
        if single:
            page_only.append({"page": pf["page"], "findings": single})

    out.append(f"PER-PAGE FINDINGS ({sum(len(p['findings']) for p in page_only)})")
    out.append(LINE)
    if not page_only:
        out.append("  (none)")
    else:
        for pf in page_only:
            out.append(f"  Page {pf['page']}:")
            for f in pf["findings"]:
                glyph = GLYPH.get(f.get("severity", "warning"), "•")
                cat = f.get("category", "?")
                out.append(f"    {glyph} [{cat}] {f.get('description', '').strip()}")
                if f.get("quoted_text"):
                    out.append(f"        text: \"{f['quoted_text'][:100]}\"")
            out.append("")

    skipped = r.get("skipped_pages", []) or []
    if skipped:
        out.append(f"SKIPPED PAGES (API or render error): {skipped}")
        out.append("")

    out.append(LINE)
    out.append(f"VERDICT: {r.get('verdict', '?')}")
    print("\n".join(out))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: report.py <audit-report.json>")
    main(sys.argv[1])
