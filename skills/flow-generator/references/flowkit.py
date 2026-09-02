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
import re
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


# A THEME colour must be exactly `#RRGGBB`. Measured against the transform service
# 2026-08-28: in `theme.colors[].light/dark`, a 3-digit (`#fff`), 8-digit (`#RRGGBBAA`),
# 7-digit, unprefixed (`FFFFFF`) or EMPTY hex is refused — and refused with the
# location-free `Generated JSON failed schema validation`, because `IColorHex` is typed as
# a bare string with no pattern, so neither the schema check nor `config preview` (which
# draws light mode only) can see it. The cheapest possible defect to introduce and one of
# the most expensive to diagnose.
#
# The constraint is POSITION-SCOPED and this is not a detail: in an ELEMENT position
# (`props.fill.color`, `props.color`) the same service accepts a 3-digit hex, an 8-digit
# one and an empty string — real exports carry 8 eight-digit and 16 empty values there and
# validate clean. So this is checked for theme colours only; a blanket rule would reject
# documents the builder itself produces.
THEME_HEX = re.compile(r'#[0-9A-Fa-f]{6}\Z')


def check_theme_hex(value, where):
    if not (isinstance(value, str) and THEME_HEX.match(value)):
        raise ValueError(
            f'{where}: theme colour {value!r} must be exactly #RRGGBB (6 hex digits). The '
            f'transform service refuses anything else here — including #RGB, #RRGGBBAA and an '
            f'empty string — with the location-free "Generated JSON failed schema validation", '
            f'which names no field. Element colours are laxer; theme colours are not.')
    return value


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


# --- conditions --------------------------------------------------------------------------
# A condition is a JSON expression tree, and the transform service validates it with ONE
# walker (`findInvalidExpressionPath`) shared by `props.visibility.condition` and
# `states[].condition` — which is why the two codes it raises, `invalid_visibility_condition`
# and `invalid_state_condition`, are one construct here. Between them they were the 3rd most
# common transformer refusal in production over the 40 days to 2026-08-28 (362 failed
# requests), and before this section flowkit had NO way to express a condition at all: an
# author needing one hand-wrote the tree. Finding 12 again — a missing helper is a missing
# capability, and the hand-written version is what the service rejects.

# The published schema's ExpressionType enum, verbatim
# (schemastore.adaptybuilder.com/latest.json -> definitions.ExpressionType).
EXPR_TYPES = ('const', 'switch', '&&', '||', '==', '!=', 'has', 'notHas', 'empty',
              'notEmpty', 'in', 'notIn', '>', '<', 'size', 'var', 'assign', 'concat')

# ...and the one member the condition walker has NO case for, so it falls through to
# `default: return `${path}.type`` and the flow is refused. `assign` is schema-legal and is
# genuinely legal inside a `setVariable` payload — it is illegal only as a CONDITION, which
# is why this set is applied here and never to expressions generally. The same class as
# `IColorHex` being typed a bare string: an enum the schema declares and a consumer does not
# honour, so neither the schema check nor `config preview` objects. 0 of 7 tracked fixtures
# use it anywhere.
COND_ILLEGAL_TYPES = ('assign',)

_BINARY = ('==', '!=', '>', '<', 'has', 'notHas', 'in', 'notIn')
_UNARY = ('empty', 'notEmpty', 'size')


def _as_expr(v, what):
    """Bare Python values become `const` nodes; a dict must already be a valid expression.

    Auto-wrapping is deliberate: `eq(ref('plan'), 'gold')` is the natural way to write it, and
    the un-wrapped string is exactly what the walker rejects (`isExpression` wants an object
    with a string `type`). Wrapping here makes that mistake unrepresentable rather than
    merely detectable.
    """
    if isinstance(v, dict):
        _check_expr(v, what)
        return v
    if isinstance(v, (list, tuple)):
        raise TypeError(f'{what}: a list is not an expression — use lit([...]) if you mean a '
                        f'constant list, or in_(...) if you mean membership')
    return lit(v)


def _check_expr(e, what='condition'):
    """Raise unless `e` is a tree the transform service's walker accepts.

    A faithful port of `findInvalidExpressionPath`, including the three places where an
    ABSENT collection is legal (`&&`/`||` predicates, `concat` operands, `switch` cases) —
    inventing a stricter rule here would refuse documents the service accepts.
    """
    bad = _bad_expr_path(e, what)
    if bad:
        raise ValueError(
            f'invalid condition expression at {bad} — the transform service refuses this with '
            f'invalid_visibility_condition / invalid_state_condition (a hard 422). Legal types '
            f'are {", ".join(t for t in EXPR_TYPES if t not in COND_ILLEGAL_TYPES)}; build the '
            f'tree with ref/lit/eq/neq/all_/any_/not_empty rather than by hand.')


