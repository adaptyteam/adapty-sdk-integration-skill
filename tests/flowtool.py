#!/usr/bin/env python3
"""Inspect and patch a flow config without reading the whole thing.

A real config is 100-250KB of JSON. Loading it into an agent's context to change one
string costs more than the entire rest of the task, so every command here is built to
answer one question in as few characters as possible, and the patch commands edit the
file in place so the full document never has to be quoted back.

    index                        screens: id, caption, elements, groups, navigation out
    outline  <screen>            element tree — id, type, caption, text preview. No props.
    text     <screen>            every editable string on the screen, id -> value
    get      <screen> <element>  one element, in full
    props    <screen> <element>  one element's props, flattened to leaf paths
    find     <pattern>           elements whose id/type/caption/text matches (regex)
    nav                          the navigation graph, including targets inside conditionals
    settext  <screen> <element> <new>       replace an element's inline text
    setprop  <screen> <element> <path> <json>   set one props path, e.g. font.preset
    stats                        top-level shape: keys, locales, theme, icons, counts

Patch commands write in place unless --out is given, and print the before/after of just
the field they touched. Structural edits (adding screens, cloning subtrees) are not here
on purpose — those need a script, and a script does not need this tool.
"""
import argparse, json, re, sys

ENVELOPE = {'config', 'remote_configs', 'status', 'updated_at'}

def load(p):
    """Accept either a bare builder config or a `flows config get` envelope.

    Same tolerance the CLI's own preview has, so the tool can be pointed straight at
    whatever `flows config get --json` wrote without an unwrapping step in between.
    """
    d = json.load(open(p))
    if isinstance(d.get('config'), dict) and ENVELOPE & set(d):
        cfg = d['config']
        cfg['_envelope'] = {k: d[k] for k in ('status', 'updated_at') if k in d}
        return cfg
    return d

def save(d, p):
    d = {k: v for k, v in d.items() if k != '_envelope'}   # never write our own marker back
    json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)

def screen_of(cfg, sid):
    for s in cfg['screens']:
        if s['id'] == sid or s.get('caption') == sid:
            return s
    sys.exit(f'no screen {sid!r}. try: index')

def el_of(scr, eid):
    m = scr['elements']['map']
    if eid in m: return m[eid]
    hits = [k for k in m if eid.lower() in k.lower()
            or eid.lower() in (m[k].get('caption') or '').lower()]
    if len(hits) == 1: return m[hits[0]]
    if hits: sys.exit(f'ambiguous {eid!r}: {hits[:8]}')
    sys.exit(f'no element {eid!r} on {scr["id"]}. try: outline {scr["id"]}')

# ---------- reading ----------
def flat_text(node):
    """The rendered string of a content value, or None."""
    if isinstance(node, str): return node
    if isinstance(node, dict) and isinstance(node.get('values'), dict):
        for blocks in node['values'].values():
            out = []
            for b in blocks if isinstance(blocks, list) else []:
                for n in b.get('content', []):
                    if n.get('type') == 'text': out.append(n.get('text', ''))
                    elif n.get('type') == 'variable':
                        out.append('{' + n['attrs']['variableId'].split('.')[-1] + '}')
                    elif n.get('type') == 'token':
                        out.append('{' + str(n['attrs'].get('token')) + '}')
            return ''.join(out)
    return None

def el_text(e):
    p = e.get('props') or {}
    for k in ('content', 'placeholder', 'title', 'message'):
        t = flat_text(p.get(k))
        if t is not None: return t
    return None

def actions_of(e):
    out = []
    for it in e.get('interactions') or []:
        for a in it.get('actions') or []:
            t = a.get('type')
            if t == 'navigate':   out.append('->' + a['payload']['screen'])
            elif t == 'purchase':
                v = a['payload']['product']
                out.append('buy:' + (v.get('value', {}).get('id', '')[:8] if v.get('type') == 'const' else v.get('variableId', '')))
            elif t == 'conditional':
                tg = []
                def w(o):
                    if isinstance(o, dict):
                        if o.get('type') == 'navigate': tg.append(o['payload']['screen'])
                        for v in o.values(): w(v)
                    elif isinstance(o, list):
                        for v in o: w(v)
                w(a); out.append('switch->' + ','.join(dict.fromkeys(tg)))
            else: out.append(t)
    return out

