#!/usr/bin/env python3
"""Carry builder-owned state from the live config into a regenerated one.

`config update` replaces the WHOLE config. So a script that rebuilds a config from source
and emits `_meta.screens: {}` will silently destroy the product attachments someone made in
the Flow Builder — the `flowProductId` values cannot be re-derived, and without them the
publish transform fails with a 422.

This is the sharp edge of "`_meta.screens` is builder-owned": it does not just mean *do not
author it*, it means **do not omit it either**. Anything the builder writes and you cannot
compute has to be carried forward on every regeneration.

    tests/preserve-builder-state.py <live-or-envelope.json> <regenerated.json> [--out FILE]

Merges, per screen id that still exists in the regenerated config:
    _meta.screens[<sid>]        product declarations incl. flowProductId, webPaywallURL
    _meta.fonts                 uploaded font records, if the regenerated config has none

Reports exactly what it carried and what it dropped, because a screen that no longer exists
legitimately loses its declarations and that should be visible rather than silent.
"""
import argparse, json, sys


def load(p):
    d = json.load(open(p))
    return d['config'] if isinstance(d.get('config'), dict) else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('live'); ap.add_argument('new'); ap.add_argument('--out')
    a = ap.parse_args()
    live, new = load(a.live), load(a.new)

    live_meta = (live.get('_meta') or {}).get('screens') or {}
    new_meta = (new.setdefault('_meta', {}).setdefault('screens', {}))
    keep = {s['id'] for s in new.get('screens', [])}

    carried, dropped, kept_existing = [], [], []
    for sid, block in live_meta.items():
        if sid not in keep:
            dropped.append(sid); continue
        if new_meta.get(sid):
            kept_existing.append(sid); continue
        new_meta[sid] = block
        n = len((block or {}).get('products') or [])
        carried.append(f'{sid} ({n} product declaration{"s" if n != 1 else ""})')

    fonts_note = ''
    live_fonts = (live.get('_meta') or {}).get('fonts') or []
    if live_fonts and not (new['_meta'].get('fonts') or []):
        new['_meta']['fonts'] = live_fonts
        fonts_note = f' | carried {len(live_fonts)} font record(s)'

    print('carried forward :', ', '.join(carried) or 'nothing' , fonts_note)
    if kept_existing:
        print('left as authored:', ', '.join(kept_existing))
    if dropped:
        print('DROPPED (screen no longer exists):', ', '.join(dropped))
    out = a.out or a.new
    json.dump(new, open(out, 'w'), indent=2, ensure_ascii=False)
    print('wrote', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
