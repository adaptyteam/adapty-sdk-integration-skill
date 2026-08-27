#!/usr/bin/env python3
"""Save a piece of an Adapty flow to a local file, and graft it into another flow.

SCOPE: this SHIPS, alongside `verify-config.py` and `diff-config.py`. Standard library
only, fully offline -- live dashboard data reaches it as a `--catalog` file the agent
fetched, never as a call from here.

    python3 references/snippet.py extract --config flow.json --element el_X \
        --name "Annual plan card" --out adapty-flow-snippets/annual-plan-card.flow-snippet.json
    python3 references/snippet.py plan  --config dest.json --snippet s.json --screen scr_1
    python3 references/snippet.py graft --config dest.json --snippet s.json --screen scr_1 \
        --out grafted.json

`plan` and `graft` take identical flags: committing means changing one word.

Exit 0 clean, 1 the run produced findings a human must act on, 2 usage or unreadable input.
Exit 1 is a DISCLOSURE OBLIGATION, not a defect -- the same call `diff-config.py` makes.
"""
import argparse, json, os, re, sys, time

FORMAT_VERSION = 1


def die(msg, code=2):
    print(f'snippet.py: {msg}', file=sys.stderr)
    sys.exit(code)


def load(path):
    """Read a flow config. Accepts the bare config or the `config get` envelope."""
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        die(f'cannot read {path}: {e}')
    if not isinstance(doc, dict):
        die(f'{path} does not look like a flow config (expected a JSON object, '
            f'got {type(doc).__name__})')
    if 'screens' not in doc and isinstance(doc.get('config'), dict):
        doc = doc['config']
    if 'screens' not in doc:
        die(f'{path} does not look like a flow config (no `screens`)')
    return doc


def find_node(hierarchy, eid):
    """Locate a hierarchy node by id. Returns (node, parent, index)."""
    def walk(node, parent, index):
        if node.get('id') == eid:
            return node, parent, index
        for i, child in enumerate(node.get('children') or []):
            hit = walk(child, node, i)
            if hit[0] is not None:
                return hit
        return None, None, None
    return walk(hierarchy, None, None)


def subtree_ids(node):
    """`node` plus every descendant id, depth-first, node itself first."""
    out = [node['id']]
    for child in node.get('children') or []:
        out.extend(subtree_ids(child))
    return out


def walk(o, fn):
    """Call fn on every dict in the tree. Same shape as verify-config.py's walker,
    deliberately -- the two must agree about what they can see."""
    if isinstance(o, dict):
        fn(o)
        for v in o.values():
            walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            walk(v, fn)


def _screen_by_id(config, sid):
    for s in config['screens']:
        if s['id'] == sid:
            return s
    die(f'no screen {sid} in this config')


def fragment_of(config, target):
    """Resolve a target spec to (elements_map_slice, hierarchy_node, screen).

    `target` is `<elementId>@<screenId>`, or `root@<screenId>` for a whole screen.
    A `pb_*` id resolves against top-level `components` and returns screen None.
    """
    if target.startswith('pb_'):
        comp = config.get('components', {}).get(target)
        if comp is None:
            die(f'no component {target}')
        return dict(comp['map']), comp['hierarchy'], None
    if '@' not in target:
        die(f'target must be <elementId>@<screenId> or pb_<id>, got {target!r}')
    eid, sid = target.split('@', 1)
    screen = _screen_by_id(config, sid)
    node, _parent, _i = find_node(screen['elements']['hierarchy'], eid)
    if node is None:
        die(f'no element {eid} on screen {sid}')
    ids = subtree_ids(node)
    slice_ = {i: screen['elements']['map'][i] for i in ids
              if i in screen['elements']['map']}
    return slice_, node, screen


def _sort_icons(icons):
    """Sort (name, weight) pairs with a missing weight ordered deterministically --
    Python 3 cannot order None against str, and a shared icon name with and without
    a declared weight is a legal input, not a malformed one."""
    return sorted((list(i) for i in icons), key=lambda i: (i[0], i[1] or ''))


def scan_dependencies(config, elements, node):
    """Every id the fragment references but does not itself define."""
    colors, presets, fonts, icons, comps = set(), set(), set(), set(), set()
    groups, products, consumes, tokens = set(), set(), set(), set()

    def visit(o):
        if isinstance(o.get('colorId'), str):
            colors.add(o['colorId'])
        if isinstance(o.get('preset'), str):
            presets.add(o['preset'])
        if isinstance(o.get('family'), dict) and isinstance(o['family'].get('id'), str):
            fonts.add(o['family']['id'])
        if isinstance(o.get('groupId'), str):
            groups.add(o['groupId'])
        if isinstance(o.get('variableId'), str):
            consumes.add(o['variableId'])
        attrs = o.get('attrs')
        if isinstance(attrs, dict):
            if isinstance(attrs.get('variableId'), str):
                consumes.add(attrs['variableId'])
            if isinstance(attrs.get('token'), str):
                tokens.add(attrs['token'])

    def scan_elements(els):
        for eid, el in els.items():
            walk(el, visit)
            if el.get('type') == 'icon':
                ic = (el.get('props') or {}).get('icon') or {}
                if ic.get('name'):
                    icons.add((ic['name'], ic.get('weight')))
            if el.get('type') == 'product':
                pid = ((el.get('props') or {}).get('product') or {}).get('id')
                if pid:
                    products.add(pid)
            # A `const` purchase binds a product with no product element behind it.
            walk(el, lambda o: products.add(o['product']['id'])
                 if isinstance(o.get('product'), dict)
                 and isinstance(o['product'].get('id'), str) else None)

    # A hierarchy node with `type: global` points into top-level `components`.
    def hier(n, into):
        if n.get('type') == 'global' and isinstance(n.get('id'), str):
            into.add(n['id'])
        for c in n.get('children') or []:
            hier(c, into)

    scan_elements(elements)
    hier(node, comps)

    # A component the fragment pulls in has dependencies of its own, and can pull in
    # further components of its own. Drain a worklist -- comps grows as it runs, so a
    # single `for cid in list(comps)` pass would miss anything found this round -- and
    # track `seen` so a cycle (a component referencing itself, directly or through
    # another) terminates instead of looping. Every element and nested-component walk
    # feeds the SAME accumulator sets above, so all nine keys are covered, not a
    # hand-picked subset.
    seen = set()
    worklist = list(comps)
    while worklist:
        cid = worklist.pop()
        if cid in seen:
            continue
        seen.add(cid)
        comp = config.get('components', {}).get(cid)
        if not comp:
            continue
        scan_elements(comp['map'])
        found = set()
        hier(comp['hierarchy'], found)
        comps |= found
        worklist.extend(found - seen)

    return {'colors': sorted(colors), 'typography': sorted(presets),
            'fonts': sorted(fonts), 'icons': _sort_icons(icons),
            'components': sorted(comps), 'groups': sorted(groups),
            'products': sorted(products), 'consumes': sorted(consumes),
            'tokens': sorted(tokens)}


