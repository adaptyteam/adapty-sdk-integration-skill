#!/usr/bin/env python3
"""Render smoke test: does a flow config actually draw something?

Every other check in this repo is referential — it proves ids agree with each
other. Two configs in this project's history passed all of them, saved cleanly,
round-tripped byte-intact, and still left the Flow Builder unable to open the
flow (`references/flow-schema.md`, trap 10). Nothing structural sees that. A
render does, so this is the only check in the repo that can.

Pipeline, per config:

    adapty flows config preview <file>   -> render URL (config gzipped in the
                                           fragment; fully local, no auth)
    headless Chrome --screenshot         -> PNG
    ink test                             -> is anything actually drawn?

The URL is never printed or read: it is thousands of characters of base64 and
carries nothing actionable. It goes from the CLI into Chrome and nowhere else.

WHAT THIS PROVES, AND WHAT IT DOES NOT. A pass means pixels appeared, not that
they are the right pixels. It catches the blank-screen class — the class both
historical failures belonged to — and it cannot catch a wrong colour, a bad
indent or a detached element. For those, look at the PNG: --keep leaves them on
disk, and looking is the point of the whole exercise.

Usage:
    tests/render-check.py [config.json ...]      # default: tests/fixtures/*.json
    tests/render-check.py --keep                 # leave the PNGs to look at
    tests/render-check.py --screen <id>          # render one screen by id

Exit codes follow the repo's lint convention:
    0  every config drew something
    1  at least one rendered blank (a finding)
    2  infrastructure problem — CLI or Chrome missing (fix the tooling)
"""
import argparse, glob, json, os, shutil, struct, subprocess, sys, tempfile, zlib

CHROME_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    shutil.which('google-chrome') or '',
    shutil.which('chromium') or '',
]
# Wide enough for a phone frame plus the render page's surrounding chrome.
VIEWPORT = (430, 932)
# Give the page time to fetch fonts and images before the shutter.
VIRTUAL_TIME_BUDGET_MS = 15000
# A render that draws fewer distinct colours than this is treated as blank: an
# error page or an empty frame lands at 1-2, a real screen at hundreds.
MIN_DISTINCT_COLOURS = 12
# A render where one colour covers this much of the frame is background plus a smudge.
# It exists because the render page answers an unusable request with a *page* rather than
# an error: `--device <anything>` is accepted by the CLI (the flag has no `options`), and an
# unrecognized value renders the words 'Unknown device "..."' on white. That screenshot
# carries 216 distinct colours from text antialiasing alone, so the colour-count test above
# passes it. Measured: real screens run 44-76% dominant; the error page is 99.7%.
MAX_DOMINANT_SHARE = 0.92
# Where --baseline writes reference renders, and what the diff compares against.
BASELINE_DIR = 'tests/render-baseline'
# Share of differing pixels above which a render counts as changed. Antialiasing and
# font hinting move a handful of pixels between runs on the same machine; a real
# layout or state change moves far more than this.
DIFF_TOLERANCE = 0.005


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


def preview_url(config_path, screen=None):
    """Ask the CLI for the render URL. Returns (url, error). Never logs the URL."""
    cmd = ['npx', 'adapty@beta', 'flows', 'config', 'preview', config_path, '--json']
    if screen:
        cmd += ['--screen', screen]
    try:
        # stdout is a pipe, so the CLI prints the URL instead of opening a browser.
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return None, 'preview timed out'
    if done.returncode != 0:
        first = (done.stderr or done.stdout or '').strip().splitlines()
        return None, f'preview failed: {first[0] if first else "no output"}'
    try:
        return json.loads(done.stdout)['render_url'], None
    except (ValueError, KeyError):
        return None, 'preview returned no render_url'


def screenshot(chrome, url, out_png):
    cmd = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
           f'--window-size={VIEWPORT[0]},{VIEWPORT[1]}',
           f'--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}',
           f'--screenshot={out_png}', url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return 'chrome timed out'
    if not os.path.exists(out_png) or os.path.getsize(out_png) == 0:
        return 'chrome wrote no screenshot'
    return None