def _bad_expr_path(v, path):
    """Return the path of the first invalid node, or None. Port of the service's own walker."""
    if not (isinstance(v, dict) and isinstance(v.get('type'), str)):
        return path
    t = v['type']
    if t in COND_ILLEGAL_TYPES:
        return f'{path}.type ({t!r} is schema-legal but has no case in the condition walker)'
    if t == 'const':
        return None
    if t == 'var':
        vid = v.get('variableId')
        return None if isinstance(vid, str) and vid else f'{path}.variableId'
    if t in _BINARY:
        return (_bad_expr_path(v.get('left'), f'{path}.left')
                or _bad_expr_path(v.get('right'), f'{path}.right'))
    if t in _UNARY:
        return _bad_expr_path(v.get('left'), f'{path}.left')
    if t in ('&&', '||'):
        if 'predicates' not in v:
            return None
        ps = v['predicates']
        if not isinstance(ps, list):
            return f'{path}.predicates'
        for i, p in enumerate(ps):
            r = _bad_expr_path(p, f'{path}.predicates[{i}]')
            if r:
                return r
        return None
    if t == 'concat':
        if 'operands' not in v:
            return None
        ops = v['operands']
        if not isinstance(ops, list):
            return f'{path}.operands'
        for i, o in enumerate(ops):
            r = _bad_expr_path(o, f'{path}.operands[{i}]')
            if r:
                return r
        return None
    if t == 'switch':
        if 'cases' not in v:
            return None
        cs = v['cases']
        if not isinstance(cs, list):
            return f'{path}.cases'
        for i, c in enumerate(cs):
            if not (isinstance(c, list) and len(c) == 2):
                return f'{path}.cases[{i}]'
            r = (_bad_expr_path(c[0], f'{path}.cases[{i}][0]')
                 or _bad_expr_path(c[1], f'{path}.cases[{i}][1]'))
            if r:
                return r
        if 'default' in v:
            return _bad_expr_path(v['default'], f'{path}.default')
        return None
    return f'{path}.type'


def ref(variable_id):
    """A variable operand: `{"type": "var", "variableId": …}`.

    Deliberately NOT named `var`, because `Var` is the rich-text span and the two are
    different nodes — this module already carries one scar from helpers whose names agreed
    and whose meanings did not.

    The id is the same vocabulary the rest of the document uses: `<inputCustomId>.value`,
    `<groupId>.selectedOptionId`, `<groupId>.selectedProduct`, a `variables[]` id. An id
    naming nothing is emitted into the generated script as a bare identifier and fails type
    checking there (`script_type_violation`, TS2304), so `config()` resolves every condition
    variable against the document it is building.
    """
    if not (isinstance(variable_id, str) and variable_id):
        raise ValueError(f'ref() needs a non-empty variable id, got {variable_id!r}')
    return {'type': 'var', 'variableId': variable_id}


def lit(value):
    """A constant operand: `{"type": "const", "value": …}`."""
    return {'type': 'const', 'value': value}


def eq(left, right, *, loose=None):
    node = {'type': '==', 'left': _as_expr(left, 'eq() left'),
            'right': _as_expr(right, 'eq() right')}
    if loose is not None:
        node['loose'] = loose
    return node


def neq(left, right):
    return {'type': '!=', 'left': _as_expr(left, 'neq() left'),
            'right': _as_expr(right, 'neq() right')}


def gt(left, right):
    return {'type': '>', 'left': _as_expr(left, 'gt() left'),
            'right': _as_expr(right, 'gt() right')}


def lt(left, right):
    return {'type': '<', 'left': _as_expr(left, 'lt() left'),
            'right': _as_expr(right, 'lt() right')}


def has(left, right):
    return {'type': 'has', 'left': _as_expr(left, 'has() left'),
            'right': _as_expr(right, 'has() right')}


def has_not(left, right):
    return {'type': 'notHas', 'left': _as_expr(left, 'has_not() left'),
            'right': _as_expr(right, 'has_not() right')}


def in_(left, right):
    return {'type': 'in', 'left': _as_expr(left, 'in_() left'),
            'right': _as_expr(right, 'in_() right')}


def not_in(left, right):
    return {'type': 'notIn', 'left': _as_expr(left, 'not_in() left'),
            'right': _as_expr(right, 'not_in() right')}


def empty(left):
    return {'type': 'empty', 'left': _as_expr(left, 'empty() operand')}


def not_empty(left):
    """The predicate a real export uses to gate a Continue button on a filled input:
    `not_empty(ref('email.value'))`."""
    return {'type': 'notEmpty', 'left': _as_expr(left, 'not_empty() operand')}


def size_of(left):
    """Named `size_of` because `size()` is the sizing helper — different construct entirely."""
    return {'type': 'size', 'left': _as_expr(left, 'size_of() operand')}


def all_(*predicates):
    """`&&`. The real-export shape for "every field is filled"."""
    return {'type': '&&', 'predicates': [_as_expr(p, f'all_() predicate {i}')
                                         for i, p in enumerate(predicates)]}


def any_(*predicates):
    return {'type': '||', 'predicates': [_as_expr(p, f'any_() predicate {i}')
                                         for i, p in enumerate(predicates)]}


def when(condition):
    """Conditional visibility: show the element only while `condition` holds.

    The third form of `props.visibility`, alongside `visible()` and `hidden()` — and the one
    with a publish gate behind it. Hiding COLLAPSES the space rather than reserving it
    (trap 14), exactly as `hidden()` does.

    This is also the only way to make a field mandatory: there is no `disabled` mechanism to
    drive, so gate the button's visibility on the input instead —
    `when(not_empty(ref('email.value')))`.
    """
    _check_expr(condition, 'when() condition')
    return {'type': 'conditional', 'condition': condition}


def _condition_var_ids(o, out):
    """Every `variableId` reachable inside a condition tree."""
    if isinstance(o, dict):
        if o.get('type') == 'var' and isinstance(o.get('variableId'), str):
            out.add(o['variableId'])
        for v in o.values():
            _condition_var_ids(v, out)
    elif isinstance(o, list):
        for v in o:
            _condition_var_ids(v, out)
    return out


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


