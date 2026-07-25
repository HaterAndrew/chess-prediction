#!/usr/bin/env bash
# Rewrite the PII out of this repo's git history (audit v3 S2).
#
# The working tree was scrubbed in an earlier commit, but the real names, home
# city/state/ZIP and payer links are still reachable in the commits that carried
# the old fixtures. A public repo's history is as public as its tip.
#
# This replaces the identifiers with the same synthetic ones the current
# fixtures use, everywhere in history. It does NOT delete the files: the older
# commit stays functional, it just describes invented people.
#
# WHY THE MAPPING IS NOT IN THIS FILE
#
# It used to be, inline, and that was worse than the problem it solves. This
# repo is PUBLIC. A real->synthetic mapping committed here would republish every
# name the scrub exists to remove, and hand over a decoder ring: anyone could
# reverse the synthetic fixtures and find the originals in the unscrubbed
# history. The pre-push review caught it before it shipped.
#
# So the mapping lives OUTSIDE the repo, on the machine that runs the scrub, and
# only the mechanism is version-controlled. Same reasoning as
# tests/test_fixtures_are_synthetic.py, which stores hashes rather than names.
#
# Create it at ~/.config/chess-prediction/pii_replacements.txt (or point PII_MAP
# elsewhere), one git-filter-repo replacement per line:
#
#     RealSurname==>SyntheticSurname
#     REALSURNAME==>SYNTHETICSURNAME
#     Real First==>Synthetic First
#
# Include the capitalisation variants that appear in the data; --replace-text is
# case-sensitive. Lowercase forms are generated automatically below.
#
# THIS REWRITES HISTORY. Every commit after the first touched commit gets a new
# SHA, and publishing the result requires a force-push, which rewrites the
# remote branch for everyone who has cloned it. Read RUNBOOK below before use.
#
# RUNBOOK
#   1. Run with --dry-run first. It clones to a temp dir, rewrites there, and
#      reports whether any identifier survives. Nothing local or remote changes.
#   2. Confirm the dry run reports "CLEAN".
#   3. Get explicit owner approval for the force-push. This is not reversible
#      from the pushing side once other clones fetch it.
#   4. Run with --apply to rewrite THIS clone. It still does not push.
#   5. Verify the tree and tests, then push manually with --force-with-lease.
#
# Usage:
#   scripts/scrub_pii_history.sh --dry-run
#   scripts/scrub_pii_history.sh --apply
set -euo pipefail

MODE="${1:---dry-run}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PII_MAP="${PII_MAP:-$HOME/.config/chess-prediction/pii_replacements.txt}"

if [[ ! -f "$PII_MAP" ]]; then
  cat >&2 <<MSG
ABORT: no replacement map at $PII_MAP

The mapping is deliberately not stored in this repository — see the comment at
the top of this script. Create the file with one replacement per line:

    RealSurname==>SyntheticSurname

then re-run. Override the location with PII_MAP=/path/to/map.
MSG
  exit 2
fi

REPLACEMENTS="$(mktemp)"
chmod 600 "$REPLACEMENTS"
grep -v '^[[:space:]]*$' "$PII_MAP" | grep -v '^[[:space:]]*#' > "$REPLACEMENTS"

if [[ ! -s "$REPLACEMENTS" ]]; then
  echo "ABORT: $PII_MAP has no usable replacement lines." >&2
  exit 2
fi

# filter-repo's --replace-text is case-sensitive, so every casing the data
# actually uses needs its own entry. Generate them rather than asking whoever
# maintains the map to think of all three.
#
# Both variants were found by dry runs, not by inspection:
#   lower  — local variable names and prose comments in test files
#   title  — the code upper-cases names for comparison and title-cases them for
#            display, so a test asserting smart_case("SURNAME") == "Surname"
#            carries a form that appears nowhere in the source data
python3 - "$REPLACEMENTS" <<'PY'
import sys
path = sys.argv[1]
seen, extra = set(), []
with open(path) as fh:
    lines = [ln.rstrip("\n") for ln in fh]
for line in lines:
    if "==>" in line:
        seen.add(line.split("==>", 1)[0])
for line in lines:
    if "==>" not in line:
        continue
    old, new = line.split("==>", 1)
    for variant in (str.lower, str.title):
        v_old, v_new = variant(old), variant(new)
        if v_old != old and v_old not in seen:
            extra.append(f"{v_old}==>{v_new}")
            seen.add(v_old)
with open(path, "a") as fh:
    for p in extra:
        fh.write(p + "\n")
PY

