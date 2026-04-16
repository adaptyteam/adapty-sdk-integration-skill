# iOS SDK Integration Reference

Platform: iOS · Language: Swift · UI: SwiftUI or UIKit

## Prerequisites

- iOS 15.0+ (iOS 13+ for core module only, but StoreKit 2 and AdaptyUI require 15+)
- Xcode with Swift Package Manager

---

## Build verification

After each stage that writes code, run a build to catch errors immediately rather than letting them pile up. Use this helper — run it yourself via Bash, do not ask the user to build in Xcode.

### Discover project info

```bash
# Find the .xcodeproj or .xcworkspace and available schemes
find . -maxdepth 3 \( -name "*.xcworkspace" -o -name "*.xcodeproj" \) ! -path "*/Pods/*" ! -path "*/.build/*"
xcodebuild -list 2>&1 | head -30
```

Use the workspace if one exists (CocoaPods projects always have one). Otherwise use the `.xcodeproj`.

### Run a build

```bash
# Replace SCHEME and WORKSPACE_OR_PROJECT with discovered values
xcodebuild \
  -workspace "YourApp.xcworkspace" \   # or -project "YourApp.xcodeproj"
  -scheme "YourApp" \
  -destination "generic/platform=iOS Simulator" \
  -quiet \
  build 2>&1 | grep -E "error:|warning:|Build succeeded|BUILD FAILED" | head -40
```

### Handle the output

**Build succeeded** → proceed to next stage.

**BUILD FAILED with errors:**
- Errors in files you wrote → fix them directly and rebuild
- Errors in files you didn't write → explain the error to the user with a concrete fix
- "Missing package product" errors → the Adapty package wasn't added in Xcode yet; use `AskUserQuestion` to walk the user through adding it (Stage 1, Step 1)
- Signing errors → not blocking for simulator builds; can ignore until device testing
- Module not found (`import Adapty` fails) → package not resolved; ask user to do **File → Packages → Resolve Package Versions** in Xcode

Rebuild after each fix. Do not move to the next stage until the build is clean.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### AppConstants.swift

Centralizes all Adapty config values. The `#error` directive causes a compile error if someone ships with placeholder values — a safety net against accidental production builds with wrong keys.

```swift
enum AppConstants {
    // Replace these before building — #error will block compilation until you do
    #if DEBUG
    static let adaptyPublicKey = "YOUR_PUBLIC_SDK_KEY"  // from Adapty Dashboard → App settings → API keys
    static let placementId = "YOUR_PLACEMENT_ID"         // from Adapty Dashboard → Placements
    #else
    static let adaptyPublicKey = "YOUR_PUBLIC_SDK_KEY"
    static let placementId = "YOUR_PLACEMENT_ID"
    #endif
    static let accessLevelId = "premium"                  // default access level; change if you use custom ones
}
```

Replace the placeholder strings with real values from Phase 3 output immediately.

### UserManager.swift (skip if app has no authentication)

Lightweight UserDefaults wrapper for the customer user ID. Pass this to `Adapty.activate()` on launch so purchases are always attributed to the right profile.

```swift
enum UserManager {
    private static let key = "app.adapty.userId"

    static var currentUserId: String? {
        UserDefaults.standard.string(forKey: key)
    }
    static func login(userId: String) {
        UserDefaults.standard.set(userId, forKey: key)
    }
    static func logout() {
        UserDefaults.standard.removeObject(forKey: key)
    }
}
```

### AdaptyService.swift (or MainViewModel)

Central ViewModel that:
- Holds the current profile as `@Published` state
- Conforms to `AdaptyDelegate` for real-time subscription updates (no polling needed)
- Exposes a clean `isPremiumUser` computed property for gating content

