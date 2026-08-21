"""flowkit — the mechanical half of authoring an Adapty flow config.

Scope is deliberately narrow. This owns the parts that are *error-prone but not creative*:

  * the `hierarchy` / `map` split — every node declared twice, in two structures that must
    agree exactly; an id in one and not the other is a broken config. `flatten()` makes that
    unrepresentable, and it is the reason this module exists. No JSON skeleton can help here.
  * the envelope, at the current `schemaVersion` with **array** fills (v10). Authoring is the
    one case with no input form to preserve, so it uses the current one.
  * one canonical rich-text builder, with the span kinds named instead of guessed.

Not in scope: anything with a design opinion. Element shapes, card recipes, spacing — those are
`patterns.md`, and they are judgement, not shape. This module will happily build an ugly screen.

Trust order is unchanged: the live `validate` outranks a schema check, which outranks this file.
Run `tests/test-flowkit.py` after touching it.

    import flowkit as fk

    body = fk.stack([
        fk.text(fk.rich("Save "), preset="h1", color="ink"),
        fk.text(fk.rich("from ", fk.Var("<uuid>.prod_price")), preset="body", color="muted"),
    ], gap=8, padding=fk.pad(16, 16, 16, 16))

    cfg = fk.config(
        screens=[fk.screen("scr_main", [body], fill="bg", padding=fk.pad(0, 0, 0, 120))],
        colors=[("bg", "Background", "#FFFFFF", "#101014"),
                ("ink", "Ink", "#111114", "#F5F5F7")],
        typography=[("h1", "H1", 28, "bold"), ("body", "Body", 16, "regular")],
    )
"""
import uuid

SCHEMA_VERSION = 10          # authoring uses the current version; a FETCHED flow keeps its own

# --- ids ---------------------------------------------------------------------------------

class Ids:
    """Sequential element ids. One instance per document, so ids are stable across a rebuild."""

    def __init__(self, prefix='el'):
        self.prefix, self.n = prefix, 0

    def __call__(self, kind='S'):
        self.n += 1
        return f'{self.prefix}_{self.n:03d}{kind}'


_ids = Ids()


def eid(kind='S'):
    """Mint an id from the module-level counter. Use your own `Ids()` for several documents."""
    return _ids(kind)


# --- primitives --------------------------------------------------------------------------

def color(color_id):
    """A reference to a theme colour by id."""
    return {'type': 'color-style', 'colorId': color_id}


def hex_color(hexval, opacity=None):
    """A literal colour. `opacity` is a 0-100 PERCENTAGE, not a fraction (trap 11)."""
    out = {'type': 'hex', 'hex': hexval}
    if opacity is not None:
        out['opacity'] = opacity
    return out


def fill(color_id=None, *, hexval=None, layers=None):
    """A fill. v10 spells this as an ARRAY of layers composited bottom -> top."""
    if layers is not None:
        return list(layers)
    c = color(color_id) if color_id is not None else hex_color(hexval)
    return [{'type': 'color', 'color': c}]


def gradient(angle, *stops):
    """`gradient(180, ('#E1D6EB', 0), ('#EDE9F0', 1))`.

    A fade whose last stop IS the page colour makes the element's tail invisible, so it renders
    shorter than it is — see trap 12. Stop one step short of the background.
    """
    return [{'type': 'gradient', 'angle': angle,
             'stops': [{'color': hex_color(h), 'position': p} for h, p in stops]}]


def pad(top, left, right, bottom):
    return {'top': top, 'left': left, 'right': right, 'bottom': bottom}


def radius(value=None, *, tl=0, tr=0, bl=0, br=0):
    if value is not None:
        return {'tl': value, 'tr': value, 'bl': value, 'br': value}
    return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}


def layout(direction='vertical', gap=0, align_h='start', align_v='start'):
    return {'alignH': align_h, 'alignV': align_v, 'direction': direction,
            'distribution': {'gap': gap, 'type': 'gap'}}


def size(kind='fill', value=None):
    """`fill`, `hug`, or `fixed` with a value.

    `fill` height collapses inside a hug-height parent (trap 13) — inside a hug row, a stretch
    has to be an explicit number.
    """
    return {'type': 'fixed', 'value': value} if kind == 'fixed' else {'type': kind}


