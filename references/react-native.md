# React Native SDK Integration Reference

Platform: React Native · Language: TypeScript / JavaScript · Package manager: npm or yarn

## Prerequisites

- iOS 13.0+ (iOS 15.0+ required for Paywall Builder paywalls)
- Android with Google Play Billing Library (Adapty ships v7.0.0 by default; compatible up to 8.x)
- React Native 0.68+ (or Expo with Dev Client — Expo Go only supports mock mode)
- Node.js with npm or yarn

---

## Build verification

After each stage that writes code, run a build to catch errors immediately rather than letting them pile up. Use these helpers — run them yourself via Bash, do not ask the user to build.

### Detect project type first

```bash
# Detect Expo vs bare React Native
ls package.json && node -e "const p=require('./package.json'); console.log(p.dependencies?.expo ? 'EXPO' : 'BARE_RN')"

# For bare RN: find the iOS workspace and Android gradle
find . -maxdepth 4 -name "*.xcworkspace" ! -path "*/Pods/*" ! -path "*/.build/*"
find . -maxdepth 3 -name "build.gradle" ! -path "*/node_modules/*" | head -5
```

### Run a build — bare React Native

```bash
# iOS (requires macOS + Xcode)
cd ios && pod install && cd ..
npx react-native build-ios --mode=Debug --simulator "iPhone 16" 2>&1 | grep -E "error:|warning:|BUILD SUCCEEDED|BUILD FAILED" | head -40

# Android (can run on macOS/Linux/Windows)
cd android && ./gradlew assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | tail -20
```

### Run a build — Expo

```bash
# iOS
npx expo run:ios 2>&1 | grep -E "error:|warning:|Build succeeded|Build failed|bundling complete" | head -40

# Android
npx expo run:android 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | tail -20
```

### Handle the output

**Build succeeded / BUILD SUCCESSFUL** → proceed to next stage.

**BUILD FAILED with errors:**
- Errors in files you wrote → fix them directly and rebuild
- `Unable to resolve module 'react-native-adapty'` → package not installed; run `npm install react-native-adapty` (or `yarn add react-native-adapty`), then `cd ios && pod install`
- iOS pod errors → run `cd ios && pod install --repo-update` and rebuild
- Android Kotlin/Gradle version error (RN < 0.73) → add `classpath "org.jetbrains.kotlin:kotlin-gradle-plugin:1.8.0"` to `/android/build.gradle` dependencies
- Manifest merger conflict (`fullBackupContent` or `dataExtractionRules`) → see the troubleshooting steps in the installation doc; for Expo, add `["react-native-adapty", { "replaceAndroidBackupConfig": true }]` to `app.json` plugins
- iOS minimum version error → update Podfile to `platform :ios, '15.0'` (bare RN) or use `expo-build-properties` to set `deploymentTarget: "15.0"` in `app.json` (Expo)
- Signing errors → not blocking for simulator/emulator builds; can ignore until device testing

Rebuild after each fix. Do not move to the next stage until the build is clean.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### constants.ts

Centralizes all Adapty config values. Update these immediately after Phase 3 output — never ship with placeholder strings.

```typescript
// src/constants.ts  (or wherever you keep app constants)
export const ADAPTY_PUBLIC_KEY = 'YOUR_PUBLIC_SDK_KEY'; // App settings → General → API keys → Public SDK Key
export const PLACEMENT_ID = 'YOUR_PLACEMENT_ID';         // Adapty Dashboard → Placements
export const ACCESS_LEVEL_ID = 'premium';                 // Default access level; change if you use custom ones
```

### UserManager.ts (skip if app has no authentication)

Lightweight AsyncStorage wrapper for the customer user ID. Pass this to `adapty.activate()` on launch so purchases are always attributed to the right profile.

```typescript
// src/UserManager.ts
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'app.adapty.userId';

export const UserManager = {
  async getCurrentUserId(): Promise<string | null> {
    return AsyncStorage.getItem(KEY);
  },
  async login(userId: string): Promise<void> {
    await AsyncStorage.setItem(KEY, userId);
  },
  async logout(): Promise<void> {
    await AsyncStorage.removeItem(KEY);
  },
};
```

### AdaptyService.ts (React Context or Zustand store)

Central service that:
- Holds the current profile as reactive state
- Listens for real-time subscription updates via `onLatestProfileLoad` event (no polling needed)
- Exposes a clean `isPremiumUser` computed value for gating content

