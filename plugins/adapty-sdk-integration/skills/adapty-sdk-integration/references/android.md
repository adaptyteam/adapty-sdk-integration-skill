# Android SDK Integration Reference

Platform: Android · Language: Kotlin / Java · UI: Jetpack Compose or XML Views

## Prerequisites

- `minSdkVersion 21` (Android 5.0+)
- Android Studio with Gradle build system
- Google Play Developer account with app registered

---

## Build verification

After each stage that writes code, run a build to catch errors immediately rather than letting them pile up. Use this helper — run it yourself via Bash, do not ask the user to build in Android Studio.

### Discover project info

```bash
# Find the root build.gradle and module structure
find . -maxdepth 3 \( -name "build.gradle" -o -name "build.gradle.kts" \) ! -path "*/.gradle/*" ! -path "*/build/*" | head -20
ls -1 . | head -20   # list top-level dirs to identify module names
```

The app module is typically named `app`. Confirm by looking for `apply plugin: 'com.android.application'` or `id("com.android.application")` in `build.gradle` / `build.gradle.kts`.

### Run a build

```bash
# From the project root directory
./gradlew assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED|FAILURE:" | head -50
```

For a faster check that skips APK packaging:

```bash
./gradlew compileDebugKotlin 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED" | head -40
```

### Handle the output

**BUILD SUCCESSFUL** → proceed to next stage.

**BUILD FAILED with errors:**
- Errors in files you wrote → fix them directly and rebuild
- Errors in files you didn't write → explain the error to the user with a concrete fix
- `Unresolved reference: Adapty` or `Cannot access class 'com.adapty'` → the Gradle dependency wasn't synced; ask user to do **File → Sync Project with Gradle Files** in Android Studio, then rebuild
- `Could not resolve io.adapty:android-sdk` → `mavenCentral()` is missing from the repository block (see Stage 1 troubleshooting)
- `Manifest merger failed` → see the backup rules troubleshooting section in the installation doc

Rebuild after each fix. Do not move to the next stage until the build is clean.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### AppConstants.kt

Centralizes all Adapty config values. The `error()` call in the init block causes a runtime crash in debug builds if placeholders are not replaced — a safety net against shipping with wrong keys.

```kotlin
object AppConstants {
    // Replace these before building — the debug check below will crash if you don't
    const val ADAPTY_PUBLIC_KEY = "YOUR_PUBLIC_SDK_KEY"  // from Adapty Dashboard → App settings → API keys
    const val PLACEMENT_ID = "YOUR_PLACEMENT_ID"          // from Adapty Dashboard → Placements
    const val ACCESS_LEVEL_ID = "premium"                  // default access level; change if you use custom ones

    init {
        if (ADAPTY_PUBLIC_KEY == "YOUR_PUBLIC_SDK_KEY") {
            error("Replace AppConstants.ADAPTY_PUBLIC_KEY with your real SDK key before building")
        }
    }
}
```

Replace the placeholder strings with real values from Phase 3 output immediately.

### UserManager.kt (skip if app has no authentication)

Lightweight SharedPreferences wrapper for the customer user ID. Pass this to `AdaptyConfig.Builder` on launch so purchases are always attributed to the right profile.

```kotlin
object UserManager {
    private const val KEY = "app.adapty.userId"

    fun getCurrentUserId(context: Context): String? {
        return context.getSharedPreferences("adapty_prefs", Context.MODE_PRIVATE)
            .getString(KEY, null)
    }

    fun login(context: Context, userId: String) {
        context.getSharedPreferences("adapty_prefs", Context.MODE_PRIVATE)
            .edit().putString(KEY, userId).apply()
    }

    fun logout(context: Context) {
        context.getSharedPreferences("adapty_prefs", Context.MODE_PRIVATE)
            .edit().remove(KEY).apply()
    }
}
```

### AdaptyService.kt (ViewModel/Repository pattern)

Central ViewModel that:
- Holds the current profile as `StateFlow` for reactive UI updates
- Sets up `Adapty.setOnProfileUpdatedListener` for real-time subscription updates (no polling needed)
- Exposes a clean `isPremiumUser` property for gating content