def relative(z=None):
    p = {'type': 'relative'}
    if z is not None:
        p['zIndex'] = z
    return p


def docked(*, bottom, left=None, right=None, top=None, z=None):
    """A `fixed` element, pinned to the screen rather than the flow.

    Each docked item must be its OWN fixed element with its own action — a fixed container
    holding relative children swallows the taps. And never set both `left` and `right` on one
    of a side-by-side pair, or it stretches full width and they overlap (patterns.md).
    """
    p = {'type': 'fixed', 'bottom': bottom}
    for k, v in (('left', left), ('right', right), ('top', top), ('zIndex', z)):
        if v is not None:
            p[k] = v
    return p


def hidden():
    """Hiding COLLAPSES the space rather than reserving it (trap 14). If two state-varying
    siblings must stay the same size, wrap this in a fixed-height parent."""
    return {'type': 'hidden'}


def visible():
    return {'type': 'visible'}


# --- rich text ---------------------------------------------------------------------------
# Three build scripts once had three `runs()` helpers agreeing on the name and disagreeing on
# what a tuple meant: one read ('var', id) as a VARIABLE node, one read (text, colorId) as a
# coloured span, one crashed. Copying a call between them silently produced the wrong node and
# still published. So the span kinds are named types here, and a bare tuple is rejected.

class Var:
    """A variable span: renders the variable's value, or its literal token if unresolved."""

    __slots__ = ('variable_id',)

    def __init__(self, variable_id):
        self.variable_id = variable_id


class Span:
    """A styled text span. `color` is a theme colour id."""

    __slots__ = ('text', 'bold', 'italic', 'underline', 'strikethrough', 'color')

    def __init__(self, text, *, bold=False, italic=False, underline=False,
                 strikethrough=False, color=None):
        self.text, self.bold, self.italic = text, bold, italic
        self.underline, self.strikethrough, self.color = underline, strikethrough, color


def _span(part):
    if isinstance(part, str):
        part = Span(part)
    if isinstance(part, Var):
        return {'type': 'variable', 'attrs': {'variableId': part.variable_id}}
    if isinstance(part, Span):
        attrs = {'bold': part.bold, 'italic': part.italic,
                 'underline': part.underline, 'strikethrough': part.strikethrough}
        if part.color is not None:
            attrs['color'] = color(part.color)
        return {'text': part.text, 'type': 'text', 'attrs': attrs}
    raise TypeError(
        f'rich() takes str, Span or Var, not {type(part).__name__}. A bare tuple is rejected '
        'on purpose — say Span(text, color=...) or Var(id) so the span kind is explicit.')


def rich(*parts, locale='en'):
    """Localizable rich text: `rich("Save ", Span("40%", bold=True), " on ", Var(vid))`.

    Localizable props are keyed by locale code and hold an array of blocks. Note `_localizable`
    does NOT imply this shape everywhere — a placeholder takes a plain string (trap 1b).
    """
    return {'values': {locale: [{'type': 'paragraph',
                                 'content': [_span(p) for p in parts]}]},
            '_localizable': True}


def localized(value, locale='en'):
    """A localizable prop whose value is a plain scalar rather than rich text (trap 1b)."""
    return {'values': {locale: value}, '_localizable': True}


# --- nodes -------------------------------------------------------------------------------

def _node(kind, props, *, children=None, caption=None, states=None,
          props_by_state=None, actions=None, node_id=None):
    node = {'id': node_id or eid('S' if kind == 'stack' else kind[:1].upper()),
            'type': kind, 'props': props, 'states': states or []}
    if caption:
        node['caption'] = caption
    if props_by_state:
        node['propsByState'] = props_by_state
    if actions:
        node['interactions'] = [{'id': 'int' + node['id'][2:], 'trigger': 'tap',
                                 'actions': actions}]
    node['_children'] = children or []
    return node