**React Context approach:**

```typescript
// src/AdaptyService.ts
import { adapty, AdaptyProfile } from 'react-native-adapty';
import { ACCESS_LEVEL_ID } from './constants';

class AdaptyService {
  private static _instance: AdaptyService;
  private _profile: AdaptyProfile | null = null;
  private _listeners: Array<(profile: AdaptyProfile | null) => void> = [];

  static get shared(): AdaptyService {
    if (!AdaptyService._instance) {
      AdaptyService._instance = new AdaptyService();
    }
    return AdaptyService._instance;
  }

  init() {
    adapty.addEventListener('onLatestProfileLoad', (profile) => {
      this._profile = profile;
      this._listeners.forEach((l) => l(profile));
    });
  }

  get isPremiumUser(): boolean {
    return this._profile?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false;
  }

  async reloadProfile(): Promise<AdaptyProfile | null> {
    try {
      this._profile = await adapty.getProfile();
      this._listeners.forEach((l) => l(this._profile));
      return this._profile;
    } catch {
      return null;
    }
  }

  subscribe(listener: (profile: AdaptyProfile | null) => void): () => void {
    this._listeners.push(listener);
    return () => {
      this._listeners = this._listeners.filter((l) => l !== listener);
    };
  }
}

export default AdaptyService;
```

**Zustand approach (if the project already uses Zustand):**

```typescript
// src/store/adaptyStore.ts
import { create } from 'zustand';
import { adapty, AdaptyProfile } from 'react-native-adapty';
import { ACCESS_LEVEL_ID } from '../constants';

interface AdaptyState {
  profile: AdaptyProfile | null;
  isPremiumUser: boolean;
  setProfile: (profile: AdaptyProfile | null) => void;
  reloadProfile: () => Promise<void>;
}

export const useAdaptyStore = create<AdaptyState>((set) => ({
  profile: null,
  isPremiumUser: false,
  setProfile: (profile) =>
    set({
      profile,
      isPremiumUser: profile?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false,
    }),
  reloadProfile: async () => {
    try {
      const profile = await adapty.getProfile();
      set({
        profile,
        isPremiumUser: profile?.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false,
      });
    } catch {
      // keep stale data
    }
  },
}));
```

---

## Stage 1: Install and configure the SDK

First fetch the full installation docs for reference:

```bash
# Fetch both — you'll need both for Expo vs bare RN detection
curl -s https://adapty.io/docs/sdk-installation-react-native-pure.md
curl -s https://adapty.io/docs/sdk-installation-react-native-expo.md
```

Then guide the user through each step based on their project type.

### Step 1: Detect project type

Ask the user (or check `package.json`):
- Does `package.json` list `expo` as a dependency? → **Expo project**
- No `expo` dependency? → **Bare React Native**

### Step 2: Install the package

**Bare React Native:**
```bash
# npm
npm install react-native-adapty

# or yarn
yarn add react-native-adapty

# iOS: install native pods
cd ios && pod install && cd ..
```

**Expo:**
```bash
npx expo install react-native-adapty
npx expo prebuild
```

For Android with React Native < 0.73, also update `/android/build.gradle`:
```groovy
// /android/build.gradle
buildscript {
  dependencies {
    // Add or update this line:
    classpath "org.jetbrains.kotlin:kotlin-gradle-plugin:1.8.0"
  }
}
```

### Step 3: Add activation code

The activation belongs in the root component entry point (`App.tsx` / `App.js` / `index.js`) — the first thing that runs.

Ask if the app has an authentication system. Use the appropriate template:

**Without authentication:**

```typescript
// App.tsx
import { adapty } from 'react-native-adapty';
import { ADAPTY_PUBLIC_KEY } from './src/constants';
import AdaptyService from './src/AdaptyService';

// Initialize profile listener before rendering
AdaptyService.shared.init();

try {
  adapty.activate(ADAPTY_PUBLIC_KEY, {
    logLevel: 'verbose', // Use 'verbose' for dev; 'error' or 'warn' for production
    __ignoreActivationOnFastRefresh: __DEV__, // Prevents double-activation on Fast Refresh
  });
} catch (error) {
  console.error('Failed to activate Adapty SDK:', error);
}
```

**With authentication (customer user ID known at launch):**