```kotlin
class AdaptyService : ViewModel() {

    private val _profile = MutableStateFlow<AdaptyProfile?>(null)
    val profile: StateFlow<AdaptyProfile?> = _profile.asStateFlow()

    val isPremiumUser: Boolean
        get() = _profile.value?.accessLevels?.get(AppConstants.ACCESS_LEVEL_ID)?.isActive == true

    init {
        // Called automatically on app start with cached data, and whenever subscription changes
        Adapty.setOnProfileUpdatedListener { updatedProfile ->
            _profile.value = updatedProfile
        }
    }

    fun reloadProfile() {
        viewModelScope.launch {
            Adapty.getProfile { result ->
                if (result is AdaptyResult.Success) {
                    _profile.value = result.value
                }
            }
        }
    }
}
```

If the project uses Hilt or another DI framework, inject `AdaptyService` as a singleton-scoped ViewModel. If not using a ViewModel, a plain `object` with a `MutableStateFlow` works too.

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s https://adapty.io/docs/sdk-installation-android.md
```

Then guide the user through each step explicitly.

### Step 1: Add Gradle dependencies

The user needs to add dependencies to their **module-level** `build.gradle` (or `build.gradle.kts`). Ask which file format they use, then write the correct block.

Get the latest SDK version badge from:
```
https://github.com/adaptyteam/AdaptySDK-Android/releases
```

**Groovy DSL (`build.gradle`):**
```groovy
dependencies {
    implementation platform('io.adapty:adapty-bom:3.x.x')  // replace with latest version
    implementation 'io.adapty:android-sdk'

    // Only add if using Paywall Builder:
    implementation 'io.adapty:android-ui'
}
```

**Kotlin DSL (`build.gradle.kts`):**
```kotlin
dependencies {
    implementation(platform("io.adapty:adapty-bom:3.x.x"))  // replace with latest version
    implementation("io.adapty:android-sdk")

    // Only add if using Paywall Builder:
    implementation("io.adapty:android-ui")
}
```

**If dependency doesn't resolve** — ensure `mavenCentral()` is in the repositories block.

For projects using `dependencyResolutionManagement` in `settings.gradle`:
```groovy
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()  // add this if missing
    }
}
```

For older projects using `allprojects` in root `build.gradle`:
```groovy
allprojects {
    repositories {
        google()
        mavenCentral()  // add this if missing
    }
}
```

After editing Gradle files, ask the user to sync: **File → Sync Project with Gradle Files** in Android Studio.

### Step 2: Add activation code in Application class

The SDK must be activated in `Application.onCreate()`. Ask the user if they already have an `Application` subclass; if not, they need to create one.

**Create or update the Application class:**

```kotlin
// MyApplication.kt
import android.app.Application
import com.adapty.Adapty
import com.adapty.models.AdaptyConfig

class MyApplication : Application() {
    override fun onCreate() {
        super.onCreate()

        // Set log level before activation (recommended for development)
        Adapty.logLevel = AdaptyLogLevel.INFO

        Adapty.activate(
            applicationContext,
            AdaptyConfig.Builder(AppConstants.ADAPTY_PUBLIC_KEY)
                .withCustomerUserId(UserManager.getCurrentUserId(this)) // remove if no auth
                .build()
        )
    }
}
```

**Register the Application class in AndroidManifest.xml** (if the user created a new one):
```xml
<application
    android:name=".MyApplication"
    ... >
