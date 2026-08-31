# Capacitor SDK Integration Reference

Platform: Capacitor · Language: TypeScript / JavaScript · Targets: iOS + Android

## Prerequisites

- `@adapty/capacitor` **4.1+** for Flow Builder. 4.1 is the first stable 4.x release; a project that cannot meet the requirements below must stay on 3.x, which has no Flow Builder
- **Capacitor 8** for SDK 4.1+ and 3.16+. Capacitor 7 works only with SDK 3.15; Capacitor 6 and below are unsupported
- iOS 15.0+ and Android minSdk 24
- **Xcode 26 or later** to build for iOS on SDK 4.x — the native iOS SDK is built with Swift tools 6.2. This is a build-machine requirement, so check it before promising a v4 upgrade
- Android with Google Play Billing Library up to 8.x
- npm or yarn

**On SDK 4.x the iOS install is Swift Package Manager only** — the `AdaptyCapacitor.podspec` is gone, there is no Podfile, and the app's iOS project must use Capacitor's SPM integration. Any guidance about editing `ios/App/Podfile` applies to 3.x alone.

---

## Build verification

After each stage that writes code, run a sync and build to catch errors immediately rather than letting them pile up.

### Sync native platforms

```bash
# After installing or changing native plugins, always sync
npx cap sync
# Or sync a specific platform
npx cap sync ios
npx cap sync android
```

### Run on a device or simulator

```bash
# iOS simulator
npx cap run ios

# Android emulator or device
npx cap run android
```

### What to check in the output

**Sync succeeded, app launches** → proceed to next stage.

**`npx cap sync` fails:**
- "Package not found" or missing plugin errors → `npm install @adapty/capacitor` was not run, or `node_modules` is out of sync; run `npm install` then `npx cap sync` again
- Gradle errors on Android → check `android/app/build.gradle` for conflicting dependency versions; Adapty requires Google Play Billing Library up to 8.x
- iOS Podfile errors about minimum version → **SDK 3.x only.** Update `ios/App/Podfile` to `platform :ios, '15.0'`. On SDK 4.x there is no Podfile: set the deployment target to 15.0 in Xcode instead, and if the error is that the Adapty package cannot be resolved at all, the iOS project is not on Capacitor's SPM integration
- iOS build fails on Swift language/tools version → SDK 4.x needs **Xcode 26+**; an older Xcode cannot build the bundled native SDK

**App launches but crashes immediately:**
- Check native logs — iOS: Xcode console or `npx cap run ios` output; Android: `adb logcat` or Android Studio
- "Public API key is missing" → placeholder was not replaced with a real key
- "Adapty can only be activated once" → `__ignoreActivationOnFastRefresh` flag is missing in development; see Stage 1

**Android backup rules conflict:**
- Manifest merger failure mentioning `android:fullBackupContent` or `android:dataExtractionRules` → multiple SDKs have conflicting backup configs; see the backup rules troubleshooting section in the installation doc:
  ```bash
  curl -s https://adapty.io/docs/sdk-installation-capacitor.md
  ```

Rebuild after each fix. Do not move to the next stage until the app launches cleanly.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### constants.ts

Centralizes all Adapty config values. Using a constants file means the key and placement ID are set in one place — never scattered across components.

```typescript
// src/adapty/constants.ts

// Replace these before building — the app will fail to activate if left as-is
export const ADAPTY_PUBLIC_KEY = 'YOUR_PUBLIC_SDK_KEY';  // App settings → API keys → Public SDK key
export const PLACEMENT_ID = 'YOUR_PLACEMENT_ID';          // Adapty Dashboard → Placements
export const ACCESS_LEVEL_ID = 'premium';                 // Default access level; change if you use custom ones
```

Replace the placeholder strings with real values from Phase 3 output immediately.

### userStorage.ts (skip if app has no authentication)

Lightweight localStorage wrapper for the customer user ID. Pass this during `adapty.activate()` on launch so purchases are always attributed to the right profile.

