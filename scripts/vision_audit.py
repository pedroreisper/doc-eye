#!/usr/bin/env python3
"""vision_audit.py — per-page vision audit via the Anthropic API.

Reads env vars: RENDER_DIR, RAW_FINDINGS, MODEL, MAX_PAGES, SAMPLE, ONLY,
                SOURCE_FILE, PAGE_COUNT.

For each page PNG, posts one Anthropic message with the image plus an
audit rubric and a forced tool-use schema. Appends one JSON line per page
to RAW_FINDINGS.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    from anthropic import Anthropic
    from anthropic import APIError, APIStatusError, APITimeoutError
except ImportError:
    print(
        "vision_audit.py: anthropic SDK not installed. "
        "Run `pip install --user --break-system-packages anthropic`.",
        file=sys.stderr,
    )
    sys.exit(1)


# Tool schema — forced JSON output via tool_use.
TOOL = {
    "name": "record_findings",
    "description": "Record visual / structural findings for this document page.",
    "input_schema": {
        "type": "object",
        "required": ["page", "findings", "page_ok"],
        "properties": {
            "page": {"type": "integer", "minimum": 1},
            "page_ok": {"type": "boolean"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["category", "severity", "description"],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "FORMATTING",
                                "TYPOGRAPHY",
                                "COLOUR",
                                "CONTENT",
                                "LAYOUT",
                                "VISUAL_COHERENCE",
                            ],
                        },
                        "subcategory": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "info"],
                        },
                        "location": {
                            "type": "string",
                            "description": "Rough page region: top-left, top-right, middle, bottom, full-page, etc.",
                        },
                        "description": {"type": "string"},
                        "quoted_text": {
                            "type": "string",
                            "description": "Exact text visible on the page that the finding refers to, if applicable.",
                        },
                    },
                },
            },
        },
    },
}


SYSTEM_PROMPT = """You are a meticulous document-quality reviewer auditing a single page of a rendered document.

You audit for SIX defect categories:
- FORMATTING: margins, indents, alignment, line spacing, page breaks in wrong place, missing/duplicate headers/footers
- TYPOGRAPHY: font mixing, inconsistent sizes, orphans/widows, hyphenation errors, bold/italic inconsistency
- COLOUR: accidental coloured runs in body text, contrast issues, palette drift
- CONTENT: typos, broken cross-references (e.g. "see Figure 3" when no Figure 3 on this page and no clear forward/back ref), placeholder text (Lorem ipsum, TODO, [insert], XXX)
- LAYOUT: SmartArt or images clipped at page edge, blank pages, tables overflowing, awkward whitespace
- VISUAL_COHERENCE: numbered lists with mixed schemes, captions disconnected from figures, inconsistent heading styles

Rules:
1. ONLY flag what you can SEE on the page. Do not speculate.
2. Severity: critical = must fix; warning = should fix; info = worth knowing.
3. If the page looks clean, return findings=[] and page_ok=true.
4. Do NOT comment on content correctness (whether facts/numbers are right) — only visual + structural.
5. Output ONLY via the record_findings tool. No prose, no apologies, no follow-up questions.
6. If categories are restricted in the user message, only emit findings in those categories.
"""


def die(msg: str, code: int = 1) -> None:
    print(f"vision_audit.py: {msg}", file=sys.stderr)
    sys.exit(code)


def select_pages(page_files: list[Path], max_pages: int | None, sample: bool) -> list[Path]:
    n = len(page_files)
    if max_pages and max_pages > 0:
        return page_files[:max_pages]
    if sample and n > 16:
        head = page_files[:10]
        tail = page_files[-5:]
        mid = page_files[10:-5:5]
        return list(dict.fromkeys(head + mid + tail))
    return page_files


def page_message(image_b64: str, page_num: int, total: int, only_cats: str) -> list[dict]:
    text = f"Page {page_num} of {total}."
    if only_cats:
        text += f"\nRestrict findings to these categories ONLY: {only_cats}."
    text += "\nAudit this page. Call record_findings with what you see."
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_b64,
            },
        },
        {"type": "text", "text": text},
    ]


def extract_tool_input(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    return None


def audit_page(client: Anthropic, model: str, page_path: Path, page_num: int, total: int, only_cats: str, retries: int = 2) -> dict:
    b64 = base64.b64encode(page_path.read_bytes()).decode("ascii")
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": "record_findings"},
                messages=[{"role": "user", "content": page_message(b64, page_num, total, only_cats)}],
            )
        except (APITimeoutError, APIStatusError, APIError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  page {page_num}: API error ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        out = extract_tool_input(response)
        if out is None:
            last_err = RuntimeError("model did not call record_findings")
            continue
        out.setdefault("page", page_num)
        out.setdefault("findings", [])
        out.setdefault("page_ok", len(out["findings"]) == 0)
        out["_usage"] = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }
        return out
    return {
        "page": page_num,
        "findings": [],
        "page_ok": False,
        "_error": str(last_err) if last_err else "unknown",
    }


def main() -> None:
    render_dir = os.environ.get("RENDER_DIR")
    raw_findings = os.environ.get("RAW_FINDINGS")
    model = os.environ.get("MODEL", "claude-haiku-4-5")
    max_pages_str = os.environ.get("MAX_PAGES", "")
    sample = bool(os.environ.get("SAMPLE", ""))
    only_cats = os.environ.get("ONLY", "")
    if not render_dir or not raw_findings:
        die("missing RENDER_DIR or RAW_FINDINGS env vars")
    max_pages = int(max_pages_str) if max_pages_str else None

    page_files = sorted(Path(render_dir).glob("page-*.png"))
    if not page_files:
        die(f"no page-*.png files found in {render_dir}")
    pages_to_audit = select_pages(page_files, max_pages, sample)

    client = Anthropic()
    print(f"  auditing {len(pages_to_audit)}/{len(page_files)} page(s) with model={model}", file=sys.stderr)

    with open(raw_findings, "w") as fh:
        for page_path in pages_to_audit:
            page_num = int(page_path.stem.split("-")[1])
            print(f"  > page {page_num}", file=sys.stderr)
            result = audit_page(client, model, page_path, page_num, len(page_files), only_cats)
            fh.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