def stack(children=(), *, width='fill', height='hug', fixed_w=None, fixed_h=None,
          direction='vertical', gap=0, align_h='start', align_v='start',
          fill_=None, padding=None, margin=None, corner=None, border=None,
          border_width=1, effects=None, position=None, visibility=None, **kw):
    props = {
        'width': size('fixed', fixed_w) if fixed_w is not None else size(width),
        'height': size('fixed', fixed_h) if fixed_h is not None else size(height),
        'layout': layout(direction, gap, align_h, align_v),
        'position': position or relative(),
    }
    if fill_ is not None:     props['fill'] = fill_
    if padding is not None:   props['padding'] = padding
    if margin is not None:    props['margin'] = margin
    if corner is not None:    props['borderRadius'] = corner
    if border is not None:    props['border'] = {'color': color(border), 'style': 'solid',
                                                 'width': border_width}
    if effects is not None:   props['effects'] = effects
    if visibility is not None: props['visibility'] = visibility
    return _node('stack', props, children=list(children), **kw)


def text(content, *, preset='body', color_id=None, align='left', width='fill',
         margin=None, position=None, **kw):
    props = {'font': {'preset': preset}, 'align': align,
             'width': size(width), 'height': size('hug'), 'layout': 'auto-height',
             'content': content, 'position': position or relative(), 'decoration': 'none'}
    if color_id is not None:
        props['color'] = color(color_id)
    if margin is not None:
        props['margin'] = margin
    return _node('text', props, **kw)


def icon(name, *, size_pt=22, color_id=None, weight='regular', position=None, **kw):
    props = {'icon': {'name': name, 'size': size_pt, 'type': 'phosphor', 'weight': weight},
             'position': position or relative()}
    if color_id is not None:
        props['icon']['color'] = color(color_id)
    return _node('icon', props, **kw)


def product(children=(), *, product_id, group_id, default=False, **kw):
    """A selectable plan card — the member type for a `product` group. For any other group
    type (`single_choice`, `multi_choice`, `toggle`) use `selectable()` instead.

    The `selectableGroups` entry on the screen must use `group_id`.

    A price variable resolves only against a screen's DECLARED products, and only the builder
    writes that declaration — so bind the product here and put the price in the copy.
    """
    node = stack(children, **kw)
    node['type'] = 'product'
    node['props'].update({'groupId': group_id, 'default': default,
                          'product': {'id': product_id}})
    if not node['states']:
        node['states'] = [{'id': 'selected', 'type': 'system'}]
    return node


GROUP_MEMBER_TYPES = ('product', 'selectable', 'tab-item')


def selectable(children=(), *, group_id, default=False, custom_id=None, **kw):
    """A member of a NON-product selectable group: `single_choice`, `multi_choice`, `toggle`.

    The element type matters and a stack will not do. `IStackElementProps` has no `groupId` and
    no `default`, so a stack carrying them is not a group member -- the props are ignored, it
    never receives the `selected` state, and **tapping it does nothing**. Verified against real
    exports: members are `product` for a product group, `selectable` for single/multi/toggle,
    `tab-item` inside tabs. Nothing else.

    `custom_id` is the handle the choice is reported under (a real quiz uses "rock", "hiphop").
    """
    node = stack(children, **kw)
    node['type'] = 'selectable'
    node['props'].update({'groupId': group_id, 'default': default})
    if custom_id is not None:
        node['props']['customId'] = custom_id
    if not node['states']:
        node['states'] = [{'id': 'selected', 'type': 'system'}]
    return node


def purchase(group_id, action_id='act_buy'):
    """Buy the group's selection, never a hardcoded product."""
    return {'id': action_id, 'type': 'purchase',
            'payload': {'product': {'type': 'var',
                                    'variableId': f'{group_id}.selectedProduct'}}}


def navigate(screen_id, action_id='act_nav'):
    """Payload shape verified against two real exports: `{"type": "screen", "screen": "<id>"}`.

    NOT `{"screenId": …}`, which is the obvious guess and what this helper shipped with for one
    commit. The config API accepts either without complaint, so the wrong one is silent.
    """
    return {'id': action_id, 'type': 'navigate',
            'payload': {'type': 'screen', 'screen': screen_id}}


def close(action_id='act_close'):
    return {'id': action_id, 'type': 'closeFlow'}


# --- assembly ----------------------------------------------------------------------------