def switch_rich(cases, default, *, locale='en'):
    """Conditional rich text: ONE element whose copy depends on what the user chose.

    This is the mechanism behind an onboarding's personalization payoff -- echoing the user's
    own answer back at them. Without it the only way to "personalize" is a stack of elements
    with `visibility` conditions, which duplicates the layout per branch and drifts.

    Shape taken from a real builder export, not from the schema: the `switch` nests INSIDE each
    locale, so every locale carries a full copy of the expression and **parity is per branch** --
    a field with a `ru` value can still be English in the branch the other choice shows.

        switch_rich([(eq(ref('goal.selectedOptionId'), 'sleep'),
                      ['Your plan for ', Span('falling asleep faster', bold=True)])],
                    default=['Your personalized plan'])

    `cases` is a sequence of `(condition, parts)`; `parts` is what `rich()` takes. The condition
    is checked against the transform service's own walker here, because a bad one is a hard 422
    (`invalid_conditional_text_predicate`), not a render defect.
    """
    def _blocks(parts, what):
        if isinstance(parts, (str, Span, Var)):
            parts = [parts]
        if isinstance(parts, dict):
            raise TypeError(
                f'{what}: pass the parts, not a built localizable — switch_rich() wraps them '
                'itself, so `rich(...)` here would nest a values map inside a switch branch.')
        return [{'type': 'paragraph', 'content': [_span(p) for p in parts]}]

    cases = list(cases)
    if not cases:
        raise ValueError(
            'switch_rich() with no cases renders the default and nothing else — use rich() '
            'if the copy does not depend on anything.')
    out = []
    for i, case in enumerate(cases):
        if not (isinstance(case, (list, tuple)) and len(case) == 2):
            raise TypeError(f'switch_rich() case {i} must be (condition, parts), got {case!r}')
        cond, parts = case
        _check_expr(cond, f'switch_rich() case {i} condition')
        out.append([cond, {'type': 'const', 'value': _blocks(parts, f'case {i} parts')}])
    return {'values': {locale: {
        'type': 'switch', 'cases': out,
        'default': {'type': 'const', 'value': _blocks(default, 'default parts')}}},
        '_localizable': True}


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
             fill_=None, padding=None, margin=None, corner=None, position=None,
             visibility=None, node_id=None, **kw):
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
    # The dot band is the last few px of the carousel's OWN box and the next element begins
    # immediately after it, so clearance from what follows is a margin -- there is nowhere else
    # to put it. Without this parameter it had to be assigned onto the node by hand.
    if margin is not None:     props['margin'] = margin
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


def spinner(icon_name, *, size_pt=32, color_id=None, hexval=None, duration_ms=1000,
            position=None, **kw):
    """A rotating loading indicator. `icon_name` must name a `_meta.icons` entry you declared.

    Two things this exists to stop, both from `patterns.md`. **The icon type must be `custom`**:
    the publish gate refuses a phosphor spinner with a 422 (`Spinner element only supports custom
    icons`), so the type is not a parameter here. And **a static `icon` is not a substitute** —
    a ring glyph renders in `flows config preview` and reads as a spinner in a screenshot, but it
    does not animate on a device; that is the fake-footer mistake wearing a loader.

    `duration_ms` is the ROTATION PERIOD, not a delay. A spinner has no completion trigger and
    fires nothing — the invisible `timer()` beside it is what moves the flow on. Say which is
    which in the handoff, because the field reads exactly like a delay.

    The spinner draws blank in `config preview`; that is a render blindness, not a broken
    element. Verify it on a device.
    """
    if not (isinstance(icon_name, str) and icon_name):
        raise ValueError('spinner() needs the name of a _meta.icons entry')
    ic = {'name': icon_name, 'size': size_pt, 'type': 'custom'}
    if color_id is not None and hexval is not None:
        raise TypeError('spinner(): pass color_id or hexval, not both')
    if color_id is not None:
        ic['color'] = color(color_id)
    elif hexval is not None:
        ic['color'] = hex_color(hexval)
    return _node('spinner', {'icon': ic, 'duration': duration_ms,
                             'position': position or relative()}, **kw)


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


# --- the input family ---------------------------------------------------------------------
# Eight element types, and flowkit had a helper for NONE of them, so every authored input was
# hand-assembled from an export — including in all six runs of the 2026-08-28 GREEN round, one
# of which said so in its own build script ("flowkit has no helper for the input family, so the
# props are assembled here"). Finding 12 once more.
#
# The stakes are not cosmetic. An input's `customId` is the PRODUCER for `<customId>.value`,
# which is what every conditional-visibility gate reads. Get it wrong or leave it out and the
# condition compiles to a bare identifier and the flow is refused (`script_type_violation`,
# TS2304) — so `custom_id` is positional and required here, and `config()` resolves every
# condition variable against the inputs this module emits.

INPUT_TYPES = ('text-input', 'email-input', 'password-input', 'number-input', 'phone-input',
               'date-picker', 'time-picker', 'date-time-picker')
DATE_FORMATS = ('dd-mm-yyyy', 'mm-dd-yyyy', 'yyyy-mm-dd')
TIME_FORMATS = ('12h', '24h')
NUMBER_FORMATS = ('integer', 'decimal-point', 'decimal-comma')
PASSWORD_RULES = ('lowercase', 'uppercase', 'number', 'specialChar', 'minLength', 'maxLength')


