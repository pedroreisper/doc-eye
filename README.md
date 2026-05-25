# doc-eye

> Claude reads your code well but doesn't *look* at the rendered PDF. This skill makes it look.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## The pain it solves

You wrote the LaTeX. You ran `pandoc`. You hit "Save as PDF". The source is right. The PDF has SmartArt clipping off the page, a heading orphaned on page 7, and `Lorem ipsum` still on page 3 because the template variable never got filled in.

Claude can read your `.tex` source. Claude cannot *see* the rendered page. So Claude says "looks good" while the PDF looks broken.

**doc-eye** closes that gap. It renders every page of a Word, PowerPoint, or PDF document, feeds each page to Claude's vision model with a structured rubric, and emits a per-page report of formatting, typography, colour, content, layout, and visual-coherence defects.

It catches what a meticulous human reviewer would catch in a 5-second skim per page — except across 50 pages, in 30 seconds, for 10 cents.

## What it catches

- **FORMATTING** — margins, indents, alignment, line spacing, broken page breaks, missing/duplicate headers
- **TYPOGRAPHY** — font mixing, inconsistent sizes, orphan/widow lines, hyphenation
- **COLOUR** — accidental coloured runs, low-contrast text, palette drift
- **CONTENT** — typos, broken cross-references, leftover `TODO` / `Lorem ipsum` placeholders
- **LAYOUT** — SmartArt overflow, blank pages, tables overflowing margins, disconnected captions
- **VISUAL_COHERENCE** — mixed numbering schemes, inconsistent heading styles, footnote/anchor mismatches

