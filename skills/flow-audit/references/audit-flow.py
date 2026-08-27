#!/usr/bin/env python3
"""Is this flow ready for production?

Structural, offline half of the `flow-audit` skill. Takes a flow config and the app's
product catalog; returns findings. No network, no CLI calls -- `SKILL.md` owns those, so
this script stays testable against fixtures.

Severity is a verdict input, not a mood:
  blocker  -- the flow will not work for a real user, OR will show them something false
  risk     -- it works and is probably not what anyone intended
  question -- not decidable from the data available; state what you could not see

Every check here is calibrated in both directions against `tests/fixtures/`. See
`checks.md` before changing one -- most of these were wrong on first contact with real
data, and the traps are recorded there.

Usage:
  audit-flow.py <config.json> [--catalog <catalog.json>] [--stores ios,android]
                [--json | --report] [--name <name>] [--flow-id <id>] [--status <status>]
Exit: 0 no blockers, 1 at least one blocker, 2 usage or unreadable input.

`--json` prints the raw findings; `--report` prints the user-facing report (verdict,
BLOCKERS/RISKS/COULD NOT CHECK, locale coverage, BEFORE YOU SHIP) and the two are
mutually exclusive. `--name`/`--flow-id`/`--status` come from `flows list`, not the
config, and feed `render()`'s header and the `flow-untitled` check.
"""
import ast, json, re, sys

SEVERITIES = ('blocker', 'risk', 'question')
FAMILIES = ('triggers', 'compliance', 'products', 'variables', 'localization',
            'placeholders')


def finding(severity, family, check, message, fix, screen=None, element=None):
    assert severity in SEVERITIES, severity
    assert family in FAMILIES, family
    return {'severity': severity, 'family': family, 'check': check, 'screen': screen,
            'element': element, 'message': message, 'fix': fix}


def load_config(path):
    """Accept either the `config get` envelope or a bare config."""
    doc = json.load(open(path))
    return doc['config'] if isinstance(doc, dict) and 'config' in doc else doc


def elements(config):
    """Yield (screen, element_id, element) over every screen element."""
    for s in config.get('screens') or []:
        for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
            yield s, eid, e


# An affordance the copy promises. Deliberately short and specific: the check is that
# copy NAMES an action while neither the element itself NOR ANY ANCESTOR (walked through
# the screen's `elements.hierarchy` tree) carries an interaction. The ancestor walk is
# load-bearing: `tabs-paywall.json`'s "Skip"/"Terms"/"Restore"/"Privacy" and this
# fixture's own "Skip" text are all standalone labels whose tap target lives on a parent
# `stack`, and the walk clears every one of them. `comparison-paywall.json`'s "Restore" /
# "Terms" / "Privacy" (el_CqN7LxyqK8 / el_WiqJNVPbb8 / el_zSZPjSyaqU) are genuinely dead --
# no ancestor is wired, and the whole flow contains no `restorePurchases` action and no
# `openUrl` action anywhere. `cancel anytime` was dropped from the vocabulary: in
# `timeline-anchored.json` it is reassurance copy ("Cancel anytime."), never an
# affordance a user taps, and it was the one true false positive under this vocabulary.
AFFORDANCE_WORDS = ('restore', 'terms', 'eula', 'privacy', 'skip',
                     'manage subscription', 'unsubscribe')

# An affordance is a LABEL, not a sentence -- word-boundary matching alone is not
# enough, since "in terms of cost per session" contains `terms` as a whole word.
# Four reproduced false-positive blockers under raw substring matching, all ordinary
# marketing copy that happens to contain an affordance word in passing: "Restore your
# natural sleep rhythm in 7 days", "We take your privacy seriously and never sell
# your data" (near-boilerplate on a paywall), "The best value in terms of cost per
# session", "Skip the guesswork — we plan every workout for you". The fix: split the
# element's text on the separators a real label ROW uses to pack several affordances
# into one element ("Restore purchase · Terms · Privacy" -- `el_089T` in
# `onboarding-multilocale.json`), then treat a segment as an affordance only when the
# ENTIRE segment (stripped of trailing punctuation) IS that affordance -- the bare
# word, or the word plus one of a small closed set of qualifiers that still read as a
# label ("Restore purchase", "Terms of use"). A segment carrying a sentence around
# the word is never a label, however it is punctuated. `comparison-paywall.json`'s
# "Restore" / "Terms" / "Privacy" (three separate elements, so each is trivially its
# own whole segment) and `el_089T`'s three-affordance row must both still fire.
AFFORDANCE_SEPARATORS = re.compile(r'\s*(?:·|\||•|/|\n)\s*|\s+and\s+', re.I)
AFFORDANCE_QUALIFIERS = ('purchase', 'purchases', 'policy', 'of use', '& conditions')


def _affordance_labels(text):
    """The AFFORDANCE_WORDS this copy names AS A LABEL -- never as a word merely
    present inside a longer sentence. See the module comment above for why."""
    segs = {seg.strip().lower().strip('.,:;!?')
            for seg in AFFORDANCE_SEPARATORS.split(text or '')}
    segs.discard('')
    out = []
    for w in AFFORDANCE_WORDS:
        if w in segs or any(f'{w} {q}' in segs for q in AFFORDANCE_QUALIFIERS):
            out.append(w)
    return out


def flat_text(value, locale=None):
    """Flatten a localizable and/or rich-text value to its literal text.

    Returns '' for a value whose only content is a variable/token/image node -- a price
    element is exactly that shape, so callers must not read '' as "empty field".
    """
    if isinstance(value, dict) and 'values' in value:
        vals = value['values']
        value = vals.get(locale) if locale in (vals or {}) else next(iter((vals or {}).values()), None)
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get('type') == 'text':
                out.append(n.get('text', ''))
            for x in (n.get('content') or []):
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, str):
            out.append(n)
    walk(value)
    return ' '.join(''.join(out).split())


def node_kinds(value, locale=None):
    """The node `type`s present in a localizable/rich-text value."""
    if isinstance(value, dict) and 'values' in value:
        vals = value['values']
        value = vals.get(locale) if locale in (vals or {}) else next(iter((vals or {}).values()), None)
    kinds = []

    def walk(n):
        if isinstance(n, dict):
            if n.get('type'):
                kinds.append(n['type'])
            for x in (n.get('content') or []):
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, str):
            kinds.append('text')
    walk(value)
    return kinds


def default_locale(config):
    return config.get('defaultLocale') or next(
        (l.get('code') for l in (config.get('locales') or [])), None)


def actions_of(element):
    for i in (element.get('interactions') or []):
        for a in (i.get('actions') or []):
            yield i, a


def _parent_map(hierarchy):
    """child element id -> parent element id, from a screen's `elements.hierarchy` tree."""
    pm = {}

    def walk(node, parent):
        nid = node.get('id')
        if parent is not None and nid is not None:
            pm[nid] = parent
        for c in (node.get('children') or []):
            walk(c, nid)
    if hierarchy:
        walk(hierarchy, None)
    return pm


def _wired(eid, elements_map, parent_map):
    """True if this element or any ancestor (per `parent_map`) carries a real interaction."""
    seen = set()
    cur = eid
    while cur is not None and cur not in seen:
        seen.add(cur)
        e = elements_map.get(cur)
        if e and (e.get('interactions') or []):
            return True
        cur = parent_map.get(cur)
    return False


def check_triggers(config):
    out = []
    dl = default_locale(config)
    pm_cache = {}
    for s, eid, e in elements(config):
        m = (s.get('elements') or {}).get('map') or {}
        key = id(s)
        if key not in pm_cache:
            pm_cache[key] = _parent_map((s.get('elements') or {}).get('hierarchy'))
        pm = pm_cache[key]
        txt = flat_text((e.get('props') or {}).get('content'), dl)
        named = _affordance_labels(txt)
        if named and not _wired(eid, m, pm):
            out.append(finding(
                'blocker', 'triggers', 'dead-affordance',
                f'copy promises {", ".join(named)} but neither the element nor any '
                f'ancestor carries an interaction: {txt[:70]!r}',
                'Split the row into one tappable element per action and wire each one, '
                'or wire the ancestor that is meant to handle the tap. The copy is not '
                'the mechanism.',
                s['id'], eid))
        for i, a in actions_of(e):
            if a.get('type') == 'nothing':
                out.append(finding(
                    'risk', 'triggers', 'action-nothing',
                    'an action is explicitly wired to `nothing`',
                    'Give it a real action, or remove the interaction so the element '
                    'does not look tappable.', s['id'], eid))
            if a.get('type') == 'openUrl' and not (a.get('payload') or {}).get('url'):
                out.append(finding(
                    'blocker', 'triggers', 'openurl-no-url',
                    'an openUrl action has no url', 'Set the url, or remove the action.',
                    s['id'], eid))
        for i in (e.get('interactions') or []):
            if not (i.get('actions') or []):
                out.append(finding(
                    'risk', 'triggers', 'interaction-no-actions',
                    f'interaction {i.get("id")!r} has an empty actions array',
                    'Wire an action or drop the interaction.', s['id'], eid))
    return out


ESCAPE_ACTIONS = ('closeFlow', 'navigateBack')

# Legal-link detection lives on the openUrl action's URL PAYLOAD, never on the
# button's label. A label is a design choice -- measured: 7 of 9 real escape
# affordances (`escape_labels` above) are icon-only with no text at all, which is
# exactly why escape detection lives on action type rather than copy. A button
# labeled "Legal" that opens https://example.com/terms is a real terms link; matching
# on the label instead would have called it absent. Two small, separate vocabularies
# of URL tokens, matched case-insensitively against the url itself:
TERMS_URL_WORDS = ('terms', 'tos', 'eula', 'legal', 'conditions')
PRIVACY_URL_WORDS = ('privacy', 'policy')