def _input(kind, custom_id, *, placeholder=None, locale='en', width='fill', height_pt=56,
           preset='body', fill_=None, border=None, border_width=1, corner=None, padding=None,
           margin=None, position=None, visibility=None, node_id=None, extra=None, **kw):
    """Shared shape for all eight. Every default below is the real export's own value."""
    if kind not in INPUT_TYPES:
        raise ValueError(f'input kind must be one of {INPUT_TYPES}, not {kind!r}')
    if not (isinstance(custom_id, str) and custom_id):
        raise ValueError(
            f'{kind} needs a non-empty custom_id, got {custom_id!r}. It is the producer for '
            f'"{custom_id}.value" — the handle a conditional-visibility gate reads. Without it '
            f'any condition naming this field compiles to a bare identifier and the flow is '
            f'refused with script_type_violation.')
    props = {
        'width': size(width),
        'height': size('fixed', height_pt),
        'font': {'preset': preset},
        'customId': custom_id,
        'position': position if position is not None else relative(),
        'padding': padding if padding is not None else pad(0, 16, 16, 0),
    }
    if placeholder is not None:
        # A placeholder is a localizable BARE STRING, not rich text: that is what all four
        # input elements in the real multi-locale export carry. `localized()` wraps a plain
        # value; `rich()` would put paragraph blocks in here, which is a different shape.
        if isinstance(placeholder, (list, dict)):
            raise TypeError(
                f'{kind} placeholder must be a plain string, got {type(placeholder).__name__}. '
                f'It is a bare localizable string in every real export — not rich text, so do '
                f'not pass rich(...) or a block list.')
        props['placeholder'] = localized(placeholder, locale=locale)
    if fill_ is not None:      props['fill'] = fill_
    if border is not None:
        # `border` is a COLOUR ID and is wrapped here, exactly as `stack()` does it. The first
        # version of this helper passed the argument through verbatim, so `border='line'`
        # emitted the bare string `"border": "line"` while the same call on a stack produced a
        # full IBorder -- two helpers, one parameter name, two meanings. That is the drift this
        # module exists to prevent (see the rich-text note above); found by an agent in the
        # 2026-08-28 round, which had to repair it by hand.
        if not isinstance(border, str):
            raise TypeError(
                f'{kind} border takes a THEME COLOUR ID like \'line\', not '
                f'{type(border).__name__} — same as stack(). Use border_width for the width.')
        props['border'] = {'color': color(border), 'style': 'solid', 'width': border_width}
    if corner is not None:     props['borderRadius'] = corner
    if margin is not None:     props['margin'] = margin
    if visibility is not None: props['visibility'] = visibility
    props.update(extra or {})
    return _node(kind, props, node_id=node_id, **kw)


def text_input(custom_id, **kw):
    """A free-text field. Exposes `<custom_id>.value`."""
    return _input('text-input', custom_id, **kw)


def email_input(custom_id, *, validate_format=True, **kw):
    """An email field. `validate_format` drives the field's own `invalid` styling.

    It does NOT gate anything: there is no validity predicate, so a Continue button can only be
    conditioned on `not_empty(ref('<custom_id>.value'))`, never on the address being well-formed.
    """
    return _input('email-input', custom_id,
                  extra={'validateEmailFormat': bool(validate_format)}, **kw)


def password_input(custom_id, *, requirements=None, show_toggle=None, **kw):
    """A password field. `requirements` is a dict over
    lowercase / uppercase / number / specialChar / minLength / maxLength."""
    extra = {}
    if requirements is not None:
        bad = sorted(set(requirements) - set(PASSWORD_RULES))
        if bad:
            raise ValueError(f'unknown password requirement(s) {bad}; '
                             f'the schema allows {list(PASSWORD_RULES)}')
        extra['passwordRequirements'] = dict(requirements)
    if show_toggle is not None:
        extra['showPasswordToggle'] = bool(show_toggle)
    return _input('password-input', custom_id, extra=extra, **kw)


def number_input(custom_id, *, number_format='integer', **kw):
    if number_format not in NUMBER_FORMATS:
        raise ValueError(f'number_format must be one of {NUMBER_FORMATS}, not {number_format!r}')
    return _input('number-input', custom_id, extra={'numberFormat': number_format}, **kw)


def phone_input(custom_id, **kw):
    return _input('phone-input', custom_id, **kw)


def _dates(date_format, min_date, max_date):
    if date_format is not None and date_format not in DATE_FORMATS:
        raise ValueError(f'date_format must be one of {DATE_FORMATS}, not {date_format!r}')
    out = {}
    if date_format is not None: out['dateFormat'] = date_format
    if min_date is not None:    out['minDate'] = min_date
    if max_date is not None:    out['maxDate'] = max_date
    return out


def date_picker(custom_id, *, date_format='yyyy-mm-dd', min_date=None, max_date=None, **kw):
    """A date field. `min_date`/`max_date` are `YYYY-MM-DD` strings — the export bounds a
    birthday picker that way rather than validating age after the fact."""
    return _input('date-picker', custom_id,
                  extra=_dates(date_format, min_date, max_date), **kw)


