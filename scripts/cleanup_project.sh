#!/usr/bin/env bash
# Repository cleanup/organizer: move docs/scripts, untrack generated artifacts.
set -euo pipefail

# Cleanup and organize the repo into a minimal, professional layout
# Safe to run multiple times. Use --push to push after commit, and --dry-run to preview.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN=false
DO_PUSH=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --push) DO_PUSH=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then
    echo "+ $*"
  else
    eval "$@"
  fi
}

exists() { [ -e "$1" ]; }

echo "[cleanup] Working directory: $ROOT_DIR"

# 1) Ensure target folders exist
run "mkdir -p docs scripts legacy logs/data"

# 2) Move documentation (if present)
for f in \
  CLEANUP_SUMMARY.md \
  FINAL_STATUS.md \
  FIXES_APPLIED.md \
  FIX_MULTIPLE_CITATIONS.md \
  MULTI_CITATION_GUIDE.md \
  PROJECT_GUIDE.md \
  SMART_ASSET_DETECTION.md \
  SMART_BATCH_GUIDE.md
do
  if exists "$f"; then run "git mv \"$f\" docs/"; fi
done

# 3) Move helper scripts/tools (if present)
if exists "logs_viewer.py"; then run "git mv logs_viewer.py scripts/"; fi
if exists "quick_batch.py"; then run "git mv quick_batch.py scripts/"; fi
if exists "batch_presentations.py"; then run "git mv batch_presentations.py scripts/"; fi
if exists "batch_web.py"; then run "git mv batch_web.py scripts/"; fi
if exists "run_flow7.command"; then run "git mv run_flow7.command scripts/"; fi

# Optionally archive older/unused scripts
if exists "queue_flow.py"; then run "git mv queue_flow.py legacy/"; fi

# 4) Generated/transient files: untrack or delete
# Keep historical CSVs in logs/data (untracked)
for f in citations.csv data.csv journal_citations.csv; do
  if exists "$f"; then run "mv -f \"$f\" logs/data/"; fi
  run "git rm --cached \"$f\" 2>/dev/null || true"
done

# Always remove these from git index (they are ignored by .gitignore)
for f in citationsPresentations.csv filled_fields_summary.txt; do
  run "git rm --cached \"$f\" 2>/dev/null || true"
done

# Control/status files and logs
run "git rm --cached citation_control_*.json 2>/dev/null || true"
run "git rm --cached citation_status_*.json 2>/dev/null || true"
run "git rm --cached -r logs 2>/dev/null || true"

# Also remove any stray control/status instances from workspace (not tracked)
for f in citation_control_*.json citation_status_*.json; do
  if compgen -G "$f" > /dev/null; then run "rm -f $f"; fi
done

echo "[cleanup] Staging and committing changes"
run "git add -A"
run "git commit -m 'cleanup: minimal root, move docs/scripts, untrack generated artifacts' 2>/dev/null || true"

if $DO_PUSH; then
  echo "[cleanup] Pushing to origin/main"
  run "git push -u origin main"
fi

echo "[cleanup] Done. Root is minimal. Bot entry: start_smart_batch.sh"