def _url_tokens(url):
    """Split a url into lowercase alphanumeric tokens on any non-alphanumeric run.

    Matching a vocabulary word by substring containment is a false-negative trap:
    'tos' matches inside 'photos' and 'autos', 'legal' matches inside 'illegally',
    which SILENCES a real compliance blocker -- a paywall whose only openUrl points
    at a hero image reads as compliant. Tokenizing on separators and requiring an
    EXACT token match closes that: 'photos'/'hero'/'jpg' and 'illegally'/'obtained'/
    'content' contain no vocabulary token, while '/tos' and 'terms-of-service' still
    tokenize to 'tos' and 'terms'/'of'/'service' respectively.

    Deliberate direction of error: a concatenated path with no separator at all
    (`/termsofservice`) now tokenizes to one unsplit word and will not match, which
    turns a would-be silent pass into a QUESTION asking the human to confirm the url.
    A question is honest; false silence on an App Store 3.1.2 requirement is not.
    """
    return set(re.split(r'[^a-z0-9]+', url.lower()))


def selling_screens(config):
    """A screen sells if it binds a product or carries a purchase action."""
    out = set()
    for s, eid, e in elements(config):
        if ((e.get('props') or {}).get('product') or {}).get('id'):
            out.add(s['id'])
        for _, a in actions_of(e):
            if a.get('type') == 'purchase':
                out.add(s['id'])
    return out


def nav_graph(config):
    """screen id -> screens reachable by one navigate/navigateNext edge."""
    order = [s['id'] for s in config.get('screens') or []]
    idx = {sid: i for i, sid in enumerate(order)}
    edges = {sid: set() for sid in order}
    for s, eid, e in elements(config):
        for _, a in actions_of(e):
            if a.get('type') == 'navigate':
                tgt = (a.get('payload') or {}).get('screen')
                if tgt:
                    edges[s['id']].add(tgt)
            elif a.get('type') == 'navigateNext':
                nxt = idx[s['id']] + 1
                if nxt < len(order):
                    edges[s['id']].add(order[nxt])
    return edges


def escape_screens(config):
    """Screens that carry an escape action of their own."""
    out = set()
    for s, eid, e in elements(config):
        for _, a in actions_of(e):
            if a.get('type') in ESCAPE_ACTIONS:
                out.add(s['id'])
    return out


def escape_labels(config):
    """(screen, label) for every escape affordance. Measured: 7 of 9 are icon-only, so
    the label is reported as evidence and never used for detection."""
    dl = default_locale(config)
    out = []
    for s, eid, e in elements(config):
        for _, a in actions_of(e):
            if a.get('type') in ESCAPE_ACTIONS:
                out.append((s['id'],
                            flat_text((e.get('props') or {}).get('content'), dl)
                            or '(icon only, no text)'))
    return out


def openurl_urls(config):
    """Every url carried by an openUrl action's payload, flattened to plain text.

    The mechanism's own target, not the button's label -- see the vocab comment
    above. A url may be a plain string or a localizable/rich-text value; `flat_text`
    already handles the latter, so both shapes are covered here. Empty urls (an
    `openUrl` with no `url` at all) are dropped -- `check_triggers`'s
    `openurl-no-url` already flags that as its own defect, so this list is never the
    reason `no-terms-link`/`no-privacy-link` mistakes an unset url for a real one.
    """
    dl = default_locale(config)
    out = []
    for _, eid, e in elements(config):
        for _, a in actions_of(e):
            if a.get('type') != 'openUrl':
                continue
            url = (a.get('payload') or {}).get('url')
            text = url if isinstance(url, str) else flat_text(url, dl)
            if text:
                out.append(text)
    return out


def _reaches(edges, start, targets):
    seen, queue = {start}, [start]
    while queue:
        cur = queue.pop(0)
        if cur in targets:
            return cur
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return None


def check_compliance(config):
    out = []
    # `no-escape-in-flow` applies to ANY flow, selling or not -- a non-paywall
    # onboarding flow with no way off is exactly the case this check exists to name,
    # so it runs ahead of the selling-screen gate below rather than behind it.
    # `no-escape-from-paywall` stays scoped to selling screens: it needs both a
    # selling screen and a nav graph to walk from it.
    edges, escapes = nav_graph(config), escape_screens(config)
    if not escapes:
        out.append(finding(
            'question', 'compliance', 'no-escape-in-flow',
            'no closeFlow or navigateBack action anywhere in the flow, so nothing in '
            'the config lets a user leave',
            'Confirm the host app presents this flow with a system dismiss. If it does '
            'not, add a closeFlow action.'))

    selling = selling_screens(config)
    if not selling:
        return out
    dl = default_locale(config)
    all_actions = {a.get('type') for _, eid, e in elements(config) for _, a in actions_of(e)}
    corpus_text = ' '.join(
        flat_text((e.get('props') or {}).get('content'), dl).lower()
        for _, eid, e in elements(config))

    if 'restorePurchases' not in all_actions:
        out.append(finding(
            'blocker', 'compliance', 'no-restore',
            'the flow sells but has no restorePurchases action anywhere'
            + (' — although the copy says "restore", which makes it look present'
               if 'restore' in corpus_text else ''),
            'Add a restorePurchases action to a tappable element. App Store 3.1.1 '
            'requires a restore path.'))

    # Three outcomes, in order of certainty. (1) No `openUrl` action anywhere: there
    # cannot be a legal link without one, so both checks are a blocker. (2) An
    # `openUrl` exists and some url matches the pattern: silent -- the link is real,
    # whatever the button says. (3) An `openUrl` exists but nothing matches: this is
    # NOT a blocker, because the audit cannot know what an arbitrary url points to --
    # a shortlink or a `/legal` page may well serve the document -- so it is a
    # question that names the urls actually found and asks the human to confirm.
    urls = openurl_urls(config)
    url_token_sets = [_url_tokens(u) for u in urls]
    for words, name, label in ((TERMS_URL_WORDS, 'no-terms-link', 'terms/EULA'),
                              (PRIVACY_URL_WORDS, 'no-privacy-link', 'privacy policy')):
        if not urls:
            out.append(finding(
                'blocker', 'compliance', name,
                f'no working link to a {label}: the flow has no openUrl action '
                'anywhere',
                f'Add an openUrl action pointing at your hosted {label}. '
                'App Store 3.1.2 requires it on a subscription screen.'))
            continue
        # Exact token match, never substring containment -- see `_url_tokens`.
        if any(w in toks for toks in url_token_sets for w in words):
            continue  # a url matches -- the link is real, regardless of the label
        shown = ', '.join(sorted(set(urls)))
        out.append(finding(
            'question', 'compliance', name,
            f'the flow has openUrl action(s) but none of their urls look like a '
            f'{label} link -- confirm one of these is it: {shown}',
            f'If one of the urls above is your {label} document, no action needed. '
            f'Otherwise add an openUrl action pointing at your hosted {label}.'))

    if escapes:
        # Evidence for the human, never a detection signal: 7 of 9 measured escape
        # affordances are icon-only with no text at all, so a label can only be shown,
        # not matched on. Dedup so a flow with several identical icon buttons prints
        # one line instead of one per button.
        seen_labels = []
        for _, lbl in escape_labels(config):
            if lbl not in seen_labels:
                seen_labels.append(lbl)
        labels_str = '; '.join(seen_labels)
        for sid in sorted(selling):
            if _reaches(edges, sid, escapes) is None:
                out.append(finding(
                    'blocker', 'compliance', 'no-escape-from-paywall',
                    'a user who does not buy cannot leave this screen: no closeFlow or '
                    'navigateBack is reachable from it. Escapes elsewhere in the flow '
                    f'are labeled: {labels_str}',
                    'Add a dismiss affordance with a closeFlow action. It does not need '
                    'to say "close" — most escapes are an icon with no text.', sid))
    # else: escapes is empty, already handled above by `no-escape-in-flow` -- when
    # there is no escape ANYWHERE, the per-screen reachability blocker below would be
    # true of every selling screen too, which is exactly the redundant restating the
    # flow-wide question already exists to avoid.
    return out


def _element_product_id(e):
    """The product id bound via a `product` ELEMENT's own props, or None.

    The one extraction site for this shape -- it used to be typed out identically in
    `bound_products`, `check_period_claim` and `check_price_integrity`, which is
    exactly the kind of duplication that lets a fix land in one place and miss the
    other two. This shape is the only one that gives a caller an element to attach a
    finding to AND card copy to read (via `card_text`/`_element_blobs`), which is
    why `check_period_claim` and `check_price_integrity` -- both of which need card
    copy -- stay scoped to it alone and never see the shape below.
    """
    return ((e.get('props') or {}).get('product') or {}).get('id')


def _const_purchase_product_id(action):
    """The product id bound by a `const` purchase ACTION's payload, or None.

    A `const` purchase action binds a product with no `product` element behind it and
    no card copy to read -- CLAUDE.md documents the shape (verified against
    `verify-config.py`'s own `missing flowProductId` check, path `...purchase.product`).
    Only the catalog checks (`product-not-in-catalog` and friends) need to see this
    shape, since none of them read card copy -- see `bound_products`.
    """
    if action.get('type') != 'purchase':
        return None
    prod = (action.get('payload') or {}).get('product') or {}
    if prod.get('type') != 'const':
        return None
    return (prod.get('value') or {}).get('id')


def bound_products(config):
    """(screen id, element id, product id) for every product binding in the flow --
    a `product` element's own props, OR a `const` purchase action carried by an
    element's interactions. Catalog-only consumer: this is the shape the four
    catalog checks need (none of them read card copy). `check_period_claim` and
    `check_price_integrity` need card copy, which only the element shape has, so
    they call `_element_product_id` directly and never this function -- see its
    docstring for why that split is deliberate, not an oversight.

    Deduplicated per (screen, element, product): an element carrying both a
    `product` prop AND a `const` purchase action for the same id would otherwise
    report the same binding site twice.
    """
    out = []
    for s, eid, e in elements(config):
        seen_here = set()
        pid = _element_product_id(e)
        if pid:
            out.append((s['id'], eid, pid))
            seen_here.add(pid)
        for _, a in actions_of(e):
            cpid = _const_purchase_product_id(a)
            if cpid and cpid not in seen_here:
                out.append((s['id'], eid, cpid))
                seen_here.add(cpid)
    return out