def time_picker(custom_id, *, time_format='24h', **kw):
    if time_format not in TIME_FORMATS:
        raise ValueError(f'time_format must be one of {TIME_FORMATS}, not {time_format!r}')
    return _input('time-picker', custom_id, extra={'timeFormat': time_format}, **kw)


def date_time_picker(custom_id, *, date_format='yyyy-mm-dd', time_format='24h',
                     min_date=None, max_date=None, **kw):
    if time_format not in TIME_FORMATS:
        raise ValueError(f'time_format must be one of {TIME_FORMATS}, not {time_format!r}')
    extra = _dates(date_format, min_date, max_date)
    extra['timeFormat'] = time_format
    return _input('date-time-picker', custom_id, extra=extra, **kw)


#: The one system state a group member receives on tap. Declared on the MEMBER; the visual
#: overrides may sit on the member, on any descendant, or both -- real exports do all three.
SELECTED_STATE = [{'id': 'selected', 'type': 'system'}]


def on_selected(node, **props):
    """Give `node` a different look while its group member is selected.

    THE reason this exists: without it there is no way to express "selected" from this module,
    so an author styles the card that starts selected differently in its BASE props -- and that
    look is then stuck on that card forever. Tapping flips the internal selection and nothing on
    screen moves, which reads to a user as "it blinks and nothing changes". Shipped to a real
    user on 2026-08-28 from a build that had `patterns.md`'s rule in front of it; the words were
    there and the helper was not, which is the difference this closes.

    Use it on the member AND on every descendant whose colour or font should follow:

        card = on_selected(product([...], product_id=P, group_id='plans', default=True),
                           fill=fill('planOn'), padding=pad(16, 16, 16, 16),
                           borderRadius=radius(16))
        name = on_selected(text(rich('Annual'), preset='plan', color_id='inkMuted'),
                           color=color('ink'), font={'preset': 'plan'})

    Give every member the SAME base look; `default=True` picks which one starts selected, never
    how it looks. A real export repeats the props it touches (fill, padding, borderRadius)
    rather than sending a delta, so pass the full set you want applied in that state.
    """
    if not props:
        raise ValueError('on_selected() with no props does nothing — pass the overrides that '
                         'should apply while selected, e.g. fill=fill("planOn").')
    if node.get('type') in ('product', 'selectable', 'tab-item'):
        node['states'] = list(SELECTED_STATE)
    node.setdefault('propsByState', {})['selected'] = props
    return node


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


def attach_point(*, product_id, group_id, element_id=None):
    """The hidden `product` element a single-plan screen attaches its product to.

    One product means there is nothing to pick, and a visible lone card carries a permanent
    `selected` look the user cannot change. But a price variable resolves only against a declared
    product and only a `product` element can be attached to -- so the element exists, hidden, and
    the price lives in ordinary copy. See patterns.md, "A single-plan screen".

    `height` is `hug`, never `fixed: 0`. `visibility: hidden` already collapses the space, and a
    zero height is the shape `verify-config.py` errors on (trap 15: it saves fine and kills the
    element on device). patterns.md spelled this skeleton with `fixed: 0` until 2026-09-02, and an
    agent following it hit that error -- which is also why this helper exists at all: the shape was
    hand-assembled every time because nothing emitted it.

    Evidence tier, since this file's callers rely on it: the composition is AUTHORED, not observed.
    No real export contains a hidden attach point. Its two halves are attested separately -- `hug`
    is what every real `product` element uses, and `visibility: hidden` occurs on real builder
    output elsewhere in the corpus.
    """
    node = product((), product_id=product_id, group_id=group_id, default=True,
                   width='hug', height='hug', visibility=hidden())
    node['props']['caption'] = 'Product attach point (hidden)'
    if element_id:
        node['id'] = element_id
    return node


# The only group types real exports declare. A tab group is `single_choice`; there is no
# `tabs` group type, and the service refuses one that is not single_choice under a tab bar
# with `wrong_tab_selectable_group_type`.
GROUP_TYPES = ('single_choice', 'multi_choice', 'product', 'toggle')

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


def tab(label, content, *, default=False, custom_id=None):
    """One tab: the `label` shown in the bar, and the `content` panel shown below it.

    Both halves are given together because the builder links them by ORDINAL POSITION — a
    `tab-content` carries no groupId and no back-reference, so the Nth panel belongs to the
    Nth tab and nothing in the document says so. Pairing them here is the only way that
    ordering cannot drift.
    """
    return {'_tab': True, 'label': list(label), 'content': list(content),
            'default': default, 'custom_id': custom_id}