```typescript
// src/adapty/userStorage.ts

const USER_ID_KEY = 'adapty.customerUserId';

export const userStorage = {
  getUserId(): string | null {
    return localStorage.getItem(USER_ID_KEY);
  },
  setUserId(userId: string): void {
    localStorage.setItem(USER_ID_KEY, userId);
  },
  clearUserId(): void {
    localStorage.removeItem(USER_ID_KEY);
  },
};
```

### AdaptyService (Angular service, Vue composable, or React context)

Central service that:
- Holds the current profile as reactive state
- Listens for real-time subscription updates via `adapty.addListener('onLatestProfileLoad')` — no polling needed
- Exposes a clean `isPremiumUser` property for gating content

**Angular service:**
```typescript
// src/app/services/adapty.service.ts
import { Injectable, signal } from '@angular/core';
import { adapty, type AdaptyProfile } from '@adapty/capacitor';
import { ACCESS_LEVEL_ID } from '../adapty/constants';

@Injectable({ providedIn: 'root' })
export class AdaptyService {
  profile = signal<AdaptyProfile | null>(null);

  get isPremiumUser(): boolean {
    return this.profile()?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false;
  }

  async reloadProfile(): Promise<void> {
    try {
      const p = await adapty.getProfile();
      this.profile.set(p);
    } catch (e) {
      console.warn('Adapty: failed to load profile', e);
    }
  }

  setupProfileListener(): void {
    adapty.addListener('onLatestProfileLoad', (data) => {
      this.profile.set(data.profile);
    });
  }
}
```

**Vue composable:**
```typescript
// src/composables/useAdapty.ts
import { ref } from 'vue';
import { adapty, type AdaptyProfile } from '@adapty/capacitor';
import { ACCESS_LEVEL_ID } from '../adapty/constants';

const profile = ref<AdaptyProfile | null>(null);

export function useAdapty() {
  const isPremiumUser = computed(
    () => profile.value?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false
  );

  async function reloadProfile() {
    try {
      profile.value = await adapty.getProfile();
    } catch (e) {
      console.warn('Adapty: failed to load profile', e);
    }
  }

  function setupProfileListener() {
    adapty.addListener('onLatestProfileLoad', (data) => {
      profile.value = data.profile;
    });
  }

  return { profile, isPremiumUser, reloadProfile, setupProfileListener };
}
```

**React context:**
```typescript
// src/context/AdaptyContext.tsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import { adapty, type AdaptyProfile } from '@adapty/capacitor';
import { ACCESS_LEVEL_ID } from '../adapty/constants';

interface AdaptyContextValue {
  profile: AdaptyProfile | null;
  isPremiumUser: boolean;
  reloadProfile: () => Promise<void>;
}

const AdaptyContext = createContext<AdaptyContextValue | null>(null);

export function AdaptyProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<AdaptyProfile | null>(null);

  const isPremiumUser =
    profile?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false;

  const reloadProfile = async () => {
    try {
      const p = await adapty.getProfile();
      setProfile(p);
    } catch (e) {
      console.warn('Adapty: failed to load profile', e);
    }
  };

  useEffect(() => {
    const listener = adapty.addListener('onLatestProfileLoad', (data) => {
      setProfile(data.profile);
    });
    return () => { listener.then(h => h.remove()); };
  }, []);

  return (
    <AdaptyContext.Provider value={{ profile, isPremiumUser, reloadProfile }}>
      {children}
    </AdaptyContext.Provider>
  );
}

export function useAdapty() {
  const ctx = useContext(AdaptyContext);
  if (!ctx) throw new Error('useAdapty must be used within AdaptyProvider');
  return ctx;
}
```

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s "https://adapty.io/docs/sdk-installation-capacitor.md?ref=skill-<sessionToken>"
```

Then guide the user through each step explicitly.

### Step 1: Install the npm package and sync native platforms

```bash
npm install @adapty/capacitor@latest
npx cap sync
```

Confirm the installed major version before writing any Stage 2 code — the fetch API differs between 3.x and 4.x, and `package.json` may carry a caret range that resolved to either:

```bash
npm ls @adapty/capacitor
```

`npx cap sync` is mandatory — it copies the native plugin code into `ios/` and `android/` directories. Skipping it means the native modules won't be available.

**Capacitor-specific note:** Both iOS and Android targets are installed with the single `@adapty/capacitor` package. No separate package is needed for the builder's renderer — it is activated alongside the core module.

**Checkpoint:** `npx cap sync` completes without errors, and `npm ls @adapty/capacitor` reports the version you intended.

**iOS on SDK 4.x:** the SDK installs through Swift Package Manager only, so there is no `Podfile` to edit — set the deployment target to **15.0** in Xcode, and make sure the iOS project uses Capacitor's SPM integration. Building requires **Xcode 26+**. (On SDK 3.x the CocoaPods path still applies: set `platform :ios, '15.0'` in `ios/App/Podfile`, then `npx cap sync ios` again.)

### Step 2: Add activation code

Ask the user where their app initializes — typically `app.component.ts` (Angular), `main.ts` (Vue/React), or `App.tsx` (React). Write the activation code there with the real SDK key from `constants.ts` (filled in from Phase 3):

```typescript
import { adapty } from '@adapty/capacitor';
import { ADAPTY_PUBLIC_KEY } from './adapty/constants';
import { userStorage } from './adapty/userStorage'; // remove if no auth