def _format_sites(sites, cap=3):
    """Render binding sites as 'scr_a/el_1, scr_b/el_2 and 3 more'.

    Caps the printed list so a product bound across many screens still produces a
    readable message, while the count after 'and' accounts for every site that did
    not make the cut.
    """
    shown = [f'{sid}/{eid}' for sid, eid in sites[:cap]]
    extra = len(sites) - len(shown)
    text = ', '.join(shown)
    return f'{text} and {extra} more' if extra > 0 else text


def check_products_catalog(config, catalog, stores):
    """Cross-reference bound products against the live catalog.

    `stores` is the set of stores the app ships on, or None when unknown. Unknown is why
    a store gap is a question rather than a blocker -- the audit cannot see the app.

    `base_plan_id` is read ONLY off a `play_store` entry -- it is a Google Play concept
    and is null on essentially every `app_store` entry, so reading it unscoped fires on
    the whole catalog.

    All four checks below dedup PER PRODUCT, not per binding: the same product bound
    on two elements must produce one finding, not two, and that finding's message
    names every binding site (`_format_sites`) so fixing the deduped finding does not
    leave the user unaware that a second screen binds the same broken product. This
    used to be inconsistent -- `product-not-in-catalog` fired once per binding because
    its `continue` sat before the `seen` check, while the other three checks deduped
    but silently dropped every site after the first. Grouping by product id up front
    fixes both: dedup is now uniform, and no location is ever silently dropped.
    """
    out = []
    if catalog is None:
        if bound_products(config):
            out.append(finding(
                'question', 'products', 'catalog-not-fetched',
                'no product catalog was supplied, so nothing about the bound products '
                'could be verified',
                'Re-run the audit with your product catalog included so the bound '
                'products can be checked.'))
        return out
    by_id = {p['id']: p for p in catalog}
    by_pid = {}
    for sid, eid, pid in bound_products(config):
        by_pid.setdefault(pid, []).append((sid, eid))

    for pid, sites in by_pid.items():
        first_sid, first_eid = sites[0]
        sites_str = _format_sites(sites)
        prod = by_id.get(pid)
        if prod is None:
            out.append(finding(
                'blocker', 'products', 'product-not-in-catalog',
                f'bound product {pid} does not exist in this app\'s catalog, so the '
                f'purchase cannot complete (bound at {sites_str})',
                'Bind a product from `adapty products list`, or create the product in '
                'the dashboard first.', first_sid, first_eid))
            continue
        title = prod.get('title') or pid
        vendors = prod.get('vendor_products') or {}
        if not prod.get('access_level_id'):
            out.append(finding(
                'blocker', 'products', 'product-no-access-level',
                f'{title} has no access level, so a purchase would grant nothing '
                f'(bound at {sites_str})',
                'Attach an access level to the product in the dashboard.',
                first_sid, first_eid))
        if not vendors:
            out.append(finding(
                'blocker', 'products', 'product-store-gap',
                f'{title} has no store binding at all, so it cannot be purchased '
                f'anywhere (bound at {sites_str})',
                'Bind the product to App Store and/or Google Play in the dashboard.',
                first_sid, first_eid))
        else:
            missing = {'ios': 'app_store', 'android': 'play_store'}
            for want, key in missing.items():
                if key in vendors:
                    continue
                if stores is None:
                    out.append(finding(
                        'question', 'products', 'product-store-gap',
                        f'{title} has no {key} entry. If you ship on '
                        f'{"Android" if want == "android" else "iOS"}, this purchase '
                        f'cannot complete there — tell me and this is a blocker '
                        f'(bound at {sites_str})',
                        f'Add the {key} binding in the dashboard.',
                        first_sid, first_eid))
                elif want in stores:
                    out.append(finding(
                        'blocker', 'products', 'product-store-gap',
                        f'{title} has no {key} entry but the app ships on {want}, so '
                        f'the purchase cannot complete there (bound at {sites_str})',
                        f'Add the {key} binding in the dashboard.',
                        first_sid, first_eid))
            play = vendors.get('play_store')
            if play and not play.get('base_plan_id'):
                out.append(finding(
                    'blocker', 'products', 'play-base-plan-missing',
                    f'{title} has a play_store entry with no base_plan_id; Google needs '
                    f'product id plus base plan id to complete a purchase '
                    f'(bound at {sites_str})',
                    'Set the base plan id on the Google Play binding.',
                    first_sid, first_eid))
    return out


# A trial duration is not a billing period: "7 Days Trial" read as weekly, which broke
# the naive version on a real flow. Stripped before any period matching.
TRIAL_RE = re.compile(r'\b\d+\s*(?:-|\s)?\s*(?:day|week|month)s?\s*(?:free\s*)?trial\b'
                      r'|\btrial\b', re.I)

# Ordered longest-unit-first. A multiplied unit ("12 mo") names the OUTER period and must
# be consumed before the bare unit ("mo") can claim it -- otherwise "12 mo • $79.99" on an
# annual product reads as monthly. `once` is deliberately absent: "Billed once a year"
# read as lifetime.
#
# `[\s-]*` between the digit and the unit, not `\s*` -- real copy hyphenates ("12-month
# plan", "3-month plan", "52-week plan") and a bare `\s*` never matches a hyphen, so
# every one of those fell through to the bare-unit rule below and read as monthly/
# weekly instead of annual/quarterly. The bare monthly/weekly rules also gained the
# plural (`months`, `weeks`) -- without it "12-months" matched no rule at all rather
# than falling through, because "month"/"mo"/"mos" all fail their own trailing `\b`
# against the extra trailing "s". The ordering and destructive consumption are
# unchanged: "12 months" is still eaten whole by the annual multiplied-unit rule
# before the bare monthly rule ever sees it, so it still resolves to {'annual'} alone.
PERIOD_RULES = [
    ('annual',    r'\b(?:12[\s-]*(?:mo|mos|month|months)|52[\s-]*(?:wk|weeks?))\b'),
    ('quarterly', r'\b(?:3[\s-]*(?:mo|mos|month|months)|13[\s-]*(?:wk|weeks?))\b'),
    ('annual',    r'\b(?:year|yearly|annual|annually|yr)\b|/\s*(?:yr|year)'),
    ('quarterly', r'\b(?:quarter|quarterly)\b'),
    ('monthly',   r'\b(?:month|months|monthly|mo|mos)\b|/\s*(?:mo|month)'),
    ('weekly',    r'\b(?:week|weeks|weekly|wk)\b|/\s*(?:wk|week)'),
    ('lifetime',  r'\b(?:lifetime|one[ -]?time)\b'),
]


# A period word is a genuine billing CLAIM only in a price/billing context -- never
# merely present anywhere in the card's copy. Reproduced: rewriting a real annual
# card's text to "Pro | Weekly progress reports" read as a WEEKLY period claim purely
# because the benefit sentence contains the word "weekly"; `period_terms` also
# returned {monthly} for "Cancel anytime, no monthly fees" (near-boilerplate),
# {annual} for "Save 50% a year" (a savings claim, not a period), and {monthly} for
# "Your monthly report" (a feature, not a plan). The real corpus is terse ("Yearly",
# "Monthly", "12 mo • $79.99"), which is exactly why calibration never caught this --
# every real card's period word WAS the whole point of its segment, so "present
# anywhere" and "in billing context" happened to coincide.
#
# `card_text` joins a card's descendant text elements with " | ", so context is
# judged per SEGMENT, split on that same separator -- one product card's own price
# line must not lend a neighbouring benefit line's unrelated period word legitimacy
# just because `card_text` concatenated them into one blob. Within a segment, a
# period match counts as a claim when EITHER removing the matched text leaves
# nothing but whitespace/punctuation or a bare plan noun (`monthly` alone, or
# `12-month plan`'s trailing `plan` -- the segment names nothing else), OR the
# segment carries a currency amount (`MONEY_RE`), a `/` rate marker (already part of
# several `PERIOD_RULES` alternatives, e.g. `/mo`), or a billing verb (`billed`,
# `per`, `every`, `renews`). A price-VARIABLE's own text never reaches this
# function at all -- `card_text` calls `flat_text`, which renders a `variable` node
# as `''`, so an empty segment is dropped by `card_text` before the join; there is
# no literal "adjacent to a price variable" case left to detect here.
PLAN_LABEL_TRAILERS = {'plan'}
BILLING_VERB_RE = re.compile(r'\b(?:billed|per|every|renews?)\b', re.I)


def _billing_context(segment, start, end):
    """True if the period match `segment[start:end]` sits in a price/billing
    context, per the module comment above `period_terms`."""
    leftover = (segment[:start] + segment[end:]).strip(' \t-—|·/.,')
    if not leftover or leftover.lower() in PLAN_LABEL_TRAILERS:
        return True
    if MONEY_RE.search(segment) or '/' in segment:
        return True
    return bool(BILLING_VERB_RE.search(segment))


def period_terms(text):
    """The billing periods this copy claims, in a price/billing context (see the
    module comment above). Longest unit first, trials stripped, one card-text
    segment at a time."""
    found = set()
    for raw in (text or '').split(' | '):
        segment = TRIAL_RE.sub(' ', raw)
        rest = segment
        for name, rx in PERIOD_RULES:
            for m in list(re.finditer(rx, rest, re.I)):
                if _billing_context(segment, m.start(), m.end()):
                    found.add(name)
                rest = rest[:m.start()] + ' ' * (m.end() - m.start()) + rest[m.end():]
    return found


def _descendants(node):
    ids = [node.get('id')]
    for ch in (node.get('children') or []):
        ids += _descendants(ch)
    return [i for i in ids if i]