def tabs(tabs_, *, group_id, width='fill', height='fill', gap=16, bar_fill=None,
         bar_gap=0, bar_padding=None, item_height=44, item_corner=None, node_id=None, **kw):
    """A tab bar and its panels, built as the FIVE element types a real export uses.

    The tree the builder emits, and the only one the SDK renders:

        tabs
        ├── tab-bar             -- the strip
        │   └── tab-item × N    -- each carrying the shared groupId and its label
        └── tab-content-wrapper
            └── tab-content × N -- one panel per tab, matched BY POSITION

    An earlier draft of this helper hung `tab-item`s straight off `tabs` and skipped the
    other three types. Every gate passed it — and it is a shape the builder never emits,
    which is this repo's most expensive recurring class. The schema check caught it here
    only because the schema happens to disagree with `tabs` for unrelated reasons.

    The screen must declare `group_id` as **`single_choice`**; the service refuses any other
    type with `wrong_tab_selectable_group_type`, and there is no `tabs` group type however
    much the name suggests one. `screen()` checks that for you.
    """
    entries = [t for t in tabs_]
    if len(entries) < 2:
        raise ValueError(f'tabs() needs at least 2 tab()s, got {len(entries)}')
    if not (isinstance(group_id, str) and group_id):
        raise ValueError(f'tabs() needs a non-empty group_id, got {group_id!r} — the service '
                         f'refuses an empty one with mixed_tab_group_ids')
    bad = [t for t in entries if not (isinstance(t, dict) and t.get('_tab'))]
    if bad:
        raise ValueError(
            f'tabs() takes tab(label, content) entries, got {len(bad)} other value(s). A stack '
            f'carrying a groupId is NOT a group member — it never receives the selected state '
            f'and tapping it does nothing.')
    if sum(1 for t in entries if t['default']) > 1:
        raise ValueError('tabs() got more than one default tab')

    items, panels = [], []
    for t in entries:
        it = stack(t['label'], width='fill', height='fixed', fixed_h=item_height,
                   direction='horizontal', align_h='center', align_v='center',
                   corner=item_corner)
        it['type'] = 'tab-item'
        it['props'].update({'groupId': group_id, 'default': t['default']})
        if t['custom_id'] is not None:
            it['props']['customId'] = t['custom_id']
        it['states'] = [{'id': 'selected', 'type': 'system'}]
        items.append(it)
        panel = stack(t['content'], width='fill', height='fill', gap=gap)
        panel['type'] = 'tab-content'
        panels.append(panel)

    bar = stack(items, width='fill', height='hug', direction='horizontal', gap=bar_gap,
                align_h='center', align_v='center', fill_=bar_fill, padding=bar_padding)
    bar['type'] = 'tab-bar'
    wrapper = stack(panels, width='fill', height='fill')
    wrapper['type'] = 'tab-content-wrapper'

    props = {'width': size(width), 'height': size(height),
             'layout': layout('vertical', gap, 'start', 'start'),
             'position': relative()}
    return _node('tabs', props, children=[bar, wrapper], node_id=node_id, **kw)


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


# --- the rest of the action vocabulary ----------------------------------------------------
# `invalid_action_payload` was the 5th most common transformer refusal in the 40 days to
# 2026-08-28 (208 failed requests), and it is one code covering sixteen distinct required-field
# checks. Until now flowkit exposed three action types out of fourteen — purchase, navigate,
# closeFlow — so ANY other action had to be hand-written, `openUrl` included, which store
# compliance requires on every paywall (terms and privacy). Finding 12: an author reaches for
# what the helper exposes, and what is not exposed gets hand-written into a 422.
#
# Every required field below is the transform service's own, read off its error messages in
# `compile-actions.ts` rather than inferred from the schema — the schema is looser than the
# service in each case.


def restore(action_id='act_restore'):
    """`restorePurchases`. Takes no payload — and a paywall without it is rejected by both
    stores, so this is a compliance element, not a nicety."""
    return {'id': action_id, 'type': 'restorePurchases'}


def open_url(url, *, external=None, action_id='act_url'):
    """`openUrl`. The service requires a non-empty `payload.url`.

    A `mailto:` URL crashes iOS unless it opens in the external browser — pass
    `external=True` for one.
    """
    if not (isinstance(url, str) and url):
        raise ValueError(
            f'open_url() needs a non-empty url, got {url!r} — the transform service refuses an '
            f'empty one with invalid_action_payload at .payload.url')
    payload = {'url': url}
    if external is not None:
        payload['external'] = external
    return {'id': action_id, 'type': 'openUrl', 'payload': payload}


def select_product(element_id, action_id='act_select'):
    """`selectProduct`. The service requires `payload.element` — the id of the product
    element to select, NOT a product id and NOT a group id."""
    if not (isinstance(element_id, str) and element_id):
        raise ValueError(
            f'select_product() needs the target ELEMENT id, got {element_id!r} '
            f'(invalid_action_payload at .payload.element)')
    return {'id': action_id, 'type': 'selectProduct', 'payload': {'element': element_id}}


def set_variable(assignments, action_id='act_set'):
    """`setVariable`. The payload is an ARRAY of assignments, each `left` naming a variable.

    `assignments` is a sequence of `(variable_id, value)` pairs. This is the one place an
    `assign` expression is legal — it is refused inside a condition, where it has no case in
    the service's walker.
    """
    pairs = list(assignments)
    if not pairs:
        raise ValueError('set_variable() needs at least one (variable_id, value) pair — the '
                         'service refuses a non-array payload with invalid_action_payload')
    payload = []
    for i, pair in enumerate(pairs):
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2):
            raise TypeError(f'set_variable() assignment {i} must be a (variable_id, value) '
                            f'pair, got {pair!r}')
        vid, value = pair
        if not (isinstance(vid, str) and vid):
            raise ValueError(f'set_variable() assignment {i} has no target variable id '
                             f'(invalid_action_payload at .payload[{i}].left.variableId)')
        payload.append({'type': 'assign', 'left': ref(vid), 'right': _as_expr(
            value, f'set_variable() assignment {i} value')})
    return {'id': action_id, 'type': 'setVariable', 'payload': payload}