```typescript
// App.tsx
import { adapty } from 'react-native-adapty';
import { ADAPTY_PUBLIC_KEY } from './src/constants';
import { UserManager } from './src/UserManager';
import AdaptyService from './src/AdaptyService';

async function initAdapty() {
  const userId = await UserManager.getCurrentUserId();
  AdaptyService.shared.init();

  try {
    adapty.activate(ADAPTY_PUBLIC_KEY, {
      customerUserId: userId ?? undefined, // pass undefined (not null) if not known yet
      logLevel: 'verbose',
      __ignoreActivationOnFastRefresh: __DEV__,
    });
  } catch (error) {
    console.error('Failed to activate Adapty SDK:', error);
  }
}

initAdapty();
```

**iOS simulator gotcha** — add `__debugDeferActivation` to suppress excessive StoreKit prompts in the simulator:

```typescript
adapty.activate(ADAPTY_PUBLIC_KEY, {
  __ignoreActivationOnFastRefresh: __DEV__,
  __debugDeferActivation: isSimulator(), // use 'react-native-device-info' or similar
});
```

**Checkpoint:** App builds and runs on both iOS and Android (or at least the target platform). Metro bundler / console logs show an Adapty activation log line.

**Gotcha:** `Adapty can only be activated once` error in development → add `__ignoreActivationOnFastRefresh: __DEV__` to the activate options.

**Gotcha:** "Public API key is missing" or silent failure → the placeholder in `constants.ts` wasn't replaced with the real key from App settings → General → API keys.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Paywall Builder

Read before writing code:
```bash
curl -s https://adapty.io/docs/react-native-quickstart-paywalls.md
curl -s https://adapty.io/docs/react-native-get-pb-paywalls.md
curl -s https://adapty.io/docs/react-native-present-paywalls.md
curl -s https://adapty.io/docs/react-native-handling-events-1.md
curl -s https://adapty.io/docs/react-native-handle-paywall-actions.md
```

**Fetch and display pattern:**

```typescript
import { adapty, createPaywallView, AdaptyPaywallView, EventHandlers } from 'react-native-adapty';
import { Linking, useCallback } from 'react-native';
import { PLACEMENT_ID } from '../constants';

// 1. Fetch the paywall
const paywall = await adapty.getPaywall(PLACEMENT_ID);

// 2. Verify it has a view configuration (Paywall Builder toggle must be ON in dashboard)
if (!paywall.hasViewConfiguration) {
  // Fall back to custom paywall UI
  return;
}

// 3a. Display as a React component (embed in your tree)
function MyPaywallScreen({ paywall }) {
  const onCloseButtonPress = useCallback<EventHandlers['onCloseButtonPress']>(() => {
    // navigate back
  }, []);
  const onUrlPress = useCallback<EventHandlers['onUrlPress']>((url) => {
    Linking.openURL(url);
  }, []);

  return (
    <AdaptyPaywallView
      paywall={paywall}
      style={{ flex: 1 }}
      onCloseButtonPress={onCloseButtonPress}
      onUrlPress={onUrlPress}
    />
  );
}

// 3b. Display modally (alternative)
const view = await createPaywallView(paywall);
await view.present(); // Each view is single-use; call createPaywallView again to re-show
```

**Checkpoint:** Paywall appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog (App Store sandbox on iOS, Google Play test on Android).

**Gotcha:** Blank paywall or `getPaywall` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** Paywall builder shows empty → **Show on device** toggle in the Paywall Builder is off. Turn it on.

### Custom paywall (manual)

Read before writing code:
```bash
curl -s https://adapty.io/docs/react-native-quickstart-manual.md
curl -s https://adapty.io/docs/fetch-paywalls-and-products-react-native.md
curl -s https://adapty.io/docs/present-remote-config-paywalls-react-native.md
curl -s https://adapty.io/docs/react-native-making-purchases.md
curl -s https://adapty.io/docs/react-native-restore-purchase.md
```

**Fetch products, make purchase, restore pattern:**

```typescript
import { adapty } from 'react-native-adapty';
import { PLACEMENT_ID } from '../constants';

// Fetch paywall and products
const paywall = await adapty.getPaywall(PLACEMENT_ID);
const products = await adapty.getPaywallProducts(paywall);

// Make a purchase
try {
  const profile = await adapty.makePurchase(products[0]);
  // profile.accessLevels['premium']?.isActive === true if purchase succeeded
} catch (error) {
  // handle purchase error
}

// Restore purchases (required button per App Store guidelines)
try {
  const profile = await adapty.restorePurchases();
  // profile has updated access levels after restore
} catch (error) {
  // handle restore error
}
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing purchase infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects, use Paywall Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on App Store Server Notifications (iOS) and RTDN (Android) being configured

Read before writing code:
```bash
curl -s https://adapty.io/docs/observer-vs-full-mode.md
curl -s https://adapty.io/docs/implement-observer-mode-react-native.md
curl -s https://adapty.io/docs/report-transactions-observer-mode-react-native.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or server notifications aren't configured in App settings.