def flatten(nodes):
    """Split a nested tree into the (`map`, `hierarchy`) pair the format requires.

    This is the whole point of the module. Every element is declared in `map` keyed by id and
    again in `hierarchy` as nesting; the two must agree exactly. Building both by hand is where
    a broken config comes from.
    """
    node_map, roots = {}, []

    def walk(node):
        kids = node.pop('_children', [])
        if node['id'] in node_map:
            raise ValueError(f'duplicate element id {node["id"]} — use one Ids() per document')
        node_map[node['id']] = node
        out = {'id': node['id']}
        children = [walk(k) for k in kids]
        if children:
            out['children'] = children
        return out

    for n in nodes:
        roots.append(walk(n))
    return node_map, {'id': 'root', 'children': roots}


def screen(screen_id, nodes, *, caption=None, fill_=None, padding=None,
           direction='vertical', gap=0, align_h='start', align_v='start',
           scrollable=True, status_bar=False, status_bar_theme='light',
           safe_area=False, selectable_groups=(), progress_bar=False):
    node_map, hierarchy = flatten(list(nodes))
    props = {
        'layout': layout(direction, gap, align_h, align_v),
        'safeArea': safe_area, 'statusBar': status_bar, 'scrollable': scrollable,
        'progressBar': {'enabled': progress_bar}, 'statusBarTheme': status_bar_theme,
    }
    if fill_ is not None:
        props['fill'] = fill_
    if padding is not None:
        props['padding'] = padding
    out = {'id': screen_id, 'props': props,
           'elements': {'map': node_map, 'hierarchy': hierarchy},
           'selectableGroups': [dict(g) for g in selectable_groups]}
    if caption:
        out['caption'] = caption
    return out


PREDECLARE_NS = uuid.UUID('1b671a64-40d5-491e-99b0-da01ff1f3341')


def predeclare(screen_id, product_ids):
    """A provisional `_meta.screens` declaration, so a NEW flow previews on a device
    immediately instead of only after the builder has saved it.

    Why this exists: the transform service (which device preview and publish run, and
    `config update` does not) rejects a bound product with no declaration --
    `missing_flow_product_id` -- and every price variable pointing at it with
    `unknown_product_id`. Without a declaration the first successful device preview comes only
    after someone opens the flow in the builder and saves it. "Publish it to preview it" is not
    a workflow you can hand a user.

    The `flowProductId` values here are FABRICATED, and deliberately so. The real derivation is
    server-side -- 19,776 namespace/name/version combinations over 4 triples with full
    provenance (app, flow, screen, element, product) produce no match. Measured: the service
    checks that a declaration is present and internally consistent, not that the value is the
    builder's own, so a draft carrying these previews on a real device with no publish and no
    builder visit.

    Two limits, both important:

      * When REWRITING a flow, never call this -- carry the live `_meta.screens` forward
        instead. Overwriting a real declaration with a provisional one is a regression.
      * `flowProductId` is a server-side handle whose other uses are unknown to this project.
        Treat a provisional value as good for previewing, and expect the builder to replace it
        on its next save.
    """
    return {screen_id: {'products': [
        {'id': pid, 'flowProductId': str(uuid.uuid5(PREDECLARE_NS, f'{screen_id}:{pid}'))}
        for pid in product_ids]}}


def config(*, screens, colors=(), typography=(), icons=(), locales=(('en', 'English'),),
           default_locale='en', variables=(), components=None, meta_screens=None):
    """The document.

    `_meta.screens` defaults to EMPTY, which is correct when rewriting a flow -- it is
    builder-owned bookkeeping and you should merge the live value in rather than inventing one.
    For a NEW flow, pass `meta_screens=predeclare(screen_id, [product_ids])` so it previews on a
    device without being published first.
    """
    return {
        'schemaVersion': SCHEMA_VERSION,
        'locales': [{'id': c, 'code': c, 'name': n} for c, n in locales],
        'defaultLocale': default_locale,
        'variables': list(variables),
        'components': components if components is not None else {},
        'theme': {
            'colors': [{'id': i, 'name': n, 'light': {'hex': lt}, 'dark': {'hex': dk}}
                       for i, n, lt, dk in colors],
            'typography': [{'id': i, 'name': n, 'settings': {'size': s, 'weight': w}}
                           for i, n, s, w in typography],
        },
        '_meta': {'icons': list(icons), 'fonts': [],
                  'screens': dict(meta_screens) if meta_screens else {}},
        'screens': list(screens),
    }
