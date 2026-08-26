#!/usr/bin/env python3
"""Structurally diff two Adapty flow configs, and name what the newer one DESTROYS.

SCOPE: this SHIPS. It sits in `references/` alongside `verify-config.py`, so a runtime agent
has it on any machine. Everything it does is local and read-only: it opens two JSON files and
prints findings. Either side may be a `config get`/`config update` envelope or a bare config.

    python3 references/diff-config.py flow.working.json draft.json     # what my write removes
    python3 references/diff-config.py stale-local.json flow.working.json   # what a human changed

Why it exists. `config update` replaces the whole config, and `--expected-updated-at` only
catches a write racing an edit that landed AFTER you fetched. It cannot catch the commoner
loss: an agent that fetches fresh, then writes a document it regenerated from its own build
script, or patched a leftover local file from an earlier session. The lock token is valid, no
409 is raised, and every dashboard edit made in between is gone. The observable those paths
share is that the bytes about to be written differ from the live config in ways nobody
intended -- so this computes that difference instead of trusting a narration of it.

TWO USES, one comparison. B is always the newer document.

  1. `diff-config.py <live> <draft>` before a write -- REMOVES is what your write destroys.
     Every line of it belongs in the phase-5 approval ask, traced to something the user asked
     for. A removal you cannot trace is someone else's work: name it and ask.

  2. `diff-config.py <old local copy> <live>` at the start of a follow-up run -- here ADDS and
     CHANGES are the human's manual edits, the ones a rebuild would silently drop. This is the
     only way to see them; the config carries no authorship and no history.

Exit codes: 0 no removals, 1 removals present, 2 unreadable file or the same path twice.
**Exit 1 is a disclosure obligation, not a defect.** Deleting a screen is a transform this
skill supports; doing it without saying so is not. Never "fix" a 1 by reverting -- report it.

WHAT IT COMPARES (identity in brackets -- a fact whose identity changes reads as one removal
plus one addition, which is the honest reading of an id rewrite):
  screens [id], elements per screen [id], components [id], locales [code], theme colours and
  typography presets [id], variables [id], `_meta.icons` [name+weight], `_meta.fonts` [family],
  `_meta.screens[].products[]` [product id] -- the builder-owned attachments a rebuilt config
  wipes -- element `type`, `props`, `interactions` and screen `caption`, plus every localizable
  value BY LOCALE, so a dropped translation is a removal rather than a change.

WHAT IT DOES NOT SEE, and each of these is a real way to lose work invisibly to this check:
  * rendering. Two configs can differ everywhere here and draw the same screen, and vice versa
    (preview.md). This is a structural diff, not a visual one -- phase 5 needs both.
  * key ORDER, and the order of an id-keyed collection. Both are invisible by design -- values
    are compared with sorted keys, and a collection is addressed by identity rather than index --
    so a builder save that re-sorts `_meta.icons` reads as silent. Do not conclude from a clean
    diff that your bytes equal theirs.
    The v9 -> v10 fill migration is the exception and is NOT silent (measured: 29 fills rewritten
    object -> array reported as 25 changed elements). It changes the shape of a value, so it is
    reported like any other change. Recognise it -- a block of `props` changes across unrelated
    elements right after someone saved in the builder -- rather than reading it as their edits.
  * anything under a key it does not enumerate. A top-level key the format gains next release
    is compared as a whole blob under `other:<key>`, which is coarse but never silent.
"""
import json, os, sys

LIMIT = 12                      # lines printed per group before the tail is summarised


def load(path):
    """Take a config out of an envelope if it is in one. `config get` and `config update`
    both return `{config, remote_configs, status, updated_at}`; `preview` and the file
    deliverable take the bare config. Accept either on either side."""
    d = json.load(open(path))
    if isinstance(d, dict) and 'config' in d and isinstance(d['config'], dict) \
            and 'screens' in d['config']:
        return d['config']
    return d


def canon(v):
    """A stable string for value comparison. Sorting keys is what makes key order invisible;
    collection *order* is handled separately, by addressing every collection by identity."""
    return json.dumps(v, sort_keys=True, separators=(',', ':'))


