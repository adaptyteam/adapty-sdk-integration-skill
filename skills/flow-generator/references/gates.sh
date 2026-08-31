#!/bin/bash
# All of phase 3 in ONE tool call. Runs every gate over the SAME bytes and prints one verdict.
#
#   gates.sh draft.json                          # local gates only
#   gates.sh draft.json <APP_UUID> <FLOW_ID>     # + the publish gate
#
# Why this exists: the gates were three separate commands, i.e. three agent turns at ~30 s of
# round-trip each — far more than the checks themselves cost. Order is deliberate: the local
# structural walk first (it names every defect at once), then the schema shape check, then
# `validate` (one fatal per round trip, and the only one that needs the network).
#
# Exit 0 only if nothing blocking was found. `validate` needs an existing flow id purely as a
# target; the call is read-only and saves nothing.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${1:?usage: gates.sh <config.json> [APP_UUID FLOW_ID]}"
APP="${2:-}"; FLOW="${3:-}"
[ -f "$CFG" ] || { echo "gates: no such file: $CFG" >&2; exit 2; }
# Absolutise both paths NOW. The schema step runs inside `cd "$AJV_DIR"`, so a relative path
# resolves against the ajv cache dir, the node call cannot find the file, and because that step is
# wrapped in `|| true` the gate is SILENTLY SKIPPED while the run still reports a pass. The -f
# guard above does not catch it: it runs in the original cwd, where the relative path is fine.
CFG="$(cd "$(dirname "$CFG")" && pwd)/$(basename "$CFG")"
[ -n "${BASELINE:-}" ] && [ -f "$BASELINE" ] && \
  BASELINE="$(cd "$(dirname "$BASELINE")" && pwd)/$(basename "$BASELINE")"

ADAPTY_BIN=${ADAPTY:-}
if [ -z "$ADAPTY_BIN" ]; then
  if command -v adapty >/dev/null 2>&1; then ADAPTY_BIN="adapty"; else ADAPTY_BIN="npx --yes adapty@latest"; fi
fi

fail=0
md5="$( { md5 -q "$CFG" 2>/dev/null || md5sum "$CFG" | cut -d' ' -f1; } )"
echo "== gates over $CFG  (md5 ${md5:0:12})"

echo "-- 1/3 structure (verify-config.py)"
# BASELINE does double duty: the schema step uses it to suppress a v9 flow's pre-existing
# findings, and verify-config.py uses it to tell a price THIS draft invented from one the flow
# already had. Both are already absolute (see above), and this runs before any `cd`.
if [ -n "${BASELINE:-}" ] && [ -f "$BASELINE" ]; then
  if python3 "$HERE/verify-config.py" --baseline "$BASELINE" "$CFG"; then :; else fail=1; fi
else
  if python3 "$HERE/verify-config.py" "$CFG"; then :; else fail=1; fi
fi

echo "-- 2/3 schema shape (ADVISORY — does not decide the verdict)"
# --config, not a positional. Pass BASELINE=flow.backup.json when editing a fetched config, or a
# v9 flow buries you in pre-existing findings that are not yours.
# ajv is installed ONCE into a cache dir, never resolved through `npx` per run. Measured: the
# npx form cost 12.7 s of a 24 s gate run — over half of it — for a step that is only advisory.
# From the cache dir the same check is 0.3 s. `loadAjv` searches cwd first, hence the subshell cd.
AJV_DIR="${AJV_DIR:-$HOME/.cache/adapty-flow-schema}"
if [ -f "$HERE/validate-with-schema.mjs" ]; then
  if [ ! -d "$AJV_DIR/node_modules/ajv" ]; then
    echo "   (installing ajv once into $AJV_DIR)"
    mkdir -p "$AJV_DIR"
    npm i --prefix "$AJV_DIR" ajv@8 --silent --no-audit --no-fund >/dev/null 2>&1 \
      || echo "   (could not install ajv — schema step skipped)"
  fi
  if [ -d "$AJV_DIR/node_modules/ajv" ]; then
    # no arrays: macOS ships bash 3.2, where an empty array under `set -u` is an unbound variable
    if [ -n "${BASELINE:-}" ]; then
      ( cd "$AJV_DIR" && node "$HERE/validate-with-schema.mjs" \
          --config "$CFG" --baseline "$BASELINE" ) 2>&1 | tail -15 || true
    else
      ( cd "$AJV_DIR" && node "$HERE/validate-with-schema.mjs" --config "$CFG" ) 2>&1 | tail -15 || true
    fi
  fi
else
  echo "   (validate-with-schema.mjs missing — skipped)"
fi

# Advisory on purpose: `validate` outranks the schema in both directions, and the schema has a
# KNOWN unsatisfiable `oneOf` (IDynamicProductValue) that fails for EVERY `purchase` action — so
# letting it decide the verdict would mark every real paywall red and teach you to ignore the
# output. Read its findings; do not let them gate. Findings clustered on one element carrying a
# `purchase` action are that artifact.
echo "-- 3/3 publish gate (flows config validate)"
if [ -z "$APP" ] || [ -z "$FLOW" ]; then
  echo "   SKIPPED — pass APP_UUID and FLOW_ID to run it. A green local pass is NOT a publish gate."
  fail=1
else
  out="$($ADAPTY_BIN flows config validate --app "$APP" "$FLOW" --config-file "$CFG" --json 2>&1)"
  verdict="$(printf '%s' "$out" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("UNPARSEABLE"); raise SystemExit
v=d.get("valid")
if v is True:  print("valid: true")
elif v is False:
    iss=d.get("issues") or []
    print("valid: false — " + "; ".join(str(i.get("message")) for i in iss[:3] or ["(no issues listed)"]))
else:
    print("API ERROR (not a verdict — retry): " + json.dumps(d)[:160])
' 2>/dev/null)"
  echo "   $verdict"
  case "$verdict" in "valid: true") ;; *) fail=1 ;; esac
fi

echo
if [ "$fail" -eq 0 ]; then echo "== ALL GATES PASS over ${md5:0:12}"; else echo "== NOT CLEAR — see above"; fi
exit "$fail"
