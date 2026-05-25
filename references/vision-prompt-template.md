# Vision-prompt template — what each per-page call sends to Claude

This is the exact shape of the prompt that `scripts/vision_audit.py` sends per page. Document this so anyone reviewing the skill can understand the contract without reading Python.

## System prompt

The system prompt is hardcoded in `vision_audit.py`. It instructs the model to:

1. Audit for SIX defect categories (FORMATTING, TYPOGRAPHY, COLOUR, CONTENT, LAYOUT, VISUAL_COHERENCE).
2. ONLY flag what is visible on the page — no speculation.
3. Use severity levels: critical / warning / info.
4. Return findings via the `record_findings` tool ONLY — no prose, no apologies.
5. Skip content-correctness judgments (this skill is about visual fidelity).

## User message (per page)

```
[image: page-NNN.png as base64 PNG]

Page <N> of <total>.
Restrict findings to these categories ONLY: <CAT1,CAT2,...>   (only if --only set)
Audit this page. Call record_findings with what you see.
```

## Tool schema — `record_findings`

The model is forced to call this tool (`tool_choice = {type: "tool", name: "record_findings"}`). The JSON it returns has this shape:

```json
{
  "page": 5,
  "page_ok": false,
  "findings": [
    {
      "category": "LAYOUT",
      "subcategory": "smartart_overflow",
      "severity": "critical",
      "location": "top-right quadrant",
      "description": "Diagram box text 'Inflamação Sistémica' clips at the right edge of the page.",
      "quoted_text": "Inflamação Sistémica"
    },
    {
      "category": "TYPOGRAPHY",
      "severity": "warning",
      "location": "page bottom",
      "description": "Last line of paragraph orphaned at the very bottom; the rest of the paragraph starts on the next page.",
      "quoted_text": "...e portanto a conclusão é"
    }
  ]
}
```

### Field meanings

| Field | Required | Description |
|---|---|---|
| `page` | yes | 1-indexed page number |
| `page_ok` | yes | `true` if no findings; `false` otherwise |
| `findings` | yes | array (can be empty) |
| `findings[].category` | yes | one of the six categories |
| `findings[].subcategory` | no | finer-grained label (e.g. `smartart_overflow`, `widow`, `broken_xref`) |
| `findings[].severity` | yes | `critical` / `warning` / `info` |
| `findings[].location` | no | rough page region: `top-left`, `top-right`, `middle`, `bottom`, `full-page` |
| `findings[].description` | yes | one-sentence description of the defect |
| `findings[].quoted_text` | no | exact text from the page that the finding refers to |

## Cross-page context

The current implementation does NOT pass prior-page findings to the next page's call. This is intentional for v1: keeps the calls stateless, parallelisable in the future, and avoids the system prompt growing unboundedly on long docs.

Trade-off: orphan/widow detection that needs both pages (the last line of page N alone, with the rest of the paragraph starting on page N+1) requires the aggregator to be smarter. v1 dedup-by-fingerprint catches the most common pattern (same heading style missing on every page); cross-page reflow is on the roadmap.

## Cost per call

Per [Anthropic vision docs](https://docs.anthropic.com/en/docs/build-with-claude/vision), a 1700×2200 PNG (A4 at DPI 200) ≈ 4800 input tokens, plus ~200 output tokens for a typical findings array.

- **Haiku 4.5**: ~$0.005 per page (input $1/M, output $5/M)
- **Sonnet 4.6**: ~$0.018 per page
- **Opus 4.7**: ~$0.029 per page

For a 50-page document:

- Haiku: ~$0.25
- Sonnet: ~$0.90
- Opus: ~$1.45

Default model is `claude-haiku-4-5`. Override with `--model` or `--opus`.

## Why forced tool use

Without `tool_choice`, the model sometimes returns prose explanations alongside the structured output. With `tool_choice = {type: "tool", name: "record_findings"}`, the model is constrained to call exactly that tool, and the SDK exposes the structured input as `block.input` on the response.

This is more reliable than asking the model to "return JSON only" in the prompt — the schema is enforced by the API, not by the model's good intentions.

## Anti-bias notes for the prompt author

If you edit the system prompt:

- Don't list specific failure modes the model should "watch out for" — that biases the output toward those modes and starves other categories.
- Don't say "be thorough" or "find as many issues as possible" — that inflates false-positive rate.
- Don't say "be conservative" or "only flag clear issues" — that suppresses real findings.
- Do specify what a finding is and what's out of scope. Let the model decide what counts.

## Versioning

This template is `v1`. Changes that alter the tool schema, severity definitions, or category set are breaking and require bumping the `schema_version` field in `audit-report.json` (see `references/output-schema.json`).