def custom_action(custom_id, action_id='act_custom'):
    """`custom`. The service requires `payload.id` — the handle your app code switches on."""
    if not (isinstance(custom_id, str) and custom_id):
        raise ValueError(f'custom_action() needs a non-empty payload id, got {custom_id!r} '
                         f'(invalid_action_payload at .payload.id)')
    return {'id': action_id, 'type': 'custom', 'payload': {'id': custom_id}}


def alert(*, title=None, message=None, action_id='act_alert'):
    """`alert`. The service requires a title OR a message — an alert with neither is refused."""
    if not title and not message:
        raise ValueError('alert() needs a title or a message (invalid_action_payload: "Alert '
                         'action requires a title or message value")')
    payload = {}
    if title is not None:
        payload['title'] = title
    if message is not None:
        payload['message'] = message
    return {'id': action_id, 'type': 'alert', 'payload': payload}


def navigate_back(action_id='act_back'):
    return {'id': action_id, 'type': 'navigateBack'}


def navigate_next(action_id='act_next'):
    """`navigateNext` resolves against the flow's screen ORDER, so it is refused on a screen
    the order does not contain. It also makes the graph implicit and order-dependent: an
    explicit `navigate(screen_id)` is preferred wherever the target is known, and a previous
    build reverted `navigateNext` after `verify-config.py` reported five screens unreachable.
    """
    return {'id': action_id, 'type': 'navigateNext'}