def _find_node(node, target):
    if node.get('id') == target:
        return node
    for ch in (node.get('children') or []):
        got = _find_node(ch, target)
        if got:
            return got
    return None


def card_text(config, screen, element_id, locale=None):
    """A product card's own text plus every descendant's, joined.

    A card's price and period live in sibling `text` elements linked through
    `hierarchy`, not nested inside the product element's props.
    """
    els = (screen.get('elements') or {})
    emap, hier = els.get('map') or {}, els.get('hierarchy') or {}
    node = _find_node(hier, element_id)
    ids = _descendants(node) if node else [element_id]
    parts = []
    for eid in ids:
        e = emap.get(eid) or {}
        if e.get('type') != 'text':
            continue
        got = flat_text((e.get('props') or {}).get('content'), locale)
        if got:
            parts.append(got)
    return ' | '.join(parts)


def check_period_claim(config, catalog):
    """A finding is a card naming EXACTLY ONE period term that disagrees.

    A card naming both (`$6.67/MO` beside `12 mo • $79.99`) is the legitimate
    equivalent-price pattern -- 4 of 8 real cards -- so presence is not the test, arity
    is.
    """
    out = []
    if not catalog:
        return out
    by_id = {p['id']: p for p in catalog}
    dl = default_locale(config)
    for s in config.get('screens') or []:
        for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
            pid = _element_product_id(e)
            if not pid or pid not in by_id:
                continue
            actual = by_id[pid].get('period')
            if not actual:
                continue
            claimed = period_terms(card_text(config, s, eid, dl))
            if len(claimed) == 1 and actual not in claimed:
                said = next(iter(claimed))
                out.append(finding(
                    'blocker', 'products', 'period-claim-mismatch',
                    f'this card says {said} but {by_id[pid].get("title") or pid} is '
                    f'{actual} — the user is shown a period the product does not have',
                    f'Either bind the {said} product, or change the copy to {actual}.',
                    s['id'], eid))
    return out


# symbol+digits, or digits+ISO code
MONEY_RE = re.compile(r'(?:[$€£¥₹₽]\s?\d[\d.,]*)'
                      r'|(?:\d[\d.,]*\s?(?:USD|EUR|GBP|RUB|INR)\b)')
VAR_RE = re.compile(r'\b([0-9a-fA-F-]{36})\.([A-Za-z_]+)\b')


def _element_blobs(config, screen, element_id, locale):
    """Per-descendant-element text blobs, variable ids rendered inline.

    Returns `[(eid, blob), ...]` for every descendant `text` element with non-empty
    content -- one entry PER ELEMENT, not one joined string for the whole card. This
    is what lets `hardcoded-price` judge a literal against the specific element that
    carries it (see the scoping comment on `check_price_integrity`).

    A price element's entire content is a single `variable` node -- `flat_text`
    returns '' for it by design, which is exactly why `card_text` cannot be reused
    here. This walk renders the variable's id inline instead of dropping it, which is
    also why the id itself must never be fed into `period_terms`: a variable id looks
    like `<uuid>.prod_price_per_month`, and the word `month` in it is not a period
    claim written by a human.
    """
    els = (screen.get('elements') or {})
    emap, hier = els.get('map') or {}, els.get('hierarchy') or {}
    node = _find_node(hier, element_id)
    ids = _descendants(node) if node else [element_id]
    out = []
    for eid in ids:
        e = emap.get(eid) or {}
        if e.get('type') != 'text':
            continue
        cont = (e.get('props') or {}).get('content')
        val = cont
        if isinstance(cont, dict) and 'values' in cont:
            vals = cont['values'] or {}
            val = vals.get(locale) if locale in vals else next(iter(vals.values()), None)
        parts = []

        def walk(n):
            if isinstance(n, dict):
                if n.get('type') == 'text':
                    parts.append(n.get('text', ''))
                elif n.get('type') == 'variable':
                    parts.append(' ' + str((n.get('attrs') or {}).get('variableId', '')) + ' ')
                for x in (n.get('content') or []):
                    walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)
            elif isinstance(n, str):
                parts.append(n)
        walk(val)
        joined = ' '.join(''.join(parts).split())
        if joined:
            out.append((eid, joined))
    return out


def _card_blob(config, screen, element_id, locale):
    """Whole-card text with variable ids rendered inline, so `foreign-price-variable`
    reads one string. `foreign-price-variable` is deliberately CARD-scoped -- see the
    scoping comment on `check_price_integrity` for why it must stay that way while
    `hardcoded-price` (using `_element_blobs` instead) is element-scoped.
    """
    return ' | '.join(b for _, b in _element_blobs(config, screen, element_id, locale))


def check_price_integrity(config, catalog):
    """Two defects, and they are scoped DIFFERENTLY on purpose -- do not "fix" that.

    `foreign-price-variable`: a card whose ONLY price variable(s) name a DIFFERENT
    product than the one it is bound to. This one stays CARD-scoped, because its
    question is arity over the whole card -- the same logic already established for
    `period-claim-mismatch`: does the card reference its OWN product's price
    variable ANYWHERE among its elements. A card referencing a foreign price variable
    ALONGSIDE its own is the was/now comparison pattern, not a defect: measured on a
    real shipped card that sells its own product and additionally shows a
    struck-through rate from another plan for comparison, purchase binding correct
    throughout. Flagging that trains a user to ignore this whole finding family. Only
    a card with NO reference to its own product's price variable is actually showing
    the wrong price -- that is the real defect this check exists to catch, and it
    stays a blocker.

    `hardcoded-price`: a plain currency literal with no price variable backing it.
    This one is ELEMENT-scoped: it judges each currency literal against the specific
    element that carries it, never against the whole card. A card-scoped test asks
    "does this card use variables at all" when the question that matters is "is THIS
    literal backed by a variable" -- measured false negative: keep a real card's
    price variable, add a sibling text element reading "was $99.99", and the
    card-scoped version reported 0 findings while the fabricated price shipped. A
    real price variable on one element must never license a fabricated literal on a
    sibling. A zero literal ("$0 during trial") is legitimate copy and is excluded --
    only a NON-ZERO literal counts, at either scope.
    """
    out = []
    by_id = {p['id']: p for p in (catalog or [])}
    dl = default_locale(config)
    for s in config.get('screens') or []:
        for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
            pid = _element_product_id(e)
            if not pid:
                continue

            # foreign-price-variable: card-scoped, arity over the whole card's blob.
            blob = _card_blob(config, s, eid, dl)
            refs = {m.group(1) for m in VAR_RE.finditer(blob)}
            foreign = refs - {pid}
            if foreign and pid not in refs:
                names = ', '.join((by_id.get(f, {}).get('title') or f) for f in sorted(foreign))
                out.append(finding(
                    'blocker', 'products', 'foreign-price-variable',
                    f'this card is bound to {by_id.get(pid, {}).get("title") or pid} but '
                    f'shows a price variable for {names}, so it displays the wrong price',
                    'Point the price variable at the product this card sells.',
                    s['id'], eid))

            # hardcoded-price: element-scoped -- judge each descendant text element
            # against ITS OWN blob, not the card's. Anchored at the element that
            # actually carries the literal, not at the card's own element id.
            for lit_eid, elblob in _element_blobs(config, s, eid, dl):
                elrefs = {m.group(1) for m in VAR_RE.finditer(elblob)}
                money = [m.group(0) for m in MONEY_RE.finditer(elblob)]
                nonzero = [m for m in money if re.sub(r'[^\d]', '', m).strip('0')]
                if nonzero and not elrefs:
                    out.append(finding(
                        'blocker', 'products', 'hardcoded-price',
                        f'a currency amount ({nonzero[0]}) is written into the copy '
                        f'here instead of coming from a price variable -- if it is '
                        f'meant to show a price, it will not localise currency and '
                        f'will not follow a store price change',
                        'If this is a price, replace the literal with a price '
                        'variable for this product. If it is a savings or '
                        'comparison figure, confirm it does not need to track a '
                        'store price change either.',
                        s['id'], lit_eid))
    return out


# A localizable field carrying only a `variable`/`token`/`image` node has no literal
# text by construction -- a price element's whole content IS a `variable` node. A
# literal-text-only presence test reports every price on every paywall as empty, which
# is the exact bug that made an earlier version of `check_localization` miss its own
# injected defect. An empty `text` node is deliberately NOT in this list: a paragraph
# containing `{'type': 'text', 'text': ''}` carries no content at all and must still
# count as empty.
SUBSTANTIVE_NODES = ('variable', 'token', 'image')


