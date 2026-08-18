# Migration Reference: RevenueCat — Attribution and integrations

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

**One unified call replaces the per-integration setters — and there are typed constructors, so do not
build the key from a string.** RC exposes a dedicated method per tool: `setAdjustID`, `setAppsflyerID`,
`setFirebaseAppInstanceID`, and around thirty more. Adapty takes the same information through
`Adapty.setIntegrationIdentifier`, and `AdaptyIntegrationIdentifier` provides a named constructor per
supported tool.

Use those constructors. The key type also accepts a bare string literal, which means a typo is **not**
an error — it silently registers an identifier under a key nothing consumes, and the integration simply
never receives the user. A named constructor cannot be misspelled. Take the exact spellings from
`references/<platform>.md`.

One mapping needs a decision rather than a lookup: RC has a single OneSignal ID setter pair while Adapty
distinguishes a **subscription** ID from a **player** ID. Check which one the app is actually sending
before picking, and record the choice.

**Six integrations have no Adapty equivalent.** mParticle, Airship, CleverTap, Kochava, SolarEngine
(RC exposes three separate setters for it) and Appstack are all absent — none of them appears anywhere in
the Adapty SDK source. Where the app feeds one, the identifier call is deleted and the integration becomes
an open item in `ADAPTY_SETUP.md` (`references/migration.md` section 5, subsection 7), stating what the
app was sending and that the tool is not currently supported.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -iE "mparticle|airship|clevertap|kochava|solarengine|appstack"
```

A hit means one of the six now has an integration — read that page and correct this entry rather than
reporting a gap.

**Do not go hunting for the reverse direction.** Adapty supports several identifiers RC has no setter
for — AppMetrica, Branch, Pushwoosh. There is nothing to migrate there and their absence from the RC
code is not a finding.

**Push tokens are not accepted.** RC's `setPushToken` / `setPushTokenString` hand APNs tokens to
RevenueCat. Adapty has no equivalent. If the app relies on RC to reach users through a push provider,
that path breaks at migration and the user needs to know before shipping, not after.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -i "push token"
```

A hit means this row is stale — read the page and do not report a gap.

**Bulk conversion data maps; the individual UTM setters do not.** These two are easy to conflate, and
the distinction decides whether you delete code or port it.

- **A whole attribution payload from a known network maps directly.** RC's
  `setAppsFlyerConversionData` hands a dictionary to RevenueCat; `Adapty.updateAttribution` takes the
  same shape plus an `AdaptyAttributionSource` naming the network. Adapty ships sources for Apple Search
  Ads, Adjust, AppsFlyer, Branch, and Tenjin. This is a port, not a deletion.
- **Field-by-field campaign setters have no equivalent.** `setMediaSource`, `setCampaign`, `setAdGroup`,
  `setAd`, `setKeyword`, `setCreative` — six setters that let the RC app assemble attribution by hand.
  Adapty does its own matching and exposes the result on the profile instead, including which sources
  have been applied. Remove them, connect the network as an integration, and read from the profile.

So the same section can produce both outcomes in one file. Record which you did in `ADAPTY_SETUP.md`,
because the deletion half looks like lost functionality in a diff and the port half looks like nothing
happened. Two pages cover the two halves:
`https://adapty.io/docs/attribution-integration` and `https://adapty.io/docs/ua-attribution-data`.

**Custom attributes are readable, which RC's were not.** RC's attributes are write-only at the SDK
level. Adapty exposes them on the profile. Nothing breaks either way — but code that kept a shadow copy
locally purely because it could not read them back no longer needs to. Mention it if you see that
pattern; do not go looking for it.

**Custom attributes are validated by Adapty and were not validated by RC — this one throws.** RC's
`setAttributes` takes a dictionary and performs no client-side checking at all: any key, any value, any
number of them, no error. Adapty enforces limits and rejects what breaks them:

- **Keys** may be at most 30 characters and may contain only letters, digits, `.`, `_`, and `-`. A key
  with a space, a colon, an emoji, or RC's `$`-prefixed style is refused.
- **String values** must be non-empty and at most 50 characters.
- **At most 30 attributes** may carry a value.

None of these are enforced by the RC code you are migrating, so the app has probably never had a reason
to respect them. Audit the actual keys and values at the call sites rather than assuming they fit — a
long free-text value or a namespaced key is the common failure — and note anything that has to be
renamed or truncated in `ADAPTY_SETUP.md`, since truncating a value silently changes data the user's
analytics may depend on.

**And the delete idiom inverts.** In RC you clear an attribute by setting it to an empty string or `nil`.
In Adapty an empty value is exactly what validation rejects, and removal is a separate explicit
operation. So the RC line that *deletes* an attribute becomes an error at runtime if ported literally.
Grep for empty-string assignments in the attribute code specifically; they read as harmless and are not.