```swift
@MainActor
final class AdaptyService: NSObject, ObservableObject, AdaptyDelegate {
    static let shared = AdaptyService()

    @Published var profile: AdaptyProfile?

    var isPremiumUser: Bool {
        profile?.accessLevels[AppConstants.accessLevelId]?.isActive ?? false
    }

    func reloadProfile() async {
        profile = try? await Adapty.getProfile()
    }

    // Called automatically when Adapty detects a subscription change
    func didReceiveUpdatedProfile(_ profile: AdaptyProfile) {
        self.profile = profile
    }
}
```

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s https://adapty.io/docs/sdk-installation-ios.md
```

Then guide the user through each step explicitly.

### Step 1: Add the Swift package

Tell the user to do this in Xcode:

1. **File → Add Package Dependencies...**
2. Enter the repository URL:
   ```
   https://github.com/adaptyteam/AdaptySDK-iOS.git
   ```
3. Select the latest stable version → click **Add Package**
4. In the "Choose Package Products" dialog, select:
   - **Adapty** — always required
   - **AdaptyUI** — only if using Paywall Builder
   - Do NOT select any other packages
5. Click **Add Package**
6. Verify: "Adapty" (and "AdaptyUI" if selected) should appear under **Package Dependencies** in the project navigator

Use `AskUserQuestion` to confirm the package was added successfully before proceeding.

### Step 2: Add activation code

Ask the user whether they use SwiftUI or UIKit. Then write the activation code in the correct location with the actual SDK key from Phase 3:

**SwiftUI** — add to the `@main` App struct:
```swift
import Adapty
import AdaptyUI  // only if using Paywall Builder

@main
struct YourApp: App {
    @StateObject private var adaptyService = AdaptyService.shared

    init() {
        let config = AdaptyConfiguration
            .builder(withAPIKey: AppConstants.adaptyPublicKey)
            .with(customerUserId: UserManager.currentUserId) // remove if no auth
            .with(logLevel: .info)
            .build()
        Adapty.delegate = AdaptyService.shared
        Task { try await Adapty.activate(with: config) }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(adaptyService)
                .task { await adaptyService.reloadProfile() }
        }
    }
}
```

**UIKit** — add to `AppDelegate.application(_:didFinishLaunchingWithOptions:)`:
```swift
import Adapty
import AdaptyUI  // only if using Paywall Builder

func application(_ application: UIApplication, didFinishLaunchingWithOptions ...) -> Bool {
    let config = AdaptyConfiguration
        .builder(withAPIKey: AppConstants.adaptyPublicKey)
        .with(customerUserId: UserManager.currentUserId) // remove if no auth
        .with(logLevel: .info)
        .build()
    Adapty.delegate = AdaptyService.shared
    Task { try await Adapty.activate(with: config) }
    return true
}
```

The SDK key comes from `AppConstants` — already set in the recommended architecture step above.

**Checkpoint:** App builds and runs without errors. Xcode console shows an Adapty activation log line.

**Gotcha:** "Public API key is missing" or silent failure → the placeholder wasn't replaced with the real key from App settings → General → API keys.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Paywall Builder

Read before writing code:
```
https://adapty.io/docs/ios-quickstart-paywalls.md
https://adapty.io/docs/get-pb-paywalls.md
https://adapty.io/docs/ios-present-paywalls.md
https://adapty.io/docs/ios-handling-events.md
https://adapty.io/docs/handle-paywall-actions.md
```

**Required call signature** — always use the labeled parameter:
```swift
// Correct
let paywall = try await Adapty.getPaywall(placementId: AppConstants.placementId)

// Wrong — Swift will not infer the label; this compiles but is incorrect usage
let paywall = try await Adapty.getPaywall(AppConstants.placementId)
```

**Checkpoint:** Paywall appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog.

**Gotcha:** Blank paywall or `getPaywall` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

### Custom paywall (manual)

Read before writing code:
```
https://adapty.io/docs/ios-quickstart-manual.md
https://adapty.io/docs/fetch-paywalls-and-products.md
https://adapty.io/docs/present-remote-config-paywalls.md
https://adapty.io/docs/making-purchases.md
https://adapty.io/docs/restore-purchase.md
```

**Required call signature** — always use the labeled parameter:
```swift
let paywall = try await Adapty.getPaywall(placementId: AppConstants.placementId)
// NOT: Adapty.getPaywall(AppConstants.placementId)
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing StoreKit purchase infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects or projects where purchases aren't yet implemented, use Paywall Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on App Store Server Notifications being configured

