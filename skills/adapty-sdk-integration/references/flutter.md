# Flutter SDK Integration Reference

Platform: Flutter · Language: Dart · Targets: iOS and Android from one codebase

## Prerequisites

- Flutter 3.32.0+ / Dart 3.8.0+ (stable channel) — required by SDK v4
- iOS 15.0+ (SDK v4 raises the minimum deployment target from 13.0); building for iOS requires Xcode 26+
- Android: Google Play Billing Library up to 8.x (Adapty defaults to 7.0.0)
- Dart null safety enabled
- `pubspec.yaml` in project root

---

## Build verification

After each stage that writes code, run a build to catch errors immediately rather than letting them pile up. Use these helpers — run them yourself via Bash. Do not ask the user to build or run the app manually.

### Discover project info

```bash
# Confirm Flutter project structure
ls -1 | grep -E "pubspec\.yaml|android|ios|lib"
flutter --version 2>&1 | head -5
```

### Run a build

Flutter targets both iOS and Android. Build for the platform most relevant to the current stage, or build both if changes affect both.

```bash
# iOS build (outputs to build/ios/)
flutter build ios --no-codesign --debug 2>&1 | grep -E "error:|warning:|Build complete|FAILED" | head -40

# Android build (outputs to build/app/)
flutter build apk --debug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | head -40
```

Use `--no-codesign` for iOS simulator/CI builds — signing is not required to verify correctness.

### Handle the output

**Build complete / BUILD SUCCESSFUL** → proceed to next stage.

**Build failed with errors:**
- Errors in files you wrote → fix them directly and rebuild
- `Error: Could not find package "adapty_flutter"` → `flutter pub get` hasn't been run; run it now
- `Could not resolve dependencies` → version conflict in `pubspec.yaml`; check constraints
- iOS CocoaPods error → run `cd ios && pod install && cd ..` then rebuild
- Android `Manifest merger failed` → see Android backup rules in the installation doc (`curl -s https://adapty.io/docs/sdk-installation-flutter.md`)
- Signing errors → use `--no-codesign` on iOS; not blocking

Rebuild after each fix. Do not move to the next stage until the build is clean.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### app_constants.dart

Centralizes all Adapty config values. The `assert` in debug mode will surface missing keys early.

```dart
class AppConstants {
  // Replace these before running — app will assert in debug mode if placeholders remain
  static const String adaptyPublicKey = 'YOUR_PUBLIC_SDK_KEY'; // App settings → General → API keys
  static const String placementId = 'YOUR_PLACEMENT_ID';       // Adapty Dashboard → Placements
  static const String accessLevelId = 'premium';               // default; change if using custom access levels
}
```

Replace placeholder strings with real values from Phase 3 output immediately.

### user_manager.dart (skip if app has no authentication)

Lightweight SharedPreferences wrapper for the customer user ID. Pass this to `Adapty().activate()` on launch so purchases are attributed to the right profile.

```dart
import 'package:shared_preferences/shared_preferences.dart';

class UserManager {
  static const _key = 'app.adapty.userId';

  static Future<String?> getCurrentUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key);
  }

  static Future<void> login(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, userId);
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }
}
```

### adapty_service.dart

Central service that:
- Holds the current profile as a `ValueNotifier` (or `ChangeNotifier` for Provider)
- Listens to the `didUpdateProfileStream` for real-time subscription updates (no polling needed)
- Exposes a clean `isPremiumUser` getter for gating content

**Provider / ChangeNotifier pattern (recommended):**

```dart
import 'dart:async';
import 'package:adapty_flutter/adapty_flutter.dart';
import 'package:flutter/foundation.dart';
import 'app_constants.dart';

class AdaptyService extends ChangeNotifier {
  static final AdaptyService shared = AdaptyService._();
  AdaptyService._();

  AdaptyProfile? _profile;
  StreamSubscription<AdaptyProfile>? _profileSubscription;

  bool get isPremiumUser =>
      _profile?.accessLevels[AppConstants.accessLevelId]?.isActive ?? false;

  AdaptyProfile? get profile => _profile;

  void startListening() {
    _profileSubscription = Adapty().didUpdateProfileStream.listen((profile) {
      _profile = profile;
      notifyListeners();
    });
  }

  Future<void> reloadProfile() async {
    try {
      _profile = await Adapty().getProfile();
      notifyListeners();
    } catch (e) {
      debugPrint('AdaptyService: failed to reload profile — $e');
    }
  }

  @override
  void dispose() {
    _profileSubscription?.cancel();
    super.dispose();
  }
}
```