def by_id(coll, keys=('id',)):
    """Yield (identity, value) for an id-keyed collection in either shape. Real exports spell
    `theme.colors`, `theme.typography`, `_meta.fonts`, `_meta.icons`, `locales` and `variables`
    as LISTS of objects carrying their own id; `components` is a dict keyed by id. Accept both
    rather than guessing, and fall back to the index only when there is no identity at all --
    which is the one case where a reorder does read as churn, and saying so beats going silent."""
    if isinstance(coll, dict):
        for k, v in coll.items():
            yield str(k), v
    elif isinstance(coll, list):
        for i, v in enumerate(coll):
            ident = None
            if isinstance(v, dict):
                parts = [str(v[k]) for k in keys if v.get(k) is not None]
                ident = '/'.join(parts) if parts else None
            yield ident or f'[{i}]', v


def facts(d):
    """Flatten a config into {address: value}. An address is a stable identity, never an
    array index -- reordering screens is not a removal, and a config whose facts were keyed
    by position would report every reorder as wholesale destruction."""
    f = {}
    locales = [l.get('code') for l in (d.get('locales') or []) if isinstance(l, dict)]
    locale_set = set(locales)

    for k in ('schemaVersion', 'defaultLocale', 'status', 'id'):
        if k in d:
            f[f'top:{k}'] = canon(d[k])

    for code, val in by_id(d.get('locales'), ('code',)):
        f[f'locale:{code}'] = canon(val)

    for kind in ('colors', 'typography'):
        for tid, val in by_id((d.get('theme') or {}).get(kind)):
            f[f'theme.{kind}:{tid}'] = canon(val)

    for vid, val in by_id(d.get('variables')):
        f[f'variable:{vid}'] = canon(val)

    meta = d.get('_meta') or {}
    for ident, val in by_id(meta.get('icons'), ('name', 'weight')):
        f[f'icon:{ident}'] = canon(val)
    for ident, val in by_id(meta.get('fonts'), ('id',)):
        f[f'font:{ident}'] = canon(val)

    # Builder-owned bookkeeping, and the single most valuable row here: a config rebuilt from
    # a script carries `_meta.screens: {}`, so every product attachment the builder made shows
    # up as a removal (products.md). That is exactly the loss this script was written for.
    for sid, entry in (meta.get('screens') or {}).items():
        for p in (entry or {}).get('products') or []:
            if isinstance(p, dict):
                f[f'_meta.screens:{sid}/product:{p.get("id")}'] = canon(p.get('flowProductId'))

    def localizables(prefix, node):
        """Every per-locale value, addressed by locale, so dropping `de` from one field is a
        removal of that field's `de` and not a change to the field. A localizable wrapper is
        recognised by a `values` dict whose keys are declared locale codes -- the schema types
        `ILocalizable.values` as unconstrained, so its shape is all there is to go on."""
        if isinstance(node, dict):
            vals = node.get('values')
            if isinstance(vals, dict) and (not vals or set(vals) & locale_set or not locale_set):
                for loc, v in vals.items():
                    f[f'{prefix}.values:{loc}'] = canon(v)
                if not vals:
                    # An empty map is a placeholder asset or an emptied text (media.md); it has
                    # to be a fact of its own or replacing a real value with {} reads as nothing.
                    f[f'{prefix}.values:<empty>'] = '{}'
            for k, v in node.items():
                if k != 'values':
                    localizables(f'{prefix}.{k}', v)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                localizables(f'{prefix}[{i}]', v)

    for s in (d.get('screens') or []):
        sid = s.get('id')
        f[f'screen:{sid}'] = canon(s.get('caption'))
        f[f'screen:{sid}.props'] = canon(s.get('props'))
        f[f'screen:{sid}.selectableGroups'] = canon(s.get('selectableGroups'))
        f[f'screen:{sid}.hierarchy'] = canon((s.get('elements') or {}).get('hierarchy'))
        for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
            base = f'screen:{sid}/element:{eid}'
            f[base] = canon(e.get('type'))
            f[f'{base}.props'] = canon(e.get('props'))
            f[f'{base}.interactions'] = canon(e.get('interactions'))
            localizables(f'{base}.props', e.get('props'))

    for cid, c in by_id(d.get('components')):
        f[f'component:{cid}'] = canon(c)

    known = {'schemaVersion', 'defaultLocale', 'status', 'id', 'locales', 'theme', 'variables',
             '_meta', 'screens', 'components'}
    for k, v in d.items():                       # never silent about a key we do not model
        if k not in known:
            f[f'other:{k}'] = canon(v)
    return f


