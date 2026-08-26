#!/usr/bin/env python3
"""Tests for skills/flow-generator/references/flowkit.py.

A shape helper that has drifted from the format is worse than no helper, because it is
confidently wrong at scale. So this asserts the invariants flowkit exists to guarantee, and
then puts its output through the same schema gate a real config goes through.

    python3 tests/test-flowkit.py

Exit codes follow the repo convention: 0 clean, 1 failures, 2 infrastructure problem.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# a skills dir installs by plain copy, so a __pycache__ under references/ would SHIP with it
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, 'skills', 'flow-generator', 'references'))

import flowkit as fk  # noqa: E402

FAILURES = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}' + (f'   {detail}' if detail else ''))
        FAILURES.append(name)


def raises(fn, exc=ValueError):
    try:
        fn()
        return False
    except exc:
        return True


def sample():
    """A document exercising the pieces most likely to drift."""
    ids = fk.Ids('el_T')
    fk._ids = ids
    tick = fk.stack([fk.icon('Check', size_pt=15, color_id='on')],
                    fixed_w=26, fixed_h=26, corner=fk.radius(9999),
                    direction='horizontal', align_h='center', align_v='center',
                    visibility=fk.hidden(), caption='Tick',
                    props_by_state={'selected': {'visibility': fk.visible(),
                                                 'fill': fk.fill('accent')}})
    card = fk.product(
        [fk.stack([tick], height='fixed', fixed_h=26, direction='horizontal',
                  align_h='end', caption='Tick row'),
         fk.text(fk.rich('Individual'), preset='h1', color_id='ink'),
         fk.text(fk.rich('12 mo, ', fk.Span('$79.99', bold=True), ' or ',
                         fk.Var('0000.prod_price')),
                 preset='body', color_id='muted')],
        product_id='11111111-2222-3333-4444-555555555555', group_id='plans', default=True,
        padding=fk.pad(14, 16, 16, 14), corner=fk.radius(16), fill_=fk.fill('card'),
        border='accent', border_width=3, caption='Plan')
    cta = fk.stack([fk.text(fk.rich('Continue'), preset='body', color_id='on', align='center')],
                   direction='horizontal', align_h='center', align_v='center',
                   fixed_h=46, corner=fk.radius(9999), fill_=fk.fill('accent'),
                   position=fk.docked(bottom=18, left=16, right=16), caption='CTA',
                   actions=[fk.purchase('plans')])
    rail = fk.stack([], fixed_w=38, fixed_h=78, corner=fk.radius(16),
                    fill_=fk.gradient(180, ('#E1D6EB', 0), ('#EDE9F0', 1)), caption='Rail')
    countdown = fk.timer([fk.timer_digits(units=('minutes', 'seconds'), preset='body',
                                          color_id='ink')],
                         custom_id='offer', minutes=15, padding=fk.pad(12, 16, 16, 12),
                         corner=fk.radius(20), fill_=fk.fill('card'),
                         visibility=fk.visible(), caption='Countdown')
    return fk.config(
        screens=[fk.screen('scr_main', [card, rail, cta, countdown], caption='Plans',
                           fill_=fk.fill('bg'), padding=fk.pad(0, 0, 0, 120),
                           selectable_groups=[{'id': 'plans', 'type': 'product'}])],
        colors=[('bg', 'Background', '#FFFFFF', '#101014'),
                ('card', 'Card', '#F3F6FB', '#1A1A20'),
                ('ink', 'Ink', '#111114', '#F5F5F7'),
                ('muted', 'Muted', '#5F6368', '#9AA0A8'),
                ('accent', 'Accent', '#4A6EBD', '#5C80CF'),
                ('on', 'On accent', '#FFFFFF', '#FFFFFF')],
        typography=[('h1', 'H1', 25, 'bold'), ('body', 'Body', 16, 'regular')],
        icons=[{'name': 'Check', 'weight': 'bold', 'raw': '<svg/>'}])


def main():
    cfg = sample()
    scr = cfg['screens'][0]
    node_map = scr['elements']['map']

    print('flowkit')
    # the invariant the module exists for: hierarchy and map must agree exactly
    seen = []

    def walk(node):
        if node['id'] != 'root':
            seen.append(node['id'])
        for kid in node.get('children', []):
            walk(kid)

    walk(scr['elements']['hierarchy'])
    check('hierarchy and map hold the same ids',
          sorted(seen) == sorted(node_map), f'{len(seen)} in tree vs {len(node_map)} in map')
    check('no id appears twice in the tree', len(seen) == len(set(seen)))
    check('no leftover _children in the map',
          not any('_children' in n for n in node_map.values()))

    # duplicate ids must raise, not silently drop an element
    try:
        dup = fk.stack([], node_id='el_dup')
        dup2 = fk.stack([], node_id='el_dup')
        fk.flatten([dup, dup2])
        check('flatten rejects a duplicate id', False, 'no error raised')
    except ValueError:
        check('flatten rejects a duplicate id', True)

    # v10 shape
    check('schemaVersion is 10', cfg['schemaVersion'] == 10)
    fills = [n['props']['fill'] for n in node_map.values() if 'fill' in n['props']]
    fills.append(scr['props']['fill'])
    check('every fill is an array (v10)', all(isinstance(f, list) for f in fills),
          f'{sum(1 for f in fills if not isinstance(f, list))} non-array')

    # the divergence this module was built to kill
    spans = None
    for n in node_map.values():
        c = n['props'].get('content')
        if isinstance(c, dict) and len(c.get('values', {}).get('en', [])) == 1:
            content = c['values']['en'][0]['content']
            if any(s.get('type') == 'variable' for s in content):
                spans = content
    check('rich() produced a span list containing a variable', spans is not None)
    if spans:
        kinds = [s['type'] for s in spans]
        check('Var -> variable node, Span -> text node',
              kinds == ['text', 'text', 'text', 'variable'], str(kinds))
        check('a Span carries its own colour only when asked',
              'color' not in spans[0]['attrs'])
        check('a bold Span sets bold', spans[1]['attrs']['bold'] is True)
    try:
        fk.rich('x', ('var', 'y'))
        check('rich() rejects an ambiguous bare tuple', False, 'tuple was accepted')
    except TypeError:
        check('rich() rejects an ambiguous bare tuple', True)

    # things the traps say must hold
    prod = [n for n in node_map.values() if n['type'] == 'product'][0]
    check('product carries groupId, default and product.id',
          prod['props']['groupId'] == 'plans' and prod['props']['default'] is True
          and 'id' in prod['props']['product'])
    check('product gets the system selected state',
          prod['states'] == [{'id': 'selected', 'type': 'system'}])
    cta = [n for n in node_map.values() if n.get('caption') == 'CTA'][0]
    check('purchase buys the group selection, not a const',
          cta['interactions'][0]['actions'][0]['payload']['product']['variableId']
          == 'plans.selectedProduct')
    check('a docked element sets left and right and bottom',
          set(cta['props']['position']) >= {'type', 'bottom', 'left', 'right'})
    rail = [n for n in node_map.values() if n.get('caption') == 'Rail'][0]
    check('a gradient does not end on a bare colour object',
          isinstance(rail['props']['fill'], list)
          and rail['props']['fill'][0]['type'] == 'gradient')
    # pinned against tests/fixtures/*.json, where two real exports use this exact shape
    check('navigate payload is {type: screen, screen: id}',
          fk.navigate('scr_x')['payload'] == {'type': 'screen', 'screen': 'scr_x'},
          json.dumps(fk.navigate('scr_x')['payload']))

    check('_meta.screens is left empty (builder-owned)', cfg['_meta']['screens'] == {})

    # predeclare(): the provisional declaration that lets a NEW draft preview on a device
    pids = ['db3cfae2-5266-4678-85b3-b2ea535301ce', 'a80615bd-86b5-4851-b895-a343fa7db228']
    dec = fk.predeclare('scr_pro', pids)
    entries = dec['scr_pro']['products']
    check('predeclare emits one entry per product', [e['id'] for e in entries] == pids)
    check('predeclare emits only id and flowProductId',
          all(set(e) == {'id', 'flowProductId'} for e in entries))
    check('predeclare is deterministic', fk.predeclare('scr_pro', pids) == dec)
    check('predeclare is screen-scoped',
          fk.predeclare('scr_other', pids)['scr_other']['products'][0]['flowProductId']
          != entries[0]['flowProductId'])
    # the exact pair that was verified to preview on an unpublished draft
    check('predeclare reproduces the verified-previewing pair',
          [e['flowProductId'] for e in entries]
          == ['63d3e909-2581-5762-9345-c2423730e27a', '55258fb4-6310-5e4e-9086-7ea4d71f9418'])
    check('config(meta_screens=...) carries it through',
          fk.config(screens=[], meta_screens=dec)['_meta']['screens'] == dec)
    check('opacity, when given, is a percentage not a fraction',
          fk.hex_color('#101828', opacity=6)['opacity'] == 6)

    # distribution has four modes, and only the gap form used to be reachable
    check('default distribution is the gap form',
          fk.layout(gap=12)['distribution'] == {'gap': 12, 'type': 'gap'})
    check('a spread mode carries no gap key',
          fk.layout(distribution='space-between')['distribution']
          == {'type': 'space-between'})
    check('all three spread modes are accepted',
          all(fk.layout(distribution=m)['distribution']['type'] == m
              for m in fk.SPREAD_MODES))
    try:
        fk.layout(distribution='space-araound')
        check('an unknown distribution raises rather than emitting junk',
              False, 'typo was accepted')
    except ValueError:
        check('an unknown distribution raises rather than emitting junk', True)
    # image() — an uploaded asset was unreachable from this module before 0.8.0's media upload
    HERO = 'https://public-media.adapty.io/public/1e/5b/1e5bbbb4/hero.png'
    img = fk.image(HERO, media_id=516395, fixed_w=242, corner=fk.radius(20))
    check('image binds the url inside the per-locale localizable map',
          img['props']['image'] == {'_localizable': True,
                                    'values': {'en': {'id': '516395', 'url': HERO}}},
          json.dumps(img['props']['image']))
    check('a numeric media id is written as a string',
          isinstance(img['props']['image']['values']['en']['id'], str))
    check('image defaults to a hug height, whose drawn size is the asset aspect',
          img['props']['height'] == {'type': 'hug'} and img['props']['objectFit'] == 'cover')
    ph = fk.image(fk.PLACEHOLDER, fixed_w=242, fixed_h=180)
    check('PLACEHOLDER emits an empty values map, wrapper intact',
          ph['props']['image'] == {'values': {}, '_localizable': True})
    check('a fixed image box is honoured over the hug default',
          ph['props']['height'] == {'type': 'fixed', 'value': 180})
    try:
        fk.image('')
        check('an image with no url raises rather than emitting an empty map', False,
              'empty url was accepted')
    except TypeError:
        check('an image with no url raises rather than emitting an empty map', True)
    try:
        fk.image(HERO, fit='contain')
        check('an objectFit outside the two-value enum raises', False, 'contain was accepted')
    except ValueError:
        check('an objectFit outside the two-value enum raises', True)

    spread_stack = fk.stack([], distribution='space-evenly')
    check('stack passes distribution through',
          spread_stack['props']['layout']['distribution']
          == {'type': 'space-evenly'})
    check('screen passes distribution through',
          fk.screen('scr_d', [], distribution='space-between',
                    scrollable=False)['props']['layout']['distribution']
          == {'type': 'space-between'})

    # The stretch-between-anchors pair. Both halves are measured render failures, so flowkit
    # refuses each half alone rather than emitting it and warning about it later.
    rail = fk.stack([], width='fixed', fixed_w=8, height='auto',
                    position=fk.absolute(top=10, left=12, bottom=-18, z=-10))
    check('absolute() keeps every offset it was given',
          rail['props']['position'] == {'type': 'absolute', 'top': 10, 'left': 12,
                                        'bottom': -18, 'zIndex': -10})
    check('a top+bottom anchored stack takes height auto',
          rail['props']['height'] == {'type': 'auto'})
    check('absolute() omits the offsets it was not given',
          fk.absolute(top=0, left=0) == {'type': 'absolute', 'top': 0, 'left': 0})
    check('anchored top+bottom with a fill height raises',
          raises(lambda: fk.stack([], height='fill',
                                  position=fk.absolute(top=10, bottom=-18))))
    check('height auto without a bottom anchor raises',
          raises(lambda: fk.stack([], height='auto', position=fk.absolute(top=10))))
    check('height auto on a relative element raises',
          raises(lambda: fk.stack([], height='auto')))
    check('size rejects a kind that is not a kind',
          raises(lambda: fk.size('atuo')))

    # A rail fades on ALPHA, so a stop needs an optional third item; without it the composition
    # in patterns.md was unreachable from this module.
    fade = fk.gradient(180, ('#0E9F6E', 0, 100), ('#0E9F6E', 1, 22))
    check('a gradient stop carries a per-stop opacity when given one',
          [s['color'].get('opacity') for s in fade[0]['stops']] == [100, 22])
    check('a two-item gradient stop still omits opacity entirely',
          'opacity' not in fk.gradient(180, ('#FFF', 0), ('#000', 1))[0]['stops'][0]['color'])

    # Typography leading, verified present on 6 of 7 presets in a real export.
    typo = fk.config(screens=[fk.screen('scr_t', [])],
                     typography=[('a', 'A', 30, 'bold', 34, -0.5),
                                 ('b', 'B', 15, 'regular', 21),
                                 ('c', 'C', 13, 'regular')])['theme']['typography']
    check('typography carries lineHeight and letterSpacing when given',
          typo[0]['settings'] == {'size': 30, 'weight': 'bold', 'lineHeight': 34,
                                  'letterSpacing': -0.5})
    check('lineHeight alone is allowed', typo[1]['settings'].get('lineHeight') == 21
          and 'letterSpacing' not in typo[1]['settings'])
    check('the plain four-item preset is unchanged',
          typo[2]['settings'] == {'size': 13, 'weight': 'regular'})

    # --- timer -------------------------------------------------------------------------
    # The bug this guards: a countdown's digit tokens carry a `timer_` PREFIX. The bare names
    # save and pass `flows config validate`, and the Flow Builder then paints them red
    # "Unknown" while the device/preview renders the literal "%minutes%".
    # `component-catalog.json` shipped the bare names until 2026-08-25, so the prefix is
    # exactly the kind of shape a helper has to own rather than leave to an author.
    digits = fk.timer_digits(units=('hours', 'minutes', 'seconds'))
    nodes = digits['props']['content']['values']['en'][0]['content']
    check('every timer digit token carries the timer_ prefix',
          [n['attrs']['token'] for n in nodes if n.get('type') == 'token']
          == ['timer_hours', 'timer_minutes', 'timer_seconds'], str(nodes))
    check('units are emitted in the order given, not in TIMER_UNITS order',
          [n['attrs']['token'] for n in
           fk.timer_digits(units=('seconds', 'minutes'))['props']['content']['values']['en'][0]
           ['content'] if n.get('type') == 'token'] == ['timer_seconds', 'timer_minutes'])
    check('the separator is a rich-text node, not a bare string',
          [n.get('text') for n in nodes if n.get('type') == 'text'] == [':', ':']
          and all('attrs' in n for n in nodes if n.get('type') == 'text'))
    check('an unknown timer unit raises rather than emitting a bare token',
          raises(lambda: fk.timer_digits(units=('hours', 'mins'))))

    delay = fk.timer(actions=[{'id': 'act_next', 'type': 'navigate',
                               'payload': {'type': 'screen', 'screen': 'scr_next'}}],
                     seconds=3)
    check("a timer's own interaction fires on timer-end, not tap",
          [i['trigger'] for i in delay.get('interactions', [])] == ['timer-end'], str(delay))
    check('a delay timer with no digit child draws nothing, which is the invisible-delay shape',
          not delay.get('_children'))
    check('duration carries all four units',
          fk.timer(days=1, hours=2, minutes=3, seconds=4)['props']['duration']
          == {'days': 1, 'hours': 2, 'minutes': 3, 'seconds': 4})
    check('a timer carries states, like every other element', fk.timer()['states'] == [])

    # and finally: does the real schema gate accept it?
    checker = os.path.join(HERE, 'schema-check.py')
    if not os.path.exists(checker):
        print('  SKIP  schema gate (tests/schema-check.py missing)')
    else:
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
            json.dump(cfg, fh)
            path = fh.name
        try:
            res = subprocess.run([sys.executable, checker, path],
                                 capture_output=True, text=True, timeout=180)
            out = (res.stdout + res.stderr).strip().splitlines()
            line = out[0] if out else '(no output)'
            if res.returncode == 2:
                print(f'  SKIP  schema gate unavailable: {line}')
            else:
                check('flowkit output passes the schema gate', ' OK ' in f' {line} ', line)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f'  SKIP  schema gate could not run: {exc}')
        finally:
            os.unlink(path)

    # The token vocabulary is the schema's, not ours: `ETimerToken` is the ground truth, so if
    # the builder ever adds a unit, TIMER_UNITS has to move with it. The gate above warms this
    # cache. Note the schema does NOT constrain a token node's own `attrs.token` (it is typed a
    # bare string and never $refs ETimerToken), which is why the bad name has to be caught here
    # and in verify-config.py rather than by the schema check.
    schema_cache = os.path.join(tempfile.gettempdir(), 'adapty-flow.schema.json')
    enum = None
    if os.path.exists(schema_cache):
        try:
            enum = json.load(open(schema_cache)).get('$defs', {}).get('ETimerToken', {}).get('enum')
        except (ValueError, OSError):
            enum = None
    if not enum:
        print('  SKIP  TIMER_UNITS vs schema enum (no cached schema, or no ETimerToken in it)')
    else:
        check('TIMER_UNITS matches the schema ETimerToken enum',
              sorted(enum) == sorted(f'timer_{u}' for u in fk.TIMER_UNITS), str(enum))

    # footer() — the pinned bottom bar. Before this existed, an author reaching for a bar that
    # stays put found only docked(), and the documented steer was AWAY from the native element;
    # the result was a "fake footer" (an empty fixed stack with a fill behind docked children)
    # that passed every local gate. Each guard below stands for one measured render.
    f = fk.footer([fk.text(fk.localized('CONTINUE'))], fill_=fk.fill('surface'))
    check('footer() emits type footer', f['type'] == 'footer', f['type'])
    check('footer() is relative, not positioned — the pinning is the element\'s own',
          f['props']['position']['type'] == 'relative', str(f['props']['position']))
    check('footer() carries the opaque fill it was given', 'fill' in f['props'])
    check('a footer with no fill raises (content would scroll through it)',
          raises(lambda: fk.footer([fk.text(fk.localized('X'))])))
    check('a positioned footer raises (that is the fake-footer shape)',
          raises(lambda: fk.footer([], fill_=fk.fill('surface'),
                                   position=fk.docked(bottom=24))))
    check('two footers on one screen raise (a second one draws zero pixels)',
          raises(lambda: fk.screen('scr_x', [fk.footer([], fill_=fk.fill('surface')),
                                             fk.footer([], fill_=fk.fill('surface'))])))
    check('a footer on a non-scrollable screen raises (device-confirmed: it does not render)',
          raises(lambda: fk.screen('scr_ns', [fk.footer([], fill_=fk.fill('surface'))],
                                   scrollable=False)))
    check('one footer per screen is fine',
          fk.screen('scr_y', [fk.stack([]), fk.footer([], fill_=fk.fill('surface'))])
            is not None)

    print()
    if FAILURES:
        print(f'{len(FAILURES)} failure(s): ' + ', '.join(FAILURES))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
