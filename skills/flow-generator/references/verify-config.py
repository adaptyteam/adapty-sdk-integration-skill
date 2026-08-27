#!/usr/bin/env python3
"""Verify the referential invariants of an Adapty flow config.

SCOPE: this SHIPS. It sits in `references/` alongside `validate-with-schema.mjs`, so it is
available to a runtime agent on any machine, not just inside the skills repo. Run it on the
config you are about to write, on a config you fetched, and on a fixture after re-sanitising
it. Every check is local and read-only: it opens one or more JSON files and prints findings.

    python3 references/verify-config.py draft.json          # from the skill directory
    python3 skills/flow-generator/references/verify-config.py tests/fixtures/*.json

It answers a third question the other two gates do not. `flows config validate` answers *is
this publishable* and skips most prop shapes; a schema check answers *are these props
well-formed* and knows nothing about publishability; this answers *do the document's internal
references agree* — and it owns outright the rows neither of the others looks at, notably
anything to do with an image, a top-level `status`/`id`, and a missing `states` key.

History worth keeping: this was called `verify-fixture.py` and lived in `tests/` until 2026-08-25 and therefore did NOT ship,
which quietly weakened several rules the repo had already escalated from prose to a mechanical
check -- every GREEN round that scored against those guards ran in-repo, where the file
existed, so the closures did not transfer to a customer install. Moving it here is what makes
them real everywhere.

Checks, in order: map keys match element ids; hierarchy references resolve;
navigate targets resolve; product elements AND `const` purchase targets are
declared in _meta.screens;
price variables reference declared products; selectableGroups and groupId agree
both ways; font.preset and colorId resolve in the file's own theme;
font.family resolves in _meta.fonts; every icon used appears in _meta.icons;
image elements carry a bound asset with a string id, since neither publish-time
gate looks at an image at all; no id is declared twice in any id-keyed
collection, and theme colour and typography ids do not collide.
Unreferenced components are reported as warnings, because real exports have them.

Severity rule: an ERROR is a publish blocker or a corrupt document; a WARNING is something
that publishes cleanly and renders wrong. A `const` matching no selection and a variable with
no producer are both the latter -- and the first of those is present in a real raw export, so
it is not a defect this repo introduced by sanitizing.

Usage: verify-config.py <config.json> [more.json ...]
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

    # `theme.colors` and `theme.typography` share ONE id namespace on the device. A collision
    # decodes as Swift `DecodingError.dataCorrupted ... "Duplicate Key"` and the flow fails to
    # open — while `validate`, the schema check and the render all pass it. Evidence: 8/8 real
    # exports (sanitized and raw) have zero overlap; the one collision seen in the wild was
    # authored here (a `footer` colour plus a `footer` preset), reported from an iOS device.
    theme = d.get('theme') or {}

    def _dups(seq):
        seq = [x for x in seq if x is not None]
        return sorted({x for x in seq if seq.count(x) > 1}, key=str)

    cids = [x.get('id') for x in (theme.get('colors') or []) if isinstance(x, dict)]
    tids = [x.get('id') for x in (theme.get('typography') or []) if isinstance(x, dict)]
    clash = sorted(set(cids) & set(tids))
    if clash:
        bad.append(f"theme id used by BOTH a colour and a typography preset: "
                   f"{', '.join(clash)} — the device decoder builds one keyed container from "
                   f"`theme` and throws DecodingError \"Duplicate Key\", so the flow will not "
                   f"open. No other gate catches this; rename one side")

    # A repeated id inside any id-keyed collection makes one entry unreachable however the
    # consumer decodes it, and where the consumer builds a dictionary it is the "Duplicate Key"
    # decode failure that took a flow down. Errors, because no real export contains one.
    meta = d.get('_meta') or {}
    icons = [i for i in (meta.get('icons') or []) if isinstance(i, dict)]
    for label, seq in (
            ('theme.colors id', cids),
            ('theme.typography id', tids),
            ('locales[].code', [l.get('code') for l in d.get('locales') or []]),
            ('locales[].id', [l.get('id') for l in d.get('locales') or []]),
            ('screens[].id', [x.get('id') for x in d.get('screens') or []]),
            ('variables[].id', [x.get('id') for x in d.get('variables') or []]),
            ('_meta.fonts[].id', [x.get('id') for x in (meta.get('fonts') or [])
                                  if isinstance(x, dict)]),
            ('_meta.icons name+weight', [(i.get('name'), i.get('weight')) for i in icons]),
    ):
        dupes = _dups(seq)
        if dupes:
            bad.append(f"{label} declared more than once: "
                       f"{', '.join(str(x) for x in dupes)}")

    # Same NAME at two weights is legal as far as anything here can prove -- but no real export
    # does it (0 of 8), and if the consumer keys icons by name alone it is the theme bug again.
    name_dupes = _dups([i.get('name') for i in icons])
    if name_dupes and not _dups([(i.get('name'), i.get('weight')) for i in icons]):
        warn.append(f"_meta.icons repeats the name(s) {', '.join(name_dupes)} at different "
                    f"weights — legal-looking, but no real export does it and it collides if "
                    f"icons are keyed by name")

    for s_ in d.get('screens') or []:
        gd = _dups([g.get('id') for g in s_.get('selectableGroups') or []])
        if gd:
            bad.append(f"screen {s_['id']}: selectableGroups declares {', '.join(gd)} twice")
        for eid, e in (s_.get('elements') or {}).get('map', {}).items():
            sd = _dups([x.get('id') for x in e.get('states') or []])
            if sd:
                bad.append(f"{eid}: states declares {', '.join(sd)} twice")
            idd = _dups([x.get('id') for x in e.get('interactions') or []])
            if idd:
                bad.append(f"{eid}: interactions declares {', '.join(idd)} twice")
            aid = [a.get('id') for i in e.get('interactions') or []
                   for a in i.get('actions') or [] if a.get('id')]
            ad = _dups(aid)
            if ad:
                bad.append(f"{eid}: action id {', '.join(ad)} used twice")

    for sid, dec in (meta.get('screens') or {}).items():
        pd = _dups([x.get('id') for x in (dec or {}).get('products') or []])
        if pd:
            bad.append(f"_meta.screens.{sid}.products declares {', '.join(pd)} twice")

    # Images are invisible to BOTH publish-time gates: `flows config validate` returned
    # valid:true on an empty values map, a numeric id and a missing id alike, and the schema
    # check passes them too, because `ILocalizable.values` is typed as an unconstrained
    # `additionalProperties`. So an empty hero publishes an "Upload Image" checkerboard to real
    # users, and this warning is the only mechanical slot that sees it. Measured 2026-08-24.
    empty_imgs, unstrung = [], []
    for _s, el in els():
        if el.get('type') != 'image':
            continue
        content = (el.get('props') or {}).get('image')
        if not isinstance(content, dict):
            continue
        vals = content.get('values') if content.get('_localizable') else {'_': content}
        if isinstance(vals, dict) and not vals:
            empty_imgs.append(el.get('id'))
        for code, entry in (vals or {}).items():
            if isinstance(entry, dict) and not isinstance(entry.get('id'), str):
                unstrung.append(f"{el.get('id')}[{code}]")
    if empty_imgs:
        warn.append(f"{len(empty_imgs)} image element(s) with an EMPTY values map "
                    f"({', '.join(str(i) for i in empty_imgs[:4])}"
                    f"{', …' if len(empty_imgs) > 4 else ''}) — they publish as an 'Upload Image' "
                    f"placeholder and no gate objects. Expected when no file exists: name each "
                    f"one in the handoff. If you WERE given the file, `flows media upload` it")
    if unstrung:
        warn.append(f"image asset id is missing or not a string on "
                    f"{', '.join(unstrung[:4])}{', …' if len(unstrung) > 4 else ''} — "
                    f"`flows media upload` prints a number, the schema wants a string")

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

    # The stretch-between-anchors pair: an absolute element anchored top AND bottom stretches to
    # its parent, and ONLY with height `auto`. Both halves are measured render failures on a
    # timeline rail and both read as "the line is too short", which is why they are mechanical:
    # `fill` with the anchors stopped 2px before the next chip, and `auto` with no bottom anchor
    # collapsed the rail and left 108px of white. Nothing else sees either one — the schema types
    # both heights as legal and `validate` has no opinion on layout.
    for s, e in els():
        p = (e.get('props') or {})
        pos, h = p.get('position'), p.get('height')
        if not isinstance(pos, dict) or not isinstance(h, dict):
            continue
        anchored = (pos.get('type') == 'absolute'
                    and pos.get('top') is not None and pos.get('bottom') is not None)
        if anchored and h.get('type') != 'auto':
            warn.append(f"{s['id']}/{e['id']}: absolute and anchored top+bottom, but height is "
                        f"{h.get('type')!r} — only `auto` stretches between the anchors; a fill "
                        f"height stops 2px short of where it should end")
        if h.get('type') == 'auto' and not anchored:
            warn.append(f"{s['id']}/{e['id']}: height `auto` without an absolute top+bottom "
                        f"anchor pair collapses to nothing — give it both offsets, or use a "
                        f"real height")

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

    # ---- a `const` compared against a selection must match something that exists.
    # transforms.md: a const matching nothing is NOT a publish blocker -- it silently sends
    # every user down the `default` branch, so routing changes with nothing failing. Renaming
    # a selectable option changes its `customId` and orphans every predicate keyed to it.
    # Predicate shape, from a real export:
    #   {"left": {"type":"var","variableId":"<gid>.selectedOptionId"},
    #    "type":"==", "right":{"type":"const","value":"<customId>"}}
    custom_by_group = {}
    for _s, _e in els():
        pr = _e.get('props') or {}
        if pr.get('groupId') and pr.get('customId') is not None:
            custom_by_group.setdefault(pr['groupId'], set()).add(pr['customId'])
    preds = []
    walk(d, lambda o: preds.append(o) if (
        o.get('type') == '==' and isinstance(o.get('left'), dict)
        and isinstance(o.get('right'), dict)) else None)
    for pd_ in preds:
        left, right = pd_['left'], pd_['right']
        if left.get('type') != 'var' or right.get('type') != 'const':
            continue
        vid, val = left.get('variableId'), right.get('value')
        if not isinstance(vid, str) or not isinstance(val, str):
            continue
        head = vid.split('.')[0]
        if vid.endswith('.selectedOptionId'):
            known = custom_by_group.get(head, set())
            if known and val not in known:
                warn.append(f'condition compares {vid} == {val!r}, but group {head!r} has no '
                            f'member with that customId (has: {sorted(known)}) — a dead route: '
                            f'this case never matches and every user takes `default`. Yours to '
                            f'fix if you wrote it this run; if it came with the config, report '
                            f'it and let the user decide')
        elif vid.endswith('.selectedProduct'):
            if val not in bound_products and val not in allprod:
                warn.append(f'condition compares {vid} == {val!r}, but no product with that id '
                            f'is bound on any screen — a dead route that never matches. Present '
                            f'in a real builder export, so expect it in fetched configs')

    # ---- every `<inputCustomId>.value` consumer still has its producing input element.
    # flow-schema.md invariant 12, and the failure is remote: delete the screen holding the
    # input and the consumers survive on screens you never opened, rendering empty.
    INPUT_TYPES = {'text-input', 'email-input', 'password-input', 'number-input',
                   'phone-input', 'date-picker', 'time-picker', 'date-time-picker'}
    produced = {(e.get('props') or {}).get('customId')
                for _, e in els() if e['type'] in INPUT_TYPES}
    group_ids = {g['id'] for s_ in d.get('screens', [])
                 for g in (s_.get('selectableGroups') or [])}
    for v in sorted(set(vids)):
        parts = v.split('.')
        if len(parts) != 2 or parts[1] != 'value':
            continue
        if parts[0] in group_ids or parts[0] in allprod or parts[0] in bound_products:
            continue                      # a group/product variable, not an input
        if parts[0] not in produced:
            warn.append(f'variable {v} has no producer: no input element carries '
                        f'customId {parts[0]!r} (invariant 12 — renders empty, publishes '
                        f'cleanly, and the consumers are often on screens you never opened)')

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

    # A countdown's digits are rich-text `token` nodes, and the builder only resolves the
    # timer_-prefixed ids. The bare names save and `validate` clean, but the Flow Builder paints
    # them red "Unknown" and the device/preview renders the literal "%hours%". Measured
    # 2026-08-25 (builder- and device-confirmed: the prefixed ids render live `23:59:59`).
    # `component-catalog.json` shipped the bare names until 2026-08-25, so a timer lifted from a
    # template is the usual source of this. Render-wrong-but-publishes, so a warning by the
    # severity rule — but it is the author's to fix if this run wrote it.
    valid_timer_tokens = {'timer_days', 'timer_hours', 'timer_minutes', 'timer_seconds'}
    bad_tokens = []
    def _timer_tokens(o):
        if isinstance(o, dict):
            if o.get('type') == 'token':
                t = (o.get('attrs') or {}).get('token')
                if isinstance(t, str) and t not in valid_timer_tokens:
                    bad_tokens.append(t)
            for v in o.values():
                _timer_tokens(v)
        elif isinstance(o, list):
            for v in o:
                _timer_tokens(v)
    _timer_tokens(d)
    if bad_tokens:
        warn.append(f"timer token(s) {sorted(set(bad_tokens))} are not resolved by the Flow "
                    f"Builder (it shows red 'Unknown', and the device/preview renders the literal "
                    f"'%name%'). Timer tokens carry a timer_ prefix — one of "
                    f"{sorted(valid_timer_tokens)}. If you lifted a timer from "
                    f"component-catalog.json, add the prefix; flowkit.timer_digits() emits it")
    # `footer` is the pinned bottom bar, and all three of these were measured 2026-08-26 by
    # rendering one screen eight ways. The element is lifted out of the flow and pinned to the
    # viewport bottom; the same props under `type: "stack"` land below the fold.
    for s in d.get('screens', []):
        m = s['elements']['map']
        feet = [k for k, e in m.items() if e.get('type') == 'footer']
        # DEVICE-CONFIRMED 2026-08-26: a footer on a non-scrollable screen does not render at
        # all, and its children go with it — so a CTA inside it takes the screen's only
        # navigation. Invisible to every local gate (preview draws it in both modes, and both
        # the schema check and `flows config validate` pass it), which is exactly why it is
        # mechanical here. Error, not warning: the bar is simply gone on a device.
        if feet and s['props'].get('scrollable') is False:
            bad.append(f'screen {s["id"]}: footer {feet[0]} on a NON-SCROLLABLE screen — '
                       f'device-confirmed to not render at all, taking any CTA inside it with '
                       f'it. Set scrollable true, or drop the footer and use the root\'s '
                       f'distribution: space-between for a bottom bar.')
        # A SECOND footer drew zero pixels — not misplaced, absent. Certainly broken, so an error.
        if len(feet) > 1:
            bad.append(f'screen {s["id"]}: {len(feet)} footer elements ({sorted(feet)}) — a '
                       f'second footer draws NOTHING. Put the CTA and the legal row inside one '
                       f'footer as children.')
        # A footer overlays the scrolling content, so with no fill the content passes visibly
        # behind the CTA. Legal (and fine on a short screen over a matching background), hence a
        # warning — but on a scrollable screen it is the defect that gets misread as a docking bug.
        for k in feet:
            if not (m[k].get('props') or {}).get('fill'):
                warn.append(f'screen {s["id"]}: footer {k} has no fill, and a footer overlays the '
                            f'scrolling content — the content will show through the bar')
            pos = ((m[k].get('props') or {}).get('position') or {}).get('type')
            if pos and pos != 'relative':
                warn.append(f'screen {s["id"]}: footer {k} is positioned {pos!r} — a footer is '
                            f'already pinned, and positioning one is the fake-footer shape')
        # The FAKE FOOTER: an empty `fixed` stack carrying a fill, parked behind separately
        # docked elements to fake an opaque bar. It reproduces the fill and the position and none
        # of the pinning, and every other gate here passes it. Warning, because an empty fixed
        # filled stack is legal (a divider, a scrim) — but on a screen with no footer and other
        # docked siblings it is almost always this.
        kids = set()
        def _kids(n, _k=kids):
            for c in n.get('children') or []:
                _k.add(c['id'])
                _kids(c)
        _kids(s['elements']['hierarchy'])
        for k, e in m.items():
            props = e.get('props') or {}
            if (e.get('type') == 'stack' and not feet
                    and (props.get('position') or {}).get('type') == 'fixed'
                    and props.get('fill') and not e.get('interactions')):
                # childless in the hierarchy = a backing plate rather than a real container
                def _has_children(nid, node=s['elements']['hierarchy']):
                    found = []
                    def w(n):
                        if n.get('id') == nid:
                            found.append(bool(n.get('children')))
                        for c in n.get('children') or []:
                            w(c)
                    w(node)
                    return any(found)
                if not _has_children(k):
                    warn.append(
                        f'screen {s["id"]}: {k} is an empty `fixed` stack with a fill and no '
                        f'interaction, and this screen has no footer — that is the "fake footer" '
                        f'shape (a backing plate behind docked elements). The pinned opaque bar '
                        f'is a `footer` element; see patterns.md')
                else:
                    # The commoner fake footer, and the one BOTH control arms of the GREEN round
                    # produced: not an empty plate but a full-bleed `fixed` container with a fill
                    # and no action of its own, holding the legal links. Keyed on full-bleed
                    # (left+right+bottom all 0) so a real docked CTA at {left:24,right:24,bottom:N}
                    # -- the shape three real exports carry -- does not trip it.
                    pos = props.get('position') or {}
                    if all(pos.get(x) == 0 for x in ('left', 'right', 'bottom')):
                        warn.append(
                            f'screen {s["id"]}: {k} is a full-bleed `fixed` bar with a fill and no '
                            f'action of its own, on a screen with no footer — that is a hand-built '
                            f'footer. A `footer` element pins itself, needs no offsets, and needs '
                            f'no `padding.bottom` reservation (authoring one adds dead space at '
                            f'full scroll); see patterns.md')

    # A FAKE CAROUSEL or FAKE PROGRESS BAR: a slider or a step indicator faked as a static card
    # plus a row of decorative dot `stack`s. The real `carousel` is swipeable and renders its OWN
    # dots (props.dots: {size, color, activeColor}); the real `progress-bar` is a `components`
    # entry wired per screen via props.progressBar — both advance, hand-built dots do not (one
    # slide/step ever shows and the dots are inert). Same class as the fake footer and the fake
    # spinner, and no other gate sees it. Heuristic, hence a warning.
    #
    # Keyed on dot-like SIBLINGS -- >=3 tiny equal rounded leaf stacks that are direct children
    # of ONE parent, which is the shape of an indicator row. Screen-wide counting tripped on
    # list bullet dots (one dot per list row, each in its own parent), a real false positive
    # measured against a live flow; requiring one shared parent drops those and still catches
    # the indicator row, whose dots are always siblings.
    def _dotlike(e):
        if e.get('type') != 'stack' or e.get('children'):
            return False
        pr = e.get('props') or {}
        w, h = pr.get('width') or {}, pr.get('height') or {}
        wv, hv = w.get('value'), h.get('value')
        return (w.get('type') == 'fixed' and h.get('type') == 'fixed'
                and wv == hv and isinstance(wv, (int, float)) and wv <= 12
                and bool(pr.get('borderRadius')))
    for s in d.get('screens', []):
        m = s['elements']['map']
        if any(e.get('type') == 'carousel' for e in m.values()):
            continue
        # walk the hierarchy; at every node, look at its DIRECT children for a dot-indicator row
        def _walk(n):
            kids = n.get('children') or []
            sib_dots = sorted(c['id'] for c in kids
                              if not c.get('children') and _dotlike(m.get(c['id'], {})))
            if len(sib_dots) >= 3:
                warn.append(
                    f'screen {s["id"]}: {len(sib_dots)} dot-like sibling stacks ({sib_dots}) '
                    f'under one parent and no `carousel` element — likely a FAKE CAROUSEL or '
                    f'progress indicator (a static card/row with decorative dots). Use the real '
                    f'`carousel` (swipeable, renders its own dots via props.dots) or the '
                    f'`progress-bar` component; never hand-build one from dot stacks. See '
                    f'patterns.md')
            for c in kids:
                _walk(c)
        _walk(s['elements']['hierarchy'])

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
