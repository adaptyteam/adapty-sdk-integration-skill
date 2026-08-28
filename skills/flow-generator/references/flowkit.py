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
    """A fill. v10 spells this as an ARRAY -- but pass ONE layer.

    A two-layer fill draws in `config preview` and is IGNORED on device (measured: an
    image+gradient screen fill shipped with the tint missing, after validate, the schema check
    and the render all passed). No real export has a multi-layer fill. Bake a tint into the
    asset instead, or give it its own element.
    """
    if layers is not None:
        return list(layers)
    c = color(color_id) if color_id is not None else hex_color(hexval)
    return [{'type': 'color', 'color': c}]


def gradient(angle, *stops):
    """`gradient(180, ('#E1D6EB', 0), ('#EDE9F0', 1))`, or with a per-stop alpha as a third
    item: `gradient(180, ('#0E9F6E', 0, 100), ('#0E9F6E', 1, 22))`.

    A fade whose last stop IS the page colour makes the element's tail invisible, so it renders
    shorter than it is — see trap 12. Stop one step short of the background, or better, fade
    ONE hex toward transparency with the opacity form: that survives a change of background,
    where a hardcoded near-background stop silently stops matching.
    """
    out = []
    for stop in stops:
        h, p, *alpha = stop
        out.append({'color': hex_color(h, alpha[0] if alpha else None), 'position': p})
    return [{'type': 'gradient', 'angle': angle, 'stops': out}]


def pad(top, left, right, bottom):
    return {'top': top, 'left': left, 'right': right, 'bottom': bottom}


def radius(value=None, *, tl=0, tr=0, bl=0, br=0):
    if value is not None:
        return {'tl': value, 'tr': value, 'bl': value, 'br': value}
    return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}


SPREAD_MODES = ('space-between', 'space-around', 'space-evenly')


def layout(direction='vertical', gap=0, align_h='start', align_v='start',
           distribution=None):
    """`distribution` is FOUR modes, not one.

    Default is the `gap` form. Pass `distribution='space-between'` (or
    `space-around` / `space-evenly`) to let the container spread its children over
    the free space instead — which is how a footer reaches the bottom of a screen
    without docking or padding arithmetic.

    A spread mode needs free space to distribute, so the container must have a
    definite height — on a screen that means `scrollable: False`. On a scrollable
    screen the root is content-height and a spread behaves like `gap: 0`.
    """
    if distribution is not None and distribution not in SPREAD_MODES:
        raise ValueError(
            f'distribution must be one of {SPREAD_MODES} or None for the gap form, '
            f'not {distribution!r}')
    dist = {'type': distribution} if distribution else {'gap': gap, 'type': 'gap'}
    return {'alignH': align_h, 'alignV': align_v, 'direction': direction,
            'distribution': dist}


SIZE_KINDS = ('fill', 'hug', 'fixed', 'auto')


def size(kind='fill', value=None):
    """`fill`, `hug`, `fixed` with a value, or `auto`.

    `fill` height collapses inside a hug-height parent (trap 13) — inside a hug row, a stretch
    has to be an explicit number, or the element has to leave the flow: see `absolute()`.

    `auto` is the stretch-between-anchors height, and it is meaningless without them. `stack()`
    enforces the pairing in both directions.
    """
    if kind not in SIZE_KINDS:
        raise ValueError(f'size kind must be one of {SIZE_KINDS}, not {kind!r}')
    return {'type': 'fixed', 'value': value} if kind == 'fixed' else {'type': kind}


def relative(z=None):
    p = {'type': 'relative'}
    if z is not None:
        p['zIndex'] = z
    return p


def absolute(*, top=None, left=None, right=None, bottom=None, z=None):
    """An element pulled out of flow, offset against its PARENT (`fixed` pins to the screen).

    Supply an offset for whichever axis the parent does not settle, or the element falls back
    into flow order and lands wherever the flow carries it (trap 9).

    Give it **both** `top` and `bottom` — with `height='auto'` — and it stretches between the
    anchors instead, following its parent's height however the content grows. A negative
    `bottom` overshoots past the parent's edge, which is how a timeline rail reaches into the
    next row. Measured, all three parts load-bearing: drop `bottom` and the element collapses to
    nothing; swap `auto` for `fill` and it stops 2px short; drop a negative `z` and it paints
    OVER its siblings rather than behind them.
    """
    p = {'type': 'absolute'}
    for k, v in (('top', top), ('left', left), ('right', right), ('bottom', bottom),
                 ('zIndex', z)):
        if v is not None:
            p[k] = v
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


