#!/usr/bin/env python3
"""Verify the referential invariants of a flow-config fixture.

SCOPE: this guards the FIXTURES in this repo — it is not part of the
flow-generator skill, which ships no scripts by owner decision (a `validate`
command is planned for the Adapty CLI). Use it after editing or re-sanitizing a
fixture, and when a new `schemaVersion` appears, to confirm the fixture is still
a valid document rather than a subtly broken one.

Checks, in order: map keys match element ids; hierarchy references resolve;
navigate targets resolve; product elements AND `const` purchase targets are
declared in _meta.screens;
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

    # An undeclared-but-bound product is a WARNING, not an error: measured, the Flow Builder
    # mints the `flowProductId` and writes the declaration the first time someone opens the
    # flow, keeping the binding as written. An agent cannot author it (the id is a UUIDv5 over
    # an input the config does not contain), so a config an agent produced is EXPECTED to look
    # like this and calling it an error just teaches you to ignore findings.

    # A locale transform is the one change with NO render check — `config preview` ignores locale
    # entirely — so structural parity is the only gate there is. Checks every DECLARED locale,
    # not merely the ones that happen to be present on a field.
    declared = [l.get('code') for l in d.get('locales', []) if l.get('code')]
    loc_vals = []

    def _collect(o):
        if isinstance(o, dict):
            if o.get('_localizable') and isinstance(o.get('values'), dict):
                loc_vals.append(o['values'])
            for v in o.values():
                _collect(v)
        elif isinstance(o, list):
            for v in o:
                _collect(v)

    _collect(d)

    # A browser export carries top-level `status` and `id`; a stored fixture keeping them is
    # fine, but a FILE DELIVERABLE that ships status:"published" imports as live-looking content,
    # and two GREEN-round agents shipped exactly that after reading every prose placement of the
    # rule (finding 10, rounds 6-7). Both agents ran THIS check and quoted its output faithfully,
    # so the warning is the mechanical slot the prose could not be.
    if d.get('status') == 'published':
        warn.append("top-level status is 'published' — fine for a stored export; NEVER ship it in "
                    "a file deliverable. Drop status/id or set draft, and say which you chose")
    elif 'status' in d or 'id' in d:
        warn.append(f"top-level {'status' if 'status' in d else ''}"
                    f"{'+' if 'status' in d and 'id' in d else ''}{'id' if 'id' in d else ''} "
                    f"present — for a file deliverable, say whether you kept or dropped them; "
                    f"the id names the flow the export came FROM")

    # A value under a code that `locales[]` does not declare renders nowhere. It is usually half a
    # locale run — the values written, the declaration forgotten — and the parity check above
    # cannot see it, because that walks DECLARED locales only. Runs even for a single-locale flow,
    # which is exactly where a stray hides.
    seen_codes = {code for vals in loc_vals for code in vals}
    stray = sorted(seen_codes - set(declared))
    if stray:
        n = sum(1 for vals in loc_vals if seen_codes.intersection(vals) & set(stray))
        warn.append(f"locale value(s) for {', '.join(stray)} on {n} field(s), but "
                    f"{'none of them are' if len(stray) > 1 else 'it is not'} in locales[] — "
                    f"nothing renders them. If this run wrote them, declaring the locale is the "
                    f"fix, not this warning; if they were already in the fetched config, report "
                    f"and ask")

    if len(declared) > 1:
        base = d.get('defaultLocale') or declared[0]

        def _blocks(v):
            """Block arrays out of a localizable value.

            A value is normally a list of blocks, but it may also be a `switch` expression whose
            cases and default each yield their own block array (a real builder export does this
            for copy that changes with the selected product). Flatten in a stable order so two
            locales are compared branch for branch.
            """
            if isinstance(v, list):
                return [v]
            if isinstance(v, dict) and v.get('type') == 'switch':
                out = []
                for case in v.get('cases') or []:
                    result = case[1] if isinstance(case, list) and len(case) > 1 else None
                    if isinstance(result, dict) and isinstance(result.get('value'), list):
                        out.append(result['value'])
                dflt = v.get('default')
                if isinstance(dflt, dict) and isinstance(dflt.get('value'), list):
                    out.append(dflt['value'])
                return out
            return []

        def _spans(v):
            return [s for blocks in _blocks(v) for b in blocks for s in (b.get('content') or [])]

        def _kinds(v):
            return ([s.get('type') for s in _spans(v)]
                    if not isinstance(v, str) else ['<plain-string>'])

        def _varids(v):
            return [s.get('attrs', {}).get('variableId') for s in _spans(v)
                    if s.get('type') == 'variable'] if not isinstance(v, str) else []

        def _branches(v):
            return len(_blocks(v))

        for vals in loc_vals:
            src = vals.get(base)
            if src is None:
                continue
            label = (src if isinstance(src, str) else ''.join(
                s.get('text', '') for s in _spans(src)))[:40]
            for code in declared:
                if code == base:
                    continue
                if code not in vals:
                    bad.append(f'locale {code}: no value for {label!r}')
                elif _branches(vals[code]) != _branches(src):
                    bad.append(f'locale {code}: {_branches(vals[code])} conditional branch(es) '
                               f'against {_branches(src)} in {base} on {label!r} — a conditional '
                               f'text is translated per branch, and a missing branch falls back '
                               f'to the wrong language')
                elif _varids(vals[code]) != _varids(src):
                    bad.append(f'locale {code}: variable nodes differ from {base} on {label!r} — '
                               f'a translated block must be a structural copy, or the locale '
                               f'loses its price')
                elif _kinds(vals[code]) != _kinds(src):
                    warn.append(f'locale {code}: span kinds differ from {base} on {label!r}')
    # Stale sizing values persist through the editor and the transformer BELIEVES them:
    # hug carrying value -> min:<value> on device (ADP-7308, team-diagnosed; content vanished at
    # 8008). Real exports carry small ones routinely (16 in one rendering fixture), so warning,
    # not error. fixed:0 kills the element on device.
    for s, e in els():
        for dim in ('width', 'height'):
            v = (e.get('props') or {}).get(dim)
            if isinstance(v, dict):
                if v.get('type') in ('hug', 'fill') and 'value' in v:
                    lvl = bad if v['value'] > 1000 else warn
                    lvl.append(f"{s['id']}/{e['id']}: {dim} is {v['type']} but carries a stale "
                               f"value {v['value']} — the transformer turns it into "
                               f"min:{v['value']} on device"
                               + (' (bigger than any screen: content will vanish)'
                                  if v['value'] > 1000 else ''))
                if v.get('type') == 'fixed' and not v.get('value'):
                    bad.append(f"{s['id']}/{e['id']}: {dim} fixed at {v.get('value')!r} — "
                               f"saves fine, kills the element on device")

    # groupId naming rules, both team-stated from publish failures: digit-led ids generate
    # invalid JavaScript (publish blocker), and a groupId reused on another screen broke
    # selection rendering.
    seen_groups = {}
    for s in d.get('screens', []):
        for g in s.get('selectableGroups') or []:
            gid = g.get('id', '')
            if gid[:1].isdigit():
                bad.append(f"{s['id']}: groupId {gid!r} starts with a digit — generates invalid "
                           f"JavaScript and blocks publish")
            if gid in seen_groups and seen_groups[gid] != s['id']:
                warn.append(f"groupId {gid!r} is used on both {seen_groups[gid]} and {s['id']} — "
                            f"a shared id across screens broke selection rendering; rename to "
                            f"unique")
            seen_groups.setdefault(gid, s['id'])

    ms = d.get('_meta', {}).get('screens', {})
    for s, e in els():
        if e['type'] == 'product':
            pid = (e.get('props') or {}).get('product', {}).get('id')
            decl = {p['id'] for p in ms.get(s['id'], {}).get('products', [])}
            if pid not in decl:
                warn.append(f'product {pid} bound on screen {s["id"]} but not yet declared in '
                            f'_meta.screens, so device preview returns HTTP 422 '
                            f'missing_flow_product_id until the builder saves. For an authored '
                            f'flow, declare it yourself: flowkit.predeclare()')

    # A `const` purchase action names a product with no element behind it, so the
    # declaration harvester — which walks `product` elements only — never sees it.
    # Measured 2026-08-24 against adapty/0.8.0 in production: `flows config validate`
    # refuses such a config with the same `missing flowProductId` error, path ending
    # `.purchase.product`. The render says nothing, because the preview page does not
    # run the transform service. Warning, not error, for the same reason as above: an
    # agent-authored config is expected to look this way until predeclare() runs.
    for s in d.get('screens', []):
        decl = {p['id'] for p in ms.get(s['id'], {}).get('products', [])}
        const_purchased = set()

        def collect(o, _s=s, _acc=const_purchased):
            if o.get('type') != 'purchase':
                return
            prod = (o.get('payload') or {}).get('product') or {}
            if prod.get('type') == 'const':
                pid = (prod.get('value') or {}).get('id')
                if pid:
                    _acc.add(pid)

        walk(s, collect)
        for pid in sorted(const_purchased - decl):
            warn.append(f'product {pid} is bought by a `const` purchase on screen {s["id"]} '
                        f'but not declared in _meta.screens, so the flow is not publishable '
                        f'("missing flowProductId", path ...purchase.product). Rendering is '
                        f'unaffected, which is why this is invisible in a preview. For an '
                        f'authored flow, declare it yourself: flowkit.predeclare()')

    # A price variable comes in TWO forms, and only one is product-relative:
    #   <productUUID>.prod_price_per_year      — bound to one specific product
    #   <groupId>.selectedProduct.prod_price   — bound to whatever the group has selected
    # The second resolves against a product-type selectableGroup, not against a
    # product id, so validating its first segment as a UUID is a false positive.
    # Only the first form appears in this corpus; the second was observed in a real
    # Flow Builder screen and is accepted here so a valid file is not rejected.
    allprod = {p['id'] for v in ms.values() for p in v.get('products', [])}
    bound_products = {(e.get('props') or {}).get('product', {}).get('id')
                      for _, e in els() if e['type'] == 'product'}
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
            # Same split as above: if the product is bound to an element on some screen, the
            # declaration is pending rather than missing, and the builder supplies it on open.
            if head in bound_products:
                warn.append(f'price variable {v} awaits the declaration the builder writes on '
                            f'save; until then it renders as its literal token and device '
                            f'preview returns 422 unknown_product_id')
            else:
                bad.append(f'price variable references a product bound nowhere: {v}')

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

        # A price variable resolves only against the screen's DECLARED products, and only
        # the builder can declare one — by attaching it to a `product` element. A screen with
        # price variables but no product element is therefore unattachable, not merely
        # unattached: the builder rejects it with "Unknown Product Id" on publish. A `const`
        # purchase payload buys a product but declares nothing, so it does not satisfy this.
        has_price_var = 'prod_price' in json.dumps(s)
        has_product_el = any(e['type'] == 'product' for e in s['elements']['map'].values())
        if has_price_var and not has_product_el:
            bad.append(f'screen {s["id"]}: uses price variables but has no `product` element, '
                       f'so no product can ever be attached and the variables cannot resolve '
                       f'(builder reports "Unknown Product Id"). Wrap the price block in a '
                       f'`product` element, even if the design has no visible plan card.')

        # A group member's ELEMENT TYPE is load-bearing. IStackElementProps has no groupId
        # and no default, so a stack carrying them is not a member: the props are ignored, it
        # never gets the `selected` state, and tapping it does nothing. Real exports use
        # `product` for product groups, `selectable` for single/multi/toggle, `tab-item` in tabs.
        legal_members = {'product', 'selectable', 'tab-item'}
        for eid, e in s['elements']['map'].items():
            if (e.get('props') or {}).get('groupId') and e['type'] not in legal_members:
                bad.append(f'{eid}: type `{e["type"]}` carries groupId '
                           f'`{e["props"]["groupId"]}` but only {sorted(legal_members)} can be '
                           f'group members — a stack with groupId is inert and will not respond '
                           f'to taps')

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
