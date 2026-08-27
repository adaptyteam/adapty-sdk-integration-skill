#!/usr/bin/env python3
"""Check `mobile-preview.mjs` builds the device-preview link correctly over the fixture corpus.

The link is the one behind the Flow Builder's "Test on Device" button, and it is pure string
construction — so it is cheaply and completely testable, unlike everything else in phase 5.
Runs without `--qr`, so `qrcode` is NOT required; the PNG path is checked only when the
dependency happens to be resolvable.

Two things this exists to guard, both of which would fail silently:

  * **The `locales` separator must stay a literal comma.** Rebuilding the query with
    `URLSearchParams` yields `%2C`, and the Adapty app is only known to accept the builder's
    spelling. Nothing else in the pipeline would notice.
  * **`defaultLocale` is a locale *id* and the link carries a *code*.** Every fixture in the
    corpus — and every live flow checked — has `id == code`, so a regression to passing the id
    through is invisible against real data. The synthetic case below is the only coverage that
    distinction has.

Usage:
    tests/mobile-preview-check.py                 # the whole fixture corpus
    tests/mobile-preview-check.py <config.json>   # one file

Exit: 0 clean, 1 findings, 2 infrastructure problem.
"""
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'mobile-preview.mjs')
FIXTURES = os.path.join(HERE, 'fixtures')

APP = '550e8400-e29b-41d4-a716-446655440000'
FLOW = '660e8400-e29b-41d4-a716-446655440001'
EXPECTED_ORIGIN = 'https://mobile-app.adapty.io'
EXPECTED_PATH = '/flow-preview'


def run(args, cwd=None):
    """Returns (exit_code, stdout, stderr). cwd defaults to the repo root, where `qrcode` is
    deliberately NOT installed — that is what proves the link-only path needs no dependency."""
    proc = subprocess.run(
        [ 'node', SCRIPT, *args],
        capture_output=True, text=True, cwd=cwd or ROOT, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def link_of(stdout):
    """The script prints the URL on line 1 and a human-readable locale summary on line 2."""
    lines = [l for l in stdout.splitlines() if l.strip()]
    if not lines:
        return None
    return lines[0]


def params_of(url):
    """Parsed WITHOUT urllib's query parser, which would happily accept a %2C-encoded comma and
    hide the exact regression this file exists to catch. The raw string is the contract."""
    query = urlsplit(url).query
    out = {}
    for pair in query.split('&'):
        key, _, value = pair.partition('=')
        out[key] = value
    return out


def expected_locales(path):
    config = json.load(open(path))
    config = config.get('config', config)
    locales = [l for l in config.get('locales', []) if isinstance(l, dict) and l.get('code')]
    codes = [l['code'] for l in locales]
    default_id = config.get('defaultLocale')
    current = next((l['code'] for l in locales if l.get('id') == default_id), codes[0] if codes else None)
    return codes, current


def check_config(path, findings):
    name = os.path.basename(path)
    codes, current = expected_locales(path)
    code, stdout, stderr = run(['--app', APP, '--flow', FLOW, '--config', path])

    if not codes:
        # No locales is a legitimate refusal, not a defect — assert it refuses cleanly.
        if code != 1:
            findings.append(f'{name}: no locales, expected exit 1, got {code}: {stderr.strip()}')
        else:
            print(f'  {name}: no locales -> refused (exit 1), correct')
        return

    if code != 0:
        findings.append(f'{name}: exit {code}: {stderr.strip()}')
        return

    url = link_of(stdout)
    if url is None:
        findings.append(f'{name}: printed no URL')
        return

    split = urlsplit(url)
    if f'{split.scheme}://{split.netloc}' != EXPECTED_ORIGIN or split.path != EXPECTED_PATH:
        findings.append(f'{name}: unexpected origin/path: {url}')

    params = params_of(url)
    if params.get('app_id') != APP:
        findings.append(f'{name}: app_id is {params.get("app_id")!r}')
    if params.get('flow_id') != FLOW:
        findings.append(f'{name}: flow_id is {params.get("flow_id")!r}')
    if params.get('cluster') != 'us':
        findings.append(f'{name}: cluster is {params.get("cluster")!r}, expected "us"')

    raw_locales = params.get('locales', '')
    if '%2C' in raw_locales.upper():
        findings.append(f'{name}: locales separator is percent-encoded, must be a literal comma: {raw_locales!r}')
    if raw_locales != ','.join(codes):
        findings.append(f'{name}: locales is {raw_locales!r}, expected {",".join(codes)!r}')
    if params.get('current_locale') != current:
        findings.append(f'{name}: current_locale is {params.get("current_locale")!r}, expected {current!r}')

    if not findings:
        print(f'  {name}: {len(codes)} locale(s), current={current} -> OK')


def check_id_differs_from_code(findings):
    """The one case real data never produces: defaultLocale names an id whose code differs.
    The link must carry the CODE."""
    config = {
        'defaultLocale': 'uk-UA',
        'locales': [
            {'id': 'en-US', 'code': 'en', 'name': 'English'},
            {'id': 'uk-UA', 'code': 'uk', 'name': 'Ukrainian'},
        ],
        'screens': [],
    }
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(config, fh)
        path = fh.name

    try:
        code, stdout, stderr = run(['--app', APP, '--flow', FLOW, '--config', path])
        if code != 0:
            findings.append(f'id!=code: exit {code}: {stderr.strip()}')
            return
        params = params_of(link_of(stdout))
        if params.get('current_locale') != 'uk':
            findings.append(
                f'id!=code: current_locale is {params.get("current_locale")!r}, expected "uk" — '
                'defaultLocale is an id, the link carries the code'
            )
        elif params.get('locales') != 'en,uk':
            findings.append(f'id!=code: locales is {params.get("locales")!r}, expected "en,uk"')
        else:
            print('  synthetic id!=code: resolved uk-UA -> uk, correct')

        # --locale must match on the id too, not only the code.
        code, stdout, stderr = run(['--app', APP, '--flow', FLOW, '--config', path, '--locale', 'en-US'])
        if code != 0 or params_of(link_of(stdout)).get('current_locale') != 'en':
            findings.append('id!=code: --locale did not accept a locale id')
        else:
            print('  synthetic id!=code: --locale en-US -> en, correct')
    finally:
        os.unlink(path)


def check_rejections(findings):
    for args, label in (
        (['--flow', FLOW, '--locales', 'en'], 'missing --app'),
        (['--app', APP, '--locales', 'en'], 'missing --flow'),
        (['--app', APP, '--flow', 'not-a-uuid', '--locales', 'en'], 'non-UUID --flow'),
        (['--app', APP, '--flow', FLOW], 'neither --config nor --locales'),
    ):
        code, _, _ = run([*args])
        if code != 2:
            findings.append(f'{label}: expected exit 2, got {code}')
        else:
            print(f'  rejects {label} (exit 2), correct')


def check_png(findings):
    """Only meaningful where `qrcode` resolves; skipped otherwise so the corpus check stays
    dependency-free."""
    cache = os.path.expanduser('~/.cache/adapty-flow-qr')
    if not os.path.isdir(os.path.join(cache, 'node_modules', 'qrcode')):
        print('  PNG: skipped (qrcode not installed at ~/.cache/adapty-flow-qr)')
        return

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'qr.png')
        code, stdout, stderr = run(
            ['--app', APP, '--flow', FLOW, '--locales', 'en,uk', '--out', out], cwd=cache
        )
        if code != 0:
            findings.append(f'PNG: exit {code}: {stderr.strip()}')
        elif not os.path.exists(out):
            findings.append('PNG: script reported success but wrote no file')
        elif open(out, 'rb').read(8) != b'\x89PNG\r\n\x1a\n':
            findings.append('PNG: file is not a PNG')
        elif f'file://{out}' not in stdout:
            findings.append(f'PNG: printed no file:// URL for {out}; stdout was {stdout!r}')
        else:
            print(f'  PNG: wrote {os.path.getsize(out)} bytes, valid header, file:// URL printed')