def container(addr):
    """The element or screen an address belongs to, so the report reads one line per thing a
    user recognises instead of one per fact. A deleted screen otherwise prints its 300
    elements, and the line that matters -- the screen -- is buried in them."""
    if '/element:' in addr:
        head, rest = addr.split('/element:', 1)
        return f'{head}/element:{rest.split(".")[0]}'
    if addr.startswith('screen:'):
        return 'screen:' + addr[len('screen:'):].split('.')[0]
    return addr


def collapse(addrs):
    """Fold a flat address set into (line, hidden_fact_count) pairs, coarsest first: a whole
    screen swallows its elements, a whole element swallows its props, interactions and per-locale
    values. Anything left is printed with the suffixes that actually differ, so a translation
    dropped from one field still reads as that field and that locale."""
    addrs = set(addrs)
    screens = {a for a in addrs if a == container(a) and '/element:' not in a and a.startswith('screen:')}
    elements = {a for a in addrs if a == container(a) and '/element:' in a}
    lines, seen = [], set()

    for s_ in sorted(screens):                       # whole screen gone/added
        members = {a for a in addrs if container(a) == s_ or a.startswith(s_ + '/element:')}
        seen |= members
        lines.append((f'{s_}  (the whole screen, {len(members) - 1} facts under it)', 0))
    for e in sorted(elements - seen):                # whole element gone/added
        members = {a for a in addrs if container(a) == e}
        seen |= members
        lines.append((f'{e}  (the whole element)', 0))

    rest = {}
    for a in sorted(addrs - seen):
        c = container(a)
        suffix = a[len(c):].lstrip('.') if a != c else ''
        rest.setdefault(c, []).append(suffix)
    for c, sfx in sorted(rest.items()):
        tail = ', '.join(x for x in sfx if x)
        lines.append((f'{c} — {tail}' if tail else c, 0))
    return lines


def show(title, addrs, note=None):
    """Print one group. Returns nothing; the counts printed here are the ones the summary
    repeats, because a summary that disagrees with the list above it gets believed over it."""
    if not addrs:
        return 0
    lines = collapse(addrs)
    print(f'  {title} — {len(lines)} item(s), {len(addrs)} facts')
    if note:
        print(f'    {note}')
    for x, _ in lines[:LIMIT]:
        print(f'    - {x}')
    if len(lines) > LIMIT:
        print(f'    - ... and {len(lines) - LIMIT} more')
    return len(lines)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0])
        print('usage: diff-config.py <older-or-live.json> <newer-or-draft.json>')
        return 2
    if os.path.abspath(argv[0]) == os.path.abspath(argv[1]):
        # Not pedantry: the skill's working file is edited in place in some runs, so passing it as
        # both sides is an easy mistake whose symptom is a clean report. A must be the pristine
        # fetch -- the phase-2 backup.
        print('ERROR: both arguments are the same file. A must be the copy nothing in this run '
              'has edited (the phase-2 backup); B is the document about to be written.')
        return 2
    try:
        a, b = load(argv[0]), load(argv[1])
    except (OSError, ValueError) as e:
        print(f'ERROR: {e}')
        return 2

    fa, fb = facts(a), facts(b)
    ka, kb = set(fa), set(fb)
    removed, added = ka - kb, kb - ka
    # A change under something already reported as removed or added is not news, so drop it:
    # renaming an element id would otherwise print the rename twice and a value change beneath it.
    moved = {container(x) for x in removed | added}
    changed = {k for k in ka & kb if fa[k] != fb[k] and container(k) not in moved}

    print(f'A (older / live):  {os.path.basename(argv[0])}   '
          f'{len(a.get("screens") or [])} screens, {len(fa)} facts')
    print(f'B (newer / draft): {os.path.basename(argv[1])}   '
          f'{len(b.get("screens") or [])} screens, {len(fb)} facts')
    print()

    nr = show('REMOVES — in A, not in B', removed,
              note="every line belongs in the approval ask; one you cannot trace to something "
                   "the user asked for is someone else's work")
    nc = show('CHANGES — same address, different value', changed)
    na = show('ADDS — in B, not in A', added)

    if not (removed or changed or added):
        print('  identical on every fact this compares '
              '(key order and rendering excluded — see the header)')
    print()
    print(f'summary: {nr} removed, {nc} changed, {na} added   '
          f'({len(removed)}/{len(changed)}/{len(added)} facts)')
    return 1 if removed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