def _by_id(seq, key='id'):
    return {x[key]: x for x in seq if isinstance(x, dict) and key in x}


def definitions_for(config, deps):
    """Turn dependency IDS into dependency DEFINITIONS, closing the transitive
    preset -> font path (invariant 9's second reference path) on the way."""
    theme = config.get('theme') or {}
    colors = _by_id(theme.get('colors') or [])
    presets = _by_id(theme.get('typography') or [])
    fonts = _by_id((config.get('_meta') or {}).get('fonts') or [])
    icons = {(i['name'], i.get('weight')): i
             for i in (config.get('_meta') or {}).get('icons') or []}
    variables = _by_id(config.get('variables') or [])
    comps = config.get('components') or {}

    out_presets = [presets[p] for p in deps['typography'] if p in presets]
    font_ids = set(deps['fonts'])
    for t in out_presets:                       # a preset may name a font of its own
        fam = ((t.get('settings') or {}).get('family') or {}).get('id')
        if fam:
            font_ids.add(fam)

    # A consumed variable may be an app-supplied custom one, declared in `variables[]`.
    heads = {c.split('.')[0] for c in deps['consumes']}
    out_vars = [variables[v] for v in variables
                if v in heads or variables[v].get('name') in deps['consumes']]

    return {
        'colors': [colors[c] for c in deps['colors'] if c in colors],
        'typography': out_presets,
        'fonts': [fonts[f] for f in sorted(font_ids) if f in fonts],
        'icons': [icons[tuple(i)] for i in deps['icons'] if tuple(i) in icons],
        'variables': out_vars,
        'components': {c: comps[c] for c in deps['components'] if c in comps},
        'groups': [], 'products': [], 'media': [],
        'consumes': list(deps['consumes']),
        'producesInternally': [], 'navigateTargets': [],
        'locales': [l['id'] for l in config.get('locales') or []],
        'defaultLocale': config.get('defaultLocale'),
    }


MEDIA_RE = re.compile(r'^https?://')


def _enrich(config, deps, defs, elements, screen, catalog):
    # Groups: the declaration lives on the screen, not in the element.
    declared = _by_id((screen or {}).get('selectableGroups') or [])
    defs['groups'] = [dict(declared[g],
                           memberCustomIds=sorted(
                               (e.get('props') or {}).get('customId')
                               for e in elements.values()
                               if (e.get('props') or {}).get('groupId') == g
                               and (e.get('props') or {}).get('customId')))
                      for g in deps['groups'] if g in declared]
    # Produced internally: a group inside the payload, and any text-input customId.
    produced = [f'{g["id"]}.selectedOptionId' for g in defs['groups']]
    produced += [f'{(e.get("props") or {}).get("customId")}.value'
                 for e in elements.values()
                 if str(e.get('type', '')).endswith('-input')
                 or e.get('type') == 'text-input']
    defs['producesInternally'] = sorted(x for x in produced if 'None' not in str(x))
    # Products: bare UUIDs, enriched from the catalog when one was given.
    cat = {}
    if catalog:
        try:
            rows = json.load(open(catalog))
            rows = rows.get('data', rows) if isinstance(rows, dict) else rows
            cat = {r['id']: r for r in rows if isinstance(r, dict) and 'id' in r}
        except (OSError, ValueError, KeyError):
            cat = {}
    prods = []
    for pid in deps['products']:
        row = cat.get(pid) or {}
        vend = row.get('vendor_products') or {}
        store = vend.get('app_store') or vend.get('play_store') or {}
        prods.append({'id': pid, 'title': row.get('title'),
                      'vendorProductId': store.get('product_id'),
                      'basePlanId': store.get('base_plan_id')})
    defs['products'] = prods
    # Media: every absolute URL anywhere in the payload.
    urls = set()
    walk(elements, lambda o: [urls.add(v) for v in o.values()
                              if isinstance(v, str) and MEDIA_RE.match(v)])
    defs['media'] = sorted(urls)
    # Navigate targets.
    tgt = set()
    walk(elements, lambda o: tgt.add(o['payload']['screen'])
         if o.get('type') == 'navigate' and isinstance(o.get('payload'), dict)
         and isinstance(o['payload'].get('screen'), str) else None)
    defs['navigateTargets'] = sorted(tgt)
    return defs


def build_snippet(config, kind, target, name, description, scope, catalog, source_app):
    if kind == 'theme':
        elements, node, screen = {}, {'id': 'root'}, None
        deps = {'colors': [c['id'] for c in (config.get('theme') or {}).get('colors') or []],
                'typography': [t['id'] for t in
                               (config.get('theme') or {}).get('typography') or []],
                'fonts': [f['id'] for f in (config.get('_meta') or {}).get('fonts') or []],
                'icons': [[i['name'], i.get('weight')]
                          for i in (config.get('_meta') or {}).get('icons') or []],
                'components': [], 'groups': [], 'products': [], 'consumes': [],
                'tokens': []}
        payload = None
    else:
        elements, node, screen = fragment_of(config, target)
        deps = scan_dependencies(config, elements, node)
        if kind == 'screen':
            payload = {'screen': screen}
        elif kind == 'component':
            payload = {'componentId': target, 'map': elements, 'hierarchy': node}
        else:
            payload = {'rootId': node['id'], 'map': elements, 'hierarchy': node}
    defs = definitions_for(config, deps)
    defs = _enrich(config, deps, defs, elements, screen, catalog)
    return {
        'formatVersion': FORMAT_VERSION,
        'kind': kind,
        'name': name,
        'description': description or '',
        'savedAt': None,          # filled by the caller; see note below
        'source': {'app': source_app, 'flowName': None,
                   'screenId': (screen or {}).get('id'),
                   'schemaVersion': config.get('schemaVersion')},
        'intendedScope': scope,
        'payload': payload,
        'dependencies': defs,
    }


