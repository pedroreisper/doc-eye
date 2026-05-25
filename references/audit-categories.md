# Audit categories — what each one catches

Six categories. Authoritative because the per-page vision prompt encodes them verbatim — if you edit a category here, also edit `scripts/vision_audit.py` SYSTEM_PROMPT and `references/vision-prompt-template.md`.

## FORMATTING

Page-level structural defects in how text is laid out.

- Margins inconsistent across pages (e.g. left margin shifts on one page)
- Indent depth wrong (numbered list items at the wrong nesting level)
- Mixed alignment in the same paragraph (left + justified + centered)
- Line spacing changes mid-section
- Page break in the middle of a heading (heading orphaned from its content)
- Header or footer missing on a page that should have one
- Duplicate header or footer (sometimes appears when a template variable repeats)

## TYPOGRAPHY

Font + character-level defects.

- Two body fonts in the same document (e.g. Calibri body + Helvetica body)
- Heading size inconsistency (H2 styled 14pt on one page, 16pt on another)
- Orphan line (last line of a paragraph alone at the top of the next page)
- Widow line (first line of a paragraph alone at the bottom of a page)
- Hyphenation errors (overlong unhyphenated words, "thro-ugh", incorrect language hyphenation)
- Bold or italic accidentally applied to a run that shouldn't have it
- Inconsistent ligatures or quote styles (smart vs straight quotes mixed)

## COLOUR

Colour-related defects.

- Coloured body text that shouldn't be coloured (red leftover from track-changes, blue from a hyperlink that should be plain)
- Insufficient contrast (dark grey text on grey background, light yellow highlighter making text unreadable)
- Palette drift from the document's stated colour scheme (one box uses brand red, another uses #FF0000)
- Highlighted text in a final-ready document
- White-on-white text (rare but happens after a fill-colour change)

## CONTENT

Visible textual defects on the page (this is NOT a deep proofreader — it catches what a human reviewer would spot on a 5-second skim).

- Typos and misspellings that are visually obvious
- Broken cross-references — "see Figure 3" / "as shown in Table 7" / "(Section 4.2)" with no nearby anchor
- Placeholder text left in — `Lorem ipsum`, `TODO`, `[insert]`, `XXX`, `Your name here`, `Lipsum`
- Mojibake / encoding artefacts (`Ã©` instead of `é`)
- Truncated text (sentence ends mid-word, suggesting a copy-paste from a narrower container)

## LAYOUT

Visual defects from how content is positioned on the page.

- SmartArt or images clipped at the page edge or extending outside the printable area
- Tables overflowing the right margin (especially after a column was added)
- Blank pages (an empty page that the document didn't intend to ship)
- Awkward whitespace (huge gap between a heading and the following paragraph, suggesting a manual break gone wrong)
- Image floating in the wrong place (text wraps around but the image is on the next page)
- Footnote disconnected from its anchor (footnote on page 5 but anchor on page 4)
- Content shifted across pages by upstream reflow (a paragraph that's clearly a continuation but starts mid-sentence)

## VISUAL_COHERENCE

Cross-element consistency on the same page.

- Numbered list with mixed numbering schemes (1, 2, 3 → A, B → i, ii in the same level)
- Bullet list with mixed bullet glyphs (• → ◦ → → in the same level)
- Caption disconnected from its figure (Figure 4 caption appears under Figure 3)
- Inconsistent heading style on the same level (H2 sometimes bold, sometimes not)
- Footnote numbering reset mid-section
- Two table styles in the same document
- Spacing-after on headings differs across instances

---

## Severity guide

- **critical** — would embarrass you if the doc went out: clipped SmartArt, placeholder TODO, broken cross-ref, white-on-white, page rendered blank
- **warning** — should fix but the doc is sendable: orphan/widow, minor margin drift, mixed quote styles, one inconsistent heading
- **info** — informational only: "your H2 uses 14pt here but 16pt elsewhere" when both are within reason

The model defaults to `warning` if it can't decide. The aggregate report's verdict treats any `critical` as `FINDINGS_PRESENT` regardless of other counts.

## What this skill does NOT flag

- Whether a fact is correct (`scientific-manuscript-reviewer` does that)
- Whether a citation actually exists in a database (`paper-lookup` does that)
- Whether a clinical guideline is up to date (a human reviewer does that)
- Code-level XML defects in `.docx` that don't show up rendered (a Word-XML linter does that)
- Brand-guideline conformance against a style sheet you haven't given the skill (a brand-audit skill does that)
