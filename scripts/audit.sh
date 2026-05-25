#!/usr/bin/env bash
# audit.sh — main driver for doc-eye
# Subcommands: <file>  |  doctor
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<EOF
doc-eye — visual audit of rendered document pages

Usage:
  audit.sh <file.docx|.pptx|.pdf> [options]
  audit.sh doctor

Options:
  --model <name>       Anthropic model (default: claude-haiku-4-5)
  --opus               shortcut for --model claude-opus-4-7
  --max-pages <N>      audit at most N pages (default: all)
  --sample             audit first 10 + last 5 + every 5th in between
  --only <CAT,CAT>     restrict to defect categories (FORMATTING,TYPOGRAPHY,COLOUR,CONTENT,LAYOUT,VISUAL_COHERENCE)
  --dpi <N>            render DPI (default: 200)
  --format <kind>      output format: prose (default) | json
  --keep-renders       don't clean up rendered PNGs
  --out <dir>          report dir (default: .doc-eye/<basename>/)
  -h, --help           this message

Requires:  ANTHROPIC_API_KEY  in environment.
Verify install: bash $SCRIPT_DIR/doctor.sh
EOF
}

# ---------------------------------------------------------------------------
case "${1:-}" in
  ""|-h|--help) usage; exit 0 ;;
  doctor)       exec bash "$SCRIPT_DIR/doctor.sh" ;;
esac

INPUT="${1:-}"
shift || true
[ -f "$INPUT" ] || { printf 'doc-eye: file not found: %s\n' "$INPUT" >&2; exit 2; }

MODEL="claude-haiku-4-5"
MAX_PAGES=""
SAMPLE=""
ONLY=""
DPI="200"
FORMAT="prose"
KEEP_RENDERS=""
OUT_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --model)         MODEL="$2"; shift 2 ;;
    --opus)          MODEL="claude-opus-4-7"; shift ;;
    --max-pages)     MAX_PAGES="$2"; shift 2 ;;
    --sample)        SAMPLE="1"; shift ;;
    --only)          ONLY="$2"; shift 2 ;;
    --dpi)           DPI="$2"; shift 2 ;;
    --format)        FORMAT="$2"; shift 2 ;;
    --keep-renders)  KEEP_RENDERS="1"; shift ;;
    --out)           OUT_DIR="$2"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *)               printf 'doc-eye: unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done

BASENAME="$(basename "$INPUT")"
STEM="${BASENAME%.*}"
[ -n "$OUT_DIR" ] || OUT_DIR=".doc-eye/$STEM"
mkdir -p "$OUT_DIR"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  printf 'doc-eye: ANTHROPIC_API_KEY is not set in your environment.\n' >&2
  printf '       Get a key at https://console.anthropic.com/ and export it before running.\n' >&2
  exit 3
fi

# Phase 1 — ingest + render -------------------------------------------------
RENDER_DIR="$OUT_DIR/pages"
mkdir -p "$RENDER_DIR"

printf '[doc-eye] rendering %s -> %s (dpi=%s) ...\n' "$BASENAME" "$RENDER_DIR" "$DPI" >&2
INPUT="$INPUT" RENDER_DIR="$RENDER_DIR" DPI="$DPI" \
  python3 "$SCRIPT_DIR/render.py"

PAGE_COUNT="$(find "$RENDER_DIR" -maxdepth 1 -name 'page-*.png' | wc -l | tr -d ' ')"
if [ "$PAGE_COUNT" = "0" ]; then
  printf 'doc-eye: rendering produced 0 pages — check the file is not encrypted or empty.\n' >&2
  exit 4
fi
printf '[doc-eye] rendered %s page(s).\n' "$PAGE_COUNT" >&2

# Phase 1b — placeholder pre-pass (cheap, no API cost) ---------------------
PLACEHOLDER_OUT="$OUT_DIR/placeholder-findings.json"
printf '[doc-eye] placeholder pre-pass (text extraction, no API) ...\n' >&2
INPUT="$INPUT" RENDER_DIR="$RENDER_DIR" OUT_PATH="$PLACEHOLDER_OUT" \
  python3 "$SCRIPT_DIR/placeholder_scan.py" || true