def png_pixels(path):
    """Decode a PNG to a list of RGB tuples. Stdlib only — no Pillow in this repo.

    Handles the one colour type Chrome emits for --screenshot (8-bit RGBA, no
    interlacing) and reports anything else rather than guessing.
    """
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    pos, idat, width, height, bit_depth, colour_type, interlace = 8, b'', 0, 0, 0, 0, 0
    while pos < len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            width, height, bit_depth, colour_type = struct.unpack('>IIBB', body[:10])
            interlace = body[12]
        elif kind == b'IDAT':
            idat += body
        elif kind == b'IEND':
            break
        pos += length + 12
    if bit_depth != 8 or colour_type not in (2, 6) or interlace != 0:
        raise ValueError(f'unsupported PNG (depth {bit_depth}, colour {colour_type}, '
                         f'interlace {interlace})')
    channels = 4 if colour_type == 6 else 3
    raw = zlib.decompress(idat)
    stride = width * channels
    out, prev = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filt = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        # PNG per-scanline filters, undone in place (spec section 9.2).
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if filt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        for x in range(0, stride, channels):
            out.append((line[x], line[x + 1], line[x + 2]))
        prev = line
    return out


def ink(path):
    """(distinct colour count, share of the most common colour)."""
    pixels = png_pixels(path)
    if not pixels:
        return 0, 1.0
    counts = {}
    for px in pixels:
        counts[px] = counts.get(px, 0) + 1
    return len(counts), max(counts.values()) / len(pixels)


def diff_share(a_png, b_png):
    """Share of pixels that differ between two PNGs, or None if sizes disagree."""
    a, b = png_pixels(a_png), png_pixels(b_png)
    if len(a) != len(b):
        return None
    if not a:
        return 0.0
    differing = sum(1 for x, y in zip(a, b) if x != y)
    return differing / len(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('configs', nargs='*')
    ap.add_argument('--keep', action='store_true', help='keep the PNGs, and print where')
    ap.add_argument('--screen', help='render this screen id instead of the first')
    ap.add_argument('--baseline', action='store_true',
                    help=f'write reference renders to {BASELINE_DIR}/ instead of comparing')
    args = ap.parse_args()

    configs = args.configs or sorted(glob.glob('tests/fixtures/*.json'))
    if not configs:
        print('no configs to check', file=sys.stderr)
        return 2

    chrome = find_chrome()
    if not chrome:
        print('INFRA: no Chrome or Chromium found. Looked in:', file=sys.stderr)
        for c in CHROME_CANDIDATES:
            if c:
                print(f'  {c}', file=sys.stderr)
        return 2

    if args.baseline:
        outdir = os.path.abspath(BASELINE_DIR)
    else:
        outdir = os.path.abspath('tests/.render') if args.keep else tempfile.mkdtemp()
    os.makedirs(outdir, exist_ok=True)

    findings, infra = 0, 0
    for path in configs:
        name = os.path.basename(path)
        png = os.path.join(outdir, name.replace('.json', '.png'))

        url, err = preview_url(path, args.screen)
        if err:
            # A preview that will not build is a real finding about the config —
            # unless the command itself is missing, which is tooling.
            if 'not found' in err or 'ENOENT' in err:
                print(f'{name:34} INFRA  {err}')
                infra += 1
            else:
                print(f'{name:34} FAIL   {err}')
                findings += 1
            continue

        err = screenshot(chrome, url, png)
        if err:
            print(f'{name:34} INFRA  {err}')
            infra += 1
            continue

        try:
            colours, dominant = ink(png)
        except ValueError as exc:
            print(f'{name:34} INFRA  {exc}')
            infra += 1
            continue

        if colours < MIN_DISTINCT_COLOURS or dominant > MAX_DOMINANT_SHARE:
            print(f'{name:34} BLANK  {colours} colours, '
                  f'{dominant:.1%} one colour — nothing meaningful drawn')
            findings += 1
            continue

        if args.baseline:
            print(f'{name:34} SAVED  baseline written ({colours} colours)')
            continue

        ref = os.path.join(BASELINE_DIR, name.replace('.json', '.png'))
        if not os.path.exists(ref):
            print(f'{name:34} OK*    {colours} colours, no baseline to compare '
                  f'(run --baseline to record one)')
            continue

        share = diff_share(ref, png)
        if share is None:
            print(f'{name:34} CHANGED  render size differs from the baseline')
            findings += 1
        elif share > DIFF_TOLERANCE:
            print(f'{name:34} CHANGED  {share:.1%} of pixels differ from the baseline')
            findings += 1
        else:
            print(f'{name:34} OK     {colours} colours, {share:.2%} pixel drift')

    if args.keep:
        print(f'\nPNGs in {outdir} — open them. A pass means pixels appeared, '
              f'not that they are the right ones.')

    if infra:
        return 2
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
