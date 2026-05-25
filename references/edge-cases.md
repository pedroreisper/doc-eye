# Edge cases — how doc-eye handles awkward inputs

## Encrypted PDFs

Detected at render time via PyMuPDF (`doc.needs_pass`). The skill exits with a clear error before consuming any vision-API tokens:

```
PDF is encrypted with a password. Provide a decrypted copy (file: confidential.pdf).
```

No partial output. No cost incurred. User must supply a decrypted copy.

## Scanned (image-only) PDFs

Pages render fine (they ARE images). The vision model can flag layout defects (skewed scans, clipped edges, missing pages) but cannot reliably check spelling of text inside scanned images — Claude vision is not OCR-grade for small text on noisy backgrounds.

Behaviour: the skill audits normally. Findings on text content from scanned pages should be read with reduced confidence. A future v1.1 might detect this case and add a `reliability: reduced` field.

For real OCR, pre-process with `ocrmypdf` and feed the result.

## Very long documents (>50 pages)

The skill audits every page by default. For long docs, two flags:

- `--max-pages N` — audit only the first N pages
- `--sample` — audit first 10 + last 5 + every 5th page in between (good coverage at fixed cost)

With `--sample`, the verdict gets `PARTIAL` in `audit-report.json` so downstream tooling knows the audit was partial.

## Mixed-orientation pages (landscape + portrait)

PyMuPDF renders each page at its native orientation. The vision model sees the page right-side up. No special handling needed.

## Right-to-left languages (Arabic, Hebrew, Farsi)

The system prompt is language-neutral — Claude vision handles RTL layout. However, the prompt currently does not pass an explicit "this doc is RTL" hint, so the model may occasionally flag right-aligned body text as a defect. v1.1 plans: detect script from PDF metadata or first-page sample and inject the hint.

For now: pass `--only LAYOUT,TYPOGRAPHY,COLOUR` to skip CONTENT category when auditing RTL docs, until the hint is wired up.

## Two-up / facing-page spreads

The skill audits one page at a time. If your document is laid out as facing-page spreads (cover + spread + spread + back cover), each page is audited in isolation — the skill doesn't see the spread as a continuous unit.

Workaround for spread-heavy designs: render the full document at half DPI and pre-stitch two pages per image before feeding to the audit (out of v1 scope; tracked as a future enhancement).

## Documents with embedded videos or interactive forms

PyMuPDF renders the page as it would print — interactive elements appear as their static representation. Form fields with no text show as empty boxes (which the skill correctly identifies as "blank form field" if visible). Embedded videos appear as their poster frame.

## Corrupt or partially-renderable files

If a page render throws an error, that page is added to `skipped_pages[]` and the audit continues. The verdict becomes `PARTIAL`. The report header surfaces skipped pages prominently.

If the entire file fails to render (zero PNGs produced), the skill exits with:

```
doc-eye: rendering produced 0 pages — check the file is not encrypted or empty.
```

## DOCX with SmartArt

Pedro's known pain point. LibreOffice headless rendering is not byte-identical to Word's SmartArt renderer. The skill flags SmartArt findings normally, but the report should be read knowing that some SmartArt defects may be artefacts of LibreOffice's rendering rather than Word's.

Pragmatic workflow: open the DOCX in Word, "Save As PDF" with Word's own renderer, then feed the PDF to doc-eye. That uses Microsoft's official SmartArt renderer and avoids the LibreOffice gap.

## Documents with custom fonts

If a custom font isn't installed on the rendering machine, LibreOffice substitutes a fallback (usually Liberation Serif or DejaVu). The substituted font will appear in the PNG and may show as a TYPOGRAPHY finding when compared to other pages with installed fonts.

To get accurate rendering, install the document's fonts on the audit machine before running.

## Multi-language documents

A doc that mixes EN + PT + DE is handled fine by Claude vision. Findings may have descriptions in the dominant language. Future enhancement: language hint in the prompt.

## Empty documents

A `.docx` with zero pages of content renders to a 1-page PDF with an empty page. The skill audits that single page and likely emits a `LAYOUT: blank page` finding. Verdict: `FINDINGS_PRESENT`.

## Documents with only images (no text)

A photo-book PDF or a presentation with image-only slides renders fine. The model audits visual composition (clipping, alignment, white-balance issues). It does NOT comment on the artistic merit of the photos.

## Re-running on the same file

The skill caches rendered PNGs in `.doc-eye/<basename>/pages/` for the lifetime of the run. With `--keep-renders`, the PNGs survive the run for inspection. Subsequent runs re-render unless you point `--out` at the existing directory — there's no content-based cache (planned for v1.1: cache by SHA of the source file).

## `.doc` (legacy Word, not `.docx`)

Handled the same as `.docx` — LibreOffice accepts both. The `render.py` script lists `.doc` as a supported extension.

## `.odt` / `.odp` (LibreOffice native formats)

Supported — same conversion path as `.docx`/`.pptx`.

## URLs / Google Docs / remote files

Not supported. The caller must download the file first. The skill accepts only local paths. Future v1.1 might add `--url` with a fetch step.
