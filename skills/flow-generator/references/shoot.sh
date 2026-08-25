#!/bin/bash
# Preview + screenshot + montage for N screens in ONE tool call, then you Read one image.
#
#   shoot.sh draft.json                                  # the default screen
#   shoot.sh draft.json scr_a scr_b scr_c                # three screens, one strip
#   OUT=/tmp/x shoot.sh draft.json scr_a                 # choose the output dir
#
# Prints the path of the strip to open. That is the only thing you need from it.
#
# Why this exists: the loop was preview -> screenshot -> montage as separate commands, three
# agent turns at ~30 s of round-trip each, per iteration. The screenshot itself is ~18 s of
# Chrome cold start and that is irreducible — but the turns around it are not.
#
# Two measured traps this handles for you. A `--virtual-time-budget` under ~3000 ms yields NO file
# while the wait runs to your timeout; and when the render HOST is slow, even 8000 ms yields
# nothing — so a failed shot is retried once at 60 s before giving up, because "no file" is far
# more often a slow host than a broken config. Chrome can also hang, so every launch is watchdogged.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${1:?usage: shoot.sh <config.json> [screen-id ...]}"; shift || true
SCREENS="$*"
OUT="${OUT:-$(dirname "$CFG")}"
BUDGET="${BUDGET:-8000}"
WINDOW="${WINDOW:-430,900}"
[ -f "$CFG" ] || { echo "shoot: no such file: $CFG" >&2; exit 2; }
mkdir -p "$OUT"

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           google-chrome chromium chromium-browser; do
    if [ -x "$c" ] || command -v "$c" >/dev/null 2>&1; then CHROME="$c"; break; fi
  done
fi
[ -n "$CHROME" ] || { echo "shoot: no Chrome/Chromium found — set CHROME=/path" >&2; exit 2; }

ADAPTY_BIN=${ADAPTY:-}
if [ -z "$ADAPTY_BIN" ]; then
  if command -v adapty >/dev/null 2>&1; then ADAPTY_BIN="adapty"; else ADAPTY_BIN="npx --yes adapty@latest"; fi
fi

# One launch, watchdogged — and it returns the moment the PNG is complete rather than waiting for
# Chrome to exit. Both halves are measured. Chrome hangs often enough that an unguarded call costs a
# whole turn; and a COLD first launch spent ~130 s inside Google's own updater before painting
# anything, so a watchdog tuned to the warm case (this was 60 s) kills shots that were going to
# succeed and reports "no file" for a config that is fine. Polling for the file is what makes a
# generous timeout free: you only ever wait the full time when nothing lands at all.
shoot_one() {  # $1 = url, $2 = out png, $3 = budget ms, $4 = watchdog s
  rm -f "$2"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size="$WINDOW" --virtual-time-budget="$3" \
    --screenshot="$2" "$1" >/dev/null 2>&1 &
  c=$!
  ticks=$(( $4 * 2 )); waited=0; last=-1
  while [ "$waited" -lt "$ticks" ]; do
    kill -0 "$c" 2>/dev/null || break
    # `wc -c <"$2"` would leak the shell's own redirect error while the file does not exist yet:
    # 2>/dev/null covers wc's stderr, not the redirection failure. Test first instead.
    if [ -f "$2" ]; then sz=$(wc -c <"$2" | tr -d ' '); else sz=0; fi
    # Non-empty AND unchanged since the last poll: Chrome has finished writing. Breaking on merely
    # non-empty would hand the caller a half-written PNG, which measures as a corrupt image.
    [ "$sz" -gt 0 ] && [ "$sz" = "$last" ] && break
    last="$sz"
    waited=$((waited + 1))
    sleep 0.5
  done
  kill -9 "$c" 2>/dev/null
  wait "$c" 2>/dev/null
}

shots=""; n=0
[ -n "$SCREENS" ] || SCREENS="__default__"
for s in $SCREENS; do
  if [ "$s" = "__default__" ]; then
    url="$($ADAPTY_BIN flows config preview "$CFG" 2>&1)"; png="$OUT/shot.png"
  else
    url="$($ADAPTY_BIN flows config preview "$CFG" --screen "$s" 2>&1)"; png="$OUT/shot-$s.png"
  fi
  case "$url" in
    http*) ;;
    *) echo "shoot: preview failed for $s: $(printf '%s' "$url" | head -2)" >&2; exit 1 ;;
  esac
  shoot_one "$url" "$png" "$BUDGET" "${WATCHDOG:-180}"
  if [ ! -s "$png" ]; then
    # Escalate before concluding anything. Measured: on a slow render host an 8 s budget produced
    # no file while 60 s produced a correct screenshot of the same config ~72 s later.
    echo "   slow host? retrying $s at 60s..." >&2
    shoot_one "$url" "$png" 60000 "${WATCHDOG_RETRY:-300}"
  fi
  if [ -s "$png" ]; then
    echo "   rendered $s -> $(basename "$png")"
    shots="$shots $png"; n=$((n+1))
  else
    echo "   FAILED  $s — no file even at 60s. Load the URL in a REAL browser before blaming the" >&2
    echo "           config: the page can render there while headless yields nothing." >&2
  fi
done

[ "$n" -gt 0 ] || { echo "shoot: nothing rendered" >&2; exit 1; }

if [ "$n" -eq 1 ]; then
  echo; echo "LOOK AT:$shots"
else
  strip="$OUT/strip.png"
  python3 "$HERE/montage.py" "$strip" $shots >/dev/null
  echo; echo "LOOK AT: $strip  ($n screens, left to right in the order given)"
fi