**Riverpod pattern (alternative):**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:adapty_flutter/adapty_flutter.dart';
import 'app_constants.dart';

class AdaptyNotifier extends AsyncNotifier<AdaptyProfile?> {
  @override
  Future<AdaptyProfile?> build() async {
    // Listen to stream
    ref.listen(adaptyProfileStreamProvider, (_, next) {
      next.whenData((profile) => state = AsyncData(profile));
    });
    return Adapty().getProfile();
  }

  Future<void> reload() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => Adapty().getProfile());
  }
}

final adaptyServiceProvider =
    AsyncNotifierProvider<AdaptyNotifier, AdaptyProfile?>(() => AdaptyNotifier());

final adaptyProfileStreamProvider = StreamProvider<AdaptyProfile>(
  (ref) => Adapty().didUpdateProfileStream,
);

// Usage in widgets:
// final profileAsync = ref.watch(adaptyServiceProvider);
// final isPremium = profileAsync.valueOrNull
//     ?.accessLevels[AppConstants.accessLevelId]?.isActive ?? false;
```

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s "https://adapty.io/docs/sdk-installation-flutter.md?ref=skill-<sessionToken>"
```

Then guide the user through each step explicitly.

### Step 1: Add the dependency

Add Adapty to `pubspec.yaml`:

```yaml
dependencies:
  adapty_flutter: ^4.0.0   # replace with latest version from pub.dev
```

Then run:

```bash
flutter pub get
```

Check pub.dev for the latest release: `https://pub.dev/packages/adapty_flutter`

**iOS native SDK comes through Swift Package Manager (v4+):** starting with v4, the native iOS SDK is no longer distributed through CocoaPods — the plugin pulls it through SPM only. Flutter 3.44+ enables SPM support by default; on Flutter 3.32–3.43, enable it once:

```bash
flutter config --enable-swift-package-manager
```

**Gotcha:** iOS build fails to resolve the Adapty native SDK → Swift Package Manager support is off (Flutter 3.32–3.43); run the config command above and rebuild. Flutter older than 3.32 must stay on `adapty_flutter` 3.x (no Flow Builder).

### Step 2: Import and activate the SDK

In `main.dart`, import Adapty and activate it as early as possible — before `runApp()` or in `initState()` of the root widget.

**Preferred — activate before runApp:**

```dart
import 'package:flutter/material.dart';
import 'package:adapty_flutter/adapty_flutter.dart';
import 'package:provider/provider.dart'; // if using Provider
import 'app_constants.dart';
import 'adapty_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Activate Adapty before the app starts
  try {
    await Adapty().activate(
      configuration: AdaptyConfiguration(apiKey: AppConstants.adaptyPublicKey)
        ..withLogLevel(AdaptyLogLevel.info), // use .verbose for debug builds
    );
  } catch (e) {
    debugPrint('Adapty activation failed: $e');
  }

  AdaptyService.shared.startListening();

  runApp(
    ChangeNotifierProvider.value(
      value: AdaptyService.shared,
      child: const MyApp(),
    ),
  );
}
```

**If using Flow Builder, also activate AdaptyUI:**

```dart
await Adapty().activate(
  configuration: AdaptyConfiguration(apiKey: AppConstants.adaptyPublicKey)
    ..withLogLevel(AdaptyLogLevel.info)
    ..withActivateUI(true), // activates AdaptyUI module automatically
);
```

**If passing a known customer user ID at launch:**

```dart
final userId = await UserManager.getCurrentUserId();

await Adapty().activate(
  configuration: AdaptyConfiguration(apiKey: AppConstants.adaptyPublicKey)
    ..withLogLevel(AdaptyLogLevel.info)
    ..withCustomerUserId(userId), // can be null if user not yet logged in
);
```

The SDK key comes from `AppConstants` — already set in the recommended architecture step above.

**Checkpoint:** App builds and runs on both iOS and Android. Debug console shows an Adapty activation log line.

**Gotcha:** "Public API key is missing" or silent failure → the placeholder wasn't replaced with the real key from App settings → General → API keys.

**Android-specific gotcha:** If the build fails with `Manifest merger failed` → see the Android backup rules troubleshooting section at the bottom of `curl -s https://adapty.io/docs/sdk-installation-flutter.md`.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Flow Builder