def report_extract(snip):
    d = snip['dependencies']
    print(f'{snip["name"]}  [{snip["kind"]}]')
    payload = snip.get('payload') or {}
    scoped = payload.get('screen') or payload
    emap = scoped.get('map') or (scoped.get('elements') or {}).get('map') or {}
    if emap:
        print(f'  {len(emap)} elements')
    for label in ('colors', 'typography', 'fonts', 'icons', 'components',
                  'groups', 'products', 'media'):
        n = len(d.get(label) or [])
        if n:
            print(f'  {label:12} {n}')
    needs = []
    for p in d.get('products') or []:
        if not p.get('vendorProductId'):
            needs.append(f'product {p["id"][:8]}… has no store id recorded — pass '
                         f'--catalog if you want this reusable in another app')
    inside = set(d.get('producesInternally') or [])
    for c in d.get('consumes') or []:
        if c not in inside and not any(h.split('.')[0] == c.split('.')[0]
                                       for h in inside):
            needs.append(f'variable {c} is produced outside this fragment — the '
                         f'destination must supply it')
    for e in emap.values():
        if e.get('type') == 'image':
            vals = (((e.get('props') or {}).get('asset') or {}).get('values')
                    or (e.get('props') or {}).get('values'))
            if isinstance(vals, dict) and not vals:
                needs.append(f'element {e["id"]} is an image with an empty `values` '
                             f'map — a placeholder, not an asset')
    for n in needs:
        print(f'  ! {n}')
    return 1 if needs else 0


SNIPPET_DIR = 'adapty-flow-snippets'


def snippet_dir(start=None):
    """(path, exists). An existing folder wins: repo root, then $HOME. Otherwise the
    proposed default, which the agent must put to the user before writing into it."""
    here = os.path.abspath(start or os.getcwd())
    root = here
    while True:
        if os.path.isdir(os.path.join(root, '.git')):
            break
        parent = os.path.dirname(root)
        if parent == root:
            root = None
            break
        root = parent
    home = os.path.join(os.path.expanduser('~'), SNIPPET_DIR)
    if root:
        cand = os.path.join(root, SNIPPET_DIR)
        if os.path.isdir(cand):
            return cand, True
    if os.path.isdir(home):
        return home, True
    return (os.path.join(root, SNIPPET_DIR) if root else home), False


def read_snippet(path):
    try:
        with open(path) as fh:
            s = json.load(fh)
    except (OSError, ValueError) as e:
        die(f'cannot read {path}: {e}')
    if not isinstance(s, dict):
        die(f'{path} does not look like a flow snippet (expected a JSON object, '
            f'got {type(s).__name__})')
    if s.get('formatVersion') != FORMAT_VERSION:
        die(f'{path}: formatVersion {s.get("formatVersion")}, this tool speaks '
            f'{FORMAT_VERSION}')
    return s


def _same_definition(a, b):
    """Equal ignoring `id` and `name` -- two flows may label one token differently."""
    strip = lambda d: {k: v for k, v in d.items() if k not in ('id', 'name')}
    return json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)


def resolve_theme(snippet, config):
    """Decide, per theme id the snippet depends on, whether the destination flow
    already means the same thing (reuse), means something different (adopt the
    destination's -- no payload rewrite needed, the snippet already refers to the id),
    or has never heard of it (carry the snippet's own definition in)."""
    dep = snippet['dependencies']
    theme = config.get('theme') or {}
    dest_colors = _by_id(theme.get('colors') or [])
    dest_presets = _by_id(theme.get('typography') or [])
    dest_fonts = _by_id((config.get('_meta') or {}).get('fonts') or [])
    dest_icons = {(i['name'], i.get('weight'))
                  for i in (config.get('_meta') or {}).get('icons') or []}
    dest_vars = _by_id(config.get('variables') or [])
    dest_comps = config.get('components') or {}

    adopt, reuse = [], []
    carry = {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
             'variables': [], 'components': {}}

    for kind, incoming, dest, bucket in (
            ('color', dep.get('colors') or [], dest_colors, 'colors'),
            ('preset', dep.get('typography') or [], dest_presets, 'typography')):
        for d in incoming:
            here = dest.get(d['id'])
            if here is None:
                carry[bucket].append(d)
            elif _same_definition(d, here):
                reuse.append(d['id'])
            else:
                adopt.append({'kind': kind, 'id': d['id'],
                              'snippet': d, 'destination': here})

    for i in dep.get('icons') or []:
        if (i['name'], i.get('weight')) not in dest_icons:
            carry['icons'].append(i)
    for v in dep.get('variables') or []:
        if v['id'] not in dest_vars:
            carry['variables'].append(v)
    for cid, cdef in (dep.get('components') or {}).items():
        if cid not in dest_comps:
            carry['components'][cid] = cdef

    # A CARRIED preset may name a font; an ADOPTED one resolves against the
    # destination's own fonts and needs nothing (Invariant 9, second path) -- so this
    # pass cannot walk `dep['fonts']` wholesale, that closure was computed at EXTRACT
    # time over every preset dependency, before graft time decided which presets are
    # being adopted rather than carried. It must run after the colour/preset pass
    # above, once `carry['typography']` is settled, AND after `carry['components']`
    # is settled just above -- a component's own elements can name a font directly
    # (a `family.id` outside any preset), and that reference was invisible to a walk
    # that only ever looked at the top-level payload. Three sources feed
    # `needed_fonts`: a font named directly by a payload element, a font named
    # directly by an element inside a CARRIED component, and a font named by a
    # preset that is actually being carried in.
    dep_fonts = _by_id(dep.get('fonts') or [])
    needed_fonts = set()
    payload = snippet.get('payload')
    if payload:
        walk(payload, lambda o: needed_fonts.add(o['family']['id'])
             if isinstance(o.get('family'), dict)
             and isinstance(o['family'].get('id'), str) else None)
    for cdef in carry['components'].values():
        walk(cdef, lambda o: needed_fonts.add(o['family']['id'])
             if isinstance(o.get('family'), dict)
             and isinstance(o['family'].get('id'), str) else None)
    for t in carry['typography']:
        fam = ((t.get('settings') or {}).get('family') or {}).get('id')
        if fam:
            needed_fonts.add(fam)

    for fid, fdef in dep_fonts.items():
        if fid in dest_fonts:
            reuse.append(fid)
        elif fid in needed_fonts:
            carry['fonts'].append(fdef)
        # else: only an ADOPTED preset named it -- nothing references it any more,
        # so it is neither carried nor reused.

    return {'adopt': adopt, 'carry': carry, 'reuse': sorted(set(reuse))}