async function activateAdapty() {
  try {
    await adapty.activate({
      apiKey: ADAPTY_PUBLIC_KEY,
      params: {
        customerUserId: userStorage.getUserId() ?? undefined, // remove if no auth
        logLevel: 'verbose', // recommended for development; switch to 'error' for production
        // Prevents "already activated" errors during Capacitor live-reload
        __ignoreActivationOnFastRefresh: true,
      },
    });
    console.log('Adapty activated successfully');
  } catch (error) {
    console.error('Failed to activate Adapty SDK:', error);
  }
}
```

Call `activateAdapty()` as early as possible in the app lifecycle — before any paywall or profile calls. Also call `setupProfileListener()` on your AdaptyService/composable/context at this point so real-time updates are wired up immediately.

**Checkpoint:** App builds and runs on iOS and Android. Console shows "Adapty activated successfully". No "Public API key is missing" errors.

**Gotcha:** "Public API key is missing" or silent failure → the placeholder `'YOUR_PUBLIC_SDK_KEY'` was not replaced with the real key from App settings → General → API keys.

**Gotcha (Android):** If the app crashes on Android with a manifest merger error, the app has conflicting backup rule configurations from multiple SDKs. Follow the backup rules troubleshooting section in `sdk-installation-capacitor.md`.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Flow Builder

Read before writing code:
```
curl -s https://adapty.io/docs/capacitor-quickstart-paywalls.md
curl -s https://adapty.io/docs/capacitor-get-pb-paywalls.md
curl -s https://adapty.io/docs/capacitor-present-paywalls.md
curl -s https://adapty.io/docs/capacitor-handling-events.md
curl -s https://adapty.io/docs/capacitor-handle-paywall-actions.md
```

**v4 API names.** Flow Builder uses `getFlow` / `AdaptyFlow` / `createFlowView` / `FlowViewController` / `FlowEventHandlers`. The same APIs also render existing Paywall Builder paywalls — no dashboard changes are needed for a user moving from Paywall Builder. `getPaywall` and `createPaywallView` do not exist on 4.x; they were removed, not deprecated. Three specific traps when porting v3 code: `getFlow` takes **no `locale`** (pass it to `createFlowView` instead), **`hasViewConfiguration` was removed from the model** — do not check it, `createFlowView` throws instead — and the handler interface is `FlowEventHandlers`, with `onRenderingFailed` renamed to `onError`. Products are still `AdaptyPaywallProduct` and `getPaywallProducts` keeps its name, now taking `{ flow }`.

**Key flow:**

1. Fetch the flow by placement ID:
```typescript
import { adapty, createFlowView } from '@adapty/capacitor';
import { PLACEMENT_ID } from './adapty/constants';

