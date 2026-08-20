#!/usr/bin/env python3
"""Verify the referential invariants of a flow-config fixture.

SCOPE: this guards the FIXTURES in this repo — it is not part of the
flow-generator skill, which ships no scripts by owner decision (a `validate`
command is planned for the Adapty CLI). Use it after editing or re-sanitizing a
fixture, and when a new `schemaVersion` appears, to confirm the fixture is still
a valid document rather than a subtly broken one.

Checks, in order: map keys match element ids; hierarchy references resolve;
navigate targets resolve; product elements are declared in _meta.screens;
price variables reference declared products; selectableGroups and groupId agree
both ways; font.preset and colorId resolve in the file's own theme;
font.family resolves in _meta.fonts; every icon used appears in _meta.icons.
Unreferenced components are reported as warnings, because real exports have them.

Usage: verify-fixture.py <fixture.json> [more.json ...]
Exit 0 if every file is clean (warnings allowed), 1 if any invariant is violated.
"""
import json, sys, os

# The only selectable-group types observed in real exports. A tab group is declared
# `single_choice`; there is no `tabs` group type. See flow-schema.md, Vocabulary.
GROUP_TYPES = {'single_choice', 'multi_choice', 'product', 'toggle'}


def walk(o, fn):
    if isinstance(o, dict):
        fn(o)
        for v in o.values():
            walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            walk(v, fn)