def mint(existing, base):
    """A free id derived from `base`. Never collides; never starts with a digit."""
    base = re.sub(r'_\d+$', '', base)
    if base[:1].isdigit():
        base = 'g_' + base
    n = 2
    while f'{base}_{n}' in existing:
        n += 1
    return f'{base}_{n}'


def _flow_element_ids(config):
    out = set()
    for s in config['screens']:
        out |= set(s['elements']['map'])
    for c in (config.get('components') or {}).values():
        out |= set(c['map'])
    return out


def _flow_group_ids(config):
    # Flow-wide, not screen-wide: invariant 6's second rule.
    return {g['id'] for s in config['screens'] for g in s.get('selectableGroups') or []}


def plan_renames(snippet, config):
    payload = snippet.get('payload') or {}
    pmap = payload.get('map') or (payload.get('screen') or {}).get(
        'elements', {}).get('map') or {}
    taken_el = _flow_element_ids(config)
    # A minted id must never collide with the PAYLOAD'S OWN un-renamed ids, or two
    # elements collapse into one on write (`new_map` in `rewrite_ids` is keyed by
    # id). Seed the mint pool with the snippet's own element ids too, not just the
    # destination's -- a payload map of {card, card_2} grafted where `card` is
    # already taken must not mint `card_2` and stomp the snippet's own second card.
    el = {}
    for eid in sorted(pmap):
        if eid in taken_el:
            el[eid] = mint(taken_el | set(pmap) | set(el.values()), eid)
    taken_g = _flow_group_ids(config)
    # Same hazard for groups: a minted group id must not collide with another
    # group this SAME snippet is carrying in.
    pgroups = {g['id'] for g in snippet['dependencies'].get('groups') or []}
    grp = {}
    for g in snippet['dependencies'].get('groups') or []:
        if g['id'] in taken_g:
            grp[g['id']] = mint(taken_g | pgroups | set(grp.values()), g['id'])
    # A screen snippet landing in the flow it came from would duplicate a screen id,
    # which strands every `navigate` naming it. Mint a fresh one.
    scr = {}
    if snippet['kind'] == 'screen':
        sid = (payload.get('screen') or {}).get('id')
        taken_s = {x['id'] for x in config['screens']}
        if sid in taken_s:
            scr[sid] = mint(taken_s, sid)
    return {'elements': el, 'groups': grp, 'screens': scr}


def _rewrite_head(value, renames):
    """`plan.selectedOptionId` -> `plan_2.selectedOptionId`. Head segment only."""
    head, dot, rest = value.partition('.')
    return (renames.get(head, head) + dot + rest) if head in renames else value


def rewrite_ids(payload, el_renames, group_renames):
    """Path-keyed, never value-keyed. See the `tabs` trap in the plan header.

    The groupId head hides in a `conditional`'s payload, and a case there is a
    two-element list -- `[predicate_dict, {"type": "const", "value": [...actions]}]`
    -- not `{"actions": [...]}`, and `default` is a sibling action container of its
    own (measured against a real quiz-and-paywall export in the tracked fixture
    corpus). Rather than hand-walk that branch shape (which drifted from it once
    already, silently), any
    `variableId` string is rewritten generically wherever it occurs under an element,
    keyed on the FIELD NAME `variableId` -- never on an arbitrary string value, so the
    `tabs` trap stays closed."""
    def fix_hierarchy(node):
        if node.get('id') in el_renames:
            node['id'] = el_renames[node['id']]
        for c in node.get('children') or []:
            fix_hierarchy(c)

    def _fix_variable_id(o):
        if isinstance(o.get('variableId'), str):
            o['variableId'] = _rewrite_head(o['variableId'], group_renames)

    def fix_element(el):
        if el.get('id') in el_renames:
            el['id'] = el_renames[el['id']]
        props = el.get('props')
        if isinstance(props, dict) and isinstance(props.get('groupId'), str):
            props['groupId'] = group_renames.get(props['groupId'], props['groupId'])
        walk(el, _fix_variable_id)

    scoped = payload.get('screen') or payload
    emap = scoped.get('map') or (scoped.get('elements') or {}).get('map')
    hier = scoped.get('hierarchy') or (scoped.get('elements') or {}).get('hierarchy')
    if emap is not None:
        for el in list(emap.values()):
            fix_element(el)
        new_map = {el_renames.get(k, k): v for k, v in emap.items()}
        emap.clear(); emap.update(new_map)
    if hier is not None:
        fix_hierarchy(hier)
    for g in scoped.get('selectableGroups') or []:
        if g.get('id') in group_renames:
            g['id'] = group_renames[g['id']]
    return payload


def resolve_locales(snippet, config, payload):
    """Intersect the snippet's localizable `values` maps against the destination's
    declared locales, mutating `payload` in place. A locale the destination does not
    declare is dropped; a destination locale the snippet lacks is filled from the
    snippet's own `defaultLocale` (or, failing that, the destination's first locale)
    and reported -- the fill is a translation ask, not a translation."""
    dest = [l['id'] for l in config.get('locales') or []]
    src_default = snippet['dependencies'].get('defaultLocale') or (dest[0] if dest else None)
    dropped, filled = set(), set()

    def visit(o):
        if not (isinstance(o, dict) and o.get('_localizable') is True):
            return
        vals = o.get('values')
        if not isinstance(vals, dict):
            return
        for code in list(vals):
            if code not in dest:
                dropped.add(code)
                del vals[code]
        if not vals:
            return
        base = vals.get(src_default) or vals[sorted(vals)[0]]
        for code in dest:
            if code not in vals:
                vals[code] = json.loads(json.dumps(base))
                filled.add(code)

    walk(payload, visit)
    return {'dropped': sorted(dropped), 'filled': sorted(filled)}