Read before writing code:
```
https://adapty.io/docs/observer-vs-full-mode.md
https://adapty.io/docs/implement-observer-mode.md
https://adapty.io/docs/report-transactions-observer-mode.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or App Store Server Notifications aren't configured in App settings → iOS SDK.

## Stage 3: Check subscription status

Read before writing code:
```
https://adapty.io/docs/ios-check-subscription-status.md
```

**What to do:** After a purchase, check `profile.accessLevels["premium"]?.isActive` to grant or deny access to paid features. For real-time updates, listen for profile changes instead of polling.

**Checkpoint:** After a sandbox purchase, checking `profile.accessLevels["premium"]?.isActive` returns `true`. Revoking the sandbox purchase returns `false`.

**Gotcha:** `accessLevels` is empty after purchase → product has no access level assigned in the dashboard (Products page → select product → access levels).

---

## Stage 4: Identify users

Use `AskUserQuestion` before deciding to skip:

> "This app has no login system, but you can still identify users with a stable ID tied to the device or installation. This gives each user a consistent Adapty profile across sessions, which helps with analytics accuracy, A/B test consistency, and avoiding duplicate profiles after reinstall. Do you have an ID you'd like to use, or would you like to discuss options?"
> - **Yes, I have an ID in mind** — tell me what it is and I'll implement identification
> - **Let's discuss** — I'll ask a few questions to help you decide
> - **No, skip** — anonymous profiles are fine for this app

If the user says no, skip the rest of this stage.

Read before writing code:
```
https://adapty.io/docs/ios-quickstart-identify.md
```

**What to do:**
- Call `Adapty.identify("your-user-id")` after `activate()` and before `getPaywall()`
- For apps where users can purchase before logging in, call `identify()` at login — Adapty handles profile merging automatically
- Call `Adapty.logout()` when users log out

**Checkpoint:** After calling `identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `identify()` → `identify()` was called after `getPaywall()`, so the purchase was attributed to the anonymous profile. Order: `activate()` → `identify()` → `getPaywall()`.

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

## Build verification

All code is written. **Run the build yourself now via Bash — do not tell the user to build. Do not say "try building and let me know". Execute the xcodebuild commands below and handle the output yourself.**

### Discover project info

```bash
find . -maxdepth 3 \( -name "*.xcworkspace" -o -name "*.xcodeproj" \) \
  ! -path "*/Pods/*" ! -path "*/.build/*"
xcodebuild -list 2>&1 | head -30
```

Use `.xcworkspace` if one exists (CocoaPods projects always have one). Otherwise use `.xcodeproj`.

### Build

```bash
xcodebuild \
  -workspace "YourApp.xcworkspace" \
  -scheme "YourApp" \
  -destination "generic/platform=iOS Simulator" \
  -quiet \
  build 2>&1 | grep -E "error:|warning:|Build succeeded|BUILD FAILED" | head -40
```

### Handle output

**Build succeeded** → proceed to the manual checklist below.

**BUILD FAILED:**
- Errors in files you wrote → fix them directly and rebuild — do not ask the user
- `import Adapty` module not found → package not yet resolved; ask user to do **File → Packages → Resolve Package Versions** in Xcode, then rebuild
- "Missing package product" → package wasn't added in Xcode; walk user through Stage 1 Step 1 again
- Signing errors → safe to ignore for simulator builds; not blocking

Do not proceed to the manual checklist until the build is clean. Do not hand off build errors to the user except for the two cases above that require Xcode UI interaction.

---

## Before you can test: manual steps

Read and follow `references/testing-setup-ios.md` (in this skill directory). It contains the full step-by-step checklist for:
1. Creating products in App Store Connect
2. Connecting App Store to Adapty (Bundle ID, In-App Purchase Key, Server Notifications)
3. Designing the paywall in Paywall Builder — template, AI generator, or from scratch *(Paywall Builder only)*
4. Sandbox testing — creating a test account, switching device to sandbox, making a test purchase, verifying results

Present the checklist to the user with the exact product IDs from Phase 3 already filled in.

---

## Stage 5: Release checklist

Run through this before submitting to App Store review.

Read before releasing:
```
https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- Store connected in App settings
- App Store Server Notifications configured in App settings → iOS SDK
- Sandbox purchase flow works end-to-end
- Premium content is gated on access level check
- Restore purchases button present (Apple requirement)
- Privacy policy URL set in App Store Connect

**Gotcha:** Missing App Store Server Notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Promotional offers** — set up subscription discounts and win-back offers for lapsed subscribers
> 4. **Onboardings** — add interactive onboarding flows powered by Adapty's builder
> 5. **Kids mode** — COPPA-compliant mode that disables IDFA and ad data collection
> 6. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 7. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `ios-use-fallback-paywalls` |
| Custom user attributes | `setting-user-attributes` |
| Promotional offers | `app-store-offers`, `create-offer` |
| Onboardings | `get-onboardings`, `ios-present-onboardings`, `ios-handling-onboarding-events` |
| Kids mode | `kids-mode` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## iOS-specific index files

For broader context when the LLM needs more coverage:
- iOS docs index: `https://adapty.io/docs/ios-llms.txt`
- iOS full docs (large): `https://adapty.io/docs/ios-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
