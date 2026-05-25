---
name: doc-eye
description: Audits a Word (.docx), PowerPoint (.pptx), or PDF document the way a human reviewer would — renders every page as an image and runs a vision-capable Claude over each page to catch formatting drift, typography mixing, broken cross-references, SmartArt overflow, blank pages, colour rot, orphans/widows, placeholder text, and visual incoherence. Use after generating a document, before sending it, or when "the code is right but the rendered output looks wrong". Triggers — "audit this PDF", "audita este Word", "review the rendered doc", "doc-eye", "check the document visually", "look at the rendered output", "the PDF looks off", "is the layout broken", "está bem formatado", "verifica o documento". NOT a content reviewer for clinical correctness or scientific argument (use scientific-manuscript-reviewer) — this is purely about visual + structural fidelity of the rendered page.
license: MIT
metadata:
  version: "1.0.0"
  priority: "8"
  audience: "claude-code"
---

# doc-eye — vision-LLM audit of rendered document pages

Claude is excellent at code-level edits to source files but blind to the visually-rendered output. SmartArt clips at the page edge. Fonts drift across sections. A heading falls into a widow on page 7. The XML looks correct; the PDF looks wrong. This skill closes that gap.

It takes a `.docx`, `.pptx`, or `.pdf`, renders every page to a PNG at print DPI, and feeds each page to a vision-capable Claude with a structured rubric. The output is a JSON report (machine-readable) plus a prose render (human-readable) that lists every finding with page number, location, severity, and a concrete description.

The skill reports — it does not modify the source file. It is a reviewer, not a fixer. You decide what to do with the findings.

## Core pipeline

```
ingest → render → per-page vision audit → aggregate + dedup → report
```

1. **Ingest** — detect format (`.docx`/`.pptx`/`.pdf`), reject encrypted PDFs early, copy to a temp workspace.
2. **Render** — DOCX/PPTX → PDF via `soffice --headless`, then PDF → PNG per page via PyMuPDF (200 DPI default). Output: `pages/page-001.png … page-NNN.png`.
3. **Per-page vision audit** — one Anthropic API call per page to Claude (Haiku 4.5 by default; Opus 4.7 with `--opus`). Forced tool use returns structured JSON per page.
4. **Aggregate + dedup** — collapse repeated findings (e.g. same broken header on every page → one document-level finding with `pages: [1,2,3,…]`).
5. **Report** — write `audit-report.json` (schema in `references/output-schema.json`) and render a prose summary.

## Defect taxonomy

Six categories. Each finding is one of:

- **FORMATTING** — margins, indents, alignment, line spacing, page breaks in the wrong place, headers/footers missing or duplicated
- **TYPOGRAPHY** — font mixing across the doc, inconsistent sizes, orphan/widow lines, hyphenation errors
- **COLOUR** — accidental coloured runs in body text, contrast issues, palette drift from spec
- **CONTENT** — typos, broken cross-references ("see Figure 3" with no Figure 3), placeholder text like "Lorem ipsum" / "TODO" / "[insert]"
- **LAYOUT** — SmartArt or images clipped at the page edge, blank pages, content shifted across pages by reflow, tables overflowing
- **VISUAL_COHERENCE** — numbered lists with mixed schemes, captions disconnected from figures, inconsistent heading styles

Severity is `critical` (must fix before sending), `warning` (should fix), or `info` (worth knowing).

Full per-category definitions and edge cases live in `references/audit-categories.md`.

## Usage

```bash
# basic
bash scripts/audit.sh path/to/document.pdf
bash scripts/audit.sh path/to/manual.docx

# choose a different model
bash scripts/audit.sh manual.docx --model claude-opus-4-7
bash scripts/audit.sh manual.docx --opus            # shortcut

# limit pages (default: audit all)
bash scripts/audit.sh long.pdf --max-pages 20
bash scripts/audit.sh long.pdf --sample              # 10 first + 5 last + every 5th in between

# scope categories
bash scripts/audit.sh manual.docx --only LAYOUT,TYPOGRAPHY

# keep rendered PNGs after the run (for inspection)
bash scripts/audit.sh manual.docx --keep-renders

# JSON-only output (for piping)
bash scripts/audit.sh manual.docx --format json
```

The audit writes to `.doc-eye/<basename>/audit-report.json` next to your invocation cwd. The prose render goes to stdout.