def _producers_in(config):
    """Every `<head>.<field>` a running destination flow can supply on its own --
    a text-input's customId, and each selectable group's own two outputs."""
    out = set()
    for s in config['screens']:
        for e in s['elements']['map'].values():
            props = e.get('props') or {}
            if isinstance(props.get('customId'), str):
                out.add(props['customId'] + '.value')
        for g in s.get('selectableGroups') or []:
            out.add(g['id'] + '.selectedOptionId')
            out.add(g['id'] + '.selectedProduct')
    return out


def resolve_identity(snippet, config, screen_id, catalog_path):
    """Everything the file cannot carry: pointers into someone's account (a product
    UUID) or into another screen (a variable producer, a navigate target). Never
    mints, guesses, copies or derives a `flowProductId`, and never writes
    `_meta.screens` -- that block is the Flow Builder's, and a value minted anywhere
    else is a lie the builder overwrites the next time someone opens the flow."""
    dep = snippet['dependencies']
    needs, rebinds = [], {}
    scope = snippet.get('intendedScope', 'same-app')

    # A catalog is user-supplied input to a shipped script -- well-formed JSON of
    # the wrong SHAPE (a bare string, a list of scalars, a dict with no usable
    # list) must degrade to the no-catalog behaviour, never crash. Row-level too:
    # a partly malformed catalog still rebinds the rows that ARE usable.
    cat = []
    if catalog_path:
        try:
            rows = json.load(open(catalog_path))
        except (OSError, ValueError):
            rows = None
        if isinstance(rows, dict):
            rows = rows.get('data')
        if isinstance(rows, list):
            # A row that matches on store ids but carries no `id` cannot be
            # rebound to -- skip it here rather than crash `match[0]['id']` below.
            cat = [r for r in rows if isinstance(r, dict) and 'id' in r]

    def store_ids(row):
        v = row.get('vendor_products')
        v = v if isinstance(v, dict) else {}
        s = v.get('app_store') or v.get('play_store') or {}
        s = s if isinstance(s, dict) else {}
        return s.get('product_id'), s.get('base_plan_id')

    declared = {p['id'] for p in ((config.get('_meta') or {}).get('screens') or {})
                .get(screen_id, {}).get('products', [])}

    # Every product UUID this snippet references. A consumed `<uuid>.prod_*` price
    # variable's head lands in here -- its producer IS the product's own
    # declaration, resolved below, never `_producers_in`. Invariant 5: keep this
    # form apart from `<groupId>.selectedProduct`, whose head is a `product`-typed
    # selectable GROUP and is resolved against `selectableGroups`, not this set.
    product_ids = {p['id'] for p in dep.get('products') or []}

    for p in dep.get('products') or []:
        if scope == 'any-app':
            match = [r for r in cat
                     if store_ids(r) == (p.get('vendorProductId'), p.get('basePlanId'))
                     and p.get('vendorProductId')]
            if match:
                rebinds[p['id']] = match[0]['id']
                continue
            needs.append({'level': '!', 'text':
                          f'product {p["id"][:8]}… "{p.get("title") or "?"}" has no '
                          f'match in the destination catalog — the binding was stripped, '
                          f'and any prod_price* references to it will render empty until '
                          f'a product is attached. Attach a product in the Flow Builder.'})
            continue
        if p['id'] not in declared:
            needs.append({'level': '!', 'text':
                          f'product {p["id"][:8]}… "{p.get("title") or "?"}" is not '
                          f'declared on this screen, and any prod_price* references to '
                          f'it will render empty until it is attached. Attach it in the '
                          f'Flow Builder after the write, or the flow will not publish.'})

    have = _producers_in(config) | set(dep.get('producesInternally') or [])
    for c in dep.get('consumes') or []:
        head = c.split('.')[0]
        if head in product_ids:
            # Already covered above, either as satisfied (declared/rebound, no ask
            # needed) or as the product ask itself -- never duplicate it here as a
            # second, per-price-field ask for the same underlying problem.
            continue
        if c not in have and not any(h.split('.')[0] == head for h in have):
            needs.append({'level': '!', 'text':
                          f'variable {c} has no producer in this flow. It renders empty '
                          f'and no gate objects — a screenshot is pixel-identical.'})

    screens = {s['id'] for s in config['screens']}
    for t in dep.get('navigateTargets') or []:
        if t not in screens:
            needs.append({'level': '!', 'text':
                          f'navigate target {t} does not exist here. Left as-is: '
                          f'inventing a destination changes routing nothing asked to '
                          f'change. Publish blocker until you repoint it.'})

    for m in dep.get('media') or []:
        if 'PLACEHOLDER' in m.upper():
            needs.append({'level': '?', 'text': f'asset {m} is a placeholder — upload a '
                                                f'real file with `flows media upload`.'})
    return {'needs': needs, 'rebinds': rebinds}


def build_plan(snippet, config, screen_id, parent, index, catalog):
    """Run all four resolvers, in order, and assemble one plan dict -- the report a
    user reads before anything is written. Operates on a DEEP COPY of the snippet's
    payload throughout; `snippet` itself is never mutated."""
    payload = json.loads(json.dumps(snippet.get('payload') or {}))   # deep copy
    theme = resolve_theme(snippet, config)
    ren = plan_renames(snippet, config)
    rewrite_ids(payload, ren['elements'], ren['groups'])
    # `plan_renames` mints a fresh screen id on a same-flow collision but does not
    # write it -- `rewrite_ids` only touches element/group ids. Apply it here, or a
    # screen grafted back into its own flow silently inserts a DUPLICATE screen id,
    # which strands every `navigate` naming it.
    if ren['screens'] and (payload.get('screen') or {}).get('id') in ren['screens']:
        payload['screen']['id'] = ren['screens'][payload['screen']['id']]
    locales = resolve_locales(snippet, config, payload)
    ident = resolve_identity(snippet, config, screen_id, catalog)
    scoped = payload.get('screen') or payload
    emap = scoped.get('map') or (scoped.get('elements') or {}).get('map') or {}
    # `type` rides along with each added group -- a `product` group and a
    # `single_choice` group behave differently, and `WILL ADD` names it.
    add_groups = [{'id': g['id'], 'type': g.get('type')}
                 for g in snippet['dependencies'].get('groups') or []]
    return {'adds': {'elements': sorted(emap), 'groups': add_groups},
            'adopt': theme['adopt'], 'carry': theme['carry'], 'reuse': theme['reuse'],
            'renames': ren,
            'locales': locales, 'needs': ident['needs'], 'rebinds': ident['rebinds'],
            'placement': {'screen': screen_id, 'parent': parent, 'index': index},
            '_payload': payload}