def conditional_action(cases, *, default=(), action_id='act_cond'):
    """`conditional`. Branch between action lists on a predicate.

    `cases` is a sequence of `(predicate, [actions])`; `default` is the fallback action list.
    The service requires an object payload carrying a `cases` ARRAY whose entries are
    `[predicate, value]` tuples — the shape is easy to get subtly wrong by hand, and each way
    of getting it wrong is a separate `invalid_action_payload`.

    A branch that should do nothing is an empty list, which is emitted as the real export's
    own no-op (`{"type": "nothing"}`) rather than as an omitted branch.
    """
    def _branch(actions, what):
        acts = list(actions)
        for a in acts:
            if not (isinstance(a, dict) and isinstance(a.get('type'), str)):
                raise TypeError(f'conditional_action() {what} must contain actions, got {a!r}')
        return lit(acts or [{'id': '', 'type': 'nothing'}])

    entries = list(cases)
    if not entries:
        raise ValueError('conditional_action() needs at least one (predicate, actions) case — '
                         'the service refuses a payload with no cases array')
    payload_cases = []
    for i, case in enumerate(entries):
        if not (isinstance(case, (tuple, list)) and len(case) == 2):
            raise TypeError(f'conditional_action() case {i} must be a (predicate, actions) '
                            f'pair, got {case!r} — the service checks for [predicate, value] '
                            f'tuples by shape')
        predicate, actions = case
        _check_expr(predicate, f'conditional_action() case {i} predicate')
        payload_cases.append([predicate, _branch(actions, f'case {i}')])
    return {'id': action_id, 'type': 'conditional',
            'payload': {'type': 'switch', 'cases': payload_cases,
                        'default': _branch(default, 'default')}}


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
    running digits.

    **A timer carrying a `timer-end` action MUST have at least one child.** Device-measured
    2026-09-01, two writes differing in nothing else: the childless form **did not advance**, the
    same timer with one child text **did**, and an isolating probe with two exits to different
    destinations confirmed it on a third trip. So the "purely invisible delay" this docstring used
    to recommend does not fire at all — an element with nothing to lay out is one the renderer
    skips, timer included. `config preview` cannot see any of this: it never navigates for any
    reason, so both forms look identical locally and `validate` passes both.

    Raised rather than warned because the failure is silent, terminal and remote: the flow stops
    dead on that screen, and the only surface that can show it is a device.

    `duration` is `{days, hours, minutes, seconds}`. `behavior='start_at_every_appear'` restarts
    the countdown each time the screen appears.
    """
    if actions and not list(children):
        raise ValueError(
            'a timer with a `timer-end` action and NO children does not fire on a device '
            '(measured 2026-09-01) — the flow stops dead on that screen, and neither '
            '`config preview` nor `flows config validate` can see it. Give it a child: '
            'timer_digits(...) if a visible countdown suits the screen, or the loader copy '
            'itself. See patterns.md -> the auto-advancing screen.')
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
    # Selectable groups, both directions. `verify-config.py` errors on each of these in a
    # finished document; raising here is the finding-12 half — the screen that cannot be
    # built wrong beats the one whose defect is reported afterwards.
    groups = {g['id']: g for g in selectable_groups}
    for gid, g in groups.items():
        if g.get('type') not in GROUP_TYPES:
            raise ValueError(f'screen {screen_id!r}: group {gid!r} has type {g.get("type")!r}; '
                             f'the only types real exports use are {", ".join(GROUP_TYPES)}. '
                             f'A tab group is declared single_choice — there is no `tabs` type.')
    members = {}
    for k, v in node_map.items():
        gid = (v.get('props') or {}).get('groupId')
        if gid:
            members.setdefault(gid, []).append((k, v.get('type')))
    undeclared = sorted(set(members) - set(groups))
    if undeclared:
        raise ValueError(
            f'screen {screen_id!r}: element(s) carry groupId {undeclared} with no matching entry '
            f'in selectable_groups. An unresolved group means the members never receive the '
            f'selected state and tapping them does nothing; for a tab bar the service refuses '
            f'the flow outright (missing_tab_selectable_group).')
    empty_groups = sorted(set(groups) - set(members))
    if empty_groups:
        raise ValueError(f'screen {screen_id!r}: group(s) {empty_groups} declared with no member '
                         f'element carrying that groupId')
    for gid, mem in members.items():
        if any(t == 'tab-item' for _, t in mem) and groups[gid].get('type') != 'single_choice':
            raise ValueError(
                f'screen {screen_id!r}: group {gid!r} has tab-item members but is declared '
                f'{groups[gid].get("type")!r}. The service requires single_choice here and '
                f'refuses anything else with wrong_tab_selectable_group_type.')
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

    # Every condition variable must resolve to something this document produces. An id that
    # resolves to nothing is not dropped: the code generator emits it as a BARE IDENTIFIER into
    # the generated TypeScript, which then fails to compile — `script_type_violation`,
    # `TS2304: Cannot find name 'email'`, the 4th most common transformer refusal in the 40 days
    # to 2026-08-28 (253 failed requests). It is checked here rather than in `when()` because
    # only the whole document knows what produces what.
    #
    # The same id in RICH TEXT is a different severity and is deliberately left alone: an
    # unresolved variable there renders as its literal token, which is wrong but publishes.
    # In a condition it is compiled, so it is fatal.
    INPUT_TYPES = ('text-input', 'email-input', 'password-input', 'number-input',
                   'phone-input', 'date-picker', 'time-picker', 'date-time-picker')
    produced, group_ids, product_ids = set(), set(), set()
    for s in screens:
        for e in s.get('elements', {}).get('map', {}).values():
            p = e.get('props') or {}
            if e.get('type') in INPUT_TYPES and p.get('customId'):
                produced.add(p['customId'])
            if p.get('customId'):
                produced.add(p['customId'])
            if isinstance(p.get('product'), dict) and p['product'].get('id'):
                product_ids.add(p['product']['id'])
        for g in s.get('selectableGroups') or []:
            group_ids.add(g['id'])
    custom_vars = {v['id'] for v in variables if isinstance(v, dict) and v.get('id')}

    # Two inputs answering to one customId make `<id>.value` ambiguous: the codegen emits one
    # variable name for both, so whichever is declared second silently wins and a gate reads a
    # field the user is not looking at. No gate downstream sees this -- the document is
    # perfectly well-formed.
    dupes, seen_cids = set(), set()
    for s in screens:
        for e in s.get('elements', {}).get('map', {}).values():
            cid = (e.get('props') or {}).get('customId')
            if cid and e.get('type') in INPUT_TYPES:
                if cid in seen_cids:
                    dupes.add(cid)
                seen_cids.add(cid)
    if dupes:
        raise ValueError(
            f'customId {sorted(dupes)} is on more than one input element. `<customId>.value` '
            f'is one variable, so the fields collide and a condition reads whichever the '
            f'generator emitted last — give each input its own id.')

    unresolved = set()
    for s in screens:
        for e in s.get('elements', {}).get('map', {}).values():
            trees = []
            vis = (e.get('props') or {}).get('visibility')
            if isinstance(vis, dict) and vis.get('type') == 'conditional' and vis.get('condition'):
                trees.append(vis['condition'])
            for st in e.get('states') or []:
                if isinstance(st, dict) and st.get('condition'):
                    trees.append(st['condition'])
            # A conditional-text `switch` (switch_rich) is COMPILED, not rendered, so an
            # unresolved id there is fatal exactly like a visibility condition -- measured
            # 2026-09-01 against the live service: `valid: false`, "Generated scripts failed
            # validation", with `code` and `path` both null, so the refusal names neither the
            # element nor the variable. This is the opposite severity from a `variable` SPAN in
            # rich text, which renders its literal token and publishes; the two shapes sit in
            # the same `props.content` and only this one compiles.
            for prop in (e.get('props') or {}).values():
                if not (isinstance(prop, dict) and prop.get('_localizable')):
                    continue
                for lv in (prop.get('values') or {}).values():
                    if isinstance(lv, dict) and lv.get('type') == 'switch':
                        trees.append(lv)
            for tree in trees:
                for vid in _condition_var_ids(tree, set()):
                    head = vid.split('.')[0]
                    if (vid in custom_vars or head in produced or head in group_ids
                            or head in product_ids):
                        continue
                    unresolved.add(vid)
    if unresolved:
        raise ValueError(
            f'condition variable(s) {sorted(unresolved)} resolve to nothing in this document. '
            f'The generated script emits an unresolved id as a bare identifier and fails to '
            f'compile (script_type_violation, TS2304 "Cannot find name"). Produce it — an input '
            f'element with that customId, a selectableGroup with that id, a bound product — or '
            f'declare it in variables=(...).')

    return {
        'schemaVersion': SCHEMA_VERSION,
        'locales': [{'id': c, 'code': c, 'name': n} for c, n in locales],
        'defaultLocale': default_locale,
        'variables': list(variables),
        'components': components if components is not None else {},
        'theme': {
            'colors': [{'id': i, 'name': n,
                        'light': {'hex': check_theme_hex(lt, f'colors[{i!r}].light')},
                        'dark': {'hex': check_theme_hex(dk, f'colors[{i!r}].dark')}}
                       for i, n, lt, dk in colors],
            'typography': [_typo(t) for t in typography],
        },
        '_meta': {'icons': list(icons), 'fonts': [],
                  'screens': dict(meta_screens) if meta_screens else {}},
        'screens': list(screens),
    }