const flow = await adapty.getFlow({ placementId: PLACEMENT_ID });
```

2. Create a view, register handlers, present it. `createFlowView` throws when the flow has no view configured, so there is nothing to check first — wrap the whole sequence:
```typescript
try {
  const view = await createFlowView(flow);

  // setEventHandlers resolves to an unsubscribe function — capture it if the view
  // outlives the screen that created it, otherwise dismiss() is enough.
  await view.setEventHandlers({
    // Defaults keep the flow OPEN after a purchase. Close it once the user has access.
    onPurchaseCompleted(purchaseResult, product) {
      return purchaseResult.type === 'success';
    },
  });

  await view.present();
} catch (error) {
  // No view configured for this flow, or presentation failed
}
```

3. Each `view` instance can only be used once. Call `createFlowView` again if you need to re-present the flow.

**The v4 defaults changed and none of it is a type error — verify by running the flow, not by reading the diff.** Only `onCloseButtonPress` and `onError` close the view by default; every other handler keeps it open. Returning `true` from a handler closes the view, `false` keeps it open. Specifically:

| Handler | v3 default | v4 default | Return to restore v3 |
|---|---|---|---|
| `onPurchaseCompleted` | closed unless cancelled | **stays open** | `purchaseResult.type !== 'user_cancelled'` |
| `onRestoreCompleted` | closed on success | **stays open** | `true` |
| `onAndroidSystemBack` | closed the view | **stays open** | `true` |

Leave `onAndroidSystemBack` at its default only if the flow has its own Close button — otherwise the flow is a dead end on Android.

**`onUrlPress` now has a working default** that opens the URL natively and honours the in-app vs external browser setting from the dashboard. Do not re-add a `window.open(url, '_blank')` handler out of habit — overriding `onUrlPress` discards that dashboard setting. Override it only if the app genuinely needs to intercept links.

**Android dialog note:** On Android, use `view.showDialog()` instead of native `alert()` when the flow is visible — native alerts appear behind the flow view.

**iOS presentation style:** `await view.present({ iosPresentationStyle: 'page_sheet' })` for a sheet instead of full screen. Android is always a full-screen activity and ignores this.

**Checkpoint:** Flow appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog, and the flow closes after a successful purchase rather than sitting there.

**Gotcha:** Blank flow or `getFlow` returns an error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `createFlowView` throws where `getFlow` succeeded → the **Show on device** toggle is off for that flow in the Flow Builder.

**Gotcha:** `paywall.hasViewConfiguration` is `undefined` → that property was removed from `AdaptyFlow` in v4. TypeScript catches it; plain JavaScript silently reads `undefined` and skips the paywall forever.

### Custom paywall (manual)

Read before writing code:
```
curl -s https://adapty.io/docs/capacitor-quickstart-manual.md
curl -s https://adapty.io/docs/fetch-paywalls-and-products-capacitor.md
curl -s https://adapty.io/docs/present-remote-config-paywalls-capacitor.md
curl -s https://adapty.io/docs/capacitor-making-purchases.md
curl -s https://adapty.io/docs/capacitor-restore-purchase.md
```

**Key flow:**

1. Fetch paywall and products:
```typescript
import { adapty } from '@adapty/capacitor';
import { PLACEMENT_ID } from './adapty/constants';

// v4 note: even a hand-built paywall fetches with getFlow — the fetch call follows the
// SDK major version, not the paywall approach. Products are still AdaptyPaywallProduct.
const flow = await adapty.getFlow({ placementId: PLACEMENT_ID });
const products = await adapty.getPaywallProducts({ flow });
```

2. Make a purchase when the user taps a product:
```typescript
const result = await adapty.makePurchase({ product });

