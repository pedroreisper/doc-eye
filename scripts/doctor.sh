#!/usr/bin/env bash
# doctor.sh — self-diagnostic for doc-eye.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0; FAIL=0
result() {
  local status="$1"; shift
  case "$status" in
    ok)   PASS=$((PASS+1)); printf '  \033[32m✓\033[0m %s\n' "$*";;
    warn) PASS=$((PASS+1)); printf '  \033[33m~\033[0m %s\n' "$*";;
    err)  FAIL=$((FAIL+1)); printf '  \033[31m✗\033[0m %s\n' "$*";;
  esac
}

printf 'doc-eye  doctor\n'
printf '%s\n' '─────────────────────────────────────────'

# 1. Skill structure
printf '\nSkill structure:\n'
[ -f "$SKILL_ROOT/SKILL.md" ]                && result ok "SKILL.md present"                          || result err "SKILL.md missing"
[ -x "$SCRIPT_DIR/audit.sh" ]                 && result ok "audit.sh is executable"                    || result warn "audit.sh not +x — run chmod +x scripts/*.sh scripts/*.py"
[ -f "$SCRIPT_DIR/render.py" ]                && result ok "render.py present"                         || result err "render.py missing"
[ -f "$SCRIPT_DIR/vision_audit.py" ]          && result ok "vision_audit.py present"                   || result err "vision_audit.py missing"
[ -f "$SCRIPT_DIR/aggregate.py" ]             && result ok "aggregate.py present"                      || result err "aggregate.py missing"
[ -f "$SCRIPT_DIR/report.py" ]                && result ok "report.py present"                         || result err "report.py missing"

# 2. Frontmatter sanity
printf '\nFrontmatter:\n'
NAME="$(awk '/^name:/ {print $2; exit}' "$SKILL_ROOT/SKILL.md" 2>/dev/null || true)"
DIR_NAME="$(basename "$SKILL_ROOT")"
if [ "$NAME" = "$DIR_NAME" ]; then
  result ok "frontmatter name ($NAME) matches directory name"
else
  result err "name '$NAME' != directory '$DIR_NAME' — install will not be auto-discovered"
fi
DESC_LEN="$(awk '/^description:/{sub(/^description: */,""); print length; exit}' "$SKILL_ROOT/SKILL.md" 2>/dev/null || echo 0)"
if [ "$DESC_LEN" -le 1024 ]; then
  result ok "description: $DESC_LEN/1024 chars (under spec limit)"
else
  result err "description: $DESC_LEN chars exceeds 1024 spec limit"
fi

# 3. Installation in Claude Code
printf '\nClaude Code discovery:\n'
CC_SKILLS="${HOME}/.claude/skills"
PROJECT_SKILLS="$(pwd)/.claude/skills"
if [ -L "$CC_SKILLS/$NAME" ] || [ -d "$CC_SKILLS/$NAME" ]; then
  result ok "installed at $CC_SKILLS/$NAME"
elif [ -L "$PROJECT_SKILLS/$NAME" ] || [ -d "$PROJECT_SKILLS/$NAME" ]; then
  result ok "installed at $PROJECT_SKILLS/$NAME (project-scoped)"
else
  result warn "not installed — run install.sh"
fi

# 4. Runtimes + binaries
printf '\nRuntimes:\n'
command -v python3 >/dev/null && result ok "python3: $(python3 --version 2>&1)" || result err "python3 missing"
command -v bash    >/dev/null && result ok "bash: $(bash --version | head -1 | sed 's/.*GNU bash, version //')" || result err "bash missing"

printf '\nPython packages:\n'
python3 -c 'import fitz; print("pymupdf", fitz.__version__)' 2>/dev/null && result ok "pymupdf importable" || result err "pymupdf missing — pip install --user --break-system-packages pymupdf"
python3 -c 'import anthropic; print("anthropic", anthropic.__version__)' 2>/dev/null && result ok "anthropic SDK importable" || result err "anthropic SDK missing — pip install --user --break-system-packages anthropic"

printf '\nDocument-rendering binaries:\n'
command -v soffice    >/dev/null && result ok "soffice: $(soffice --version 2>&1 | head -1)" || \
  ( command -v libreoffice >/dev/null && result ok "libreoffice on PATH" || result warn "soffice/libreoffice missing — needed for .docx/.pptx (brew install --cask libreoffice)" )

# 5. API key
printf '\nAnthropic credentials:\n'
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  KEY_TAIL="${ANTHROPIC_API_KEY: -4}"
  result ok "ANTHROPIC_API_KEY set (...$KEY_TAIL)"
else
  result err "ANTHROPIC_API_KEY not set — export it before running audit.sh"
fi

# Summary
printf '\n%s\n' '─────────────────────────────────────────'
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '\nFix the FAIL items above before running an audit.\n'
  exit 1
fi
printf '\nAll critical checks pass.\n'
