# Kotlin Multiplatform SDK Integration Reference

Platform: Kotlin Multiplatform · Language: Kotlin · Targets: Android + iOS

## Prerequisites

- Kotlin Multiplatform project with Android and/or iOS targets
- Xcode 16.2+ (for iOS target); iOS deployment target 15.0+
- Google Play Billing Library up to 8.x (Adapty defaults to 7.0.0)
- `mavenCentral()` in your Gradle repositories
- SDK v4 is currently a pre-release — pin the exact version (see Stage 1)

---

## Build verification

After each stage that writes code, run a build to catch errors immediately rather than letting them pile up. Use these helpers — run them yourself via Bash, do not ask the user to build in their IDE.

### Discover project info

```bash
# Find Gradle wrapper and list module structure
find . -maxdepth 3 -name "gradlew" ! -path "*/node_modules/*"
find . -maxdepth 4 -name "build.gradle.kts" -o -name "build.gradle" | head -20

# Find iOS workspace/project (if targeting iOS)
find . -maxdepth 5 \( -name "*.xcworkspace" -o -name "*.xcodeproj" \) ! -path "*/Pods/*" ! -path "*/.build/*"
```

### Run Android target build

```bash
# Replace :androidApp with your actual Android app module name (commonly :androidApp, :app, or :composeApp)
./gradlew :androidApp:assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | head -40
```

### Run iOS target build

```bash
# Replace SCHEME and path values with discovered values
xcodebuild \
  -workspace "YourApp.xcworkspace" \
  -scheme "YourApp" \
  -destination "generic/platform=iOS Simulator" \
  -quiet \
  build 2>&1 | grep -E "error:|warning:|Build succeeded|BUILD FAILED" | head -40
```

### Handle the output

**BUILD SUCCESSFUL / Build succeeded** → proceed to next stage.

**BUILD FAILED with errors:**
- Errors in files you wrote → fix them directly and rebuild
- `Unresolved reference: Adapty` or `adapty-kmp` dependency not found → `mavenCentral()` is missing or the dependency wasn't added to `commonMain`; check build files
- iOS: "Missing package product" or `import Adapty` fails → KMP Gradle plugin hasn't generated the iOS framework; ensure `./gradlew :shared:assembleXCFramework` (or equivalent) ran
- Android signing errors → not blocking for debug builds; can ignore until release
- iOS signing errors → not blocking for simulator builds; can ignore until device testing

Rebuild after each fix. Do not move to the next stage until the build is clean.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### AppConstants.kt (in commonMain)

Centralizes all Adapty config values in shared code. Using a `companion object` with `const val` catches placeholder values at compile time.

```kotlin
// commonMain/kotlin/com/yourapp/AppConstants.kt
object AppConstants {
    // Replace these before building
    const val ADAPTY_PUBLIC_KEY = "YOUR_PUBLIC_SDK_KEY"  // App settings → General → API keys
    const val PLACEMENT_ID = "YOUR_PLACEMENT_ID"          // Adapty Dashboard → Placements
    const val ACCESS_LEVEL_ID = "premium"                  // default; change if you use custom ones
}
```

Replace the placeholder strings with real values from Phase 3 output immediately.

### UserManager.kt (skip if app has no authentication — commonMain)

Lightweight wrapper for storing the customer user ID. Use whichever storage mechanism your KMP project uses (e.g., `multiplatform-settings`, `DataStore`, or platform-specific `expect/actual`). Example using a simple in-memory + platform storage pattern:

```kotlin
// commonMain/kotlin/com/yourapp/UserManager.kt
expect object UserManager {
    var currentUserId: String?
    fun login(userId: String)
    fun logout()
}
```

Provide `actual` implementations per platform using `SharedPreferences` (Android) and `NSUserDefaults` (iOS), or use a multiplatform settings library.

### AdaptyService.kt (commonMain shared ViewModel/Repository)

Central service that:
- Holds the current profile as observable state
- Registers the `setOnProfileUpdatedListener` for real-time subscription updates (no polling)
- Exposes a clean `isPremiumUser` computed property for gating content