def _check_stretch(props):
    """`height: auto` and a top+bottom anchor pair are one construct, so neither half is
    representable alone. Both halves were measured on a rendered timeline row: anchors without
    `auto` (a `fill` height) stopped 2px short of the next chip, and `auto` without the `bottom`
    anchor collapsed the rail to nothing and left 108px of white.
    """
    pos, h = props['position'], props['height']
    anchored = (pos.get('type') == 'absolute'
                and pos.get('top') is not None and pos.get('bottom') is not None)
    if anchored and h.get('type') != 'auto':
        raise ValueError(
            f"an absolute element anchored top AND bottom needs height='auto' to stretch "
            f"between them, not {h.get('type')!r} — a fill height stops 2px short")
    if h.get('type') == 'auto' and not anchored:
        raise ValueError(
            "height='auto' only means anything on an absolute element carrying BOTH a top and "
            "a bottom offset; on its own it collapses to nothing. Use absolute(top=…, bottom=…)")


def stack(children=(), *, width='fill', height='hug', fixed_w=None, fixed_h=None,
          direction='vertical', gap=0, align_h='start', align_v='start',
          distribution=None, fill_=None, padding=None, margin=None, corner=None,
          border=None, border_width=1, effects=None, position=None,
          visibility=None, **kw):
    props = {
        'width': size('fixed', fixed_w) if fixed_w is not None else size(width),
        'height': size('fixed', fixed_h) if fixed_h is not None else size(height),
        'layout': layout(direction, gap, align_h, align_v, distribution),
        'position': position or relative(),
    }
    _check_stretch(props)
    if fill_ is not None:     props['fill'] = fill_
    if padding is not None:   props['padding'] = padding
    if margin is not None:    props['margin'] = margin
    if corner is not None:    props['borderRadius'] = corner
    if border is not None:    props['border'] = {'color': color(border), 'style': 'solid',
                                                 'width': border_width}
    if effects is not None:   props['effects'] = effects
    if visibility is not None: props['visibility'] = visibility
    return _node('stack', props, children=list(children), **kw)


def footer(children=(), *, fill_=None, padding=None, gap=16, direction='vertical',
           align_h='center', align_v='end', height='hug', **kw):
    """The screen's pinned bottom bar. NOT a stack you position yourself.

    A `footer` is lifted out of the layout flow and pinned to the bottom of the viewport while
    the content scrolls past it. **It requires the screen to be `scrollable`** -- device-confirmed,
    with the scroll off it does not render at all, and the preview cannot show you that
    (`screen()` refuses the pair). Measured 2026-08-26, one variable at a time: the same props under
    `type: "stack"` put the bar below the fold; the pinned band is identical whether the screen is
    `scrollable` or not, and whether the footer is declared first or last.

    Three measured constraints are enforced here rather than left to the caller, because each one
    produced a real defect:

    * `fill_` is REQUIRED. The footer overlays the scrolling content, so without an opaque fill
      the content passes visibly behind the CTA — which is the symptom that gets misread as
      "docking is broken" and answered with an invented backing plate.
    * a `position` cannot be passed. Docking a footer is the fake-footer shape; the pinning is
      the element's own behaviour.
    * one per screen. A second `footer` drew ZERO pixels, so `screen()` refuses two.

    Take the geometry from the builder's own template rather than inventing it:
    `jq '.components[]|select(.id=="footer")|.template' component-catalog.json`.
    """
    if fill_ is None:
        raise ValueError(
            'footer(fill_=...) is required: a footer overlays the scrolling content, so without '
            'an opaque fill the content shows through the bar. Pass fill_=fill("surface") (or a '
            'hex). If you genuinely want content visible behind it, say so and use a stack.')
    if 'position' in kw:
        raise ValueError(
            'a footer is already pinned — do not give it a position. An empty fixed stack with a '
            'fill behind separately docked elements is the FAKE FOOTER this helper exists to '
            'replace; use footer(children=[...]) and put the CTA inside it.')
    node = stack(children, height=height, fill_=fill_, padding=padding, gap=gap,
                 direction=direction, align_h=align_h, align_v=align_v, **kw)
    node['type'] = 'footer'
    return node


def _is_dotlike(node):
    """The hand-built indicator dot: a tiny childless square `stack` with a corner radius.

    Deliberately the same predicate `verify-config.py` warns on, so the helper refuses at author
    time what the checker would flag afterwards.
    """
    if node.get('type') != 'stack' or node.get('_children'):
        return False
    pr = node.get('props') or {}
    w, h = pr.get('width') or {}, pr.get('height') or {}
    wv, hv = w.get('value'), h.get('value')
    return (w.get('type') == 'fixed' and h.get('type') == 'fixed'
            and wv == hv and isinstance(wv, (int, float)) and wv <= 12
            and bool(pr.get('borderRadius')))