def check_qr_lands_beside_config(findings):
    """--qr must write NEXT TO THE CONFIG. Anywhere else and the reader's viewer refuses to open it
    ("outside the working directory"), which is the whole reason the QR is a file."""
    cache = os.path.expanduser('~/.cache/adapty-flow-qr')
    if not os.path.isdir(os.path.join(cache, 'node_modules', 'qrcode')):
        print('  --qr placement: skipped (qrcode not installed)')
        return

    with tempfile.TemporaryDirectory() as tmp:
        config_path = os.path.join(tmp, 'flow.working.json')
        with open(config_path, 'w') as fh:
            json.dump({'defaultLocale': 'en', 'locales': [{'id': 'en', 'code': 'en'}], 'screens': []}, fh)

        code, stdout, stderr = run(['--app', APP, '--flow', FLOW, '--config', config_path, '--qr'], cwd=cache)
        if code != 0:
            findings.append(f'--qr: exit {code}: {stderr.strip()}')
            return

        expected = os.path.join(tmp, f'flow-preview-qr-{FLOW[:8]}.png')
        if not os.path.exists(expected):
            written = os.listdir(tmp)
            findings.append(f'--qr wrote no {os.path.basename(expected)} beside the config; dir holds {written}')
        elif f'file://{expected}' not in stdout:
            findings.append('--qr printed no file:// URL for the image it wrote')
        else:
            print(f'  --qr placement: wrote {os.path.basename(expected)} beside the config, correct')


def check_no_character_art(findings):
    """Character-art QRs were removed on purpose: bulky in an answer, and the colour-free form is
    inverted on a dark terminal. Nothing should print half-blocks any more."""
    code, stdout, _ = run(['--app', APP, '--flow', FLOW, '--locales', 'en,uk'])
    if code == 0 and any(ch in stdout for ch in '█▀▄'):
        findings.append('character art is back in stdout; the QR must only ever be a file')
    else:
        print('  no character art in stdout, correct')


def main():
    if not os.path.exists(SCRIPT):
        print(f'no such script: {SCRIPT}', file=sys.stderr)
        return 2

    targets = sys.argv[1:]
    if not targets:
        targets = sorted(
            os.path.join(FIXTURES, f) for f in os.listdir(FIXTURES) if f.endswith('.json')
        )

    findings = []
    print(f'fixtures ({len(targets)}):')
    for path in targets:
        check_config(path, findings)

    print('resolution:')
    check_id_differs_from_code(findings)
    print('usage:')
    check_rejections(findings)
    print('qr:')
    check_png(findings)
    check_qr_lands_beside_config(findings)
    check_no_character_art(findings)

    print()
    if findings:
        print(f'{len(findings)} finding(s):')
        for f in findings:
            print(f'  - {f}')
        return 1

    print('mobile-preview: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