```kotlin
// commonMain/kotlin/com/yourapp/AdaptyService.kt
import com.adapty.kmp.Adapty
import com.adapty.kmp.models.AdaptyProfile
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AdaptyService {
    private val _profile = MutableStateFlow<AdaptyProfile?>(null)
    val profile: StateFlow<AdaptyProfile?> = _profile.asStateFlow()

    val isPremiumUser: Boolean
        get() = _profile.value?.accessLevels?.get(AppConstants.ACCESS_LEVEL_ID)?.isActive == true

    fun initialize() {
        // Called after activate() — listen for real-time subscription changes
        Adapty.setOnProfileUpdatedListener { updatedProfile ->
            _profile.value = updatedProfile
        }
    }

    suspend fun reloadProfile() {
        Adapty.getProfile()
            .onSuccess { profile -> _profile.value = profile }
            .onError { /* log or handle */ }
    }
}
```

Expose this as a singleton (via `object`, a DI framework, or your KMP ViewModel layer) and inject or reference it wherever paywall or access checks occur.

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s "https://adapty.io/docs/sdk-installation-kotlin-multiplatform.md?ref=skill-<sessionToken>"
```

Then guide the user through each step explicitly.

### Step 1: Add Gradle dependencies

**Ask the user which Gradle setup they use** (`.gradle`, `.gradle.kts`, or version catalog). Then write the dependency in the correct location.

The dependency goes in the **shared module's** `build.gradle.kts` (or equivalent), under `commonMain` — NOT in the Android app module.

**Option A: module-level build.gradle.kts**
```kotlin
kotlin {
    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation("io.adapty:adapty-kmp:4.0.0-beta.1")
                // Add adapty-kmp-ui only if using Flow Builder with Compose Multiplatform:
                // implementation("io.adapty:adapty-kmp-ui:4.0.0-beta.1")
            }
        }
    }
}
```

**Option B: version catalog (libs.versions.toml)**
```toml
[versions]
adapty-kmp = "4.0.0-beta.1"

[libraries]
adapty-kmp = { module = "io.adapty:adapty-kmp", version.ref = "adapty-kmp" }
adapty-kmp-ui = { module = "io.adapty:adapty-kmp-ui", version.ref = "adapty-kmp" }
```

Then in `build.gradle.kts`:
```kotlin
kotlin {
    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation(libs.adapty.kmp)
                // implementation(libs.adapty.kmp.ui)  // only for Flow Builder + Compose Multiplatform
            }
        }
    }
}
```

**SDK v4 is a pre-release — pin the exact version.** Gradle does not resolve pre-release versions through dynamic ranges (`+`, `latest.release`), so a dynamic range silently falls back to 3.x. Check [Maven Central](https://search.maven.org/search?q=io.adapty:adapty-kmp) for the latest 4.x version and use it verbatim.

If you get a Maven-related error, make sure `mavenCentral()` is in your Gradle repositories:
```groovy
// settings.gradle or top-level build.gradle
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}
```

### Step 2: Activate the SDK

Adapty must be activated as early as possible on each platform. The configuration is built in shared Kotlin code, but the activation call must happen on the platform-specific entry point.

**Shared configuration builder (commonMain):**
```kotlin
// commonMain/kotlin/com/yourapp/AdaptyInitializer.kt
import com.adapty.kmp.Adapty
import com.adapty.kmp.AdaptyConfig
import com.adapty.kmp.AdaptyLogLevel

fun initializeAdapty(customerUserId: String? = null) {
    val config = AdaptyConfig
        .Builder(AppConstants.ADAPTY_PUBLIC_KEY)
        .withLogLevel(AdaptyLogLevel.INFO) // use VERBOSE during development
        .withCustomerUserId(customerUserId) // pass null if no auth system
        // Add .withActivateUI(true) if using Flow Builder
        .build()

    Adapty.activate(configuration = config)
        .onSuccess {
            AdaptyService.initialize() // register profile update listener
        }
        .onError { error ->
            // log error; app can continue, but Adapty features will be unavailable
        }
}
```

**Android entry point — Application class (androidMain or androidApp module):**
```kotlin
// androidApp/src/main/kotlin/com/yourapp/App.kt
import android.app.Application

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        initializeAdapty(customerUserId = UserManager.currentUserId)
    }
}
```

Register it in `AndroidManifest.xml`:
```xml
<application android:name=".App" ...>
```

**iOS entry point — AppDelegate or SwiftUI App (iosMain or iOS Xcode project):**

SwiftUI:
```swift
// iosApp/iosApp/YourApp.swift
import SwiftUI
import shared // your KMP shared module