```

**Proguard rule** — add this to `proguard-rules.pro` before any production build:
```
-keep class com.adapty.** { *; }
```

The SDK key comes from `AppConstants` — already set in the recommended architecture step above.

**Checkpoint:** App builds and runs without errors. Logcat shows an Adapty activation log line (`Adapty activated`).

**Gotcha:** "Public API key is missing" or silent failure → the placeholder wasn't replaced with the real key from App settings → General → API keys.

**Gotcha:** `Manifest merger failed` involving `android:fullBackupContent` → another SDK also defines backup rules. See the [Troubleshooting section in the installation doc](https://adapty.io/docs/sdk-installation-android.md) for the merge fix.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Paywall Builder

Read before writing code:
```
https://adapty.io/docs/android-quickstart-paywalls.md
https://adapty.io/docs/android-get-pb-paywalls.md
https://adapty.io/docs/android-present-paywalls.md
https://adapty.io/docs/android-handling-events.md
https://adapty.io/docs/android-handle-paywall-actions.md
```

**Required call signature** — always use a string placement ID:
```kotlin
// Correct
Adapty.getPaywall(AppConstants.PLACEMENT_ID) { result ->
    if (result is AdaptyResult.Success) {
        val paywall = result.value

        if (!paywall.hasViewConfiguration) return@getPaywall

        AdaptyUI.getViewConfiguration(paywall) { configResult ->
            if (configResult is AdaptyResult.Success) {
                val viewConfiguration = configResult.value
                // display the paywall
                val paywallView = AdaptyUI.getPaywallView(
                    activity,
                    viewConfiguration,
                    null, // null = auto-fetch products
                    eventListener,
                )
                setContentView(paywallView)
            }
        }
    }
}
```

**Checkpoint:** Paywall appears on screen with configured products. Tapping a product triggers the Google Play sandbox purchase dialog.

**Gotcha:** Blank paywall or `getPaywall` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `hasViewConfiguration` is `false` → the **Show on device** toggle in the Paywall Builder is off. Tell the user to enable it in the dashboard.

### Custom paywall (manual)

Read before writing code:
```
https://adapty.io/docs/android-quickstart-manual.md
https://adapty.io/docs/fetch-paywalls-and-products-android.md
https://adapty.io/docs/present-remote-config-paywalls-android.md
https://adapty.io/docs/android-making-purchases.md
https://adapty.io/docs/android-restore-purchase.md
```

**Required call signature:**
```kotlin
Adapty.getPaywall(AppConstants.PLACEMENT_ID) { result ->
    if (result is AdaptyResult.Success) {
        val paywall = result.value
        Adapty.getPaywallProducts(paywall) { productResult ->
            if (productResult is AdaptyResult.Success) {
                val products = productResult.value
                // build your custom paywall UI with products
            }
        }
    }
}
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the Google Play sandbox purchase dialog. A restore button calls `Adapty.restorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing the existing Google Play Billing infrastructure is not feasible (e.g., deeply embedded legacy code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new projects or projects where purchases aren't yet implemented, use Paywall Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on Google Play Real-Time Developer Notifications (RTDN) being configured

Read before writing code:
```
https://adapty.io/docs/observer-vs-full-mode.md
https://adapty.io/docs/implement-observer-mode-android.md
https://adapty.io/docs/report-transactions-observer-mode-android.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or Google Play RTDN isn't configured in App settings → Android SDK.

---

## Stage 3: Check subscription status

Read before writing code:
```
https://adapty.io/docs/android-check-subscription-status.md
```

**What to do:** After a purchase, check `profile.accessLevels["premium"]?.isActive` to grant or deny access to paid features. For real-time updates, use `setOnProfileUpdatedListener` instead of polling.

The `AdaptyService` ViewModel set up in the recommended architecture already handles this via `StateFlow`. In a Composable or Activity/Fragment, collect the flow:

```kotlin
// In a Composable
val profile by adaptyService.profile.collectAsStateWithLifecycle()
val isPremium = profile?.accessLevels?.get(AppConstants.ACCESS_LEVEL_ID)?.isActive == true
```

```kotlin
// In an Activity/Fragment (non-Compose)
lifecycleScope.launch {
    adaptyService.profile.collect { profile ->
        val isPremium = profile?.accessLevels?.get(AppConstants.ACCESS_LEVEL_ID)?.isActive == true
        updateUI(isPremium)
    }
}
```

**Checkpoint:** After a sandbox purchase, checking `profile.accessLevels["premium"]?.isActive` returns `true`. Revoking the sandbox entitlement returns `false`.

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
| Airbridge | `airbridge` |
| Singular | `singular` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

Note: Apple Search Ads is iOS-only and does not apply to Android.

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
https://adapty.io/docs/android-quickstart-identify.md
```

**What to do:**
- Call `Adapty.identify("your-user-id")` after `activate()` and before `getPaywall()`
- For apps where users can purchase before logging in, call `identify()` at login — Adapty handles profile merging automatically
- Call `Adapty.logout()` when users log out

```kotlin
// At login
Adapty.identify("YOUR_USER_ID") { error ->
    if (error == null) {
        UserManager.login(context, "YOUR_USER_ID")
        // proceed with app flow
    }
}

// At logout
Adapty.logout { error ->
    if (error == null) {
        UserManager.logout(context)
    }
}
```

Alternatively, if the user ID is known at app launch, pass it directly in `AdaptyConfig.Builder`:

```kotlin
AdaptyConfig.Builder(AppConstants.ADAPTY_PUBLIC_KEY)
    .withCustomerUserId(UserManager.getCurrentUserId(this))
    .build()