def cmd_index(cfg, a):
    print(f'{len(cfg["screens"])} screens, {sum(len(s["elements"]["map"]) for s in cfg["screens"])} elements')
    for i, s in enumerate(cfg['screens']):
        g = ','.join(f'{x["id"]}:{x["type"]}' for x in s.get('selectableGroups') or []) or '-'
        outs = []
        def w(o):
            if isinstance(o, dict):
                if o.get('type') == 'navigate': outs.append(o['payload']['screen'])
                for v in o.values(): w(v)
            elif isinstance(o, list):
                for v in o: w(v)
        w(s)
        print(f'  [{i}] {s["id"]:18} {(s.get("caption") or "-")[:22]:24} '
              f'{len(s["elements"]["map"]):4} el  groups={g:22} -> {",".join(dict.fromkeys(outs)) or "(end)"}')

def cmd_outline(cfg, a):
    s = screen_of(cfg, a.screen); m = s['elements']['map']
    def walk(n, d=0):
        eid = n['id']
        e = m.get(eid)
        if e is None:
            print('  ' * d + f'{eid}  (component ref)')
        else:
            bits = [e['type']]
            p = e.get('props') or {}
            if p.get('groupId'):  bits.append(f'group={p["groupId"]}' + (f'/{p["customId"]}' if p.get('customId') else ''))
            if p.get('default'):  bits.append('DEFAULT')
            if e.get('states'):   bits.append('states=' + ','.join(x['id'] for x in e['states']))
            acts = actions_of(e)
            if acts: bits.append('[' + ' '.join(acts) + ']')
            t = el_text(e)
            lbl = f'  "{t[:44]}"' if t else (f'  ({e["caption"]})' if e.get('caption') else '')
            print('  ' * d + f'{eid:16} {" ".join(bits)}{lbl}')
        for c in n.get('children') or []: walk(c, d + 1)
    print(f'{s["id"]}  {s.get("caption")}  ({len(m)} elements)')
    walk(s['elements']['hierarchy'])

def cmd_text(cfg, a):
    s = screen_of(cfg, a.screen)
    for eid, e in s['elements']['map'].items():
        t = el_text(e)
        if t is not None:
            shape = 'bare' if isinstance((e['props'] or {}).get('content'), str) else 'loc'
            print(f'{eid:16} {shape:5} {t}')

def cmd_get(cfg, a):
    print(json.dumps(el_of(screen_of(cfg, a.screen), a.element), indent=1, ensure_ascii=False))

def cmd_props(cfg, a):
    e = el_of(screen_of(cfg, a.screen), a.element)
    def leaves(o, path=''):
        if isinstance(o, dict):
            for k, v in o.items(): leaves(v, f'{path}.{k}' if path else k)
        elif isinstance(o, list):
            if o and all(not isinstance(x, (dict, list)) for x in o): print(f'  {path} = {o}')
            else:
                for i, v in enumerate(o): leaves(v, f'{path}[{i}]')
        else: print(f'  {path} = {json.dumps(o)}')
    leaves(e.get('props') or {})

def cmd_find(cfg, a):
    rx = re.compile(a.pattern, re.I)
    for s in cfg['screens']:
        for eid, e in s['elements']['map'].items():
            t = el_text(e) or ''
            hay = f'{eid} {e["type"]} {e.get("caption") or ""} {t}'
            if rx.search(hay):
                print(f'{s["id"]:18} {eid:16} {e["type"]:14} {(e.get("caption") or "")[:18]:20} {t[:40]}')

def cmd_nav(cfg, a):
    ids = {s['id'] for s in cfg['screens']}
    for s in cfg['screens']:
        edges = []
        for eid, e in s['elements']['map'].items():
            for act in actions_of(e):
                if act.startswith('->') or act.startswith('switch->'):
                    edges.append((eid, act))
        print(f'{s["id"]:18} {(s.get("caption") or "")[:18]:20} ' +
              ('; '.join(f'{a}' for _, a in edges) or '(no outbound)'))
    dangling = []
    def w(o):
        if isinstance(o, dict):
            if o.get('type') == 'navigate' and o['payload']['screen'] not in ids:
                dangling.append(o['payload']['screen'])
            for v in o.values(): w(v)
        elif isinstance(o, list):
            for v in o: w(v)
    w(cfg)
    print('dangling:', dangling or 'none')

