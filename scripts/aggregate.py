#!/usr/bin/env python3
"""aggregate.py — collapse per-page findings into audit-report.json.

Reads env vars: RAW_FINDINGS, REPORT_JSON, SOURCE_FILE, PAGE_COUNT, MODEL.

Dedup logic:
1. Findings with the same (category, subcategory or description-prefix) on
   multiple pages collapse into one document-level finding with pages: [...].
2. Per-page findings that did NOT match a document-level cluster stay per-page.
3. The verdict is derived deterministically from severity counts.

Verdict states (per output-schema.json):
- CLEAN — no findings of any kind
- FINDINGS_PRESENT — any critical/warning/info finding
- PARTIAL — some pages skipped but others audited cleanly
- AUDIT_FAILED — every page errored; verdict cannot be trusted
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path


def die(msg: str, code: int = 1) -> None:
    print(f"aggregate.py: {msg}", file=sys.stderr)
    sys.exit(code)


def fingerprint(f: dict) -> str:
    cat = f.get("category", "?")
    sub = f.get("subcategory", "") or f.get("description", "")[:60]
    return f"{cat}::{sub.strip().lower()[:80]}"


def main() -> None:
    raw_path = os.environ.get("RAW_FINDINGS")
    out_path = os.environ.get("REPORT_JSON")
    source_file = os.environ.get("SOURCE_FILE", "")
    page_count_str = os.environ.get("PAGE_COUNT", "0")
    model = os.environ.get("MODEL", "")
    if not raw_path or not out_path:
        die("missing RAW_FINDINGS or REPORT_JSON env vars")
    page_count = int(page_count_str) if page_count_str else 0

    raw_rows: list[dict] = []
    for line in Path(raw_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw_rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Merge placeholder pre-pass findings (no API cost) into the raw rows.
    # They look like per-page findings emitted from text extraction.
    work_dir = os.path.dirname(raw_path)
    placeholder_path = os.path.join(work_dir, "placeholder-findings.json")
    if os.path.exists(placeholder_path):
        try:
            ph = json.loads(Path(placeholder_path).read_text(encoding="utf-8") or "[]")
            # Group by page and append as a synthetic raw_rows entry per page.
            by_page: dict[int, list[dict]] = {}
            for f in ph:
                p = int(f.get("page", 0))
                by_page.setdefault(p, []).append({
                    "category": f.get("category", "CONTENT"),
                    "subcategory": f.get("subcategory", "placeholder-leftover"),
                    "severity": f.get("severity", "warning"),
                    "description": f.get("description", ""),
                    "quoted_text": f.get("quoted_text", ""),
                    "location": f"line {f.get('line', '?')}",
                })
            for p, findings in by_page.items():
                raw_rows.append({"page": p, "findings": findings, "page_ok": False, "_source": "placeholder-prepass"})
        except Exception as e:
            print(f"  warning: could not merge placeholder findings: {e}", file=sys.stderr)

    # group identical-fingerprint findings across pages
    clusters: dict[str, dict] = defaultdict(lambda: {"pages": [], "findings": []})
    page_findings: list[dict] = []
    skipped_pages: list[int] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for row in raw_rows:
        if "_error" in row:
            skipped_pages.append(row.get("page", -1))
        usage = row.get("_usage", {})
        total_input_tokens += int(usage.get("input_tokens", 0) or 0)
        total_output_tokens += int(usage.get("output_tokens", 0) or 0)
        p_num = row.get("page")
        f_list = row.get("findings", []) or []
        page_findings.append({"page": p_num, "findings": f_list})
        for f in f_list:
            fp = fingerprint(f)
            clusters[fp]["pages"].append(p_num)
            clusters[fp]["findings"].append({**f, "page": p_num})

    document_findings: list[dict] = []
    for fp, c in clusters.items():
        pages = sorted(set(c["pages"]))
        if len(pages) >= 2:
            first = c["findings"][0]
            document_findings.append({
                "category": first.get("category", "?"),
                "subcategory": first.get("subcategory", ""),
                "severity": first.get("severity", "warning"),
                "pages": pages,
                "description": first.get("description", ""),
                "location": first.get("location", ""),
                "quoted_text": first.get("quoted_text", ""),
                "occurrences": len(c["findings"]),
            })

    # severity counts (sum across page-level findings; deduped document findings still
    # count once per finding instance to reflect total visible-rot count)
    counts = {"critical": 0, "warning": 0, "info": 0}
    for pf in page_findings:
        for f in pf["findings"]:
            sev = f.get("severity", "warning")
            if sev in counts:
                counts[sev] += 1

    # AUDIT_FAILED: every single audited page errored — verdict cannot be trusted.
    audited_count = max(1, len(raw_rows))
    all_failed = skipped_pages and len(skipped_pages) >= audited_count
    if all_failed:
        verdict = "AUDIT_FAILED"
    elif counts["critical"] > 0:
        verdict = "FINDINGS_PRESENT"
    elif skipped_pages:
        verdict = "PARTIAL"
    elif counts["warning"] > 0 or counts["info"] > 0:
        verdict = "FINDINGS_PRESENT"
    else:
        verdict = "CLEAN"

    report = {
        "schema_version": "doc-eye-report-v1",
        "source_file": source_file,
        "rendered_pages": page_count,
        "audited_pages": len(raw_rows),
        "audit_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model,
        "verdict": verdict,
        "summary_counts": counts,
        "document_findings": document_findings,
        "page_findings": page_findings,
        "skipped_pages": skipped_pages,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
    }
    Path(out_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