---

## Stage 3: Check subscription status

Read before writing code:
```bash
curl -s https://adapty.io/docs/react-native-check-subscription-status.md
curl -s https://adapty.io/docs/react-native-listen-subscription-changes.md
```

**What to do:** After a purchase, check `profile.accessLevels['premium']?.isActive` to grant or deny access to paid features. For real-time updates, listen for `onLatestProfileLoad` events instead of polling.

**One-time check (e.g. on app launch or entering premium section):**

```typescript
import { adapty } from 'react-native-adapty';
import { ACCESS_LEVEL_ID } from '../constants';

const profile = await adapty.getProfile();
const hasPremium = profile.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false;
```

**Continuous listener (recommended — put this in AdaptyService.init()):**

```typescript
adapty.addEventListener('onLatestProfileLoad', (profile) => {
  const hasPremium = profile.accessLevels?.[ACCESS_LEVEL_ID]?.isActive ?? false;
  // update your state / store
});
```

Note: `onLatestProfileLoad` also fires on app start with cached data, so it works offline.

**Checkpoint:** After a sandbox purchase, `profile.accessLevels['premium']?.isActive` returns `true`. Revoking the sandbox subscription returns `false` on the next check.

**Gotcha:** `accessLevels` is empty after purchase → product has no access level assigned in the dashboard (Products page → select product → access levels).

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
curl -s https://adapty.io/docs/react-native-quickstart-identify.md
curl -s https://adapty.io/docs/react-native-identifying-users.md
```

**What to do:**
- Pass `customerUserId` to `adapty.activate()` at launch if you already have it stored — this is the most efficient path and avoids creating an anonymous profile first
- If the user ID isn't available at launch (e.g. user hasn't logged in yet), call `adapty.identify("your-user-id")` after login/signup
- For apps where users can purchase before logging in, call `identify()` at login — Adapty handles profile merging automatically
- Call `adapty.logout()` when users log out; also call `UserManager.logout()` to clear the stored ID

```typescript
// At login
import { adapty } from 'react-native-adapty';
import { UserManager } from './UserManager';

async function handleLogin(userId: string) {
  await UserManager.login(userId);
  try {
    await adapty.identify(userId);
    // Re-request paywalls after identify — the new profile may have different data
  } catch (error) {
    console.error('Failed to identify user:', error);
  }
}

// At logout
async function handleLogout() {
  try {
    await adapty.logout();
    await UserManager.logout();
  } catch (error) {
    console.error('Failed to logout:', error);
  }
}
```

**Checkpoint:** After calling `identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `identify()` → `identify()` was called after `getPaywall()`, so the purchase was attributed to the anonymous profile. Correct order: `activate()` → `identify()` → `getPaywall()`.

**Gotcha:** After `identify()`, always re-request paywalls and products — the identified profile may have different offerings, A/B test variants, or access levels than the anonymous profile had.

---

## Build verification

All code is written. **Run the build yourself now via Bash — do not tell the user to build. Do not say "try building and let me know". Execute the commands below and handle the output yourself.**

### Detect project type

```bash
node -e "const p=require('./package.json'); console.log(p.dependencies?.expo ? 'EXPO' : 'BARE_RN')"
```

### Build — bare React Native

```bash
# iOS
cd ios && pod install && cd .. && npx react-native build-ios --mode=Debug --simulator "iPhone 16" 2>&1 | grep -E "error:|warning:|BUILD SUCCEEDED|BUILD FAILED" | head -40

# Android
cd android && ./gradlew assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | tail -20
```

### Build — Expo

```bash
# iOS
npx expo run:ios 2>&1 | grep -E "error:|warning:|Build succeeded|Build failed|bundling complete" | head -40

# Android
npx expo run:android 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | tail -20
```

### Handle output

**Build succeeded / BUILD SUCCESSFUL** → proceed to the manual checklist below.