@main
struct YourApp: App {
    init() {
        AdaptyInitializerKt.initializeAdapty(customerUserId: UserManager.shared.currentUserId)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

UIKit AppDelegate:
```swift
import UIKit
import shared

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        AdaptyInitializerKt.initializeAdapty(customerUserId: UserManager.shared.currentUserId)
        return true
    }
}
```

The SDK key comes from `AppConstants` — already set in the recommended architecture step above.

**Android Proguard:** Before production, add to your Proguard configuration:
```
-keep class com.adapty.** { *; }
```

**Checkpoint:** App builds and runs without errors. Logcat (Android) shows an Adapty activation log line. Xcode console (iOS) shows the same.

**Gotcha:** "Public API key is missing" or silent failure → the placeholder wasn't replaced with the real key from App settings → General → API keys.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Flow Builder

Read before writing code:
```
https://adapty.io/docs/kmp-quickstart-paywalls.md
https://adapty.io/docs/kmp-get-pb-paywalls.md
https://adapty.io/docs/kmp-present-paywalls.md
https://adapty.io/docs/kmp-handling-events.md
https://adapty.io/docs/kmp-handle-paywall-actions.md
```

**v4 API names:** Flow Builder uses the new `getFlow` / `AdaptyFlow` / `createFlowView` / `AdaptyUIFlowView` / `AdaptyUIFlowsEventsObserver` family. The same APIs also render existing Paywall Builder paywalls — no dashboard changes are required for users migrating from Paywall Builder. You no longer pass a `locale` when fetching (localization resolves automatically on render), the observer registers via `setFlowsEventsObserver`, and all `paywallViewDid*` callbacks are now `flowViewDid*`. Products are still `AdaptyPaywallProduct`.

**Required call signature** — always use the named parameter:
```kotlin
// Correct
Adapty.getFlow(placementId = AppConstants.PLACEMENT_ID)

// Wrong — compiles but incorrect usage
Adapty.getFlow(AppConstants.PLACEMENT_ID)
```

**With Compose Multiplatform (recommended):**
```kotlin
// commonMain ViewModel or coroutine scope
viewModelScope.launch {
    Adapty.getFlow(placementId = AppConstants.PLACEMENT_ID)
        .onSuccess { flow ->
            AdaptyUI.createFlowView(flow = flow)
                .onSuccess { view ->
                    view.present()
                }
                .onError { error ->
                    // the flow has no on-device design, or view creation failed
                }
        }
        .onError { error ->
            // handle flow fetch error
        }
}
```

A flow view is single-use: after `dismiss()`, the view is destroyed — call `createFlowView` again to present the flow once more.

**Handle events:** all observer callbacks have default implementations in Kotlin — override only what you need. The v4 defaults differ from v3: the close button dismisses the view, but the Android system back button **keeps it open**, a successful purchase **does not auto-dismiss**, an error **dismisses** the view, and URLs open natively.

```kotlin
AdaptyUI.setFlowsEventsObserver(object : AdaptyUIFlowsEventsObserver {
    override fun flowViewDidFinishPurchase(
        view: AdaptyUIFlowView,
        product: AdaptyPaywallProduct,
        purchaseResult: AdaptyPurchaseResult
    ) {
        // v4 no longer auto-dismisses after purchase — dismiss yourself,
        // or do nothing to let the flow continue
        if (purchaseResult !is AdaptyPurchaseResult.UserCanceled) {
            mainUiScope.launch { view.dismiss() }
        }
    }

    override fun flowViewDidPerformAction(view: AdaptyUIFlowView, action: AdaptyUIAction) {
        when (action) {
            // restore the v3 behavior where system back closes the flow
            is AdaptyUIAction.AndroidSystemBackAction -> mainUiScope.launch { view.dismiss() }
            // keep the defaults: CloseAction dismisses, OpenUrlAction opens natively
            else -> super.flowViewDidPerformAction(view, action)
        }
    }
})
```

**Without Compose Multiplatform** — use `createNativeFlowView` from the core module (no `adapty-kmp-ui` dependency needed):

Android:
```kotlin
val nativeView = AdaptyUI.createNativeFlowView(
    context = context,
    viewModelStoreOwner = activity,
    flow = flow,
    observer = myFlowObserver,
)
// Embed nativeView.view in your layout
```

Embedded views don't apply safe-area paddings by default (your layout handles insets); pass `androidEnableSafeArea = true` to opt in (Android-only).

iOS (requires a base class workaround due to KMP Swift interop):
```kotlin
// iosMain — declare open base class so Swift can subclass it
open class BaseFlowObserver : AdaptyUIFlowsEventsObserver
```

```swift
// Swift
class MyFlowObserver: BaseFlowObserver {
    override func flowViewDidPerformAction(view: AdaptyUIFlowView, action: any AdaptyUIAction) {
        if action is AdaptyUIActionCloseAction {
            // remove nativeView from your view hierarchy
        }
    }
}

let nativeView = AdaptyUI.shared.createNativeFlowView(flow: flow, observer: MyFlowObserver())
// nativeView.viewController is a UIViewController — add to SwiftUI or UIKit hierarchy
```

Call `nativeView.dispose()` when removing an embedded view from your layout — it unregisters the event listener and releases resources.

**Checkpoint:** Flow appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog (Play Store sandbox on Android, App Store sandbox on iOS).

**Gotcha:** Blank flow or `getFlow` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `createFlowView` fails → the flow has no on-device design, or the **Show on device** toggle is off in the Flow Builder.

### Custom paywall (manual)

Read before writing code:
```
https://adapty.io/docs/kmp-quickstart-manual.md
https://adapty.io/docs/fetch-paywalls-and-products-kmp.md
https://adapty.io/docs/present-remote-config-paywalls-kmp.md
https://adapty.io/docs/kmp-making-purchases.md
https://adapty.io/docs/kmp-restore-purchase.md
```

**Fetch the flow and its products:**
```kotlin
Adapty.getFlow(
    placementId = AppConstants.PLACEMENT_ID,
    fetchPolicy = AdaptyPaywallFetchPolicy.Default,
    loadTimeout = 5.seconds
).onSuccess { flow ->
    Adapty.getPaywallProducts(flow)
        .onSuccess { products ->
            // render your custom paywall UI with products
        }
        .onError { error ->
            // handle error
        }
}.onError { error ->
    // handle error
}
```

**v4 note:** Even for custom paywalls, the v4 SDK uses `getFlow` / `AdaptyFlow` for the fetch — there is no `locale` parameter anymore. Products are still `AdaptyPaywallProduct`, and `getPaywallProducts(flow)` is the right call to fetch them.

**Do not hardcode product IDs.** The number and type of products can change in the dashboard without an app update. Display all products returned by `getPaywallProducts`.

**Make a purchase:**
```kotlin
Adapty.makePurchase(product = selectedProduct)
    .onSuccess { purchaseResult ->
        when (purchaseResult) {
            is AdaptyPurchaseResult.Success -> {
                val isPremium = purchaseResult.profile
                    .accessLevels[AppConstants.ACCESS_LEVEL_ID]?.isActive == true
                // unlock content if isPremium
            }
            is AdaptyPurchaseResult.UserCanceled -> { /* user backed out — no error UI needed */ }
            is AdaptyPurchaseResult.Pending -> { /* e.g. awaiting approval; deliver on profile update */ }
        }
    }
    .onError { error ->
        // handle purchase error
    }
```

**Restore purchases (required by both App Store and Play Store guidelines):**
```kotlin
Adapty.restorePurchases()
    .onSuccess { profile ->
        // profile updated with restored purchases
    }
    .onError { error ->
        // handle error
    }
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing purchase infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects, use Flow Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management, Flow Builder, or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on App Store Server Notifications (iOS) and Play Store RTDN (Android) being configured

Read before writing code:
```
https://adapty.io/docs/observer-vs-full-mode.md
https://adapty.io/docs/implement-observer-mode-kmp.md
https://adapty.io/docs/report-transactions-observer-mode-kmp.md
https://adapty.io/docs/kmp-present-flows-in-observer-mode.md
```

**v4 note:** If the user wants to show Flow Builder flows while staying in Observer mode, v4 supports it: register an `AdaptyUIObserverModeResolver` via `AdaptyUI.setObserverModeResolver(...)` and run your own purchase/restore code when the resolver fires — without it, nothing happens when the user taps buy. See the last doc above.

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or server notifications aren't configured (App Store Server Notifications for iOS, RTDN for Android).

---

## Stage 3: Check subscription status

Read before writing code:
```
https://adapty.io/docs/kmp-check-subscription-status.md
https://adapty.io/docs/kmp-listen-subscription-changes.md
```

**What to do:** Use the `AdaptyService` from the recommended architecture. For immediate checks, call `getProfile`. For reactive updates, the `setOnProfileUpdatedListener` registered during `initialize()` keeps the profile fresh automatically.

**Immediate check:**
```kotlin
Adapty.getProfile()
    .onSuccess { profile ->
        val isActive = profile.accessLevels[AppConstants.ACCESS_LEVEL_ID]?.isActive == true
        if (!isActive) showPaywall() else showPremiumContent()
    }
    .onError { showPaywall() } // safe fallback
```

**Reactive (using the service):**
```kotlin
// Collect from AdaptyService.profile StateFlow in your ViewModel
viewModelScope.launch {
    adaptyService.profile.collect { profile ->
        val hasAccess = profile?.accessLevels?.get(AppConstants.ACCESS_LEVEL_ID)?.isActive == true
        // update UI accordingly
    }
}
```

**Checkpoint:** After a sandbox purchase, `profile.accessLevels["premium"]?.isActive` returns `true`. Revoking the sandbox subscription returns `false`.

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
```
https://adapty.io/docs/kmp-quickstart-identify.md
https://adapty.io/docs/kmp-identifying-users.md
```

**What to do:**

- **Preferred:** Pass `customerUserId` during `activate()` if you already have the ID at launch (see `initializeAdapty` in Stage 1):
  ```kotlin
  AdaptyConfig.Builder(AppConstants.ADAPTY_PUBLIC_KEY)
      .withCustomerUserId(UserManager.currentUserId)
      .build()
  ```

- **After login/signup:** Call `Adapty.identify()` when the user authenticates:
  ```kotlin
  Adapty.identify("your-user-id") // must be unique per user — never hardcode
      .onSuccess { /* user is now identified */ }
      .onError { error -> /* handle */ }
  ```

- **On logout:** Call `Adapty.logout()` to create a new anonymous profile:
  ```kotlin
  Adapty.logout()
      .onSuccess { UserManager.logout() }
      .onError { error -> /* handle */ }
  ```

- For apps where users can purchase before logging in: `identify()` at login time will correctly link the anonymous profile's purchases to the identified profile — Adapty handles the merge automatically.

**Checkpoint:** After calling `identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `identify()` → `identify()` was called after `getFlow()`, so the purchase was attributed to the anonymous profile. Order: `activate()` → `identify()` → `getFlow()`.

---

## Build verification

All code is written. **Run both platform builds yourself now via Bash — do not tell the user to build. Do not say "try building and let me know". Execute the commands below and handle the output yourself.**

### Discover project info

```bash
find . -maxdepth 3 -name "gradlew" ! -path "*/node_modules/*"
find . -maxdepth 5 \( -name "*.xcworkspace" -o -name "*.xcodeproj" \) ! -path "*/Pods/*" ! -path "*/.build/*"
```

### Android build

```bash
# Replace :androidApp with your actual Android app module
./gradlew :androidApp:assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | head -40
```

### iOS build

```bash
xcodebuild \
  -workspace "YourApp.xcworkspace" \
  -scheme "YourApp" \
  -destination "generic/platform=iOS Simulator" \
  -quiet \
  build 2>&1 | grep -E "error:|warning:|Build succeeded|BUILD FAILED" | head -40
```

### Handle output

**BUILD SUCCESSFUL / Build succeeded** → proceed to the manual checklist below.

**BUILD FAILED (Android):**
- Errors in files you wrote → fix them directly and rebuild
- `Unresolved reference: Adapty` → dependency not in `commonMain` or `mavenCentral()` missing
- Manifest merger conflict (`android:fullBackupContent`, `android:dataExtractionRules`) → fetch the troubleshooting section of the install doc: `curl -s https://adapty.io/docs/sdk-installation-kotlin-multiplatform.md`
- `launchMode` purchase issues → Activity starting purchases must use `standard` or `singleTop`

**BUILD FAILED (iOS):**
- Errors in files you wrote → fix them directly and rebuild
- KMP Swift interop issues with `AdaptyUIFlowsEventsObserver` → use the open base class pattern from Stage 2
- `import shared` fails → KMP framework wasn't generated; run `./gradlew :shared:assembleXCFramework` (or your project's equivalent task) first
- Signing errors → safe to ignore for simulator builds

Do not proceed to the manual checklist until both builds are clean. Do not hand off build errors to the user except for cases that require IDE or Xcode UI interaction.

---

## Before you can test: manual steps

Both platforms require store-side setup before sandbox testing works.

**For iOS:** Read and follow `references/testing-setup-ios.md` (in this skill directory). It covers:
1. Creating products in App Store Connect
2. Connecting App Store to Adapty (Bundle ID, In-App Purchase Key, App Store Server Notifications)
3. Designing the flow in Flow Builder — template, AI generator, or from scratch *(Flow Builder only)*
4. Sandbox testing — creating a sandbox tester account, switching device to sandbox, making a test purchase, verifying results

Present the iOS checklist with the exact iOS product IDs from Phase 3 already filled in (`--ios-product-id` values).

**For Android:** Fetch the Android testing guide:
```bash
curl -s https://adapty.io/docs/testing-on-android.md
```

Key Android testing setup steps:
1. Publish the app to at least **internal testing** track in Google Play Console (needed to test billing)
2. Add a **license tester** email in Google Play Console → Setup → License testing
3. Connect Google Play to Adapty: App settings → Android SDK (service account key, bundle ID)
4. Configure **Real-Time Developer Notifications (RTDN)** in App settings → Android SDK
5. Make a test purchase using the license tester account on a physical Android device

Present the Android checklist with the exact Android product IDs from Phase 3 already filled in (`--android-product-id` values).

---

## Stage 5: Release checklist

Run through this before submitting to store review.

Read before releasing:
```
https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- App Store connected in App settings (iOS apps)
- Google Play connected in App settings (Android apps)
- App Store Server Notifications configured in App settings → iOS SDK
- Google Play RTDN configured in App settings → Android SDK
- Sandbox purchase flow works end-to-end on both platforms
- Premium content is gated on access level check
- Restore purchases button present (required by both Apple and Google)
- Proguard rule added: `-keep class com.adapty.** { *; }` (Android)
- Privacy policy URL set in App Store Connect and Google Play Console

**Gotcha:** Missing server notifications (either platform) → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations.

**Gotcha:** Proguard stripping Adapty classes → `ClassNotFoundException` in production. Always add the `-keep class com.adapty.** { *; }` rule.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Promotional offers** — set up subscription discounts and win-back offers for lapsed subscribers
> 4. **Onboardings** — *(deprecated in SDK v4)* legacy WebView-based onboardings still work but no longer receive fixes; Flow Builder covers onboarding flows natively
> 5. **Kids mode** — COPPA/GDPR-compliant mode that disables GAID and ad data collection
> 6. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 7. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `kmp-use-fallback-paywalls` |
| Custom user attributes | `kmp-setting-user-attributes` |
| Promotional offers | `app-store-offers`, `create-offer` |
| Onboardings | `kmp-get-onboardings`, `kmp-present-onboardings`, `kmp-handling-onboarding-events` |
| Kids mode | `kids-mode-kmp` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| Web paywalls | `kmp-web-paywalls` |
| App Tracking Transparency (iOS) | `kmp-deal-with-att` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## KMP index files

For broader context when the LLM needs more coverage:
- KMP docs index: `https://adapty.io/docs/kmp-llms.txt`
- KMP full docs (large): `https://adapty.io/docs/kmp-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
- All Adapty docs (very large): `https://adapty.io/docs/llms-full.txt`