def _hex_repr(color_def):
    """`#F4F4F6` alone, or `#F4F4F6 / #1A1A1D` when a dark variant is defined --
    the same light/dark notation the spec's own WILL ADD carry line uses."""
    light = (color_def.get('light') or {}).get('hex') or '?'
    dark = (color_def.get('dark') or {}).get('hex')
    return f'{light} / {dark}' if dark else light


ADOPT_LABEL_W = 8   # len('snippet') + 1 -- 'here' and 'snippet' line up under it


def _preset_desc(settings, diff_fields):
    """One side's description: size/weight always, plus each of `diff_fields` that
    THIS side actually has a value for -- never a marker for the side that lacks
    it. That asymmetry is the whole point: a field appearing on one line and not
    the other IS the difference, stated positively rather than with a placeholder
    that a `←` notation collides with."""
    s = settings or {}
    parts = [f'{s.get("size", "?")}/{s.get("weight", "?")}']
    for field in diff_fields:
        v = s.get(field)
        if v is not None:
            parts.append(f'{field} {v}')
    return ', '.join(parts)


def _preset_lines(dest_settings, snip_settings):
    """(here_desc, snippet_desc) -- size/weight always, `lineHeight`/`letterSpacing`
    only when the two sides actually differ on that field."""
    d, s = dest_settings or {}, snip_settings or {}
    diff_fields = [f for f in ('lineHeight', 'letterSpacing') if d.get(f) != s.get(f)]
    return _preset_desc(d, diff_fields), _preset_desc(s, diff_fields)


def render_plan(plan, snippet, config, screen_id):
    """The human-readable report. One line per thing a user recognises -- never one
    line per element -- because a wall of lines buries the one that matters. Exit 1
    (see the caller) means a disclosure obligation, not a defect: a check whose red
    means "you did something wrong" gets argued with."""
    name = os.path.basename(snippet.get('_path', snippet['name']))
    # A `theme` snippet (or any plan run with no `--screen`) targets the flow as a
    # whole, not a screen -- render a header that says so rather than the
    # placeholder `screen "None" (None)` a lookup-by-None produces.
    if snippet.get('kind') == 'theme' or not screen_id:
        L = [f'GRAFT PLAN — {name} → flow-wide theme (no screen)', '']
    else:
        scr = next((s for s in config['screens'] if s['id'] == screen_id), {})
        cap = (scr.get('caption') or {}).get('value') if isinstance(scr.get('caption'), dict) \
            else scr.get('caption')
        L = [f'GRAFT PLAN — {name} → screen "{cap or screen_id}" ({screen_id})', '']
    add = [f'{len(plan["adds"]["elements"])} elements']
    if plan['adds']['groups']:
        gtxt = []
        for g in plan['adds']['groups']:
            t = f' ({g["type"]})' if g.get('type') else ''
            gtxt.append(f'group `{g["id"]}`{t}')
        add.append(' · '.join(gtxt))
    L.append(f'WILL ADD      {" · ".join(add)}')
    for bucket, label in (('colors', 'theme.colors'), ('typography', 'theme.typography'),
                          ('fonts', '_meta.fonts'), ('icons', '_meta.icons'),
                          ('variables', 'variables')):
        items = plan['carry'].get(bucket) or []
        if items:
            names = ', '.join(str(i.get('id') or i.get('name')) for i in items[:4])
            more = f' +{len(items) - 4} more' if len(items) > 4 else ''
            L.append(f'              {label} + {names}{more}')
    for a in plan['adopt']:
        # Both values, labelled, never arrowed -- this is the one decision in the
        # whole flow a user might veto, and a generic "had a different value" (or a
        # `←`-only notation that collides with an absent-field marker) gives no
        # basis for that call. `here` is the destination flow: the value that wins.
        if a['kind'] == 'color':
            dest_v = _hex_repr(a['destination'])
            snip_v = _hex_repr(a['snippet'])
            L.append(f'WILL ADOPT    colorId {a["id"]:<12} '
                     f'{"here":<{ADOPT_LABEL_W}}{dest_v}        '
                     f'{"snippet":<{ADOPT_LABEL_W}}{snip_v}')
        else:
            d_s = a['destination'].get('settings') or {}
            s_s = a['snippet'].get('settings') or {}
            here_desc, snip_desc = _preset_lines(d_s, s_s)
            L.append(f'WILL ADOPT    font.preset {a["id"]}')
            L.append(f'                {"here":<{ADOPT_LABEL_W}}{here_desc}')
            L.append(f'                {"snippet":<{ADOPT_LABEL_W}}{snip_desc}')
    for kind in ('elements', 'groups', 'screens'):
        for old, new in sorted(plan['renames'].get(kind, {}).items()):
            L.append(f'WILL RENAME   {old} → {new}')
    if plan['locales']['filled']:
        L.append(f'WILL FILL     locales {", ".join(plan["locales"]["filled"])} '
                 f'from the snippet default')
    if plan['locales']['dropped']:
        L.append(f'WILL DROP     locales {", ".join(plan["locales"]["dropped"])} '
                 f'(not declared here)')
    if plan['needs']:
        L += ['', 'NEEDS YOU']
        for n in plan['needs']:
            L.append(f'  {n["level"]} {n["text"]}')
    return '\n'.join(L)