def _localizable_values(config, locales):
    """Every localizable `values` map keyed by at least one declared locale."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            vals = o.get('values')
            if isinstance(vals, dict) and set(vals) & set(locales):
                found.append(vals)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(config)
    return found


def _has_content(value, locale):
    """A value counts as present if it carries literal text OR a variable/token/image
    node. See `SUBSTANTIVE_NODES` above for why -- get this wrong and the check is
    worthless, because it either misses a truly empty translation or flags every price.

    A per-locale IMAGE ELEMENT value is a second trap of the exact same shape, and it
    was measured firing an `empty-translation` false positive on two real, working
    fixtures (`onboarding-quiz-paywall.json`, `vpn-timer-draft.json`) before this
    clause existed: the value there is a bare `{'id': ..., 'url': ...}` object with
    NO `type` discriminator at all (`verify-config.py`'s own image check reads the
    same shape), so `node_kinds`/`flat_text` -- which only understand richtext-shaped
    nodes (`type` + `content`) -- see nothing and call it empty. A truthy `url` is
    the signal; an unfilled slot is `{}` and stays correctly empty.
    """
    if flat_text(value, locale):
        return True
    if any(k in SUBSTANTIVE_NODES for k in node_kinds(value, locale)):
        return True
    return isinstance(value, dict) and bool(value.get('url'))


def locale_coverage(config):
    """Per-locale coverage stats and examples, over every localizable value in the flow.

    `stat[code]` is `{'missing', 'empty', 'same'}` int counts: `missing` is the value
    has no key for this locale at all (already reported, per-field, by
    `verify-config.py` -- counted here only so Task 10's report can build the coverage
    table, never turned into a finding of its own by `check_localization`); `empty` is
    the key exists but carries no substantive content (`_has_content` says no); `same`
    is the value is identical to the base locale's text (a proper noun, or a missed
    translation -- `check_localization` cannot tell which, so it is a risk, not a
    blocker). `examples[code]` holds up to 4 sample base-locale strings behind a
    `same` hit, for the report to show.
    """
    locales = [l.get('code') for l in (config.get('locales') or []) if l.get('code')]
    base = default_locale(config)
    stat = {l: {'missing': 0, 'empty': 0, 'same': 0} for l in locales}
    examples = {l: [] for l in locales}
    for vals in _localizable_values(config, locales):
        base_text = flat_text(vals.get(base), base) if base in vals else ''
        for code in locales:
            if code not in vals:
                stat[code]['missing'] += 1
                continue
            if not _has_content(vals[code], code):
                stat[code]['empty'] += 1
                continue
            if code != base and base_text and flat_text(vals[code], code) == base_text \
                    and len(base_text) > 3:
                stat[code]['same'] += 1
                if len(examples[code]) < 4:
                    examples[code].append(base_text[:40])
    return stat, examples


def check_localization(config):
    """`empty-translation` and `locale-entirely-empty` are blockers -- a user in that
    locale sees a blank field, or a whole language that was declared and never filled.
    `untranslated` is different in kind, not just severity: matching the base locale is
    not itself wrong (a brand name is SUPPOSED to be identical everywhere), so it can
    only ever be a risk, and it is reported ONCE for the whole flow rather than once
    per locale.

    That last point is a deliberate departure from the plan this check was written
    from: appending one `untranslated` finding per locale double-counts a value that
    is identical across every non-base locale (this fixture's two brand-name hits are
    identical in BOTH `sr` and `sr-Latn`), and the coverage table already carries the
    per-locale breakdown -- a second, per-locale finding would just restate it.
    """
    out = []
    locales = [l.get('code') for l in (config.get('locales') or []) if l.get('code')]
    if not locales:
        return out
    base = default_locale(config)
    stat, examples = locale_coverage(config)
    total = len(_localizable_values(config, locales))

    for code in locales:
        s = stat[code]
        if s['empty']:
            out.append(finding(
                'blocker', 'localization', 'empty-translation',
                f'{code}: {s["empty"]} field(s) have a value with no content at all, so '
                f'the screen shows nothing there in {code}',
                f'Fill the {code} values, or remove {code} from the flow\'s locales.'))
        if total and s['missing'] == total and code != base:
            out.append(finding(
                'blocker', 'localization', 'locale-entirely-empty',
                f'{code} is declared but has no values anywhere in the flow',
                f'Translate the flow into {code}, or remove it from locales.'))

    # Grouped, once for the whole flow -- see the docstring above for why.
    hit_locales = [code for code in locales if code != base and stat[code]['same']]
    if hit_locales:
        seen = []
        for code in hit_locales:
            for ex in examples[code]:
                if ex not in seen:
                    seen.append(ex)
        counts = ', '.join(f'{code}: {stat[code]["same"]}' for code in hit_locales)
        shown = ', '.join(repr(x) for x in seen[:4])
        out.append(finding(
            'risk', 'localization', 'untranslated',
            f'value(s) identical to the base locale ({base}) elsewhere in the flow '
            f'({counts}) -- for example {shown}. Brand names and product names are '
            f'expected here; check whether the rest is a missed translation.',
            'Translate anything in that list that is not a proper noun.'))
    return out


# Anchored or multi-word on purpose. A bare word list flags real copy: "Sample a new
# workout every week" is a legitimate headline, so `sample` alone cannot be a signal.
PLACEHOLDER_RE = re.compile(
    r'lorem ipsum'
    r'|\byour (?:text|headline|title|copy|value) here\b'
    r'|^(?:text|title|subtitle|button|label|heading|placeholder)$'
    r'|\bTODO\b|\bTBD\b|\bFIXME\b'
    r'|\bplaceholder text\b', re.I)


def check_placeholders(config):
    out = []
    dl = default_locale(config)
    for s, eid, e in elements(config):
        txt = flat_text((e.get('props') or {}).get('content'), dl)
        if txt and PLACEHOLDER_RE.search(txt.strip()):
            out.append(finding(
                'risk', 'placeholders', 'placeholder-copy',
                f'this looks like unfinished copy: {txt[:60]!r}',
                'Replace it with the real wording.', s['id'], eid))
    return out


def _variable_refs(config):
    """Every `variableId` value referenced anywhere in the config as a real
    consumption site -- a `var` predicate operand (`{'type': 'var', 'variableId':
    ...}`), a `purchase` action's dynamic product, or a rich-text `variable` node's
    `attrs`. Walked structurally over the parsed document rather than over a
    serialized blob: a substring scan also matches a vid that happens to be a
    substring of an unrelated string, and undercounts nothing here since every
    consumption site puts the id under a `variableId` key.

    Skips a `setVariable` action node entirely (not just its `payload`), so the
    assignment that PRODUCES a variable is never mistaken for a site that READS one
    -- whether that action names its own target under `payload.id` or
    `payload.variableId`.
    """
    refs = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get('type') == 'setVariable':
                return
            vid = n.get('variableId')
            if isinstance(vid, str):
                refs.add(vid)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(config)
    return refs


def check_variables(config):
    """A producer nobody consumes. `verify-config.py` already owns the reverse (a
    consumer with no producer), so only this direction is checked here.

    Scoped to explicit `setVariable` actions only -- deliberately narrower than an
    earlier draft, which also treated any element's `groupId` as a producer of
    `<groupId>.selectedOptionId`. That fired on every real, shipped fixture that
    has a group, and the reason is that the variable a group implies is not
    decidable from the config alone: a product group's is
    `<groupId>.selectedProduct` (`onboarding-quiz-paywall.json`'s `products` group,
    `comparison-paywall.json`'s), a `tab-item` group exposes no readable variable
    at all (`tabs-paywall.json`'s three-member `tabs` group switches visible
    content natively), and a single `selectable` sharing a `groupId` with no other
    member is a plain toggle, not a choice with a reader to find
    (`onboarding-multilocale.json`'s one-member `notify` group). Three different
    real shapes, all of them fine, and no rule short of a fixture-specific
    exception separated them -- so this check stays on the one producer kind the
    config states unambiguously.
    """
    out = []
    produced = {}
    for s, eid, e in elements(config):
        for _, a in actions_of(e):
            if a.get('type') == 'setVariable':
                payload = a.get('payload') or {}
                vid = payload.get('id') or payload.get('variableId')
                if vid:
                    produced.setdefault(vid, (s['id'], eid))
    if not produced:
        return out
    refs = _variable_refs(config)
    for vid, (sid, eid) in produced.items():
        if vid not in refs:
            out.append(finding(
                'risk', 'variables', 'variable-no-consumer',
                f'variable {vid!r} is set but never read anywhere in the flow',
                'Use it in a condition or a text field, or remove the action that '
                'sets it.', sid, eid))
    return out


def audit(config, catalog=None, stores=None):
    findings = []
    findings += check_triggers(config)
    findings += check_compliance(config)
    findings += check_products_catalog(config, catalog, stores)
    findings += check_period_claim(config, catalog)
    findings += check_price_integrity(config, catalog)
    findings += check_localization(config)
    findings += check_placeholders(config)
    findings += check_variables(config)
    return findings


def check_meta(meta):
    """Findings about the flow's dashboard metadata rather than its config -- the
    NAME and STATUS live in `flows list` output, not in the config, so neither can be
    reached from inside `audit()`. Wired into `main()` after `audit()` runs.
    """
    out = []
    name = (meta or {}).get('name') or ''
    if name.strip().lower() in ('untitled', 'untitled flow', 'new flow', ''):
        if name:
            out.append(finding(
                'question', 'placeholders', 'flow-untitled',
                f'the flow is still called {name!r}, which usually means it was never '
                f'named',
                'Rename it in the dashboard so your team can find it.'))
    status = (meta or {}).get('status') or ''
    if status == 'publication_failed':
        out.append(finding(
            'question', 'placeholders', 'publication-failed',
            'the dashboard reports this flow as publication_failed -- the last '
            'attempt to publish it did not go through. No check in this audit '
            'explains why; do not guess a cause here.',
            'Open the flow in the Flow Builder -- it will show the real reason the '
            'publish failed.'))
    return out


ORDER = {'blocker': 0, 'risk': 1, 'question': 2}
HEADINGS = {'blocker': 'BLOCKERS', 'risk': 'RISKS', 'question': 'COULD NOT CHECK'}

# A short, human label per check -- a few words, no colon-clauses -- for the verdict
# line ONLY. The full message stays in the finding row below it; the verdict line is
# the one thing a client is guaranteed to read, so it names the FAMILY of defect, not
# a slice of prose. Derived from the check name, never from the message text.
CHECK_LABELS = {
    'dead-affordance': 'dead affordance row',
    # `dead-affordance-merged` sets its own `_label` at creation time (from whichever
    # of `MERGE_ORDER`'s checks it absorbed), so `_verdict_labels`'s
    # `f.get('_label') or CHECK_LABELS.get(...)` fallback never reaches this entry
    # today -- it exists so a future change that ever constructs one WITHOUT `_label`
    # set still prints a real label instead of the raw check name.
    'dead-affordance-merged': 'dead affordance row',
    'action-nothing': 'unwired action',
    'openurl-no-url': 'broken link action',
    'interaction-no-actions': 'empty interaction',
    'no-restore': 'no restore action',
    'no-terms-link': 'no legal links',
    'no-privacy-link': 'no legal links',
    'no-escape-in-flow': 'no way off the flow',
    'no-escape-from-paywall': 'no way off the paywall',
    'catalog-not-fetched': 'catalog not fetched',
    'product-not-in-catalog': 'product not in catalog',
    'product-no-access-level': 'product missing access level',
    'product-store-gap': 'missing store binding',
    'play-base-plan-missing': 'missing Play base plan',
    'period-claim-mismatch': 'wrong billing period',
    'foreign-price-variable': 'wrong price shown',
    'hardcoded-price': 'hardcoded price',
    'empty-translation': 'empty translation',
    'locale-entirely-empty': 'locale entirely empty',
    'untranslated': 'untranslated text',
    'placeholder-copy': 'placeholder copy',
    'variable-no-consumer': 'unused variable',
    'flow-untitled': 'flow untitled',
    'publication-failed': 'flow failed to publish',
}

# Plural forms that a naive trailing-'s' gets wrong (a leading noun, not the last
# word, needs to change). Anything absent from this dict falls back to a trailing
# 's' on the whole label, which is correct for every single-final-noun label above
# (`hardcoded price` -> `hardcoded prices`, `empty translation` -> `empty
# translations`).
PLURAL_OVERRIDES = {
    'product not in catalog': 'products not in catalog',
    'product missing access level': 'products missing access level',
    'wrong price shown': 'wrong prices shown',
    'locale entirely empty': 'locales entirely empty',
}

# Labels that are already a negation read correctly no matter how many times the
# underlying check fired -- "no legal links" is true whether one link is missing or
# both, so it is never counted. (Two distinct checks, `no-terms-link` and
# `no-privacy-link`, share this one label, which is exactly how a naive count-prefix
# produced the ungrammatical "2 no legal links".) A count only helps a countable
# noun, where pluralizing the label (via `PLURAL_OVERRIDES` or the trailing-'s'
# fallback) keeps it grammatical instead.
NEGATION_LABELS = {
    'no restore action',
    'no legal links',
    'no way off the flow',
    'no way off the paywall',
}


def _pluralize(label):
    if label in PLURAL_OVERRIDES:
        return PLURAL_OVERRIDES[label]
    return label if label.endswith('s') else label + 's'


def _verdict_labels(blockers, cap=4):
    """Distinct, short labels for the verdict line -- counting repeats where a count
    helps a countable noun (`2 hardcoded prices`), capped so a dozen blocker rows
    still fit on one line. A merged finding (see `_collapse_for_report`) carries its
    own `_label`, chosen by `MERGE_ORDER`, instead of the raw `check` name.

    A label in `NEGATION_LABELS` reads correctly whether it fired once or several
    times ("no legal links" is true regardless of how many links are missing), so it
    is printed once with no count prefix -- prefixing a count there ("2 no legal
    links") reads ungrammatically because the label already negates.
    """
    order, counts = [], {}
    for f in blockers:
        label = f.get('_label') or CHECK_LABELS.get(f['check'], f['check'])
        if label not in counts:
            counts[label] = 0
            order.append(label)
        counts[label] += 1
    parts = [
        (l if l in NEGATION_LABELS else
         (f'{counts[l]} {_pluralize(l)}' if counts[l] > 1 else l))
        for l in order
    ]
    shown = parts[:cap]
    extra = len(parts) - len(shown)
    return ', '.join(shown) + (f' +{extra} more' if extra > 0 else '')


# --- Report-only collapse of `dead-affordance` with the compliance blockers it
# already explains, AND of several SIBLING `dead-affordance` findings with each
# other. This lives entirely in the renderer -- `check_triggers` and
# `check_compliance` keep firing independently, which is what lets a flow that is
# missing a restore action but has NO dead-affordance row of its own still report its
# own separate `no-restore` blocker. Only `--report` output collapses; `--json` and
# `audit()` keep printing every finding the checks actually produced, which is what
# calibration (`tests/test-audit-flow.py`'s `of()` helper) reads.
AFFORDANCE_TO_CHECK = {'restore': 'no-restore', 'terms': 'no-terms-link',
                       'eula': 'no-terms-link', 'privacy': 'no-privacy-link'}
MERGE_ORDER = ('no-restore', 'no-terms-link', 'no-privacy-link')
BULLET_INFO = {
    'no-restore': ('no restorePurchases action anywhere in the flow', 'App Store 3.1.1'),
    'no-terms-link': ('no link to terms/EULA', 'App Store 3.1.2'),
    'no-privacy-link': ('no link to a privacy policy', 'App Store 3.1.2'),
}
LEGAL_NAME = {'no-terms-link': 'terms', 'no-privacy-link': 'privacy'}
# What to wire ONE element to, for the one-affordance fix line -- see
# `_merge_dead_affordance_group`'s `len(parsed) == 1, n == 1` branch and the sibling
# branch's per-check clause. Keyed the same as `BULLET_INFO`/`LEGAL_NAME`.
ACTION_PHRASE = {
    'no-restore': 'a restorePurchases action',
    'no-terms-link': 'an openUrl action pointing at your hosted terms URL',
    'no-privacy-link': 'an openUrl action pointing at your hosted privacy URL',
}
WORD_NUM = {1: 'one', 2: 'two', 3: 'three'}
DEAD_AFFORDANCE_RE = re.compile(r'^copy promises (.+?) but neither the element')


def _dead_raw_text(dead):
    """The literal copy a `dead-affordance` finding's message quotes, recovered by
    parsing `check_triggers`' own message text. A known, accepted coupling -- see
    the module docstring's note on it -- kept rather than threaded through the
    finding dict, which a contract test pins to an exact key set.
    """
    lit = re.search(r': (.*)$', dead['message'])
    try:
        return ast.literal_eval(lit.group(1)) if lit else ''
    except (ValueError, SyntaxError):
        return lit.group(1) if lit else ''


def _join_and(items):
    """'a' / 'a and b' / 'a, b and c' -- no Oxford comma, matching `render`'s own
    `blocker_nums` join."""
    items = list(items)
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + f' and {items[-1]}'


def _merge_dead_affordance_group(screen, parent, parsed, matched):
    """One finding covering every `dead-affordance` finding in `parsed` -- a list of
    `(raw_finding, named_words)` pairs that all share one screen and one parent
    element (or, when `parent` is None, a single pair that has no parent at all) --
    plus the compliance blockers named in `matched` (a subsequence of `MERGE_ORDER`).

    `len(parsed) == 1` is the original shape: one element whose OWN copy names
    several affordance words (`el_089T` reading "Restore purchase · Terms ·
    Privacy"). `len(parsed) > 1` is DEFECT 1's shape: several SIBLING elements
    under one parent, each naming exactly one word
    (`comparison-paywall.json`'s Restore/Terms/Privacy row). The two read and fix
    differently -- the first names ONE row and asks to split or wire IT; the second
    already has N separate rows and asks to wire EACH of them -- so the branch is on
    `len(parsed)`, not on `len(matched)` alone.
    """
    legal = [c for c in matched if c in LEGAL_NAME]
    trailer = ''
    if legal:
        trailer = ('\n   In fact openUrl appears nowhere in this flow, so no legal '
                   'link exists to wire to.')

    if len(parsed) == 1:
        dead, _named = parsed[0]
        where = ' / '.join(x for x in (dead['screen'], dead['element']) if x)
        raw_text = _dead_raw_text(dead)
        bullets = '\n'.join(
            f'     · {BULLET_INFO[c][0]:<50} → {BULLET_INFO[c][1]}'
            for c in matched)
        message = (
            'This row is dead text.\n'
            f'   {where} reads "{raw_text}" and carries no interaction at all. It '
            f'renders exactly like a working row, and none of the following work:\n'
            f'{bullets}{trailer}'
        )
        n_tap = len(matched)
        if n_tap == 1:
            # One element, one affordance: it already IS one tappable element, so
            # the fix is to wire it, not to "split" a row that is not split (DEFECT
            # 2 -- the old wording, "Split the row into one tappable element", was
            # nonsense for exactly this case).
            fix = f'Wire this element to {ACTION_PHRASE[matched[0]]}.'
        else:
            fix_bits = []
            if 'no-restore' in matched:
                fix_bits.append('one restorePurchases action')
            if legal:
                ln = len(legal)
                names = ' and '.join(LEGAL_NAME[c] for c in legal)
                fix_bits.append(f'{WORD_NUM.get(ln, str(ln))} openUrl action'
                                 f'{"s" if ln != 1 else ""} pointing at your hosted '
                                 f'{names} URL{"s" if ln != 1 else ""}')
            tap_count = WORD_NUM.get(n_tap, str(n_tap))
            fix = (f'Split the row into {tap_count} tappable elements — '
                   + ', '.join(fix_bits) + '.') if fix_bits else dead['fix']
        element = dead['element']
    else:
        by_eid = {d['element']: (d, words) for d, words in parsed}
        where = ' / '.join(x for x in (screen, parent) if x)
        rows = []
        covered = set()
        for c in matched:
            owners = [eid for eid, (_d, words) in by_eid.items()
                      if any(w in words for w, cc in AFFORDANCE_TO_CHECK.items()
                             if cc == c)]
            covered.update(owners)
            named_owners = _join_and(
                f'{eid} ("{_dead_raw_text(by_eid[eid][0])}")' for eid in owners)
            rows.append(f'     · {named_owners}: {BULLET_INFO[c][0]:<40} → '
                       f'{BULLET_INFO[c][1]}')
        # A sibling whose named word maps to no firing compliance check (e.g. a
        # "skip" label sitting in the same row) is still named here, so nothing in
        # the group is silently dropped from the finding.
        for eid, (d, _words) in by_eid.items():
            if eid not in covered:
                rows.append(f'     · {eid} ("{_dead_raw_text(d)}"): also carries no '
                           f'interaction, though no compliance check names it')
        bullets = '\n'.join(rows)
        elem_list = _join_and(
            f'{d["element"]} ("{_dead_raw_text(d)}")' for d, _words in parsed)
        n = len(parsed)
        message = (
            'This row is dead text.\n'
            f'   {where} groups {WORD_NUM.get(n, str(n))} sibling elements that '
            f'render like a working row and carry no interaction at all -- '
            f'{elem_list}. None of the following work:\n'
            f'{bullets}{trailer}'
        )
        fix_clauses = []
        for c in matched:
            owners = [eid for eid, (_d, words) in by_eid.items()
                      if any(w in words for w, cc in AFFORDANCE_TO_CHECK.items()
                             if cc == c)]
            if owners:
                fix_clauses.append(f'{_join_and(owners)} to {ACTION_PHRASE[c]}')
        fix = ('Wire ' + _join_and(fix_clauses) + '.') if fix_clauses else (
            'Wire each element to a real action.')
        element = parent

    # Carry the row's own screen/element forward -- the merged finding is still
    # about that one row (or that one group of sibling rows), and WHAT TO DO NEXT
    # names the screen/element for every flow edit, which this would otherwise be
    # the only one to leave blank.
    merged = finding('blocker', 'triggers', 'dead-affordance-merged', message, fix,
                      screen, element)
    merged['_label'] = CHECK_LABELS[next(c for c in MERGE_ORDER if c in matched)]
    return merged


def _collapse_for_report(findings, config):
    """Merge each `dead-affordance` blocker with the flow-wide compliance blockers it
    names and that are already firing, AND merge several SIBLING `dead-affordance`
    findings that share a parent element with each other first (DEFECT 1). Returns
    a new list; never mutates `findings`, and never touches a compliance finding
    that no dead row actually overlaps with.

    Sibling grouping is STRUCTURAL, not text-parsed: it walks the same
    `elements.hierarchy` tree `check_triggers`' own ancestor check uses (via
    `_parent_map`, over `config` -- the one piece of context `findings` alone does
    not carry) and groups STRICTLY by `(screen, parent element)`. Two dead rows on
    the same screen under DIFFERENT parents never merge -- a user sees those as
    separate rows -- and a dead-affordance finding whose element has no parent at
    all (the screen's own root) groups alone, since it cannot share a parent with
    anything. Only the per-finding AFFORDANCE WORD list still comes from parsing
    `check_triggers`' message text (`DEAD_AFFORDANCE_RE`) -- that coupling is a
    known, accepted limitation the finding dict's fixed key set does not allow
    fixing without a new key, so it stays as before.
    """
    compliance_pos = {}
    for i, f in enumerate(findings):
        if (f['severity'] == 'blocker' and f['screen'] is None
                and f['check'] in BULLET_INFO and f['check'] not in compliance_pos):
            compliance_pos[f['check']] = i

    screens_by_id = {s['id']: s for s in config.get('screens') or []}
    parent_maps = {}

    def parent_of(sid, eid):
        if sid not in parent_maps:
            scr = screens_by_id.get(sid) or {}
            hier = (scr.get('elements') or {}).get('hierarchy')
            parent_maps[sid] = _parent_map(hier)
        return parent_maps[sid].get(eid)

    groups = {}
    order = []
    for i, f in enumerate(findings):
        if f['severity'] != 'blocker' or f['check'] != 'dead-affordance':
            continue
        m = DEAD_AFFORDANCE_RE.match(f['message'])
        if not m:
            continue
        named = {w.strip() for w in m.group(1).split(',')}
        parent = parent_of(f['screen'], f['element'])
        key = ((f['screen'], parent) if parent is not None
               else (f['screen'], f['element'], '_solo'))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((i, f, named))

    consumed = set()
    replacements = {}
    for key in order:
        members = groups[key]
        named_union = set().union(*(named for _, _, named in members))
        matched = [c for c in MERGE_ORDER
                   if c in compliance_pos
                   and any(w in named_union for w, cc in AFFORDANCE_TO_CHECK.items()
                           if cc == c)]
        if not matched:
            continue
        for c in matched:
            consumed.add(compliance_pos[c])
        screen = key[0]
        parent = key[1] if len(key) == 2 else None
        parsed = [(f, named) for _, f, named in members]
        replacements[members[0][0]] = _merge_dead_affordance_group(
            screen, parent, parsed, matched)
        for idx, _f, _named in members[1:]:
            consumed.add(idx)

    return [replacements.get(i, f) for i, f in enumerate(findings) if i not in consumed]


# --- WHAT TO DO NEXT: route every (already-numbered) finding by WHO does the work,
# which is a different axis from severity -- severity says how bad it is, this says
# who has to act on it. Routed by CHECK NAME, never by parsing `message` text (that
# trap already exists once, in `DEAD_AFFORDANCE_RE` above; a second instance would be
# worse). An unmapped check name defaults to GROUP_FLOW rather than being dropped --
# a finding missing from this section entirely is the one failure this must never
# have, and "assume I can fix it in the config" is the least surprising wrong guess
# for a check nobody has taught this table about yet.
GROUP_ANSWER, GROUP_FLOW, GROUP_DASHBOARD, GROUP_OPTIONAL = 1, 2, 3, 4
NEXT_STEP_ORDER = (GROUP_ANSWER, GROUP_FLOW, GROUP_DASHBOARD, GROUP_OPTIONAL)
NEXT_STEP_HEADINGS = {
    GROUP_ANSWER: 'Answer these — they change the verdict',
    GROUP_FLOW: 'Change in the flow — I can do these',
    GROUP_DASHBOARD: 'Change in the Adapty dashboard — only you can',
    GROUP_OPTIONAL: 'Optional',
}

# Default group per check name: where the FIX lives, regardless of this instance's
# severity. `catalog-not-fetched` is deliberately absent -- its fix (re-run the audit
# with a catalog) is neither a flow edit, a dashboard action nor a judgement call, and
# the unmapped-default (GROUP_FLOW) is as reasonable a home for it as any of the three.
CHECK_TO_GROUP = {
    'dead-affordance': GROUP_FLOW,
    'dead-affordance-merged': GROUP_FLOW,
    'action-nothing': GROUP_FLOW,
    'openurl-no-url': GROUP_FLOW,
    'interaction-no-actions': GROUP_FLOW,
    'no-restore': GROUP_FLOW,
    'no-terms-link': GROUP_FLOW,
    'no-privacy-link': GROUP_FLOW,
    'no-escape-in-flow': GROUP_FLOW,
    'no-escape-from-paywall': GROUP_FLOW,
    'product-not-in-catalog': GROUP_DASHBOARD,
    'product-no-access-level': GROUP_DASHBOARD,
    'product-store-gap': GROUP_DASHBOARD,
    'play-base-plan-missing': GROUP_DASHBOARD,
    'period-claim-mismatch': GROUP_FLOW,
    'foreign-price-variable': GROUP_FLOW,
    'hardcoded-price': GROUP_FLOW,
    'empty-translation': GROUP_FLOW,
    'locale-entirely-empty': GROUP_FLOW,
    'untranslated': GROUP_OPTIONAL,
    'placeholder-copy': GROUP_FLOW,
    'variable-no-consumer': GROUP_FLOW,
    'flow-untitled': GROUP_DASHBOARD,
    'publication-failed': GROUP_DASHBOARD,
}

# Checks whose severity for THIS instance is a question that an answer could turn
# into a real blocker -- these get an EXTRA line in GROUP_ANSWER, on top of (never
# instead of) their normal `CHECK_TO_GROUP` line, exactly like `product-store-gap`
# does in the worked example: "do you ship on Android" up top, "add the play_store
# binding" still listed under the dashboard, because the fix is worth doing whether
# or not the answer turns out to matter. `flow-untitled`, `catalog-not-fetched` and
# `publication-failed` are deliberately excluded: none of them is a question whose
# ANSWER changes whether this finding is a problem -- a name is cosmetic, a missing
# catalog is just missing, and opening the Flow Builder does not change today's
# verdict, only tells the user why the last publish failed.
VERDICT_CONDITIONAL = {'no-terms-link', 'no-privacy-link', 'no-escape-in-flow',
                        'product-store-gap'}


def _next_step_groups(f):
    """Which WHAT TO DO NEXT group(s) get a line for this finding. Never zero."""
    groups = []
    if f['check'] in VERDICT_CONDITIONAL and f['severity'] == 'question':
        groups.append(GROUP_ANSWER)
    groups.append(CHECK_TO_GROUP.get(f['check'], GROUP_FLOW))
    return groups


def _answer_prompt(f, n):
    """The yes/no question for GROUP_ANSWER. Reads `message` for the one word that
    decides the phrasing (which store, which document) -- display detail, not a
    routing decision, so it does not reopen the message-parsing rule above.
    """
    check = f['check']
    if check == 'product-store-gap':
        store = 'Android' if 'ship on Android' in f['message'] else 'iOS'
        return f'Do you ship on {store}? If yes, finding {n} becomes a blocker.'
    if check in ('no-terms-link', 'no-privacy-link'):
        doc = 'terms' if check == 'no-terms-link' else 'privacy'
        return (f'Is one of the linked urls really your {doc} document? If not, '
                f'finding {n} needs a real one.')
    if check == 'no-escape-in-flow':
        return (f'Does the host app give users its own way to dismiss this flow? '
                f'If not, finding {n} needs a closeFlow action.')
    return f'See finding {n} — your answer may change the verdict.'


def _next_step_line(group, f, n):
    if group == GROUP_ANSWER:
        return _answer_prompt(f, n)
    where = ' / '.join(x for x in (f['screen'], f['element']) if x)
    ref = f'finding {n}' + (f', {where}' if where else '')
    return f"{f['fix'].rstrip('.')} ({ref})"


def render(findings, config, meta=None):
    """The user-facing report. See the design spec's `## What the skill prints` for
    the exact shape this reproduces: a verdict first line that is the answer on its
    own, BLOCKERS/RISKS/COULD NOT CHECK numbered continuously, a LOCALE COVERAGE
    table only when more than one locale is declared, a fixed BEFORE YOU SHIP
    reminder (never a numbered finding -- the placement link is unverifiable by
    design, not a question about this flow's data), a WHAT TO DO NEXT section that
    routes every numbered finding by who acts on it (present only when there is at
    least one finding, omitted entirely on a clean flow), and a closing offer to hand
    any blockers to `flow-generator`.

    Deliberately prints NO gate-status section: a passing `verify-config.py` or
    `flows config validate` run tells a client nothing, and a failing one is already
    reported as a blocker above, in the user's own terms.
    """
    meta = meta or {}
    findings = _collapse_for_report(findings, config)
    lines = []
    name = meta.get('name') or 'this flow'
    status = meta.get('status')
    lines.append(f'Flow: {name}' + (f'  ·  {status}' if status else ''))
    if meta.get('flow_id'):
        lines.append(f'https://app.adapty.io/flows/{meta["flow_id"]}/builder')
    locales = [l.get('code') for l in (config.get('locales') or []) if l.get('code')]
    n_products = len({pid for _, _, pid in bound_products(config)})
    n_screens = len(config.get('screens') or [])
    bits = [f'{n_screens} screen{"s" if n_screens != 1 else ""}']
    if locales:
        bits.append(f'{len(locales)} locale{"s" if len(locales) != 1 else ""}')
    if n_products:
        bits.append(f'{n_products} product{"s" if n_products != 1 else ""}')
    lines.append(' · '.join(bits))
    lines.append('')

    blockers = [f for f in findings if f['severity'] == 'blocker']
    questions = [f for f in findings if f['severity'] == 'question']
    if blockers:
        lines.append(f'NOT READY FOR PRODUCTION — {len(blockers)} '
                     f'blocker{"s" if len(blockers) != 1 else ""}: '
                     + _verdict_labels(blockers))
    elif questions:
        lines.append(f'READY, PENDING {len(questions)} CHECK'
                     f'{"S" if len(questions) != 1 else ""} I CANNOT MAKE')
    else:
        lines.append('READY FOR PRODUCTION')
    lines.append('')

    n = 0
    blocker_nums = []
    numbered = []
    for sev in ('blocker', 'risk', 'question'):
        group = [f for f in findings if f['severity'] == sev]
        if not group:
            continue
        lines += ['', HEADINGS[sev], '']
        for f in group:
            n += 1
            numbered.append((n, f))
            if sev == 'blocker':
                blocker_nums.append(n)
            where = ' / '.join(x for x in (f['screen'], f['element']) if x)
            lines.append(f'{n}. {f["message"]}')
            # The merged dead-affordance finding already opens with its own
            # `where` inside the message body (see `_merge_dead_affordance`); its
            # `screen`/`element` fields exist so WHAT TO DO NEXT can name them, not
            # to repeat the location a second time right above `Fix:`.
            if where and f['check'] != 'dead-affordance-merged':
                lines.append(f'   {where}')
            lines.append(f'   Fix: {f["fix"]}')
            lines.append('')

    if len(locales) > 1:
        stat, examples = locale_coverage(config)
        base = default_locale(config)
        total = len(_localizable_values(config, locales))
        lines += ['', f'LOCALE COVERAGE — {total} localizable fields', '',
                  f'  {"locale":12}{"missing":>9}{"empty":>8}{"same as " + str(base):>16}']
        for code in locales:
            s = stat[code]
            same = '-' if code == base else str(s['same'])
            lines.append(f'  {code:12}{s["missing"]:>9}{s["empty"]:>8}{same:>16}')
        lines.append('')

        # The narrative sentence the table alone can't carry: WHICH values repeat and
        # whether that's expected (a brand name), plus the missing/empty verdict --
        # "is everything localized" deserves a yes/no, not just a grid to read.
        same_total = sum(s['same'] for s in stat.values())
        gap_total = sum(s['missing'] + s['empty'] for s in stat.values())
        if same_total or gap_total:
            parts = []
            if same_total:
                uniq = []
                for code in locales:
                    for ex in examples[code]:
                        if ex not in uniq:
                            uniq.append(ex)
                if len(uniq) <= 1:
                    quoted = f'"{uniq[0]}"' if uniq else ''
                elif len(uniq) == 2:
                    quoted = f'"{uniq[0]}" and "{uniq[1]}"'
                else:
                    quoted = (', '.join(f'"{x}"' for x in uniq[:-1])
                              + f', and "{uniq[-1]}"')
                noun = 'value is' if len(uniq) == 1 else 'values are'
                parts.append(f'The {len(uniq)} identical {noun} {quoted} — a '
                             f'brand or product name, correctly left untranslated.')
            parts.append('Nothing is missing.' if not gap_total
                          else f'{gap_total} field(s) are missing or empty above.')
            lines.append('  ' + ' '.join(parts))
            lines.append('')

    lines += ['', 'BEFORE YOU SHIP', '',
              '  · Confirm this flow is attached to a placement. The CLI cannot see the',
              '    flow→placement link, so no audit can tell you whether your app can',
              '    reach this flow at all.', '']

    # WHAT TO DO NEXT: every finding is already numbered above (in `numbered`); this
    # section never restates a finding's own text, only points back at its number.
    # Silent on a clean flow -- there is nothing to route and no group would have a
    # single line, so the section itself is a no-op that would only add noise.
    if numbered:
        next_groups = {g: [] for g in NEXT_STEP_ORDER}
        for num, f in numbered:
            for g in _next_step_groups(f):
                next_groups[g].append(_next_step_line(g, f, num))
        # Unconditional whenever there is at least one finding to route -- the same
        # placement gap BEFORE YOU SHIP always names, listed here too because it is a
        # dashboard-only action like every other line in that group.
        next_groups[GROUP_DASHBOARD].append('Confirm the flow is attached to a placement.')
        lines += ['', 'WHAT TO DO NEXT', '']
        for g in NEXT_STEP_ORDER:
            bullets = next_groups[g]
            if not bullets:
                continue
            lines.append(f'  {NEXT_STEP_HEADINGS[g]}')
            for b in bullets:
                lines.append(f'    · {b}')
            lines.append('')

    # A fixed BEFORE YOU SHIP reminder is not a finding, and neither is this: the
    # offer is only about the numbered blockers above, so it is silent when there
    # are none to fix.
    if blocker_nums:
        label = 'blocker' if len(blocker_nums) == 1 else 'blockers'
        pronoun = 'it' if len(blocker_nums) == 1 else 'them'
        if len(blocker_nums) == 1:
            nums = str(blocker_nums[0])
        else:
            nums = (', '.join(str(x) for x in blocker_nums[:-1])
                    + f' and {blocker_nums[-1]}')
        lines += ['', f'Want me to fix {label} {nums}? I would hand {pronoun} to '
                  'flow-generator, which will show you a before/after render and ask '
                  'before writing anything.', '']

    return '\n'.join(lines)


VALUE_FLAGS = ('--catalog', '--stores', '--name', '--flow-id', '--status')


def parse_args(argv):
    """Split argv into (positional, flags). Returns (None, None, error) on a usage error.

    The positional is collected by INDEX as the scan proceeds, never by filtering argv
    for values that "look like" a flag's argument -- a positional equal in VALUE to a
    flag's value (e.g. the same path passed as both the config and the catalog) must
    not be mistaken for that flag's argument, or vice versa. A value-flag (`--catalog`,
    `--stores`) that is the last token, or is immediately followed by another `--flag`,
    has no value to take: that is a usage error, not a silent no-op.
    """
    positional = []
    flags = {}
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a.startswith('--'):
            if '=' in a:
                key, val = a.split('=', 1)
                flags[key] = val
                i += 1
            elif a in VALUE_FLAGS:
                if i + 1 >= n or argv[i + 1].startswith('--'):
                    return None, None, f'{a} requires a value'
                flags[a] = argv[i + 1]
                i += 2
            else:
                flags[a] = True
                i += 1
        else:
            positional.append(a)
            i += 1
    return positional, flags, None


def main(argv):
    args, flags, err = parse_args(argv)
    if err:
        print(err, file=sys.stderr)
        return 2
    if len(args) != 1:
        print(__doc__.strip().split('Usage:')[1].strip(), file=sys.stderr)
        return 2
    if flags.get('--report') and flags.get('--json'):
        print('--report and --json are mutually exclusive -- pick one output format',
              file=sys.stderr)
        return 2
    try:
        config = load_config(args[0])
        catalog = json.load(open(flags['--catalog'])) if isinstance(
            flags.get('--catalog'), str) else None
    except (OSError, ValueError) as exc:
        print(f'cannot read input: {exc}', file=sys.stderr)
        return 2
    if isinstance(catalog, dict):
        catalog = catalog.get('data') or []
    stores = (set(flags['--stores'].split(','))
              if isinstance(flags.get('--stores'), str) else None)

    findings = audit(config, catalog, stores)
    meta = {'name': flags.get('--name') if isinstance(flags.get('--name'), str) else None,
            'flow_id': flags.get('--flow-id') if isinstance(flags.get('--flow-id'), str)
            else None,
            'status': flags.get('--status') if isinstance(flags.get('--status'), str)
            else None}
    findings += check_meta(meta)
    if flags.get('--report'):
        print(render(findings, config, meta))
    elif flags.get('--json'):
        print(json.dumps({'findings': findings}, indent=1))
    else:
        for f in findings:
            where = ' / '.join(x for x in (f['screen'], f['element']) if x)
            print(f'{f["severity"].upper():9} [{f["family"]}] {f["message"]}'
                  + (f'\n          {where}' if where else ''))
        if not findings:
            print('no findings')
    return 1 if any(f['severity'] == 'blocker' for f in findings) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