def _dot_color(value, default):
    """A dot colour: a theme colour id, a literal '#hex', or an already-built colour dict.

    `IDots.color`/`activeColor` are `IColor`, which accepts a `color-style` reference — so the
    dots CAN follow the theme, and usually should. Measured: the real export's hardcoded white
    dots are invisible on a light screen, and the preview draws light mode only, so a hex dot
    that looks fine in the export is a dot nobody sees. Pass a theme colour id.
    """
    if value is None:
        return default
    if isinstance(value, dict):
        return value
    return hex_color(value) if value.startswith('#') else color(value)


def carousel(slides=(), *, slide_w, slide_h, height=None, gap=12, width='fill',
             dots=True, dot_size=6, dot_gap=6, dot_color=None, dot_active_color=None,
             fill_=None, padding=None, corner=None, position=None, visibility=None,
             node_id=None, **kw):
    """A swipeable `carousel`. Reviews, testimonials, sliders, swipeable cards, cards with dots.

    Reach for this whenever the design shows more than one card the user is meant to move
    between. The lookalike -- one static card plus a row of decorative dot `stack`s -- screenshots
    identically and ships **one frozen slide with dead dots**, the same class of defect as the
    fake footer and the fake spinner, and `config preview` cannot tell you apart because the
    preview never swipes. Before this helper existed there was nothing here to reach for, which is
    the mechanical reason the fake got built: an author reaches for what the helper exposes.

    **The dots are the element's own.** `props.dots` is schema-confirmed (`IDots`) and renders the
    indicator row for you -- never add dot children. All four of `color`, `activeColor`, `size`
    and `gap` are REQUIRED by `IDots`, so they are always emitted together; pass `dots=False` for
    the one-full-slide layout that shows none. `dot_color`/`dot_active_color` take a THEME COLOUR
    ID (preferred -- the dots then follow light/dark), a literal `'#hex'`, or a built colour; they
    default to the real export's white, which is invisible on a light screen.

    **Fixed geometry or nothing.** `slide_w`/`slide_h` are required numbers because a `hug` slide
    is dropped on device (support-channel, device-verified -- see `patterns.md`). `height`
    defaults to the slide height. The SDK supports exactly two layouts: adjacent-slide peek, or
    one full slide with neighbours invisible.

    Note there is no `layout` prop on a carousel (schema-confirmed: `ICarouselElementProps` has
    none) -- `gap` is the whole spacing story, and the slides are its `children`, one per slide.
    """
    slides = list(slides)
    if len(slides) < 2:
        raise ValueError(
            f'carousel() needs at least 2 slides, got {len(slides)}. A single slide is the FROZEN '
            'SLIDE this helper exists to replace — it renders in the preview and never moves. If '
            'you genuinely want one static card, use stack() and do not draw dots under it.')
    dotty = sorted(s['id'] for s in slides if _is_dotlike(s))
    if dotty:
        raise ValueError(
            f'carousel() was passed {len(dotty)} dot-like stack(s) as slides ({", ".join(dotty)}). '
            'The indicator dots are the element\'s own — they come from props.dots. Pass one '
            'stack per SLIDE (the card itself) and let the carousel draw the dots.')
    props = {
        'gap': gap,
        'width': size(width),
        'height': size('fixed', slide_h if height is None else height),
        'slideWidth': size('fixed', slide_w),
        'slideHeight': size('fixed', slide_h),
    }
    if dots:
        props['dots'] = {
            'gap': dot_gap, 'size': dot_size,
            'color': _dot_color(dot_color, hex_color('#FFFFFF', 30)),
            'activeColor': _dot_color(dot_active_color, hex_color('#FFFFFF', 95))}
    if fill_ is not None:      props['fill'] = fill_
    if padding is not None:    props['padding'] = padding
    if corner is not None:     props['borderRadius'] = corner
    if position is not None:   props['position'] = position
    if visibility is not None: props['visibility'] = visibility
    return _node('carousel', props, children=slides, node_id=node_id, **kw)

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


#: The deliberate "no asset exists" content for `image()`. Spelled as a constant so an empty
#: values map is something you *asked* for and a reader can grep, never something you forgot.
PLACEHOLDER = object()

OBJECT_FIT = ('cover', 'fit')