if (result.type === 'success') {
  const isSubscribed = result.profile?.accessLevels[ACCESS_LEVEL_ID]?.isActive;
  if (isSubscribed) {
    // Grant access to paid features
  }
} else if (result.type === 'user_cancelled') {
  // User tapped away — no action needed
} else if (result.type === 'pending') {
  // Pending purchase (e.g. prepaid plan or parental approval)
}
```

3. Restore purchases (required by Apple — always provide a restore button):
```typescript
const profile = await adapty.restorePurchases();
const isRestored = profile.accessLevels[ACCESS_LEVEL_ID]?.isActive;
```

**Do not hardcode product IDs.** The only ID to hardcode is the placement ID. Fetch and display whatever products the paywall returns — the count and offerings can change remotely.

**Android subscription change:** To replace a subscription on Google Play, pass `subscriptionUpdateParams` to `makePurchase`:
```typescript
const result = await adapty.makePurchase({
  product,
  params: {
    android: {
      subscriptionUpdateParams: {
        oldSubVendorProductId: 'old.product.id',
        prorationMode: 'charge_prorated_price',
      },
    },
  },
});
```

**Checkpoint:** Custom paywall UI displays products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or the placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing purchase infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects or projects where purchases aren't yet implemented, use Flow Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management, Flow Builder, or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on server notifications being configured for both App Store and Google Play

Read before writing code:
```
curl -s https://adapty.io/docs/observer-vs-full-mode.md
curl -s https://adapty.io/docs/implement-observer-mode-capacitor.md
curl -s https://adapty.io/docs/report-transactions-observer-mode-capacitor.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or server notifications aren't configured for the store (App settings → iOS SDK / Android SDK).

---

## Stage 3: Check subscription status

Read before writing code:
```bash
curl -s https://adapty.io/docs/capacitor-check-subscription-status.md
```

**What to do:** After a purchase, check `profile.accessLevels['premium']?.isActive` to grant or deny access to paid features. Use `adapty.addListener('onLatestProfileLoad')` for real-time updates (already wired in AdaptyService from the recommended architecture) instead of polling.

Two patterns for checking access:

**Immediate check (on app launch, before showing gated content):**
```typescript
const profile = await adapty.getProfile();
const hasAccess = profile?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive === true;
```

**Reactive check (using the listener already set up in AdaptyService):**
```typescript
// In AdaptyService / composable / context:
adapty.addListener('onLatestProfileLoad', (data) => {
  // Fires automatically on app start and on any subscription change
  this.profile = data.profile;
});
```

**Checkpoint:** After a sandbox purchase, `profile.accessLevels['premium']?.isActive` returns `true`. Revoking the sandbox purchase returns `false`.

**Gotcha:** `accessLevels` is empty after purchase → the product has no access level assigned in the dashboard (Products page → select product → access levels).

---

## Stage 3.5: Third-party integrations (skip if user said "none")

For each integration the user selected in Phase 2, fetch the doc and implement both the dashboard configuration and the SDK code. Do them one at a time — dashboard side first, then code.

### Analytics integrations

| Tool | Doc slug |
|---|---|
| Amplitude | `amplitude` |
| Firebase / Google Analytics | `firebase-and-google-analytics` |
| Mixpanel | `mixpanel` |
| AppMetrica | `appmetrica` |
| PostHog | `posthog` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

### Attribution integrations

| Tool | Doc slug |
|---|---|
| AppsFlyer | `appsflyer` |
| Adjust | `adjust` |
| Branch | `branch` |
| Apple Search Ads | `apple-search-ads` |
| Airbridge | `airbridge` |
| Singular | `singular` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

**Capacitor note:** Attribution integrations require passing attribution data to Adapty via `adapty.updateExternalAttribution()` (renamed from `updateAttribution` in SDK 4.1, with its `source` option renamed to `provider`; there is no deprecated alias, so a v3 call site stops working). The native attribution SDK (AppsFlyer, Adjust, etc.) runs on the native layer — check whether a Capacitor plugin exists for that SDK, or whether attribution data must be captured natively and bridged.

**Adapty Attribution is off by default from SDK 4.1** (it was automatic below 4.1). If the user relies on Adapty's own install attribution, pass `adaptyAttributionEnabled: true` in the `activate()` params — without it the SDK registers no installs and delivers no installation details, silently. Two related renames land in the same release: `AttributionSource` → `AdaptyExternalAttributionProvider`, and `AdaptyProfile.appliedAttributionSources` → `appliedExternalAttributionProviders`.

### Messaging / CRM integrations

