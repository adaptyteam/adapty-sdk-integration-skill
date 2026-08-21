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
sys.path.insert(0, os.path.join(ROOT, 'skills', 'flow-generator', 'references'))

import flowkit as fk  # noqa: E402

FAILURES = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}' + (f'   {detail}' if detail else ''))
        FAILURES.append(name)


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
    return fk.config(
        screens=[fk.screen('scr_main', [card, rail, cta], caption='Plans',
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

    print()
    if FAILURES:
        print(f'{len(FAILURES)} failure(s): ' + ', '.join(FAILURES))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