def image(url, *, media_id=None, fit='cover', width='fill', height='hug',
          fixed_w=None, fixed_h=None, corner=None, margin=None, position=None,
          locale='en', **kw):
    """An `image` element bound to an uploaded asset.

    `url` is the CDN URL that `flows media upload` printed, and `media_id` the id it printed
    alongside — passed through `str()`, because the command prints a number while the schema
    declares `IImage.id` as a string. Pass `flowkit.PLACEHOLDER` as the url for the no-asset
    case; anything else falsy is an error rather than a silent empty map.

    Geometry, measured (media.md): with `height='hug'` the drawn height comes from the ASSET's
    aspect ratio, so the screen re-flows if the file is swapped and `fit` has no visible effect.
    With a fixed height the box wins and the asset absorbs the mismatch — `cover` crops it,
    `fit` letterboxes it and leaves a dead band.
    """
    if fit not in OBJECT_FIT:
        raise ValueError(f'objectFit must be one of {OBJECT_FIT}, not {fit!r}')
    if url is PLACEHOLDER:
        content = {'values': {}, '_localizable': True}
    elif isinstance(url, str) and url.strip():
        entry = {'url': url}
        if media_id is not None:
            entry['id'] = str(media_id)
        content = {'values': {locale: entry}, '_localizable': True}
    else:
        raise TypeError(
            'image(url=...) wants the URL that `flows media upload` printed, or '
            'flowkit.PLACEHOLDER for an image no file exists for — never an invented URL, and '
            f'never {url!r}')
    props = {
        'image': content,
        'width': size('fixed', fixed_w) if fixed_w is not None else size(width),
        'height': size('fixed', fixed_h) if fixed_h is not None else size(height),
        'objectFit': fit,
        'position': position or relative(),
    }
    if corner is not None:  props['borderRadius'] = corner
    if margin is not None:  props['margin'] = margin
    return _node('image', props, **kw)


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


# --- timer -------------------------------------------------------------------------------
# A countdown's digits are `token` nodes, and the token ids carry a `timer_` PREFIX:
# `timer_days`, `timer_hours`, `timer_minutes`, `timer_seconds`. Builder- and device-confirmed
# 2026-08-25 (the builder shows a recognised chip and renders live `23:59:59`). The bare names
# `days`/`hours`/`minutes`/`seconds` do NOT resolve: the Flow Builder paints them red `Unknown`
# and the device/preview renders the literal `%hours%`. `config validate` accepts either, so the
# wrong one is silent — which is exactly why this is a helper and not something you hand-author.
# `component-catalog.json`'s timer templates carried the bare names until 2026-08-25; if you lift
# a timer shape from anywhere, run it through here or fix the prefix by hand.

TIMER_UNITS = ('days', 'hours', 'minutes', 'seconds')


def timer_digits(units=('hours', 'minutes', 'seconds'), *, sep=':', preset='h2',
                 color_id=None, align='center', width='hug', locale='en', node_id=None, **kw):
    """The digit `text` that goes INSIDE a `timer` element, as `HH:MM:SS`.

    `units` is any ordered subset of `TIMER_UNITS`; each becomes a `timer_<unit>` token, joined by
    `sep`. Never write the bare token name — see the note above.
    """
    bad = [u for u in units if u not in TIMER_UNITS]
    if bad:
        raise ValueError(f'timer units must be a subset of {TIMER_UNITS}, not {bad}')
    content = []
    for i, u in enumerate(units):
        if i:
            content.append({'type': 'text', 'text': sep,
                            'attrs': {'bold': False, 'italic': False,
                                      'underline': False, 'strikethrough': False}})
        content.append({'type': 'token', 'attrs': {'token': f'timer_{u}'}})
    value = {'values': {locale: [{'type': 'paragraph', 'content': content}]},
             '_localizable': True}
    return text(value, preset=preset, color_id=color_id, align=align, width=width,
                node_id=node_id, **kw)


