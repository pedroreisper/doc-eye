# Fixtures

Regression fixtures for doc-eye. Each fixture is a rendered document with a
**known** defect plus a note of what the audit should catch, so prompt or
pipeline changes can be checked against a stable expected output.

## Layout

```
examples/
  <fixture-name>/
    source.{docx,pptx,pdf}   # the document to audit (carries a deliberate defect)
    expected.md              # the finding(s) doc-eye must surface
```

## `expected.md` format

```md
# <fixture-name>

- page: <1-indexed page the defect is on>
  category: <one of the report categories — typography-mixing, smartart-overflow,
             placeholder-text, broken-cross-ref, blank-page, colour-rot, orphan-widow, …>
  must_flag: <one line describing what a correct audit reports>
```

A fixture **passes** when an audit of `source.*` produces at least one finding
matching every `must_flag` entry (same page, same category). False negatives on a
`must_flag` are regressions.

## Adding one

1. Create `examples/<name>/`.
2. Drop in a `source.docx`/`.pptx`/`.pdf` that contains exactly one clear defect
   (keep fixtures single-defect so failures are unambiguous).
3. Write `expected.md` per the format above.
4. Run the audit against it and confirm the finding is produced before committing.

Keep fixtures small (1–3 pages) so they render fast and the defect is isolated.