## When to use

- Before sending any document to a stakeholder (client, regulator, journal, IRB).
- After programmatic generation (LaTeX, python-pptx, mail-merge, template fill).
- After a multi-edit session on a Word doc where you can't easily eyeball every page.
- As a `delegate: doc-eye` review criterion inside a `did-it-actually` contract.
- When a user says "the doc looks weird" and you can't see why.

## When NOT to use

- Single-page documents you can look at in 2 seconds.
- Source-level code review — that's `/code-review`.
- Scientific content correctness — that's `scientific-manuscript-reviewer`.
- Brand-guideline conformance check on marketing assets — that's a separate brand-audit skill.
- Scanned/image-only PDFs without OCR — the skill flags `⚠️ ocr-required` and skips text-content checks.

## Cost + performance

- **Haiku 4.5 default**: ~$0.006 per page (≈ 4800 in tokens + ~200 out). A 50-page doc ≈ $0.30, ~30 seconds.
- **Opus 4.7 with `--opus`**: ~$0.029 per page. A 50-page doc ≈ $1.50, ~90 seconds.
- Haiku is sufficient for typography/layout/typo audit. Reserve Opus for argument-level review (you probably want a different skill then).

`audit.sh` prints an estimated cost before the audit phase and refuses to proceed on >$1 runs without `DOC_EYE_NO_CONFIRM=1` or an interactive `y` confirmation.

Rendered PNGs are written to `.doc-eye/<basename>/pages/` and removed at end-of-run unless `--keep-renders` is passed.

## Honest limits

- **SmartArt fidelity**: LibreOffice headless rendering is not byte-identical to Word for SmartArt. The skill flags this in the report header — read findings on SmartArt with healthy scepticism.
- **Vision is not OCR-grade**: Claude vision reads text from page images but misses very small text or low-contrast scans. Don't use this for proofreading body-text typos on a 50-page doc — use a text-based spell-checker for that.
- **One page at a time**: the audit doesn't see facing-page spreads or two-up layouts as continuous. Spread-aware analysis is out of scope.
- **No semantic content check**: the skill catches "see Figure 3" with no Figure 3 because both are visually present. It does NOT verify that Figure 3 *says the right thing* — that's a content review, not a visual one.

## Integration with did-it-actually

If you use `did-it-actually` for request-fidelity audits, you can express "the rendered doc must have no critical visual defects" as a contract criterion:

```yaml
- id: manual-renders-cleanly
  intent: the exported PDF has no critical visual defects
  type: review
  spec:
    delegate: doc-eye
    target: exports/manual.pdf
    max_severity_allowed: warning
  severity: critical
```

`audit.sh run` in did-it-actually will invoke `doc-eye`, parse its `audit-report.json`, and translate the verdict into the criterion result. See `references/did-it-actually-bridge.md` for the wiring.

## Requirements

- Python 3.10+ with `pymupdf` and `anthropic` (auto-installed by `install.sh`)
- LibreOffice (`soffice` on PATH) for DOCX/PPTX rendering — `brew install --cask libreoffice`
- `ANTHROPIC_API_KEY` env var (the skill calls the Anthropic API directly)
- macOS or Linux — Windows untested

Run `bash scripts/doctor.sh` after install to verify everything's wired up.

## Reference index

- `references/audit-categories.md` — full defect taxonomy with examples
- `references/vision-prompt-template.md` — exact per-page prompt sent to Claude
- `references/output-schema.json` — JSON Schema for `audit-report.json`
- `references/edge-cases.md` — encrypted PDFs, scanned docs, RTL languages, monorepos of docs
- `references/did-it-actually-bridge.md` — how to delegate from a contract criterion
- `scripts/audit.sh` — main driver (ingest → render → placeholder pre-pass → vision audit → aggregate → report)
- `scripts/render.py` — DOCX/PPTX → PDF → PNG via soffice + PyMuPDF (handles format detection inline)
- `scripts/placeholder_scan.py` — cheap text-extraction pre-pass for placeholders (no API cost)
- `scripts/vision_audit.py` — per-page Claude vision calls with forced tool use
- `scripts/aggregate.py` — dedup + scoring + verdict
- `scripts/report.py` — JSON → prose
- `scripts/doctor.sh` — self-diagnostic
- `install.sh` — one-liner installer