def apply_plan(config, snippet, plan):
    """Write a `build_plan` result into `config`. Returns a NEW config -- `config`
    itself is never mutated, so the caller (and the file it read it from) is
    untouched. Order matters: theme definitions are carried BEFORE any element is
    inserted, or an intermediate state references a colour/preset/font/icon/
    variable/component that does not exist yet."""
    cfg = json.loads(json.dumps(config))          # never mutate the caller's document
    theme = cfg.setdefault('theme', {})
    have_c = {c['id'] for c in theme.setdefault('colors', [])}
    for c in plan['carry']['colors']:
        if c['id'] not in have_c:
            theme['colors'].append(c); have_c.add(c['id'])
    have_t = {t['id'] for t in theme.setdefault('typography', [])}
    for t in plan['carry']['typography']:
        if t['id'] not in have_t:
            theme['typography'].append(t); have_t.add(t['id'])
    meta = cfg.setdefault('_meta', {})
    have_f = {f['id'] for f in meta.setdefault('fonts', [])}
    for f in plan['carry']['fonts']:
        if f['id'] not in have_f:
            meta['fonts'].append(f); have_f.add(f['id'])
    have_i = {(i['name'], i.get('weight')) for i in meta.setdefault('icons', [])}
    for i in plan['carry']['icons']:
        if (i['name'], i.get('weight')) not in have_i:
            meta['icons'].append(i); have_i.add((i['name'], i.get('weight')))
    have_v = {v['id'] for v in cfg.setdefault('variables', [])}
    for v in plan['carry']['variables']:
        if v['id'] not in have_v:
            cfg['variables'].append(v); have_v.add(v['id'])
    comps = cfg.setdefault('components', {})
    for cid, cdef in plan['carry']['components'].items():
        comps.setdefault(cid, cdef)

    payload = plan['_payload']
    kind = snippet['kind']

    # Product bindings the resolver rebound. PATH-KEYED, for the same reason the id
    # rewriter is: a value-keyed pass would rewrite any dict that happens to carry a
    # matching `id` (the `tabs`-trap bug class). Products live at `props.product.id`
    # and at a purchase action's `payload.product.id`, nowhere else. Applied to the
    # PAYLOAD, before any kind branch, so there is exactly ONE call site -- every
    # kind that can carry a product (`screen`, `component`, `element`) goes through
    # it, and a kind branch's early `return` can no longer skip it the way it did
    # when this ran on the destination `screen` object afterwards: `screen` and
    # `component` both returned before a local `screen` name even existed, so a
    # cross-app graft of either kind silently kept the SOURCE app's product UUIDs
    # while the plan's own report claimed the rebind happened.
    #
    # A rebound product's PRICE VARIABLES need the same treatment, in the SAME
    # pass: `<productUUID>.prod_price_per_month` is the product-relative form
    # (invariant 5 in flow-schema.md -- the head IS a product uuid by definition),
    # so once that uuid moves, the reference has to move with it or the card binds
    # the right product while the price beside it renders empty -- this repo's
    # plain-text-prices failure class, the worst outcome a paywall can ship. Reuses
    # `_rewrite_head` (Task 5's id rewriter) keyed on `rebinds` instead of an
    # element/group rename map: it is still PATH-KEYED, just keyed on the FIELD
    # NAME `variableId` rather than on an arbitrary string value, which is exactly
    # why the `tabs` trap stays closed. The other two variable forms are
    # untouched, structurally rather than by exclusion logic: a `<groupId>.
    # selectedProduct.<field>` head is a group id and a `<customId>.value` head is
    # a text-input custom id, and `rebinds` contains only product uuids, so
    # `_rewrite_head` simply never finds either head in the map.
    rebinds = plan.get('rebinds') or {}
    if rebinds:
        def rebind(o):
            prod = o.get('product')
            if isinstance(prod, dict) and prod.get('id') in rebinds:
                prod['id'] = rebinds[prod['id']]
            if isinstance(o.get('variableId'), str):
                o['variableId'] = _rewrite_head(o['variableId'], rebinds)
        walk(payload, rebind)

    if kind == 'theme':
        return cfg
    if kind == 'component':
        comps[payload['componentId']] = {'map': payload['map'],
                                         'hierarchy': payload['hierarchy']}
        return cfg
    if kind == 'screen':
        scr = payload['screen']
        at = plan['placement'].get('index')
        cfg['screens'].insert(len(cfg['screens']) if at is None else at, scr)
        return cfg

    screen = _screen_by_id(cfg, plan['placement']['screen'])
    screen['elements']['map'].update(payload['map'])
    parent_id = plan['placement'].get('parent')
    hier = screen['elements']['hierarchy']
    target = hier if not parent_id else find_node(hier, parent_id)[0]
    if target is None:
        die(f'no parent {parent_id} on that screen')
    kids = target.setdefault('children', [])
    idx = plan['placement'].get('index')
    kids.insert(len(kids) if idx is None else idx, payload['hierarchy'])
    for g in snippet['dependencies'].get('groups') or []:
        gid = plan['renames']['groups'].get(g['id'], g['id'])
        groups = screen.setdefault('selectableGroups', [])
        if gid not in {x['id'] for x in groups}:
            groups.append({**g, 'id': gid})
    return cfg