**BUILD FAILED:**
- Errors in files you wrote → fix them directly and rebuild — do not ask the user
- `Unable to resolve module 'react-native-adapty'` → run `npm install react-native-adapty && cd ios && pod install` and rebuild
- iOS pod errors → `cd ios && pod install --repo-update` and rebuild
- Minimum iOS version error (bare RN) → update `ios/Podfile`: change `platform :ios, ...` to `platform :ios, '15.0'`
- Minimum iOS version error (Expo) → add `expo-build-properties` and set `deploymentTarget: "15.0"` in `app.json`, then `npx expo prebuild --clean`
- Android Gradle/Kotlin error → check `android/build.gradle` for `kotlin-gradle-plugin:1.8.0` or newer
- Manifest merger conflict → follow the Android backup troubleshooting steps in the installation docs
- Signing errors → safe to ignore for simulator/emulator builds; not blocking

Do not proceed to the manual checklist until the build is clean. Do not hand off build errors to the user except for Xcode-only interactions (adding provisioning profiles, signing certificates).

---

## Before you can test: manual steps

Testing in-app purchases requires platform setup that cannot be done in code. Follow the appropriate guides:

**iOS testing:**
Read and follow the iOS sandbox testing setup. Required steps:
1. App Store Connect: create App ID and In-App Purchase products (use product IDs from Phase 3)
2. Connect App Store to Adapty: Bundle ID, In-App Purchase Key, App Store Server Notifications
3. Design the paywall in Paywall Builder (if using Paywall Builder mode)
4. Create a sandbox test account in App Store Connect → Users and Access → Sandbox Testers
5. On device: Settings → App Store → Sandbox Account → sign in with test account
6. Make a test purchase, verify it appears in Adapty dashboard **Event Feed**

```bash
curl -s https://adapty.io/docs/test-purchases-in-sandbox.md
```

**Android testing:**
```bash
curl -s https://adapty.io/docs/testing-on-android.md
```

Required steps:
1. Google Play Console: create the app, add In-App Products / Subscriptions (use product IDs from Phase 3)
2. Connect Google Play to Adapty: package name, service account key, RTDN notifications
3. Add your Google account as a license tester in Play Console → Setup → License Testing
4. Upload a signed APK to internal testing track and opt in with the tester account
5. Make a test purchase, verify it appears in Adapty dashboard **Event Feed**

Present the checklist to the user with the actual product IDs from Phase 3 already filled in. Both platforms should be tested if the app targets both iOS and Android.

---

## Stage 5: Release checklist

Run through this before submitting to App Store or Google Play review.

Read before releasing:
```bash
curl -s https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- App Store and/or Google Play connected in App settings → General
- App Store Server Notifications configured in App settings → iOS SDK (iOS)
- Real-time Developer Notifications (RTDN) configured in App settings → Android SDK (Android)
- Sandbox purchase flow works end-to-end on both target platforms
- Premium content is gated on access level check
- Restore purchases button present (Apple requirement)
- `logLevel` changed from `'verbose'` to `'error'` or `'warn'` for production build
- Privacy policy URL set in App Store Connect and Google Play Console
- `__debugDeferActivation` and `__ignoreActivationOnFastRefresh` are gated on `__DEV__` (not set to `true` unconditionally)

**Gotcha:** Missing App Store Server Notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations.

**Gotcha:** Missing RTDN → same problem for Android — renewal and cancellation events won't fire.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Promotional offers** — set up subscription discounts and win-back offers for lapsed subscribers
> 4. **Onboardings** — add interactive onboarding flows powered by Adapty's builder
> 5. **Kids mode** — COPPA-compliant mode that disables IDFA/GAID and ad data collection
> 6. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 7. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features
> 8. **App Tracking Transparency (ATT)** — handle the iOS ATT prompt correctly in relation to Adapty activation

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `react-native-use-fallback-paywalls` |
| Custom user attributes | `react-native-setting-user-attributes` |
| Promotional offers | `app-store-offers`, `create-offer` |
| Onboardings | `react-native-get-onboardings`, `react-native-present-onboardings`, `react-native-handling-onboarding-events` |
| Kids mode | `kids-mode-react-native` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| ATT | `react-native-deal-with-att` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## React Native index files

For broader context when more coverage is needed:
- React Native docs index: `https://adapty.io/docs/react-native-llms.txt`
- React Native full docs (large): `https://adapty.io/docs/react-native-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