| Tool | Doc slug |
|---|---|
| Braze | `braze` |
| OneSignal | `onesignal` |
| Pushwoosh | `pushwoosh` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

### Webhook / data export

```bash
curl -s https://adapty.io/docs/set-up-webhook-integration.md
curl -s https://adapty.io/docs/webhook-event-types-and-fields.md
```

---

## Stage 4: Identify users

Use `AskUserQuestion` before deciding to skip:

> "This app has no login system, but you can still identify users with a stable ID tied to the device or installation. This gives each user a consistent Adapty profile across sessions, which helps with analytics accuracy, A/B test consistency, and avoiding duplicate profiles after reinstall. Do you have an ID you'd like to use, or would you like to discuss options?"
> - **Yes, I have an ID in mind** — tell me what it is and I'll implement identification
> - **Let's discuss** — I'll ask a few questions to help you decide
> - **No, skip** — anonymous profiles are fine for this app

If the user says no, skip the rest of this stage.

Read before writing code:
```bash
curl -s https://adapty.io/docs/capacitor-quickstart-identify.md
curl -s https://adapty.io/docs/capacitor-identifying-users.md
```

**What to do:**
- If you already have the user ID when the app launches, pass it in `adapty.activate()` via `customerUserId` (already wired in Stage 1 via `userStorage`)
- If users can sign in after the app starts, call `adapty.identify()` after login:

```typescript
// On login
await adapty.identify({ customerUserId: 'your-user-id' });
userStorage.setUserId('your-user-id');

// On logout
await adapty.logout();
userStorage.clearUserId();
```

- For apps where users can purchase before logging in: no extra setup needed. Adapty handles profile merging automatically when `identify()` is called after an anonymous purchase.

**Order matters:** `activate()` → `identify()` → `getFlow()`. If `identify()` is called after `getFlow()`, the purchase may be attributed to the anonymous profile.

**Checkpoint:** After calling `adapty.identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows an anonymous ID even after `identify()` → `identify()` was called after `getFlow()`. Ensure the order is `activate()` → `identify()` → `getFlow()`.

---

## Build verification

All code is written. **Run the sync and build yourself now via Bash — do not tell the user to run it. Do not say "try building and let me know". Execute these commands and handle the output yourself.**

```bash
# Sync native platforms
npx cap sync

# Run iOS build check
npx cap run ios --no-sync 2>&1 | tail -30