```

**Checkpoint:** After calling `identify("your-user-id")`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `identify()` → `identify()` was called after `getPaywall()`, so the purchase was attributed to the anonymous profile. Order: `activate()` → `identify()` → `getPaywall()`.

---

## Build verification

All code is written. **Run the build yourself now via Bash — do not tell the user to build. Do not say "try building and let me know". Execute the Gradle commands below and handle the output yourself.**

### Discover project info

```bash
find . -maxdepth 3 \( -name "build.gradle" -o -name "build.gradle.kts" \) \
  ! -path "*/.gradle/*" ! -path "*/build/*" | head -20
ls -1 .
```

Confirm the app module name (usually `app`) and that `./gradlew` is present at the project root.

### Build

```bash
./gradlew assembleDebug 2>&1 | grep -E "error:|warning:|BUILD SUCCESSFUL|BUILD FAILED|FAILURE:" | head -50
```

### Handle output

**BUILD SUCCESSFUL** → proceed to the manual checklist below.

**BUILD FAILED:**
- Errors in files you wrote → fix them directly and rebuild — do not ask the user
- `Unresolved reference: Adapty` → dependency not resolved; ask user to do **File → Sync Project with Gradle Files** in Android Studio, then rebuild
- `Could not resolve io.adapty:android-sdk` → `mavenCentral()` missing from repository block; add it and sync
- `Manifest merger failed` → see backup rules fix in the installation doc — do not hand this off to the user, apply the fix directly
- Signing errors → not blocking for debug builds; can ignore until release

Do not proceed to the manual checklist until the build is clean. Do not hand off build errors to the user except for cases that require Android Studio UI interaction (dependency sync).

---

## Before you can test: manual steps

Read and follow `references/testing-setup-android.md` (in this skill directory). It contains the full step-by-step checklist for:
1. Creating products in Google Play Console (subscriptions or one-time products)
2. Connecting Google Play to Adapty (Service Account key, Real-Time Developer Notifications)
3. Designing the paywall in Paywall Builder — template, AI generator, or from scratch *(Paywall Builder only)*
4. Sandbox testing — adding a license tester, making a test purchase on a real device or emulator, verifying results in the Adapty dashboard Event Feed

Present the checklist to the user with the exact product IDs from Phase 3 already filled in.

---

## Stage 5: Release checklist

Run through this before submitting to Google Play review.

Read before releasing:
```
https://adapty.io/docs/release-checklist.md
```

**Checkpoint:** All items confirmed:
- Google Play connected in App settings → Android SDK
- Real-Time Developer Notifications (RTDN) configured in App settings → Android SDK
- Proguard rule added: `-keep class com.adapty.** { *; }`
- Sandbox purchase flow works end-to-end on a real device
- Premium content is gated on access level check (not just purchase callback)
- Restore purchases button present (Google Play requirement)
- `AdaptyLogLevel` set to `AdaptyLogLevel.ERROR` or `AdaptyLogLevel.NONE` for production builds
- Privacy policy URL set in Google Play Console

**Gotcha:** Missing Real-Time Developer Notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations. This must be configured in **App settings → Android SDK** in the Adapty Dashboard and in the Google Play Console pubsub topic settings.

---

## Want to go further?

After the basics are working, use `AskUserQuestion` to present this menu. Keep it casual — the user can pick one, several, or nothing.

> "Your integration is complete! Here are some things you might want to set up next. Which ones interest you? (or say 'done' to wrap up)"
>
> 1. **Fallback paywalls** — show a cached paywall if the user is offline or Adapty is unreachable
> 2. **Custom user attributes** — tag users with properties (plan, country, cohort) to enable segmentation and A/B testing
> 3. **Onboardings** — add interactive onboarding flows powered by Adapty's builder
> 4. **Kids mode** — complies with Google Play Families policy by disabling GAID and ad data collection
> 5. **A/B testing** — run experiments on paywalls and offers from the dashboard without app updates
> 6. **Custom access levels** — set up multiple subscription tiers (e.g. `basic` vs `pro`) if different products unlock different features
> 7. **Promotional offers** — set up subscription discounts and win-back offers for lapsed subscribers

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `android-use-fallback-paywalls` |
| Custom user attributes | `android-setting-user-attributes` |
| Onboardings | `android-get-onboardings`, `android-present-onboardings`, `android-handle-onboarding-events` |
| Kids mode | `kids-mode-android` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| Promotional offers | `create-offer` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## Android-specific index files

For broader context when the LLM needs more coverage:
- Android docs index: `https://adapty.io/docs/android-llms.txt`
- Android full docs (large): `https://adapty.io/docs/android-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