def cmd_stats(cfg, a):
    env = cfg.get('_envelope')
    if env: print('envelope:', env, '(read from a `flows config get` payload)')
    print('top-level:', sorted(k for k in cfg if k != '_envelope'))
    print('locales:', [l['id'] for l in cfg['locales']], 'default:', cfg['defaultLocale'])
    print('schemaVersion:', cfg.get('schemaVersion'), '| status/id present:',
          'status' in cfg, 'id' in cfg)
    print('theme: %d colors, %d presets' % (len(cfg['theme']['colors']), len(cfg['theme']['typography'])))
    print('icons:', [f'{i["name"]}/{i["weight"]}' for i in cfg['_meta']['icons']])
    print('fonts:', [f.get('name') for f in cfg['_meta']['fonts']] or '(none)')
    print('components:', list(cfg.get('components') or {}) or '(none)')
    print('_meta.screens:', {k: len(v.get('products', [])) for k, v in (cfg['_meta'].get('screens') or {}).items()} or '(none)')

# ---------- patching ----------
def cmd_settext(cfg, a):
    e = el_of(screen_of(cfg, a.screen), a.element)
    p = e['props']
    key = next((k for k in ('content', 'placeholder', 'title', 'message') if k in p), None)
    if key is None: sys.exit(f'{e["id"]} has no text field')
    before = flat_text(p[key])
    if isinstance(p[key], str):
        p[key] = a.new                                  # bare stays bare
    else:
        vals = p[key]['values']
        for loc, blocks in vals.items():
            done = False
            for b in blocks:
                for n in b.get('content', []):
                    if n.get('type') == 'text' and not done:
                        n['text'] = a.new; done = True
                    elif n.get('type') == 'text':
                        n['text'] = ''                   # collapse extra runs
            if not done and blocks:
                blocks[0].setdefault('content', []).insert(0, {
                    'text': a.new, 'type': 'text',
                    'attrs': {'bold': False, 'italic': False, 'underline': False, 'strikethrough': False}})
    print(f'{e["id"]}: {before!r} -> {flat_text(p[key])!r}')
    save(cfg, a.out or a.config)

def cmd_setprop(cfg, a):
    e = el_of(screen_of(cfg, a.screen), a.element)
    node = e['props']; parts = a.path.split('.')
    for k in parts[:-1]:
        node = node.setdefault(k, {})
        if not isinstance(node, dict): sys.exit(f'{a.path}: {k} is not an object')
    before = node.get(parts[-1])
    node[parts[-1]] = json.loads(a.value)
    print(f'{e["id"]}.props.{a.path}: {json.dumps(before)} -> {a.value}')
    save(cfg, a.out or a.config)

CMDS = {'index': cmd_index, 'outline': cmd_outline, 'text': cmd_text, 'get': cmd_get,
        'props': cmd_props, 'find': cmd_find, 'nav': cmd_nav, 'stats': cmd_stats,
        'settext': cmd_settext, 'setprop': cmd_setprop}

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=CMDS)
    ap.add_argument('config')
    ap.add_argument('rest', nargs='*')
    ap.add_argument('--out')
    a = ap.parse_args()
    names = {'outline': ['screen'], 'text': ['screen'], 'get': ['screen', 'element'],
             'props': ['screen', 'element'], 'find': ['pattern'],
             'settext': ['screen', 'element', 'new'],
             'setprop': ['screen', 'element', 'path', 'value']}.get(a.cmd, [])
    if len(a.rest) < len(names):
        ap.error(f'{a.cmd} needs: {" ".join(names)}')
    for n, v in zip(names, a.rest): setattr(a, n, v)
    CMDS[a.cmd](load(a.config), a)

if __name__ == '__main__':
    main()