Read before writing code:
```bash
curl -s https://adapty.io/docs/flutter-quickstart-paywalls.md
curl -s https://adapty.io/docs/flutter-get-pb-paywalls.md
curl -s https://adapty.io/docs/flutter-present-paywalls.md
curl -s https://adapty.io/docs/flutter-handling-events.md
curl -s https://adapty.io/docs/flutter-handle-paywall-actions.md
```

**v4 API names:** Flow Builder uses the new `getFlow` / `AdaptyFlow` / `createFlowView` / `AdaptyUIFlowView` / `AdaptyUIFlowsEventsObserver` family. The same APIs also render existing Paywall Builder paywalls — no dashboard changes are required for users migrating from Paywall Builder. You no longer pass a `locale` when fetching (localization resolves automatically on render), the observer registers via `setFlowsEventsObserver`, and all `paywallViewDid*` callbacks are now `flowViewDid*`. Products are still `AdaptyPaywallProduct`.

**Required pattern — get flow, create view, present:**

```dart
import 'package:adapty_flutter/adapty_flutter.dart';
import 'app_constants.dart';

Future<void> showFlow(BuildContext context) async {
  try {
    // 1. Fetch the flow by placement ID
    final flow = await Adapty().getFlow(
      placementId: AppConstants.placementId,
    );

    // 2. Create the flow view (only works if the flow has an on-device design)
    final view = await AdaptyUI().createFlowView(flow: flow);

    // 3. Present the flow
    await view.present();
  } on AdaptyError catch (e) {
    debugPrint('Adapty error ${e.code}: ${e.message}');
  } catch (e) {
    debugPrint('Unexpected error: $e');
  }
}
```

