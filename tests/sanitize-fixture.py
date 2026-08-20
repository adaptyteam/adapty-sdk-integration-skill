#!/usr/bin/env python3
"""Sanitize a real Adapty flow export into a committable test fixture.

Removes real identifiers while preserving every internal reference, so all the
referential invariants a test cares about still hold:

  - every UUID is remapped consistently (same input UUID -> same fake UUID),
    so product ids, _meta.screens.products entries, price variableIds,
    navigate targets, font ids and screen ids all still agree with each other
  - public-media.adapty.io asset URLs become example.invalid placeholders
  - numeric asset ids are remapped to a stable fake range

Deliberately NOT preserved: `flowProductId` is a UUIDv5 derived from the real
product id, so after remapping the pair is no longer a genuine v5 derivation.
A sanitized fixture therefore cannot be used to demonstrate that fact.

Usage: sanitize-fixture.py <in.json> <out.json>
"""
import json, re, sys, hashlib

UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')
MEDIA_RE = re.compile(r'https://public-media\.adapty\.io/[^"\s]*')

def fake_uuid(real, salt='adapty-fixture'):
    """Deterministic fake UUID. Keeps the version nibble so shape-checks still pass."""
    h = hashlib.sha256((salt + real).encode()).hexdigest()
    ver = real[14] if len(real) > 14 else '4'
    return f'{h[0:8]}-{h[8:12]}-{ver}{h[13:16]}-{h[16:20]}-{h[20:32]}'

def main(src, dst):
    raw = open(src).read()

    uuids = sorted(set(UUID_RE.findall(raw)))
    mapping = {u: fake_uuid(u) for u in uuids}
    for real, fake in mapping.items():
        raw = raw.replace(real, fake)

    media = sorted(set(MEDIA_RE.findall(raw)))
    for i, url in enumerate(media, 1):
        ext = url.rsplit('.', 1)[-1] if '.' in url.rsplit('/', 1)[-1] else 'png'
        raw = raw.replace(url, f'https://example.invalid/fixture-asset-{i}.{ext}')

    doc = json.loads(raw)

    # numeric asset ids ("444588") -> stable fakes, keeping equal ids equal
    seen = {}
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == 'id' and isinstance(v, str) and v.isdigit():
                    o[k] = seen.setdefault(v, str(900000 + len(seen)))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc)

    json.dump(doc, open(dst, 'w'), indent=2, ensure_ascii=False)
    print(f'{src} -> {dst}')
    print(f'  UUIDs remapped: {len(mapping)}')
    print(f'  media URLs replaced: {len(media)}')
    print(f'  numeric asset ids remapped: {len(seen)}')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
