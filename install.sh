#!/usr/bin/env bash
# install.sh — install doc-eye as a Claude Code skill.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/pedroreisper/doc-eye/main/install.sh | bash
#   bash install.sh                # from a clone
#   bash install.sh --project      # install to .claude/skills/ in CWD instead of ~/.claude/skills/
#   bash install.sh --uninstall    # remove the install
set -euo pipefail

REPO_URL="https://github.com/pedroreisper/doc-eye.git"
SKILL_NAME="doc-eye"
INSTALL_DIR="${HOME}/.claude/skills"
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project)   INSTALL_DIR="$(pwd)/.claude/skills";;
    --uninstall) UNINSTALL=1;;
    -h|--help)   sed -n '2,9p' "$0"; exit 0 ;;
    *) printf 'unknown flag: %s\n' "$1" >&2; exit 2;;
  esac
  shift
done

TARGET="$INSTALL_DIR/$SKILL_NAME"

if [ "$UNINSTALL" -eq 1 ]; then
  if [ -e "$TARGET" ]; then rm -rf "$TARGET"; printf 'removed %s\n' "$TARGET"
  else printf 'nothing to remove at %s\n' "$TARGET"; fi
  exit 0
fi

mkdir -p "$INSTALL_DIR"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SELF_DIR/SKILL.md" ] && grep -q "name: $SKILL_NAME" "$SELF_DIR/SKILL.md"; then
  printf 'installing from local checkout: %s\n' "$SELF_DIR"
  rm -rf "$TARGET"
  cp -R "$SELF_DIR" "$TARGET"
else
  if [ -d "$TARGET/.git" ]; then
    printf 'updating existing install at %s\n' "$TARGET"
    git -C "$TARGET" pull --ff-only
  else
    printf 'cloning into %s\n' "$TARGET"
    rm -rf "$TARGET"
    git clone --depth 1 "$REPO_URL" "$TARGET"
  fi
fi

chmod +x "$TARGET/scripts/"*.sh "$TARGET/scripts/"*.py "$TARGET/install.sh" 2>/dev/null || true

# Best-effort dependency install — doesn't fail the install if pip refuses.
printf '\nInstalling Python deps (pymupdf, anthropic) ...\n'
if ! python3 -c 'import fitz' 2>/dev/null; then
  pip3 install --user --break-system-packages pymupdf 2>&1 | tail -1 || true
fi
if ! python3 -c 'import anthropic' 2>/dev/null; then
  pip3 install --user --break-system-packages anthropic 2>&1 | tail -1 || true
fi

# LibreOffice check (warn only)
if ! command -v soffice >/dev/null 2>&1 && ! command -v libreoffice >/dev/null 2>&1; then
  printf '\n\033[33m~\033[0m LibreOffice not found. Install with:\n'
  printf '    brew install --cask libreoffice    # macOS\n'
  printf '    sudo apt install libreoffice       # Debian/Ubuntu\n'
  printf '  (needed for .docx/.pptx — .pdf works without it)\n'
fi

printf '\n\033[32m✓\033[0m doc-eye installed at %s\n' "$TARGET"
printf '\nNext steps:\n'
printf '  • Export ANTHROPIC_API_KEY in your shell (https://console.anthropic.com/)\n'
printf '  • Verify install:  bash %s/scripts/doctor.sh\n' "$TARGET"
printf '  • Run an audit:    bash %s/scripts/audit.sh path/to/document.pdf\n' "$TARGET"
