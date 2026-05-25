# Bridging doc-eye into did-it-actually contracts

[`did-it-actually`](https://github.com/pedroreisper/did-it-actually) is Pedro's request-fidelity audit skill. It lets you express the user's request as a contract of falsifiable criteria and forces Claude to verify each one before reporting done.

`doc-eye` can be a criterion inside that contract — useful when the user asked for a document that "must look right" and you want that requirement mechanically checked.

## How the criterion looks

In your `.did-it-actually/contract.yml`:

```yaml
- id: manual-pdf-renders-cleanly
  intent: the exported PDF has no critical visual defects
  type: review
  spec:
    delegate: doc-eye
    target: exports/manual_v4.pdf
    max_severity_allowed: warning   # critical findings → criterion FAILS
    categories: [LAYOUT, TYPOGRAPHY, CONTENT]   # optional — defaults to all 6
    model: claude-haiku-4-5                      # optional — overrides default
  severity: critical
```

Fields:

| Field | Required | Description |
|---|---|---|
| `delegate` | yes | must be `doc-eye` |
| `target` | yes | path to the document (`.docx`, `.pptx`, `.pdf`) |
| `max_severity_allowed` | no | `info` / `warning` / `critical`. Any finding strictly higher than this fails the criterion. Default: `warning` (so any `critical` finding fails). |
| `categories` | no | restrict the audit to these categories (passed as `--only`) |
| `model` | no | override the default model (passed as `--model`) |

## How the verdict maps

The doc-eye audit emits one of: `CLEAN`, `FINDINGS_PRESENT`, `PARTIAL`, `AUDIT_FAILED`.

The bridge translates this into a `did-it-actually` criterion result:

| doc-eye verdict | + worst severity | → criterion status |
|---|---|---|
| `CLEAN` | (n/a) | `PASS` |
| `FINDINGS_PRESENT` | only `info` | `PASS` with note |
| `FINDINGS_PRESENT` | up to `max_severity_allowed` | `PASS` with note (warnings surfaced) |
| `FINDINGS_PRESENT` | exceeds `max_severity_allowed` | `FAIL` |
| `PARTIAL` | (any) | `PASS` with `⚠️ partial-audit` note |
| `AUDIT_FAILED` | (n/a) | `FAIL` with `audit error` |

The criterion's `evidence` field points at the `audit-report.json` so the user can inspect findings directly.

## Wiring it in audit.sh (not yet in did-it-actually v1)

The current `did-it-actually` v1.0.0 evaluates `review` criteria via its critic sub-agent, not by delegating to other skills. To make this bridge work, `did-it-actually/scripts/audit.sh` needs a small addition in the `eval_review` function — pseudocode:

```python
if spec.get("delegate") == "doc-eye":
    target = spec["target"]
    max_sev = spec.get("max_severity_allowed", "warning")
    cats = spec.get("categories", [])
    model = spec.get("model", "")
    cmd = [doc_eye_path, target, "--format", "json"]
    if cats:
        cmd += ["--only", ",".join(cats)]
    if model:
        cmd += ["--model", model]
    out = subprocess.check_output(cmd).decode()
    report = json.loads(out)
    return translate_verdict(report, max_sev)
```

This bridge is a planned addition for `did-it-actually` v1.1. The contract format above is forward-compatible — you can write the criterion now, and it will activate when `did-it-actually` ships the bridge.

In the meantime, you can manually invoke `doc-eye` from any contract by using a `command` criterion:

```yaml
- id: manual-pdf-renders-cleanly-manual
  intent: doc-eye audit emits no critical findings
  type: command
  spec:
    cmd: 'bash ~/.claude/skills/doc-eye/scripts/audit.sh exports/manual_v4.pdf --format json | jq -e ".summary_counts.critical == 0"'
    expect_exit: 0
    timeout_seconds: 180
  severity: critical
```

Less elegant but works today.

## Why this composability matters

Without the bridge, `did-it-actually` only knows about file existence, regex matches, and command exit codes. It cannot answer "does this Word doc look right" — that's a perceptual question that needs a vision model.

With the bridge, perceptual quality becomes a first-class contract criterion. The user's request "the PDF must render cleanly" stops being a vague hope and becomes a checkable predicate. Same anti-gaming guarantees apply: every PASS cites the `audit-report.json`, the verdict is a pure function of the report, the contract SHA is recorded.

This is the model for chaining skills generally — single-purpose, structured-output, with a delegate field that downstream skills can consume.
