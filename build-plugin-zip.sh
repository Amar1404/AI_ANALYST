#!/usr/bin/env bash
# Build a clean ai-analyst-plugin.zip for Claude Cowork admin-UI upload.
# Excludes: virtualenv (symlinks!), git internals, caches, build artifacts,
# the graphify graph + graphify skill, dev-only dirs (docs/tests/.github),
# and — critically — the PII CSVs.
# Lives in the repo root. Run it from anywhere: ./build-plugin-zip.sh
set -euo pipefail

# Derive the repo root from this script's own location (it lives in the repo root).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

OUT="ai-analyst-plugin.zip"
rm -f "$OUT"

zip -r "$OUT" . \
  -x 'venv/*' \
     '.git/*' \
     'node_modules/*' \
     'graphify-out/*' \
     '.claude/*' \
     'docs/*' \
     'tests/*' \
     '.github/*' \
     '.python-version' \
     '.knowledge-cache/*' \
     '*/__pycache__/*' '__pycache__/*' \
     '*.pyc' '*.pyo' \
     '*.egg-info/*' 'dist/*' 'build/*' \
     '.DS_Store' '*.log' \
     '.pytest_cache/*' \
     'working/*' 'outputs/*' \
     '*.local' \
     'build-plugin-zip.sh' \
     'ai-analyst-plugin.zip' \
     'knowledge-repo/*.csv' \
     'knowledge-repo/superset_config.json'
# Excluded above (kept off the continued lines so no '#' breaks the \ continuation):
#   knowledge-repo/*.csv                 -> PII: phone-number exports, never ship
#   knowledge-repo/superset_config.json  -> live Superset password, never ship

echo
echo "=== verification (all checks should say clean / no symlinks) ==="
# 1. No symlinks survived (zip entries starting with 'l')
if zipinfo "$OUT" | grep -q '^l'; then
  echo "FAIL: symlinks present:"; zipinfo "$OUT" | grep '^l'
else
  echo "OK: no symlinks"
fi
# 2. No venv / git / graphify / dev / PII / secret-config / cache leaked in
if unzip -l "$OUT" | grep -Ei 'venv/|\.git/|graphify-out/|\.claude/|^.*docs/|tests/|\.pytest_cache/|superset_config\.json|phone|all_users|crm_users'; then
  echo "FAIL: unwanted files above"
  exit 1
else
  echo "OK: no venv / git / graphify / dev / PII / secret-config / cache files"
fi
# 2b. Secret scan: FAIL the build if any shipped CONFIG/DATA file (json/yaml/env/
# ini/cfg/toml — NOT source code) hardcodes a non-empty credential VALUE. Source
# files legitimately reference credential-named variables (password=password,
# token=..., api_key: str), so they are excluded to avoid false positives.
echo "--- secret scan (config/data files only) ---"
SCAN_DIR="$(mktemp -d)"
trap 'rm -rf "$SCAN_DIR"' EXIT
unzip -qq "$OUT" -d "$SCAN_DIR"
# In config files, a leaked secret looks like  "password": "actualvalue"  or
# password = actualvalue . Require a quoted/bare LITERAL value that is not a
# placeholder, env-ref, or empty. Restrict to data file extensions only.
SECRET_HITS="$(
  find "$SCAN_DIR" -type f \( -name '*.json' -o -name '*.yaml' -o -name '*.yml' \
      -o -name '*.env' -o -name '*.ini' -o -name '*.cfg' -o -name '*.toml' \) -print0 \
    | xargs -0 grep -InaE '"?(password|passwd|secret|client_secret|api[_-]?key|access[_-]?key|private[_-]?key|pat)"?\s*[:=]\s*("[^"]+"|[^[:space:],}{]+)' 2>/dev/null \
    | grep -vEi '(\$\{|<your|example|placeholder|changeme|xxx+|: *""|= *""|: *$|= *$|null|none|false|true|"")' \
    || true
)"
if [ -n "$SECRET_HITS" ]; then
  echo "$SECRET_HITS"
  echo "FAIL: possible hardcoded secret value(s) in shipped config/data files (above). Aborting."
  exit 1
else
  echo "OK: no hardcoded credential values in shipped config/data files"
fi
# 3. The essentials ARE present
echo "--- key files present? ---"
unzip -l "$OUT" | grep -E '\.claude-plugin/(plugin|marketplace)\.json' || echo "WARN: manifest missing!"
echo
echo "Built: $REPO_ROOT/$OUT"
echo "Upload it via Claude Cowork admin UI -> Plugins -> Upload."
