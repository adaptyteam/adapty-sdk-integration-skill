#!/usr/bin/env python3
"""Validate a flow config against the official JSON Schema shipped with the skill.

This is a NEW gate and a weak one — read `flow-schema.md` on the trust order before acting
on anything it says. The schema is a static snapshot of **schemaVersion 10** while most live
flows are **v9**, and the two genuinely differ (notably `fill`: one object in v9, an array of
layers in v10). So on a v9 config, expect shape complaints that are not defects, and never
"fix" a v9 flow to satisfy a v10 schema — a write does not migrate a flow.

What it is good for: catching a *typo-class* error in something you authored — a misspelled
element `type`, an enum value that does not exist, a prop that belongs to a different element.
What it is not: authority. The live `validate` outranks it, and the config you fetched outranks
it on shape.

Usage:
    tests/schema-check.py <config.json> [...]                  # summary per file
    tests/schema-check.py --baseline live.json new.json        # only what YOUR edit caused
    tests/schema-check.py --verbose <config.json>              # every error, deepest first

Pass --baseline whenever you are checking an edited config: the schema is a v10 snapshot and a
v9 flow mismatches it in hundreds of pre-existing places that are not yours.
Exit: 0 clean, 1 findings, 2 infrastructure problem.
"""
import json, os, sys, tempfile, time, urllib.request
from collections import Counter

# The schema is published and versioned, not bundled — a shipped snapshot buys nothing and
# goes stale. Cached to the same path the official `validate-with-schema.mjs` uses, and for
# the same day, so the two share one download and grep the same file.
SCHEMA_URL = 'https://schemastore.adaptybuilder.com/latest.json'
CACHE = os.path.join(tempfile.gettempdir(), 'adapty-flow.schema.json')
CACHE_MAX_AGE = 24 * 60 * 60


def load_schema(refresh=False):
    fresh = (not refresh and os.path.exists(CACHE)
             and time.time() - os.path.getmtime(CACHE) < CACHE_MAX_AGE)
    if not fresh:
        try:
            # a default Python-urllib User-Agent gets a 403 from this host; curl does not
            req = urllib.request.Request(SCHEMA_URL, headers={'User-Agent': 'adapty-flow-tools'})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            json.loads(body)                      # refuse to cache junk
            open(CACHE, 'wb').write(body)
        except Exception as exc:
            if not os.path.exists(CACHE):
                raise RuntimeError(f'could not fetch {SCHEMA_URL}: {exc}') from exc
            print(f'  (fetch failed, using cached copy: {exc})', file=sys.stderr)
    return json.load(open(CACHE))


def main():
    argv = sys.argv[1:]
    baseline = None
    if '--baseline' in argv:
        i = argv.index('--baseline')
        try:
            baseline = argv[i + 1]
        except IndexError:
            print('--baseline needs a file', file=sys.stderr); return 2
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith('-')]
    verbose = '--verbose' in argv or '-v' in argv
    if not args:
        print(__doc__)
        return 2
    try:
        import jsonschema
    except ImportError:
        print('INFRA: pip install jsonschema', file=sys.stderr)
        return 2
    try:
        schema = load_schema('--refresh' in argv)
    except RuntimeError as exc:
        print(f'INFRA: {exc}', file=sys.stderr)
        return 2
    validator = jsonschema.Draft202012Validator(schema)


    # Known false positive, by construction in the schema itself: expression nodes
    # (`JSONVariable` / `JSONConstant`) are declared as a `oneOf` over two IDENTICAL
    # permissive branches — `{type: object, properties: {type: string}, required: [type]}` —
    # with the comment "shape intentionally opaque, validated by the transformer". Anything
    # matches both branches, so `oneOf` always fails. Every `purchase` payload, every
    # conditional predicate, trips it. Verified on a real builder export, not just on
    # authored configs, so suppressing it is reading the schema correctly rather than
    # excusing our own output.
    def opaque_expression(err):
        e = err
        while e.context:
            e = sorted(e.context, key=lambda x: -len(list(x.absolute_path)))[0]
        if e.validator != 'oneOf':
            return False
        branches = e.validator_value if isinstance(e.validator_value, list) else []
        return any('intentionally opaque' in str(b.get('$comment', '')) for b in branches)

    # A baseline turns "hundreds of pre-existing v9-vs-v10 mismatches" into "what my edit
    # caused". Without it the output trains you to ignore real findings. Same reasoning as
    # the official `validate-with-schema.mjs --baseline`.
    def fingerprints(path):
        cfg = json.load(open(path))
        if isinstance(cfg.get('config'), dict):
            cfg = cfg['config']
        out = set()
        for e in validator.iter_errors(cfg):
            if not opaque_expression(e):
                out.add(('.'.join(str(x) for x in e.absolute_path), e.message))
        return out

    pre = fingerprints(baseline) if baseline else set()

    findings = 0
    for path in args:
        cfg = json.load(open(path))
        if isinstance(cfg.get('config'), dict):      # accept a `config get` envelope
            cfg = cfg['config']
        raw = list(validator.iter_errors(cfg))
        suppressed = [e for e in raw if opaque_expression(e)]
        errs = sorted((e for e in raw if not opaque_expression(e)
                       and ('.'.join(str(x) for x in e.absolute_path), e.message) not in pre),
                      key=lambda e: list(e.absolute_path))
        ignored_pre = len([e for e in raw if not opaque_expression(e)]) - len(errs)
        name = os.path.basename(path)
        ver = cfg.get('schemaVersion')
        note = f' [{len(suppressed)} opaque-expression false positives suppressed]' if suppressed else ''
        if baseline: note += f' [{ignored_pre} pre-existing ignored]'
        if not errs:
            print(f'{name:34} OK      (schemaVersion {ver} vs schema v10){note}')
            continue
        findings += 1
        # group by the property that failed, which is what makes this readable at all
        buckets = Counter()
        for e in errs:
            p = list(e.absolute_path)
            key = next((str(x) for x in reversed(p) if isinstance(x, str)), '(root)')
            buckets[key] += 1
        print(f'{name:34} {len(errs)} errors  (schemaVersion {ver} vs schema v10){note}')
        for key, n in buckets.most_common(12):
            print(f'    {n:5}  {key}')
        if verbose:
            for e in errs[:40]:
                loc = '.'.join(str(x) for x in e.absolute_path) or '(root)'
                print(f'      {loc}: {e.message[:150]}')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
