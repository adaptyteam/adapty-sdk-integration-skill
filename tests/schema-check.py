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
    tests/schema-check.py <config.json> [...]        # summary per file
    tests/schema-check.py --verbose <config.json>    # every error, deepest path first
Exit: 0 clean, 1 findings, 2 infrastructure problem.
"""
import json, sys, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, '..', 'skills', 'flow-generator', 'references', 'flow.schema.json')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    if not args:
        print(__doc__)
        return 2
    try:
        import jsonschema
    except ImportError:
        print('INFRA: pip install jsonschema', file=sys.stderr)
        return 2
    if not os.path.exists(SCHEMA):
        print(f'INFRA: schema not found at {SCHEMA}', file=sys.stderr)
        return 2
    schema = json.load(open(SCHEMA))
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

    findings = 0
    for path in args:
        cfg = json.load(open(path))
        if isinstance(cfg.get('config'), dict):      # accept a `config get` envelope
            cfg = cfg['config']
        raw = list(validator.iter_errors(cfg))
        suppressed = [e for e in raw if opaque_expression(e)]
        errs = sorted((e for e in raw if not opaque_expression(e)),
                      key=lambda e: list(e.absolute_path))
        name = os.path.basename(path)
        ver = cfg.get('schemaVersion')
        note = f' [{len(suppressed)} opaque-expression false positives suppressed]' if suppressed else ''
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