# Run Android build check
npx cap run android --no-sync 2>&1 | tail -30
```

### Handle output

**Sync and runs succeeded** → proceed to the manual checklist below.

**`npx cap sync` fails:**
- Missing plugin → `npm install @adapty/capacitor` was not run; install and retry
- iOS Podfile errors about minimum version → update `ios/App/Podfile` to `platform :ios, '15.0'` and retry
- Android manifest merger errors → follow the backup rules section in `sdk-installation-capacitor.md`

**App crashes on launch:**
- "Public API key is missing" → placeholder not replaced; update `constants.ts`
- "Adapty can only be activated once" → `__ignoreActivationOnFastRefresh: true` is missing in dev mode
- Module not found → `npx cap sync` was not run after installing the package

Do not proceed to the manual checklist until the app launches cleanly on both platforms (or whichever platforms the user targets). Do not hand off errors to the user except for steps that require Xcode UI interaction (e.g., adding entitlements) or Android Studio configuration.

---

## Before you can test: manual steps

Read and follow `references/testing-setup-ios.md` (in this skill directory) for iOS setup, and `references/testing-setup-android.md` (in this skill directory) for Android setup.

If you received this playbook on its own, without this skill's directory, those checklist files are not available to you — fetch https://adapty.io/docs/app-store-connection-configuration.md, https://adapty.io/docs/enable-app-store-server-notifications.md and https://adapty.io/docs/app-store-test.md for iOS, and https://adapty.io/docs/google-play-store-connection-configuration.md, https://adapty.io/docs/enable-real-time-developer-notifications-rtdn.md and https://adapty.io/docs/testing-on-android.md for Android. They cover the connection, notification and sandbox-testing steps; creating the store products and designing the paywall are console and dashboard work with no docs substitute.

The full checklist covers:

**iOS (App Store Connect + Adapty Dashboard):**
1. Create products in App Store Connect — use the exact product IDs from Phase 3
2. Connect App Store to Adapty: App settings → iOS SDK → enter Bundle ID, upload In-App Purchase Key, configure Server Notifications URL
3. If using Flow Builder: design the flow in the Adapty Dashboard, enable the **Show on device** toggle
4. Create a sandbox tester account in App Store Connect
5. On the test device: Settings → App Store → Sandbox Account → sign in with the sandbox tester
6. Make a test purchase and verify it appears in the Adapty dashboard **Event Feed**

**Android (Google Play Console + Adapty Dashboard):**
1. Create products in Google Play Console (in-app products or subscriptions) — use the exact product IDs from Phase 3
2. Connect Google Play to Adapty: App settings → Android SDK → enter Package Name, upload Service Account JSON, configure Real-Time Developer Notifications (RTDN)
3. Set up a license tester in Google Play Console (account must be added as a tester in the internal test track)
4. Make a test purchase and verify it appears in the Adapty dashboard **Event Feed**

**Capacitor-specific notes:**
- Both iOS and Android product IDs may be needed if the app targets both platforms — confirm with the user
- When testing on iOS, always build and run via Xcode or `npx cap run ios` on a real device for in-app purchase testing (simulator purchases work for sandbox, but a real device is more reliable)
- When testing on Android, the app must be signed and the APK/AAB uploaded to at least the internal track before Google Play billing works

Present this checklist to the user with the actual product IDs and placement IDs from Phase 3 already filled in.

---

## Stage 5: Release checklist

Run through this before submitting to App Store / Google Play review.

Read before releasing:
```bash
curl -s https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- App Store connected in App settings (Bundle ID, In-App Purchase Key)
- App Store Server Notifications configured in App settings → iOS SDK
- Google Play connected in App settings (Package Name, Service Account JSON)
- Google Play Real-Time Developer Notifications configured in App settings → Android SDK
- Sandbox / test purchase flow works end-to-end on both platforms
- Premium content is gated on access level check (`accessLevels[ACCESS_LEVEL_ID]?.isActive`)
- Restore purchases button present (Apple requirement — required for App Store review approval)
- `logLevel` changed from `'verbose'` to `'error'` (or removed) for production builds
- Privacy policy URL set in App Store Connect and Google Play Console

**Gotcha:** Missing App Store Server Notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations.

**Gotcha:** Missing Google Play RTDN → same problem on Android; subscription lifecycle events won't be tracked.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Promotional offers** — set up subscription discounts and win-back offers for lapsed subscribers
> 4. **Onboardings** — build them as flows in Flow Builder. On SDK 4.x the legacy `getOnboarding` API still works but is deprecated in favour of `getFlow` and will be removed
> 5. **Kids mode** — COPPA/COPPA-compliant mode that disables IDFA and ad data collection
> 6. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 7. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features
> 8. **Web paywalls** — implement paywalls that open in a web view for cross-platform consistency

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `capacitor-use-fallback-paywalls` |
| Custom user attributes | `capacitor-setting-user-attributes` |
| Promotional offers | `app-store-offers`, `create-offer` |
| Onboardings (Flow Builder) | `capacitor-quickstart-paywalls`, `adapty-flow-builder` |
| Flow screen-view analytics | `capacitor-flow-screen-views` |
| Kids mode | `kids-mode-capacitor` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| Web paywalls | `capacitor-web-paywall` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## Capacitor index files

For broader context when more coverage is needed:
- Capacitor docs index: `https://adapty.io/docs/capacitor-llms.txt`
- Capacitor full docs (large): `https://adapty.io/docs/capacitor-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
- Sample app (SDK-team maintained, close to real usage — open it when a docs page doesn't show how the pieces fit together in a real app; take API usage from it, not the sample's app architecture): https://github.com/adaptyteam/AdaptySDK-Capacitor/tree/master/examples