# Phase 1c — cost estimate + confirmation gate ------------------------------
# Effective pages to audit (respects --max-pages / --sample)
EFFECTIVE_PAGES="$PAGE_COUNT"
if [ -n "$MAX_PAGES" ] && [ "$MAX_PAGES" -lt "$PAGE_COUNT" ]; then
  EFFECTIVE_PAGES="$MAX_PAGES"
fi
# Per-model price ($ per page input + output, rounded)
case "$MODEL" in
  claude-haiku-4-5*)  PER_PAGE_DOLLAR="0.006" ;;
  claude-sonnet-4-6*) PER_PAGE_DOLLAR="0.018" ;;
  claude-opus-4-7*)   PER_PAGE_DOLLAR="0.029" ;;
  *)                  PER_PAGE_DOLLAR="0.010" ;;
esac
EST_DOLLAR="$(python3 -c "print(f'{${PER_PAGE_DOLLAR} * ${EFFECTIVE_PAGES}:.2f}')")"
printf '[doc-eye] estimated cost: ~$%s (%s pages × $%s/page on %s)\n' \
  "$EST_DOLLAR" "$EFFECTIVE_PAGES" "$PER_PAGE_DOLLAR" "$MODEL" >&2

# Require confirmation when estimate exceeds $1, unless DOC_EYE_NO_CONFIRM is set
if [ -z "${DOC_EYE_NO_CONFIRM:-}" ]; then
  EXCEEDS="$(python3 -c "print('1' if float('${EST_DOLLAR}') > 1.0 else '0')")"
  if [ "$EXCEEDS" = "1" ]; then
    if [ -t 0 ]; then
      printf '[doc-eye] Estimate exceeds $1 — proceed? (y/N) ' >&2
      read -r REPLY
      case "$REPLY" in
        y|Y|yes|YES) ;;
        *) printf 'doc-eye: cancelled.\n' >&2; exit 5 ;;
      esac
    else
      printf 'doc-eye: estimate exceeds $1 and no tty for confirmation. Set DOC_EYE_NO_CONFIRM=1 to skip.\n' >&2
      exit 5
    fi
  fi
fi

# Phase 2 — per-page vision audit ------------------------------------------
RAW_FINDINGS="$OUT_DIR/raw-findings.jsonl"
printf '[doc-eye] running vision audit (model=%s) ...\n' "$MODEL" >&2
RENDER_DIR="$RENDER_DIR" \
RAW_FINDINGS="$RAW_FINDINGS" \
MODEL="$MODEL" \
MAX_PAGES="$MAX_PAGES" \
SAMPLE="$SAMPLE" \
ONLY="$ONLY" \
SOURCE_FILE="$INPUT" \
PAGE_COUNT="$PAGE_COUNT" \
  python3 "$SCRIPT_DIR/vision_audit.py"

# Phase 3 — aggregate ------------------------------------------------------
REPORT_JSON="$OUT_DIR/audit-report.json"
printf '[doc-eye] aggregating findings ...\n' >&2
RAW_FINDINGS="$RAW_FINDINGS" \
REPORT_JSON="$REPORT_JSON" \
SOURCE_FILE="$INPUT" \
PAGE_COUNT="$PAGE_COUNT" \
MODEL="$MODEL" \
  python3 "$SCRIPT_DIR/aggregate.py"

# Phase 4 — report ---------------------------------------------------------
if [ "$FORMAT" = "json" ]; then
  cat "$REPORT_JSON"
else
  python3 "$SCRIPT_DIR/report.py" "$REPORT_JSON"
fi

# Phase 5 — cleanup --------------------------------------------------------
if [ -z "$KEEP_RENDERS" ]; then
  rm -rf "$RENDER_DIR"
fi

printf '\n[doc-eye] report: %s\n' "$REPORT_JSON" >&2