It does NOT:
- Review code or source — that's `/code-review`
- Check clinical / scientific correctness — that's `scientific-manuscript-reviewer`
- OCR scanned PDFs (it can still audit layout on them, but won't proofread the scanned text)
- Propose fixes — reports only; you decide what to do

## Install

```bash
git clone https://github.com/pedroreisper/doc-eye
cd doc-eye
less install.sh         # 80 lines, no obfuscation
bash install.sh
```

One-liner if you trust the source:

```bash
curl -fsSL https://raw.githubusercontent.com/pedroreisper/doc-eye/main/install.sh | bash
```

Set your API key (the skill calls the Anthropic API directly):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Verify:

```bash
bash ~/.claude/skills/doc-eye/scripts/doctor.sh
```

Project-scoped (team-shared via your repo):

```bash
bash install.sh --project
```

## Requirements

- Python 3.10+
- `pymupdf` and `anthropic` Python packages (auto-installed)
- `soffice` (LibreOffice) for `.docx`/`.pptx` rendering: `brew install --cask libreoffice` on macOS, `apt install libreoffice` on Debian/Ubuntu
- `ANTHROPIC_API_KEY` env var
- macOS or Linux

The `doctor.sh` self-diagnostic confirms each of these.

## Usage

```bash
# basic
bash scripts/audit.sh path/to/document.pdf
bash scripts/audit.sh path/to/manual.docx

# use Opus instead of default Haiku (more expensive, better for nuance)
bash scripts/audit.sh manual.docx --opus

# audit only a subset of pages
bash scripts/audit.sh long.pdf --max-pages 10
bash scripts/audit.sh long.pdf --sample              # first 10 + last 5 + every 5th in between

# restrict to specific defect categories
bash scripts/audit.sh manual.docx --only LAYOUT,TYPOGRAPHY

# JSON output (for piping into other tools)
bash scripts/audit.sh manual.docx --format json | jq '.summary_counts'

# keep the rendered PNGs for inspection
bash scripts/audit.sh manual.docx --keep-renders
```

The audit writes `.doc-eye/<basename>/audit-report.json` next to your cwd.

## Cost

| Model | Per page | 50-page doc | Best for |
|---|---|---|---|
| `claude-haiku-4-5` (default) | ~$0.006 | ~$0.30 | Typography, layout, typos |
| `claude-sonnet-4-6` | ~$0.018 | ~$0.90 | + nuanced visual coherence |
| `claude-opus-4-7` (`--opus`) | ~$0.029 | ~$1.45 | + argument-level visual analysis |

Haiku is usually enough. Reserve Opus for documents where the cost of a missed defect is high (regulatory submissions, journal manuscripts).

`audit.sh` prints an estimated cost before the audit phase. Estimates over $1 require either `DOC_EYE_NO_CONFIRM=1` or an interactive `y` confirmation — protects against accidental `--opus` on huge docs.

A free placeholder pre-pass (PyMuPDF text extraction, no API cost) runs before the vision phase and catches the cheapest, highest-frequency defect class: leftover `TODO`, `CITATION`, `Lorem ipsum`, `{{template_var}}`, `[insert]`, `FALAR DE`, `SINTETIZAR`, etc. Calibrated against real failure patterns.

## Example output

```
DOC-EYE — visual audit report
────────────────────────────────────────────────────────────
Source:        exports/Manual_NC_v4.docx
Model:         claude-haiku-4-5
Pages:         42 audited / 42 rendered
Findings:      ❌ 3 critical   ⚠️  11 warning   • 4 info
Token usage:   201840 in / 4218 out

DOCUMENT-LEVEL FINDINGS (2)
────────────────────────────────────────────────────────────
  ❌ [LAYOUT] pp. 7, 12, 19
      Diagram box text clips at the right edge of the page (consistent SmartArt overflow).
      location: top-right quadrant

  ⚠️  [TYPOGRAPHY] pp. 3, 5, 11, 14, 22, 30 (6 occurrences)
      Body text mixes Calibri 11pt with Liberation Serif 11pt across paragraphs.

PER-PAGE FINDINGS (5)
────────────────────────────────────────────────────────────
  Page 8:
    ❌ [CONTENT] Placeholder text "TODO: insert reference" left in body.
        text: "TODO: insert reference here"
  Page 23:
    ⚠️  [TYPOGRAPHY] Widow line: last line of paragraph alone at bottom of page.
        text: "...portanto a conclusão é"
  ...

────────────────────────────────────────────────────────────
VERDICT: FINDINGS_PRESENT
```

## Integration with did-it-actually

If you use [`did-it-actually`](https://github.com/pedroreisper/did-it-actually) for request-fidelity audits, the result of a doc-eye audit can be a `must_review` criterion in your contract — see [`references/did-it-actually-bridge.md`](references/did-it-actually-bridge.md).

## Honest limits

- **SmartArt fidelity** — LibreOffice headless is not byte-identical to Word for SmartArt. If your doc has lots of SmartArt, prefer to export the PDF from Word directly (File → Save As → PDF) and feed that PDF.
- **Not OCR-grade** — Claude vision reads text from images well but isn't a substitute for spell-check on long body text. Use a text-based spell-checker alongside.
- **One page at a time** — no facing-page-spread awareness in v1.
- **Stateless across pages** — each page is audited independently. Multi-page patterns are caught by post-hoc fingerprint deduplication, not by passing context between calls.

See [`references/edge-cases.md`](references/edge-cases.md) for the full taxonomy.

## Layout

```
doc-eye/
├── SKILL.md                              # entry point
├── README.md
├── LICENSE
├── install.sh
├── references/
│   ├── audit-categories.md               # full defect taxonomy
│   ├── vision-prompt-template.md         # per-page prompt + tool schema
│   ├── output-schema.json                # JSON Schema for audit-report.json
│   ├── edge-cases.md                     # encrypted PDFs, scans, RTL, monorepos
│   └── did-it-actually-bridge.md         # composability with did-it-actually
└── scripts/
    ├── audit.sh                          # main driver
    ├── render.py                         # DOCX/PPTX → PDF → PNG via PyMuPDF
    ├── vision_audit.py                   # per-page vision calls (forced tool use)
    ├── aggregate.py                      # dedup + scoring → audit-report.json
    ├── report.py                         # JSON → prose
    └── doctor.sh                         # self-diagnostic
```

## Contributing

Two things especially valuable:

1. **Fixtures** — add a `.docx` or `.pdf` with a known defect to `examples/` and a corresponding expected-finding note. Helps regression-test prompt changes.
2. **New categories or sub-categories** — propose via issue. Edits to the category set are a breaking change to the report schema (bump version).

## License

[MIT](LICENSE).

## Acknowledgments

Designed via parallel-think-tank simulation (research + architecture + technical feasibility) following the same methodology as [`did-it-actually`](https://github.com/pedroreisper/did-it-actually). The unifying insight across both skills: **Claude can't see what it's producing without an explicit perceptual loop**.