def main(argv):
    ap = argparse.ArgumentParser(prog='snippet.py', add_help=True)
    sub = ap.add_subparsers(dest='cmd')
    for name in ('extract', 'inspect', 'list', 'plan', 'graft', 'scan', 'where'):
        help_ = ('debug surface for the test suite; not a user-facing command'
                 if name == 'scan' else None)
        sub.add_parser(name, help=help_)
    if not argv:
        ap.print_usage(sys.stderr)
        return 2
    args, _rest = ap.parse_known_args(argv)
    if args.cmd is None:
        return 2

    if args.cmd == 'scan':
        ap2 = argparse.ArgumentParser(prog='snippet.py scan')
        ap2.add_argument('--config', required=True)
        ap2.add_argument('targets', nargs='+')
        a2 = ap2.parse_args(argv[1:])
        cfg = load(a2.config)
        merged = {'colors': set(), 'typography': set(), 'fonts': set(), 'icons': set(),
                  'components': set(), 'groups': set(), 'products': set(),
                  'consumes': set(), 'tokens': set()}
        for t in a2.targets:
            els, node, _s = fragment_of(cfg, t)
            for k, v in scan_dependencies(cfg, els, node).items():
                merged[k] |= {tuple(x) if isinstance(x, list) else x for x in v}
        # Same hazard as `_sort_icons`: an `icons` entry is a (name, weight) pair and
        # weight may be None, which Python 3 cannot order against the str entries the
        # other eight keys hold -- key on a None-safe tuple for list-shaped entries.
        def _sort_key(x):
            return tuple(p if p is not None else '' for p in x) if isinstance(x, list) else x
        print(json.dumps({k: sorted((list(x) if isinstance(x, tuple) else x for x in v),
                                    key=_sort_key) for k, v in merged.items()}))
        return 0

    if args.cmd == 'extract':
        ap2 = argparse.ArgumentParser(prog='snippet.py extract')
        ap2.add_argument('--config', required=True)
        ap2.add_argument('--out', required=True)
        ap2.add_argument('--name', required=True)
        ap2.add_argument('--description', default='')
        ap2.add_argument('--scope', choices=('same-app', 'any-app'), default='same-app')
        ap2.add_argument('--catalog')
        ap2.add_argument('--app', default=None)
        g = ap2.add_mutually_exclusive_group(required=True)
        g.add_argument('--element'); g.add_argument('--screen')
        g.add_argument('--component'); g.add_argument('--theme', nargs='?', const='all')
        a2 = ap2.parse_args(argv[1:])
        cfg = load(a2.config)
        if a2.screen:
            kind, target = 'screen', 'root@' + a2.screen
        elif a2.component:
            kind, target = 'component', a2.component
        elif a2.theme:
            kind, target = 'theme', None
        else:
            kind, target = 'element', a2.element
        snip = build_snippet(cfg, kind, target, a2.name, a2.description,
                             a2.scope, a2.catalog, a2.app)
        snip['savedAt'] = time.strftime('%Y-%m-%d')
        os.makedirs(os.path.dirname(os.path.abspath(a2.out)), exist_ok=True)
        with open(a2.out, 'w') as fh:
            json.dump(snip, fh, indent=2, sort_keys=False)
            fh.write('\n')
        print(f'saved: {os.path.abspath(a2.out)}')
        return report_extract(snip)

    if args.cmd == 'inspect':
        ap2 = argparse.ArgumentParser(prog='snippet.py inspect')
        ap2.add_argument('path')
        a2 = ap2.parse_args(argv[1:])
        snip = read_snippet(a2.path)
        print(f'{snip["name"]}  [{snip["kind"]}]  saved {snip["savedAt"]}')
        print(f'  scope: {snip["intendedScope"]}   source app: '
              f'{snip["source"].get("app")}   schemaVersion: '
              f'{snip["source"].get("schemaVersion")}')
        d = snip['dependencies']
        for label in ('colors', 'typography', 'fonts', 'icons', 'products',
                      'groups', 'consumes', 'media'):
            if d.get(label):
                print(f'  {label:12} {len(d[label])}')
        return 0

    if args.cmd == 'list':
        ap2 = argparse.ArgumentParser(prog='snippet.py list')
        ap2.add_argument('--dir', required=True)
        a2 = ap2.parse_args(argv[1:])
        for fn in sorted(os.listdir(a2.dir)):
            if fn.endswith('.flow-snippet.json'):
                try:
                    s = read_snippet(os.path.join(a2.dir, fn))
                except SystemExit:
                    continue
                print(f'{fn:52} {s["kind"]:10} {s["name"]}')
        return 0

    if args.cmd in ('plan', 'graft'):
        # `plan` and `graft` take IDENTICAL flags: committing means changing one
        # word. `plan` never writes anything -- report only. `graft`'s write lands
        # in Task 9; today it shares this parsing and this same report, then falls
        # through to the module's usage-level return below.
        ap2 = argparse.ArgumentParser(prog=f'snippet.py {args.cmd}')
        ap2.add_argument('--config', required=True)
        ap2.add_argument('--snippet', required=True)
        ap2.add_argument('--screen')
        ap2.add_argument('--parent'); ap2.add_argument('--index', type=int)
        ap2.add_argument('--catalog')
        ap2.add_argument('--json', action='store_true')
        if args.cmd == 'graft':
            ap2.add_argument('--out', required=True)
        a2 = ap2.parse_args(argv[1:])
        cfg = load(a2.config)
        snip = read_snippet(a2.snippet)
        snip['_path'] = a2.snippet
        # Only an `element` snippet attaches to an existing screen -- a `screen`
        # snippet is inserted into `screens[]`, a `component` lands in top-level
        # `components`, and a `theme` snippet touches neither. `--screen` is
        # therefore required for `element` alone.
        if snip['kind'] == 'element' and not a2.screen:
            die('--screen is required for this snippet kind')
        # `plan` must fail exactly the way `graft` does on a screen that does not
        # exist. The whole discipline of this feature is "read the plan first" --
        # a plan that happily describes a graft onto a screen `graft` will then
        # refuse teaches the user the plan is not worth reading. Resolve it here,
        # before either command does anything else, so both share one message and
        # one exit code (2 -- a usage error, not a `NEEDS YOU` disclosure).
        if a2.screen:
            _screen_by_id(cfg, a2.screen)
        pl = build_plan(snip, cfg, a2.screen, a2.parent, a2.index, a2.catalog)
        if a2.json:
            print(json.dumps(pl))   # `_payload` included: it is how the suite checks
                                    # the rewriter without needing a graft
        else:
            print(render_plan(pl, snip, cfg, a2.screen))
        if args.cmd == 'plan':
            return 1 if pl['needs'] else 0
        out = apply_plan(cfg, snip, pl)
        with open(a2.out, 'w') as fh:
            json.dump(out, fh, indent=2)
            fh.write('\n')
        print(f'\nwrote: {os.path.abspath(a2.out)}')
        print('next: verify-config.py, then `flows config validate`, then preview — '
              'SKILL.md phase 3.')
        return 1 if pl['needs'] else 0

    if args.cmd == 'where':
        path, exists = snippet_dir()
        print(f'{path}\n{"existing" if exists else "proposed — ask before writing"}')
        return 0

    return 2  # remaining subcommands land in later tasks


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