def timer(children=(), *, custom_id='offer', days=0, hours=0, minutes=0, seconds=0,
          behavior='start_at_every_appear', width='hug', height='hug', fixed_w=None,
          fixed_h=None, fill_=None, padding=None, corner=None, align_h='center',
          align_v='center', visibility=None, position=None, actions=None, node_id=None,
          **kw):
    """A countdown `timer` element. Pass `timer_digits(...)` as one of its `children` to show the
    running digits; a bare timer with no digit child draws nothing (which is the correct shape for
    a purely invisible delay — pair it with `actions` carrying a `timer-end` navigate).

    `duration` is `{days, hours, minutes, seconds}`. `behavior='start_at_every_appear'` restarts
    the countdown each time the screen appears.
    """
    props = {
        'customId': custom_id, 'behavior': behavior,
        'duration': {'days': days, 'hours': hours, 'minutes': minutes, 'seconds': seconds},
        'width': size('fixed', fixed_w) if fixed_w is not None else size(width),
        'height': size('fixed', fixed_h) if fixed_h is not None else size(height),
        'layout': layout('horizontal', 0, align_h, align_v),
        'position': position or relative(),
    }
    if fill_ is not None:     props['fill'] = fill_
    if padding is not None:   props['padding'] = padding
    if corner is not None:    props['borderRadius'] = corner
    if visibility is not None: props['visibility'] = visibility
    node = _node('timer', props, children=list(children), node_id=node_id, **kw)
    if actions:
        # a timer's own interaction fires on `timer-end`, not `tap`
        node['interactions'] = [{'id': 'int' + node['id'][2:], 'trigger': 'timer-end',
                                 'actions': actions}]
    return node


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
           distribution=None, scrollable=True, status_bar=False,
           status_bar_theme='light', safe_area=False, selectable_groups=(),
           progress_bar=False):
    """A bar that must stay put while content scrolls past it is `footer()`, not a
    distribution — the pinning is that element's own behaviour.

    `distribution='space-between'` with `scrollable=False` is the different job: a SHORT
    screen whose content should spread to fill the height, with the bar as the second of two
    children. It does not pin anything, and `scrollable=False` clips content taller than the
    viewport. See `layout()` for why a spread needs it anyway."""
    node_map, hierarchy = flatten(list(nodes))
    feet = [k for k, v in node_map.items() if v.get('type') == 'footer']
    if feet and not scrollable:
        raise ValueError(
            f'screen {screen_id!r} pairs a footer ({feet[0]}) with scrollable=False. '
            'DEVICE-CONFIRMED: with the scroll off the footer does not render at all, and every '
            'child goes with it -- a CTA in the footer takes the screen\'s navigation with it. '
            'The preview draws it in both modes, so no local check can see this. Either '
            'scrollable=True, or drop the footer and put the bar at the bottom with '
            "distribution='space-between'.")
    if len(feet) > 1:
        raise ValueError(
            f'{len(feet)} footer elements on screen {screen_id!r} ({", ".join(sorted(feet))}) — '
            'measured, a second footer draws ZERO pixels. Put the CTA and the legal row inside '
            'ONE footer as children.')
    props = {
        'layout': layout(direction, gap, align_h, align_v, distribution),
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


def _typo(entry):
    """`(id, name, size, weight)`, optionally extended with `lineHeight` and `letterSpacing`.

    Both extras are plain numbers inside `settings`, verified against a real export that carries
    them on 6 of its 7 presets. Leading is a design lever, not a nicety: at the default the
    renderer gives a 30pt heading noticeably loose line spacing, and there is nowhere else to
    set it — a `text` element cannot override what the preset does not carry.
    """
    i, n, s, w, *rest = entry
    settings = {'size': s, 'weight': w}
    if len(rest) > 0 and rest[0] is not None:
        settings['lineHeight'] = rest[0]
    if len(rest) > 1 and rest[1] is not None:
        settings['letterSpacing'] = rest[1]
    return {'id': i, 'name': n, 'settings': settings}


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
    declared = [c for c, _ in locales]
    written = set()

    def _codes(o):
        if isinstance(o, dict):
            if o.get('_localizable') and isinstance(o.get('values'), dict):
                written.update(o['values'])
            for v in o.values():
                _codes(v)
        elif isinstance(o, list):
            for v in o:
                _codes(v)

    _codes(list(screens))
    _codes(components if components is not None else {})
    stray = sorted(written - set(declared))
    if stray:
        raise ValueError(
            f'locale value(s) written for {", ".join(stray)} but only {declared} declared. '
            'A value under an undeclared code renders nowhere. You wrote it, so declare it: '
            'pass locales=(("en", "English"), ("ru", "Russian"), …) — do not ship it as a '
            'warning for someone else to clear up.')

    return {
        'schemaVersion': SCHEMA_VERSION,
        'locales': [{'id': c, 'code': c, 'name': n} for c, n in locales],
        'defaultLocale': default_locale,
        'variables': list(variables),
        'components': components if components is not None else {},
        'theme': {
            'colors': [{'id': i, 'name': n, 'light': {'hex': lt}, 'dark': {'hex': dk}}
                       for i, n, lt, dk in colors],
            'typography': [_typo(t) for t in typography],
        },
        '_meta': {'icons': list(icons), 'fonts': [],
                  'screens': dict(meta_screens) if meta_screens else {}},
        'screens': list(screens),
    }