**Handling events — three callbacks are required (the observer won't compile without them):**

```dart
class MyFlowsObserver extends AdaptyUIFlowsEventsObserver {
  @override
  void flowViewDidFinishPurchase(AdaptyUIFlowView view,
      AdaptyPaywallProduct product, AdaptyPurchaseResult purchaseResult) {
    // No auto-dismiss in v4 — dismiss yourself, or do nothing to let the flow continue
    if (purchaseResult is! AdaptyPurchaseResultUserCancelled) {
      view.dismiss();
    }
  }

  @override
  void flowViewDidFinishRestore(AdaptyUIFlowView view, AdaptyProfile profile) {
    // check access level, then dismiss if appropriate
    view.dismiss();
  }

  @override
  void flowViewDidReceiveError(AdaptyUIFlowView view, AdaptyError error) {
    debugPrint('Flow view error ${error.code}: ${error.message}');
  }
}

// Register before presenting any flow view:
AdaptyUI().setFlowsEventsObserver(MyFlowsObserver());
```

All other observer callbacks are optional. The default `flowViewDidPerformAction` already dismisses on `CloseAction` and opens URLs natively; the Android system back button no longer closes a flow by default — override `flowViewDidPerformAction` and handle `AndroidSystemBackAction` if the user wants that behavior back.

**Checkpoint:** Flow appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog.

**Gotcha:** Blank flow or `getFlow` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `hasViewConfiguration` is false → the flow has no on-device design, or the **Show on device** toggle is off in the Flow Builder.

### Custom paywall (manual)

Read before writing code:
```bash
curl -s https://adapty.io/docs/flutter-quickstart-manual.md
curl -s https://adapty.io/docs/fetch-paywalls-and-products-flutter.md
curl -s https://adapty.io/docs/present-remote-config-paywalls-flutter.md
curl -s https://adapty.io/docs/flutter-making-purchases.md
curl -s https://adapty.io/docs/flutter-restore-purchase.md
```

**Fetch the flow and its products:**

```dart
import 'package:adapty_flutter/adapty_flutter.dart';
import 'app_constants.dart';

Future<void> loadPaywallData() async {
  try {
    final flow = await Adapty().getFlow(
      placementId: AppConstants.placementId,
    );
    final products = await Adapty().getPaywallProducts(flow: flow);
    // Pass products to your custom paywall UI widget
  } on AdaptyError catch (e) {
    debugPrint('Adapty error ${e.code}: ${e.message}');
  }
}
```

**v4 note:** Even for custom paywalls, the v4 SDK uses `getFlow` / `AdaptyFlow` for the fetch — but products are still `AdaptyPaywallProduct`, and `getPaywallProducts(flow: flow)` is the right call to fetch them.

**Make a purchase:**

```dart
Future<void> purchaseProduct(AdaptyPaywallProduct product) async {
  try {
    final profile = await Adapty().makePurchase(product: product);
    final hasAccess =
        profile?.accessLevels[AppConstants.accessLevelId]?.isActive ?? false;
    if (hasAccess) {
      // Unlock premium content
    }
  } on AdaptyError catch (e) {
    if (e.code == AdaptyErrorCode.paymentCancelled) {
      // User cancelled — no action needed
    } else {
      debugPrint('Purchase failed ${e.code}: ${e.message}');
    }
  }
}
```

**Restore purchases:**

```dart
Future<void> restorePurchases() async {
  try {
    final profile = await Adapty().restorePurchases();
    // Check access level as above
  } on AdaptyError catch (e) {
    debugPrint('Restore failed ${e.code}: ${e.message}');
  }
}
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing purchase infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects or projects where purchases aren't yet implemented, use Flow Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management, Flow Builder, or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on App Store / Google Play Server Notifications being configured

Read before writing code:
```bash
curl -s https://adapty.io/docs/observer-vs-full-mode.md
curl -s https://adapty.io/docs/implement-observer-mode-flutter.md
curl -s https://adapty.io/docs/report-transactions-observer-mode-flutter.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or server notifications aren't configured in App settings → iOS SDK / Android SDK.

---

## Stage 3: Check subscription status

Read before writing code:
```bash
curl -s https://adapty.io/docs/flutter-check-subscription-status.md
```

**What to do:** After a purchase, check `profile.accessLevels['premium']?.isActive` to grant or deny access to paid features. For real-time updates, listen to `didUpdateProfileStream` instead of polling.

**Immediate check (e.g., on app launch or gated screen):**

```dart
Future<bool> checkPremiumAccess() async {
  try {
    final profile = await Adapty().getProfile();
    return profile.accessLevels[AppConstants.accessLevelId]?.isActive ?? false;
  } catch (e) {
    return false; // Fail closed — show paywall if unsure
  }
}
```

**Reactive updates via AdaptyService (preferred — no polling):**

```dart
// In a widget using Provider:
final isPremium = context.watch<AdaptyService>().isPremiumUser;
```

**Checkpoint:** After a sandbox purchase, `profile.accessLevels['premium']?.isActive` returns `true`. Revoking the sandbox purchase returns `false`.

**Gotcha:** `accessLevels` is empty after purchase → product has no access level assigned in the dashboard (Products page → select product → access levels).

**Android-specific gotcha:** Local access levels are disabled on Android by default. If you need offline access level caching on Android, activate with `..withGoogleLocalAccessLevelAllowed(true)`.

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

**Flutter note:** Attribution SDKs that require platform-specific setup (e.g., AppsFlyer) must be configured separately for both iOS (`ios/`) and Android (`android/`). The Adapty integration call itself is the same Dart code on both platforms.

**iOS attribution (AppsFlyer example):**
```dart
// After AppsFlyer SDK initializes and you have an IDFA/GAID:
await Adapty().updateAttribution(
  attribution,            // Map<String, dynamic> from AppsFlyer
  source: 'appsflyer',
  networkUserId: appsflyerUID,
);
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
curl -s https://adapty.io/docs/flutter-quickstart-identify.md
```

**What to do:**
- If the user ID is known at launch, pass it to `activate()` via `..withCustomerUserId(userId)` — already covered in Stage 1
- If users log in after launch, call `Adapty().identify()` after `activate()` and before `getFlow()`
- Call `Adapty().logout()` when users log out

**Identify after login:**

```dart
Future<void> onUserLogin(String userId) async {
  try {
    await Adapty().identify(userId);
    await AdaptyService.shared.reloadProfile();
  } on AdaptyError catch (e) {
    debugPrint('Adapty identify failed ${e.code}: ${e.message}');
  }
}
```

**Logout:**

```dart
Future<void> onUserLogout() async {
  try {
    await Adapty().logout();
    await UserManager.logout();
  } on AdaptyError catch (e) {
    debugPrint('Adapty logout failed ${e.code}: ${e.message}');
  }
}
```

**Checkpoint:** After calling `Adapty().identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `identify()` → `identify()` was called after `getFlow()`, so the purchase was attributed to the anonymous profile. Order: `activate()` → `identify()` → `getFlow()`.

---

## Build verification

All code is written. **Run the build yourself now via Bash — do not tell the user to build. Do not say "try building and let me know". Execute the commands below and handle the output yourself.**

### Verify dependencies are resolved

```bash
cd "$(pwd)" && flutter pub get 2>&1 | tail -5
```

### Build iOS

```bash
flutter build ios --no-codesign --debug 2>&1 | grep -E "error:|warning:|Build complete|FAILED|Xcode build done" | head -40
```

### Build Android

```bash
flutter build apk --debug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED|apk built" | head -40
```

### Handle output

**Build complete / BUILD SUCCESSFUL** → proceed to the manual checklist below.

**Build failed:**
- Errors in files you wrote → fix them directly and rebuild — do not ask the user
- `Error: Could not find package` → run `flutter pub get` then rebuild
- iOS CocoaPods conflict → run `cd ios && pod install && cd ..` then rebuild
- Android `Manifest merger failed` → fetch the installation doc and apply the backup rules fix: `curl -s https://adapty.io/docs/sdk-installation-flutter.md`
- Signing errors → use `--no-codesign` for iOS; signing is not needed to verify logic
- Android `launchMode` purchase issue → see Android troubleshooting in installation doc

Do not proceed to the manual checklist until both builds are clean. Do not hand off build errors to the user except for steps that genuinely require Xcode/Android Studio UI interaction.

---

## Before you can test: manual steps

### iOS

Read and follow `references/testing-setup-ios.md` (in this skill directory). It contains the full step-by-step checklist for:
1. Creating products in App Store Connect
2. Connecting App Store to Adapty (Bundle ID, In-App Purchase Key, Server Notifications)
3. Designing the flow in Flow Builder — template, AI generator, or from scratch *(Flow Builder only)*
4. Sandbox testing — creating a test account, switching device to sandbox, making a test purchase, verifying results

Present the iOS checklist to the user with the exact product IDs from Phase 3 already filled in.

### Android

Android requires separate setup in Google Play Console. Key steps:
1. Create products (subscriptions or one-time purchases) in **Google Play Console → Monetize → Products**
2. Connect Google Play to Adapty in **App settings → Android SDK** (provide Service Account key and Package name)
3. Configure Real-Time Developer Notifications in **App settings → Android SDK**
4. Create a closed testing track and add a test account to it
5. Use the Google Play sandbox (a physical Android device signed in with the test account; internal test track allows instant sandbox purchases)

There is no dedicated `testing-setup-android.md` in this skill yet. Fetch the relevant doc if needed:
```bash
curl -s https://adapty.io/docs/initial-android.md
curl -s https://adapty.io/docs/test-purchases-in-sandbox.md
```

---

## Stage 5: Release checklist

Run through this before submitting to App Store or Google Play.

Read before releasing:
```bash
curl -s https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- App Store connected in App settings (iOS)
- Google Play connected in App settings (Android)
- App Store Server Notifications configured in App settings → iOS SDK
- Google Play Real-Time Developer Notifications configured in App settings → Android SDK
- Sandbox purchase flow works end-to-end on both platforms
- Premium content is gated on access level check
- Restore purchases button present (Apple and Google requirement)
- Privacy policy URL set in App Store Connect and Google Play Console
- Log level set to `.warn` or `.error` for production builds (not `.verbose`)

**Gotcha:** Missing server notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations on either platform.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Onboardings** — add interactive onboarding flows powered by Adapty's builder
> 4. **Kids mode** — COPPA/COPPA-compliant mode that disables IDFA/GAID and ad data collection
> 5. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 6. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features
> 7. **Web paywalls** — set up web-based paywalls to accept payments outside the app stores

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `flutter-use-fallback-paywalls` |
| Custom user attributes | `flutter-setting-user-attributes` |
| Onboardings | `flutter-get-onboardings`, `flutter-present-onboardings`, `flutter-handling-onboarding-events` |
| Kids mode | `kids-mode-flutter` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| Web paywalls | `flutter-web-paywall` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## Flutter-specific index files

For broader context when more coverage is needed:
- Flutter docs index: `https://adapty.io/docs/flutter-llms.txt`
- Flutter full docs (large): `https://adapty.io/docs/flutter-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
- Sample app (SDK-team maintained, close to real usage — open it when a docs page doesn't show how the pieces fit together in a real app; take API usage from it, not the sample's app architecture): https://github.com/adaptyteam/AdaptySDK-Flutter/tree/master/example