# What must NOT survive anywhere in the rewritten history: the left-hand side of
# every mapping, whole and deduplicated case-insensitively. Derived from the map
# rather than kept as a second hardcoded list, which is how the original version
# ended up checking fewer names than it replaced.
#
# Whole entries, not word-split. Splitting "First Last" into its parts and
# substring-matching turns a 3-4 letter given name into a false-positive
# generator — the first run of this flagged .gitignore and a CI workflow because
# a short name appeared inside ordinary English words. Matching is word-bounded
# (-w) for the same reason.
mapfile -t CHECK_IDENTIFIERS < <(
  sed 's/==>.*//' "$REPLACEMENTS" | grep -v '^[[:space:]]*$' | sort -u -f
)

scan_clone() {
  # Search every blob in every commit, not just the tip.
  #
  # The commit list must come BEFORE any `--`. Passing it after makes git treat
  # the SHAs as pathspecs, which matches nothing and returns "clean" for a repo
  # that is full of the very strings being searched for. That mistake was in the
  # first version of this script and a control run against unscrubbed history
  # caught it. Hence verify_scanner_works() below: the scanner is tested for its
  # ability to FAIL before its pass is believed.
  local dir="$1" found=0 hits
  # shellcheck disable=SC2046  # word splitting of the rev list is intended
  for name in "${CHECK_IDENTIFIERS[@]}"; do
    hits="$(cd "$dir" && git grep -I -i -w -l -- "$name" $(git rev-list --all) 2>/dev/null | head -3)"
    if [[ -n "$hits" ]]; then
      echo "  STILL PRESENT: $name"
      echo "$hits" | sed 's/^/      /'
      found=1
    fi
  done
  return $found
}

verify_scanner_works() {
  # A scanner that cannot fail is worse than no scanner. Confirm it detects the
  # identifiers in the UNSCRUBBED clone before trusting its verdict on the
  # rewritten one.
  local dir="$1"
  if scan_clone "$dir" > /dev/null; then
    echo "ABORT: the scanner found no identifiers in the pre-rewrite history."
    echo "Either the history is already clean, or the scanner is broken."
    echo "Refusing to report a pass that has not been shown to be meaningful."
    return 1
  fi
  return 0
}

if [[ "$MODE" == "--dry-run" ]]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK" "$REPLACEMENTS"' EXIT
  echo "Using replacement map: $PII_MAP ($(wc -l < "$REPLACEMENTS") entries)"
  echo "Cloning to $WORK ..."
  git clone --no-local --quiet "$REPO_ROOT" "$WORK/repo"

  echo "Control check: confirming the scanner can detect the identifiers ..."
  if ! verify_scanner_works "$WORK/repo"; then
    exit 1
  fi
  echo "  scanner works (identifiers found in pre-rewrite history, as expected)"

  echo "Rewriting history in the clone ..."
  git -C "$WORK/repo" filter-repo --force --quiet \
      --replace-text "$REPLACEMENTS"
  echo
  echo "Scanning rewritten history for surviving identifiers ..."
  if scan_clone "$WORK/repo"; then
    echo "  CLEAN — no removed identifier survives in any commit."
    echo
    # A rewrite that removes the names but breaks the tests is not a fix. The
    # replacements touch fixture data AND the assertions that read it, so run
    # the suite against the rewritten tree before calling this safe.
    echo "Running the test suite against the rewritten tree ..."
    if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
      if (cd "$WORK/repo" && "$REPO_ROOT/.venv/bin/python" -m pytest tests/ -q 2>&1 | tail -3); then
        echo "  suite ran — check the counts above match the pre-rewrite run"
      else
        echo "  FAILED — the rewritten tree does not pass its own tests."
        exit 1
      fi
    else
      echo "  (skipped: no .venv found; run pytest manually in the rewritten clone)"
    fi
    echo
    echo "Dry run complete. Nothing here or on the remote was modified."
    echo "Next: get explicit approval, then run with --apply."
  else
    echo
    echo "FAILED — the replacement list is incomplete. Do not proceed."
    exit 1
  fi
  exit 0
fi

if [[ "$MODE" != "--apply" ]]; then
  echo "Usage: $0 [--dry-run|--apply]" >&2
  exit 2
fi

echo "Rewriting history in $REPO_ROOT (local only; this does NOT push) ..."
cd "$REPO_ROOT"
git filter-repo --force --replace-text "$REPLACEMENTS"
rm -f "$REPLACEMENTS"
echo
echo "Local history rewritten. Every commit has a new SHA."
echo "Verify with: pytest tests/ -q"
echo "Then push MANUALLY and deliberately:"
echo "    git push --force-with-lease origin main"
echo "The remote was NOT touched by this script."