def check(path):
    d = json.load(open(path))
    bad, warn = [], []
    els = lambda: ((s, e) for s in d.get('screens', [])
                   for e in s.get('elements', {}).get('map', {}).values())

    for s in d.get('screens', []):
        for k, e in s['elements']['map'].items():
            if k != e.get('id'):
                bad.append(f'map key {k} != element id {e.get("id")}')
        ids, refs = set(s['elements']['map']), []
        def h(n):
            if n.get('id') != 'root' and n.get('type') != 'global':
                refs.append(n['id'])
            for c in n.get('children') or []:
                h(c)
        h(s['elements']['hierarchy'])
        miss = [r for r in refs if r not in ids]
        if miss:
            bad.append(f'screen {s["id"]}: hierarchy refs not in map: {miss}')

    # Components: hierarchy refs must resolve into the component's own map, but the
    # reverse does NOT hold — vpn-timer-draft's pb_GgGITFkb keeps a progress-bar-loader
    # in `map` that no hierarchy node references. Unreferenced entries are legal and must
    # never be pruned, so they are a warning, not an error.
    for cid, c in (d.get('components') or {}).items():
        crefs = []
        def ch(n):
            if n.get('id') != 'root':
                crefs.append(n['id'])
            for x in n.get('children') or []:
                ch(x)
        ch(c.get('hierarchy', {}))
        cmap = set(c.get('map', {}))
        unresolved = [r for r in crefs if r not in cmap]
        if unresolved:
            bad.append(f'component {cid}: hierarchy refs not in its map: {unresolved}')
        orphans = sorted(cmap - set(crefs))
        if orphans:
            warn.append(f'component {cid}: in map but not in hierarchy (legal — do not prune): {orphans}')

    # Element well-formedness, not just referential integrity. `states` is present on
    # 100% of screen elements in every real export (76/76 in comparison-paywall) and on
    # NO element inside `components`. A screen element without it crashed the Flow
    # Builder on import — the transformer's minimized fixtures omit `states`, so copying
    # their shape produces an element the builder cannot read.
    for s in d.get('screens', []):
        for eid, e in s['elements']['map'].items():
            if 'states' not in e:
                bad.append(f'screen element {eid} ({e.get("type")}) has no `states` key '
                           f'— present on every screen element in every real export')
            if 'id' not in e or 'type' not in e or 'props' not in e:
                miss = [k for k in ('id', 'type', 'props') if k not in e]
                bad.append(f'screen element {eid} missing required key(s) {miss}')

    sids = {s['id'] for s in d.get('screens', [])}
    tg = []
    walk(d, lambda o: tg.append(o['screen'])
         if o.get('type') == 'screen' and isinstance(o.get('screen'), str) else None)
    dang = sorted({t for t in tg if t not in sids})
    if dang:
        bad.append(f'dangling navigate targets: {dang}')

    ms = d.get('_meta', {}).get('screens', {})
    for s, e in els():
        if e['type'] == 'product':
            pid = (e.get('props') or {}).get('product', {}).get('id')
            decl = {p['id'] for p in ms.get(s['id'], {}).get('products', [])}
            if pid not in decl:
                bad.append(f'product {pid} not declared in _meta.screens[{s["id"]}]')

    # A price variable comes in TWO forms, and only one is product-relative:
    #   <productUUID>.prod_price_per_year      — bound to one specific product
    #   <groupId>.selectedProduct.prod_price   — bound to whatever the group has selected
    # The second resolves against a product-type selectableGroup, not against a
    # product id, so validating its first segment as a UUID is a false positive.
    # Only the first form appears in this corpus; the second was observed in a real
    # Flow Builder screen and is accepted here so a valid file is not rejected.
    allprod = {p['id'] for v in ms.values() for p in v.get('products', [])}
    product_groups = {g['id'] for s in d.get('screens', [])
                      for g in (s.get('selectableGroups') or [])
                      if g.get('type') == 'product'}
    vids = []
    walk(d, lambda o: vids.append(o['variableId'])
         if isinstance(o.get('variableId'), str) else None)
    for v in sorted(set(vids)):
        if '.prod_' not in v:
            continue
        head = v.split('.')[0]
        if '.selectedProduct.' in v:
            if head not in product_groups:
                bad.append(f'group-relative price variable on unknown product group: {v}')
        elif head not in allprod:
            bad.append(f'price variable references undeclared product: {v}')

    for s in d.get('screens', []):
        gids = {(e.get('props') or {}).get('groupId')
                for e in s['elements']['map'].values() if (e.get('props') or {}).get('groupId')}
        decl = {g['id'] for g in s.get('selectableGroups') or []}
        if gids - decl:
            bad.append(f'screen {s["id"]}: groupId with no group: {sorted(gids - decl)}')
        if decl - gids:
            bad.append(f'screen {s["id"]}: group with no members: {sorted(decl - gids)}')
        # `opacity` on a colour is a 0-100 percentage (flow-schema.md trap 11). A value in
        # (0, 1] is legal but is almost always a 0-1 fraction written by mistake, which paints
        # at ~1% and reads as "the fill vanished". Warning, not an error: 1% is valid.
        def thin_opacity(obj, where):
            if isinstance(obj, dict):
                op = obj.get('opacity')
                if obj.get('type') == 'hex' and isinstance(op, (int, float)) and 0 < op <= 1:
                    warn.append(f'{where}: colour opacity is {op} on a 0-100 scale (~{op}% '
                                f'opaque) — did you mean {int(op * 100)}?')
                for v in obj.values():
                    thin_opacity(v, where)
            elif isinstance(obj, list):
                for v in obj:
                    thin_opacity(v, where)
        for eid, e in s['elements']['map'].items():
            thin_opacity(e.get('props'), eid)
            thin_opacity(e.get('propsByState'), f'{eid}.propsByState')
        thin_opacity(s['props'], f'screen {s["id"]}')

        # Group `type` against the four legal values. This is here because an invalid
        # type is one of the two defects that broke the Flow Builder in this project's
        # history (flow-schema.md trap 10) and it is invisible to every referential
        # check: `tabs` was taken from a source-level constant in the builder
        # transformer, wired up consistently, and agreed with everything around it.
        # The render is no help either — a config with a bogus group type still draws,
        # it just silently loses the selected state.
        for g in s.get('selectableGroups') or []:
            if g.get('type') not in GROUP_TYPES:
                bad.append(f'screen {s["id"]}: group {g.get("id")!r} has type '
                           f'{g.get("type")!r}, not one of {sorted(GROUP_TYPES)} '
                           f'(a tab group is `single_choice`)')

    # Reachability, which is NOT the same property as "every navigate target resolves".
    # A flow whose targets all resolve can still loop forever or strand a screen: measured
    # on a hand-built onboarding where two screens navigated back to the branch that sent
    # them, so the paywall was unreachable and every referential check passed.
    sids = [s['id'] for s in d.get('screens', [])]
    if sids:
        edges = {}
        for s in d['screens']:
            outs = []
            def collect(o):
                if isinstance(o, dict):
                    if o.get('type') == 'navigate':
                        t = (o.get('payload') or {}).get('screen')
                        if t: outs.append(t)
                    for v in o.values(): collect(v)
                elif isinstance(o, list):
                    for v in o: collect(v)
            collect(s)
            edges[s['id']] = outs
        seen, stack = set(), [sids[0]]
        while stack:
            cur = stack.pop()
            if cur in seen: continue
            seen.add(cur)
            stack.extend(t for t in edges.get(cur, []) if t in edges)
        unreachable = [x for x in sids if x not in seen]
        if unreachable:
            warn.append(f'screens unreachable from screens[0]: {unreachable}')
        # a screen with outbound edges that only ever lead back into already-seen screens,
        # and from which no terminal screen is reachable, is a trap
        terminals = [x for x in sids if not edges.get(x)]
        if terminals:
            can_end = set(terminals)
            changed = True
            while changed:
                changed = False
                for x in sids:
                    if x not in can_end and any(t in can_end for t in edges.get(x, [])):
                        can_end.add(x); changed = True
            trapped = [x for x in sids if x in seen and x not in can_end]
            if trapped:
                bad.append(f'no path from these screens to any end of the flow '
                           f'(navigation loop): {trapped}')

    presets = {t['id'] for t in d['theme']['typography']}
    colors = {c['id'] for c in d['theme']['colors']}
    up, uc = set(), set()
    def themerefs(o):
        if isinstance(o.get('preset'), str):
            up.add(o['preset'])
        if isinstance(o.get('colorId'), str):
            uc.add(o['colorId'])
    walk(d, themerefs)
    if up - presets:
        bad.append(f'font.preset not in theme.typography: {sorted(up - presets)}')
    if uc - colors:
        bad.append(f'colorId not in theme.colors: {sorted(uc - colors)}')

    fonts = {x['id'] for x in d.get('_meta', {}).get('fonts', [])}
    uf = set()
    walk(d, lambda o: uf.add(o['family']['id'])
         if isinstance(o.get('family'), dict) and o['family'].get('id') else None)
    if uf - fonts:
        bad.append(f'font.family.id not in _meta.fonts: {sorted(uf - fonts)}')

    used = {(e['props']['icon']['name'], e['props']['icon']['weight'])
            for _, e in els() if e['type'] == 'icon'}
    meta = {(i['name'], i['weight']) for i in d.get('_meta', {}).get('icons', [])}
    if used - meta:
        bad.append(f'icons used but absent from _meta.icons: {sorted(used - meta)}')

    refs = set()
    walk(d, lambda o: refs.add(o['id']) if o.get('type') == 'global' else None)
    unref = sorted(set(d.get('components', {})) - refs)
    if unref:
        warn.append(f'components defined but never referenced as global: {unref}')
    return bad, warn

rc = 0
for path in sys.argv[1:]:
    bad, warn = check(path)
    print(f'{os.path.basename(path):34} {"OK" if not bad else "VIOLATIONS"}')
    for b in bad:
        print(f'   ERROR:   {b}')
        rc = 1
    for w in warn:
        print(f'   warning: {w}')
sys.exit(rc)
