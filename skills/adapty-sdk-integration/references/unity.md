# Unity SDK Integration Reference

Platform: Unity · Language: C# · Targets: iOS and Android from one project

## Prerequisites

- Unity 2020.3 LTS or later
- iOS 13.0+ (iOS 15.0+ for Paywall Builder)
- Android with Google Play Billing Library support
- External Dependency Manager for Unity (EDM4U / unity-jar-resolver)

---

## Build verification

Unity builds happen through the Editor UI, not a simple CLI invocation. Automated `unity -batchmode -buildTarget` runs are possible but require a valid Unity license activation on the CI machine and a build script — this is often impractical in a local dev session. Follow the guidance below.

### When you have access to Unity Editor (normal dev workflow)

After each stage that writes code, ask the user to do a quick compilation check in Unity Editor:

1. Switch focus to the Unity Editor window — Unity recompiles C# scripts automatically on focus.
2. Check the **Console** window (Window → General → Console) for any **errors** (red entries).
3. If no red errors appear, the code is compilable — proceed to the next stage.

Do NOT ask the user to do a full platform build after every stage. A full build (File → Build Settings → Build) is only needed once at the "Build verification" section near the end.

### When running headless / CI builds

If a Unity installation with a valid license is available on the machine, use batchmode:

```bash
# Discover Unity installation path (macOS)
find /Applications -name "Unity" -type f 2>/dev/null | head -5
# On Windows: C:\Program Files\Unity\Hub\Editor\<version>\Editor\Unity.exe

# iOS build (requires Xcode to be installed — Unity outputs an Xcode project)
/Applications/Unity/Hub/Editor/<VERSION>/Unity/Contents/MacOS/Unity \
  -batchmode \
  -quit \
  -projectPath "/path/to/project" \
  -buildTarget iOS \
  -executeMethod BuildScript.BuildIOS \
  -logFile /tmp/unity-build.log 2>&1; cat /tmp/unity-build.log | grep -E "error|warning|Build succeeded|Build FAILED" | head -40

# Android build
/Applications/Unity/Hub/Editor/<VERSION>/Unity/Contents/MacOS/Unity \
  -batchmode \
  -quit \
  -projectPath "/path/to/project" \
  -buildTarget Android \
  -executeMethod BuildScript.BuildAndroid \
  -logFile /tmp/unity-build.log 2>&1; cat /tmp/unity-build.log | grep -E "error|warning|Build succeeded|Build FAILED" | head -40
```

This requires a `BuildScript.cs` in an `Editor/` folder that calls `BuildPipeline.BuildPlayer(...)`. If one doesn't exist, fall back to asking the user to check the Console for errors in the Unity Editor.

### Handle compilation errors

**No red errors in Console** → code is compilable — proceed.

**Red errors in Console:**
- Errors in files you wrote → fix them directly (do not ask the user)
- `CS0246` / type not found → `using AdaptySDK;` namespace missing, or the `.unitypackage` was not imported
- `AdaptyUI` type not found → AdaptyUI module not activated with `.SetActivateUI(true)` in the builder, or the package import was incomplete
- `EditorOnly` or `UNITY_EDITOR` preprocessor errors → code is running outside the Editor; wrap Editor-only code in `#if UNITY_EDITOR` blocks

After fixing errors, switch focus back to the Unity Editor to trigger recompilation. Confirm errors are resolved before moving on.

---

## Recommended architecture

Before writing any Adapty code, create these files. They establish patterns the rest of the integration builds on.

### AppConstants.cs

Centralizes all Adapty config values. Using `#error` in a `#if` block causes a compile error if a placeholder value ships to production — a safety net against misconfigured builds.

```csharp
public static class AppConstants
{
    // Replace these before building.
#if DEVELOPMENT_BUILD || UNITY_EDITOR
    public const string AdaptyPublicKey = "YOUR_PUBLIC_SDK_KEY";  // from Adapty Dashboard → App settings → API keys
    public const string PlacementId    = "YOUR_PLACEMENT_ID";     // from Adapty Dashboard → Placements
#else
    public const string AdaptyPublicKey = "YOUR_PUBLIC_SDK_KEY";
    public const string PlacementId    = "YOUR_PLACEMENT_ID";
#endif
    public const string AccessLevelId  = "premium";               // default access level; change if you use custom ones
}
```

Replace the placeholder strings with real values from Phase 3 output immediately.

### UserManager.cs (skip if app has no authentication)

Lightweight `PlayerPrefs` wrapper for the customer user ID. Pass this ID during `Adapty.Activate()` (or call `Adapty.Identify()` after login) so purchases are always attributed to the right profile.

```csharp
using UnityEngine;

public static class UserManager
{
    private const string Key = "adapty.userId";

    public static string CurrentUserId => PlayerPrefs.GetString(Key, null);

    public static void Login(string userId)
    {
        PlayerPrefs.SetString(Key, userId);
        PlayerPrefs.Save();
    }

    public static void Logout()
    {
        PlayerPrefs.DeleteKey(Key);
        PlayerPrefs.Save();
    }
}
```

### AdaptyService.cs (GameManager / persistent MonoBehaviour)

Central service that:
- Lives on a `DontDestroyOnLoad` `GameObject` (persists across scene loads)
- Implements `AdaptyEventListener` for real-time subscription updates (no polling needed)
- Exposes a clean `IsPremiumUser` property for gating content throughout the game

```csharp
using UnityEngine;
using AdaptySDK;

public class AdaptyService : MonoBehaviour, AdaptyEventListener
{
    public static AdaptyService Instance { get; private set; }

    public AdaptyProfile CurrentProfile { get; private set; }

    public bool IsPremiumUser
    {
        get
        {
            if (CurrentProfile?.AccessLevels == null) return false;
            return CurrentProfile.AccessLevels.TryGetValue(AppConstants.AccessLevelId, out var level)
                   && level.IsActive;
        }
    }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);

        // Register event listener before activation
        Adapty.SetEventListener(this);

        var builder = new AdaptyConfiguration.Builder(AppConstants.AdaptyPublicKey)
            .SetLogLevel(AdaptyLogLevel.Info);

        // If the user is already identified (e.g., returned user), pass the ID here
        var savedId = UserManager.CurrentUserId;
        if (!string.IsNullOrEmpty(savedId))
            builder.SetCustomerUserId(savedId);

        Adapty.Activate(builder.Build(), (error) =>
        {
            if (error != null)
                Debug.LogError($"[Adapty] Activation error: {error.Message}");
            else
                Debug.Log("[Adapty] SDK activated successfully.");
        });
    }

    // Called automatically when Adapty detects a subscription change
    public void OnLoadLatestProfile(AdaptyProfile profile)
    {
        CurrentProfile = profile;
        Debug.Log($"[Adapty] Profile updated. Premium: {IsPremiumUser}");
    }

    public void OnInstallationDetailsSuccess(AdaptyInstallationDetails details) { }
    public void OnInstallationDetailsFail(AdaptyError error) { }
}
```

Attach `AdaptyService` to a persistent `GameObject` in your first scene (e.g., a `GameManager` object). Set its **Script Execution Order** to run before Default Time: **Edit → Project Settings → Script Execution Order → + → AdaptyService → set to -100**.

---

## Stage 1: Install and configure the SDK

First fetch the full installation doc for reference:
```bash
curl -s https://adapty.io/docs/sdk-installation-unity.md
```

Then guide the user through each step explicitly.

### Step 1: Import the Adapty `.unitypackage`

Tell the user to do this in Unity Editor:

1. Go to the [Adapty Unity SDK releases page](https://github.com/adaptyteam/AdaptySDK-Unity/tree/main/Releases) on GitHub.
2. Download the latest `adapty-unity-plugin-*.unitypackage`.
3. In Unity Editor: **Assets → Import Package → Custom Package...** → select the downloaded file → click **Import All**.
4. Verify: `AdaptySDK` folder should appear under **Assets** in the Project window.

### Step 2: Import the External Dependency Manager (EDM4U)

EDM4U resolves iOS CocoaPods and Android Gradle dependencies automatically.

1. Download and import the [External Dependency Manager plugin](https://github.com/googlesamples/unity-jar-resolver) (`.unitypackage`).
2. After import, resolve dependencies:
   - **Android:** Assets → External Dependency Manager → Android Resolver → Force Resolve
   - **iOS:** Assets → External Dependency Manager → iOS Resolver → Install Cocoapods
3. Verify: No resolver errors appear in the Console.

### Step 3: Add Kotlin plugin for Android (required — do not skip)

Without this step, the Android build will crash when displaying a paywall.

1. In **Edit → Project Settings → Player → Android tab → Publishing Settings**, enable:
   - **Custom Launcher Gradle Template**
   - **Custom Base Gradle Template**

2. Open `Assets/Plugins/Android/launcherTemplate.gradle` and add the Kotlin plugin line:
   ```groovy
   apply plugin: 'com.android.application'
   apply plugin: 'kotlin-android'   // ADD THIS LINE
   ```

3. Open `Assets/Plugins/Android/baseProjectTemplate.gradle` and add the Kotlin version:
   ```groovy
   id 'org.jetbrains.kotlin.android' version '1.8.0' apply false   // ADD THIS LINE
   ```

### Step 4: Create the AdaptyService GameObject and add activation code

1. Create a new empty `GameObject` in your initial/bootstrap scene. Name it `AdaptyService`.
2. Attach the `AdaptyService.cs` script (from the Recommended Architecture section above) to it.
3. Set Script Execution Order: **Edit → Project Settings → Script Execution Order → +** → select `AdaptyService` → set value to `-100`.
4. Open `AppConstants.cs` and replace `YOUR_PUBLIC_SDK_KEY` with the real key from **Adapty Dashboard → App settings → General → API keys → Public SDK key**.
5. Replace `YOUR_PLACEMENT_ID` with the placement ID from **Adapty Dashboard → Placements**.

The SDK key comes from `AppConstants` — already set up in the recommended architecture step above.

**If using Paywall Builder**, also enable AdaptyUI by adding `.SetActivateUI(true)` to the builder in `AdaptyService.Awake()`:
```csharp
var builder = new AdaptyConfiguration.Builder(AppConstants.AdaptyPublicKey)
    .SetActivateUI(true)
    .SetLogLevel(AdaptyLogLevel.Info);
```

**Checkpoint:** Switch to Unity Editor. No red errors in Console. After entering Play mode, Console shows `[Adapty] SDK activated successfully.`

**Gotcha:** "Public API key is missing" or silent activation failure → the placeholder string `"YOUR_PUBLIC_SDK_KEY"` was not replaced with the real key from the dashboard.

**Gotcha:** `AdaptySDK` namespace not found → the `.unitypackage` was not imported, or the import was incomplete (try re-importing).

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Paywall Builder

Read before writing code:
```bash
curl -s https://adapty.io/docs/unity-quickstart-paywalls.md
curl -s https://adapty.io/docs/unity-get-pb-paywalls.md
curl -s https://adapty.io/docs/unity-present-paywalls.md
curl -s https://adapty.io/docs/unity-handling-events.md
curl -s https://adapty.io/docs/unity-handle-paywall-actions.md
```

**Key implementation pattern:**

```csharp
using AdaptySDK;
using UnityEngine;

public class PaywallPresenter : MonoBehaviour, AdaptyPaywallsEventsListener
{
    void Start()
    {
        Adapty.SetPaywallsEventsListener(this);
    }

    public void ShowPaywall()
    {
        Adapty.GetPaywall(AppConstants.PlacementId, (paywall, error) =>
        {
            if (error != null)
            {
                Debug.LogError($"[Adapty] GetPaywall error: {error.Message}");
                return;
            }

            if (!paywall.HasViewConfiguration)
            {
                Debug.LogWarning("[Adapty] Paywall has no view configuration — check that 'Show on device' is enabled in Paywall Builder.");
                return;
            }

            var parameters = new AdaptyUICreatePaywallViewParameters();
            AdaptyUI.CreatePaywallView(paywall, parameters, (view, viewError) =>
            {
                if (viewError != null)
                {
                    Debug.LogError($"[Adapty] CreatePaywallView error: {viewError.Message}");
                    return;
                }
                view.Present(null);
            });
        });
    }

    // Handle close and URL buttons — purchases are handled automatically by AdaptyUI
    public void PaywallViewDidPerformAction(AdaptyUIPaywallView view, AdaptyUIUserAction action)
    {
        switch (action.Type)
        {
            case AdaptyUIUserActionType.Close:
                view.Dismiss(null);
                break;
            case AdaptyUIUserActionType.OpenUrl:
                Application.OpenURL(action.Value);
                break;
        }
    }
}
```

**Checkpoint:** Paywall appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog.

**Gotcha:** Blank paywall or `GetPaywall` returns error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `HasViewConfiguration` is `false` → open the paywall in Paywall Builder in the Adapty Dashboard and make sure the **Show on device** toggle is enabled.

**Gotcha:** App crashes on Android when displaying paywall → Kotlin plugin was not added (Stage 1, Step 3).

### Custom paywall (manual)

Read before writing code:
```bash
curl -s https://adapty.io/docs/unity-quickstart-manual.md
curl -s https://adapty.io/docs/fetch-paywalls-and-products-unity.md
curl -s https://adapty.io/docs/present-remote-config-paywalls-unity.md
curl -s https://adapty.io/docs/unity-making-purchases.md
curl -s https://adapty.io/docs/unity-restore-purchase.md
```

**Key implementation pattern:**

```csharp
using AdaptySDK;
using UnityEngine;

public class CustomPaywallManager : MonoBehaviour
{
    public void LoadAndShowPaywall()
    {
        Adapty.GetPaywall(AppConstants.PlacementId, (paywall, error) =>
        {
            if (error != null) { /* handle */ return; }

            Adapty.GetPaywallProducts(paywall, (products, productsError) =>
            {
                if (productsError != null) { /* handle */ return; }
                // Build your UI using the products array
                // Each AdaptyPaywallProduct has .LocalizedPrice, .LocalizedTitle, etc.
            });
        });
    }

    public void Purchase(AdaptyPaywallProduct product)
    {
        Adapty.MakePurchase(product, (result, error) =>
        {
            if (error != null) { /* handle */ return; }

            switch (result.Type)
            {
                case AdaptyPurchaseResultType.Success:
                    // result.Profile contains updated access levels
                    break;
                case AdaptyPurchaseResultType.UserCancelled:
                    break;
                case AdaptyPurchaseResultType.Pending:
                    // Deferred purchase (e.g., parental approval)
                    break;
            }
        });
    }

    public void RestorePurchases()
    {
        Adapty.RestorePurchases((profile, error) =>
        {
            if (error != null) { /* handle */ return; }
            // profile contains updated access levels after restore
        });
    }
}
```

**Checkpoint:** Custom paywall UI shows products fetched from Adapty. Tapping a product triggers the sandbox purchase dialog. A restore button calls `RestorePurchases()`.

**Gotcha:** Empty products array → paywall in the dashboard has no products assigned, or placement has no audience.

### Observer mode *(not recommended)*

> **When to use:** Only if replacing an existing purchase infrastructure is not feasible (e.g., deeply embedded legacy in-app-purchase code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new Unity projects or projects where purchases aren't yet implemented, use Paywall Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management or Paywall Builder support
> - No A/B testing on paywalls or offers
> - Transactions must be manually reported to Adapty after each purchase
> - Subscription events depend on App Store Server Notifications / Google Play RTDN being configured

Read before writing code:
```bash
curl -s https://adapty.io/docs/observer-vs-full-mode.md
curl -s https://adapty.io/docs/implement-observer-mode-unity.md
curl -s https://adapty.io/docs/report-transactions-observer-mode-unity.md
```

**Checkpoint:** After a sandbox purchase through the existing purchase flow, the transaction appears in the Adapty dashboard **Event Feed**.

**Gotcha:** No events in the dashboard → transactions aren't being reported to Adapty, or server notifications aren't configured for iOS (App settings → iOS SDK) / Android (App settings → Android SDK).

---

## Stage 3: Check subscription status

Read before writing code:
```bash
curl -s https://adapty.io/docs/unity-check-subscription-status.md
```

**What to do:** Use `AdaptyService.Instance.IsPremiumUser` (from the recommended architecture) to gate content. This is backed by `OnLoadLatestProfile`, which Adapty calls automatically whenever the subscription state changes — no polling required.

For immediate checks (e.g., on a scene load), call `GetProfile` directly:

```csharp
Adapty.GetProfile((profile, error) =>
{
    if (error != null) { /* handle */ return; }

    bool hasAccess = profile.AccessLevels.TryGetValue(AppConstants.AccessLevelId, out var level)
                     && level.IsActive;
    // gate content accordingly
});
```

**Checkpoint:** After a sandbox purchase, `AdaptyService.Instance.IsPremiumUser` returns `true`. Revoking the sandbox purchase (or waiting for expiry) returns `false`.

**Gotcha:** `AccessLevels` is empty after purchase → the product has no access level assigned in the dashboard (Products page → select product → access levels).

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
curl -s https://adapty.io/docs/unity-quickstart-identify.md
```

**What to do:**
- Call `Adapty.Identify("your-user-id", callback)` after `Activate()` and before `GetPaywall()`
- For apps where users can purchase before logging in, call `Identify()` at login — Adapty handles profile merging automatically
- Call `Adapty.Logout(callback)` when users log out (this creates a new anonymous profile)

```csharp
// At login
Adapty.Identify(UserManager.CurrentUserId, (error) =>
{
    if (error != null)
        Debug.LogError($"[Adapty] Identify error: {error.Message}");
    else
        Debug.Log("[Adapty] User identified.");
});

// At logout
Adapty.Logout((error) =>
{
    if (error != null)
        Debug.LogError($"[Adapty] Logout error: {error.Message}");
    UserManager.Logout();
});
```

**Checkpoint:** After calling `Adapty.Identify("your-user-id", ...)`, the Adapty dashboard **Profiles** section shows the custom user ID on the profile.

**Gotcha:** Profile shows anonymous ID even after `Identify()` → `Identify()` was called after `GetPaywall()`, so the purchase was attributed to the anonymous profile. Correct order: `Activate()` → `Identify()` → `GetPaywall()`.

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

All code is written. Now verify the full build for each target platform.

### Check for compilation errors in Unity Editor

Switch focus to Unity Editor. Check the **Console** window for any red errors. Fix all errors before proceeding. Do not ask the user to fix errors you can fix in the code you wrote.

### Full iOS build verification

When building for iOS, Unity generates an Xcode project. The user must open it in Xcode to build for a device or simulator.

**Ask the user to:**
1. In Unity Editor: **File → Build Settings** → select **iOS** → click **Build** (or **Build And Run** for device).
2. Unity outputs a folder (e.g., `iOSBuild/`) containing `Unity-iPhone.xcworkspace`.
3. Open `Unity-iPhone.xcworkspace` (NOT `Unity-iPhone.xcodeproj` — CocoaPods requires the workspace).
4. In Xcode: select a simulator or connected device → click **Build** (⌘B).

If you can run `xcodebuild` from bash (e.g., the project has already been built once and the workspace exists), use it:

```bash
# Find the generated Xcode workspace
find . -maxdepth 5 -name "*.xcworkspace" ! -path "*/Pods/*" 2>/dev/null

# Build for iOS Simulator
xcodebuild \
  -workspace "Unity-iPhone.xcworkspace" \
  -scheme "Unity-iPhone" \
  -destination "generic/platform=iOS Simulator" \
  -quiet \
  build 2>&1 | grep -E "error:|warning:|Build succeeded|BUILD FAILED" | head -40
```

**Handle output:**
- **Build succeeded** → proceed to manual checklist
- **BUILD FAILED** with errors in your files → fix directly and rebuild
- CocoaPods errors / missing frameworks → the user opened `.xcodeproj` instead of `.xcworkspace`; redirect them to the workspace
- Signing errors → safe to ignore for simulator builds; not blocking for testing

### Full Android build verification

Ask the user to:
1. In Unity Editor: **File → Build Settings** → select **Android** → click **Build**.
2. If the build fails, check the Console and the build log for errors.

Common Android build errors:
- Kotlin plugin not applied → revisit Stage 1, Step 3
- Duplicate class / Gradle conflicts → check `baseProjectTemplate.gradle` for version conflicts
- `launchMode` warning → ensure the main Activity uses `standard` or `singleTop` launch mode in `Assets/Plugins/Android/AndroidManifest.xml`

---

## Before you can test: manual steps

Unity targets both iOS and Android. Testing setup differs per platform.

### iOS testing

Follow `references/testing-setup-ios.md` (in this skill directory) for:
1. Creating products in App Store Connect
2. Connecting App Store to Adapty (Bundle ID, In-App Purchase Key, Server Notifications)
3. Designing the paywall in Paywall Builder *(Paywall Builder only)*
4. Sandbox testing — creating a sandbox account, switching device to sandbox, making a test purchase

Note: When building for iOS from Unity, always open `Unity-iPhone.xcworkspace` in Xcode, never `Unity-iPhone.xcodeproj`.

### Android testing

Read the Android testing guide:
```bash
curl -s https://adapty.io/docs/testing-on-android.md
```

Key steps:
1. Create products in Google Play Console (requires the app to be uploaded at least once as an internal test track)
2. Connect Google Play to Adapty: App settings → Android SDK → add Service Account credentials
3. Configure Google Play Real-Time Developer Notifications (RTDN) in App settings → Android SDK
4. Add test accounts as **License Testers** in Google Play Console → Setup → License Testing
5. Build a signed APK/AAB and upload to the internal test track, or use a debug build with the test account

---

## Stage 5: Release checklist

Run through this before submitting to the App Store or Google Play.

Read before releasing:
```bash
curl -s https://adapty.io/docs/release-checklist.md
```

**Checkpoint — all items confirmed:**
- App Store and/or Google Play connected in Adapty App settings
- App Store Server Notifications configured in App settings → iOS SDK
- Google Play RTDN configured in App settings → Android SDK
- Sandbox purchase flow works end-to-end on both platforms
- Premium content is gated on access level check
- Restore purchases button present (required by both stores)
- Privacy policy URL set in both App Store Connect and Google Play Console
- `AppConstants` placeholder values replaced with real keys (not `YOUR_PUBLIC_SDK_KEY`)
- `AdaptyLogLevel` set to `Warn` or `Error` for production (not `Verbose`)

**Gotcha:** Missing App Store Server Notifications → subscription events (renewal, cancellation, billing retry) won't appear in the Adapty dashboard or reach integrations.

**Gotcha:** Missing Google Play RTDN → same problem on Android; subscription lifecycle events are lost.

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
> 8. **App Tracking Transparency (ATT)** — handle ATT prompt timing relative to Adapty initialization on iOS

For each item the user picks, fetch the relevant doc and implement it:

| Feature | Doc slug(s) |
|---|---|
| Fallback paywalls | `unity-use-fallback-paywalls` |
| Custom user attributes | `unity-setting-user-attributes` |
| Promotional offers | `app-store-offers`, `create-offer` |
| Onboardings | `unity-get-onboardings`, `unity-present-onboardings`, `unity-handling-onboarding-events` |
| Kids mode | `kids-mode-unity` |
| A/B testing | `ab-tests`, `run_stop_ab_tests` |
| Custom access levels | `create-access-level`, `assigning-access-level-to-a-product` |
| ATT | `unity-deal-with-att` |

```bash
curl -s https://adapty.io/docs/<slug>.md
```

---

## Unity index files

For broader context when the LLM needs more coverage:
- Unity docs index: `https://adapty.io/docs/unity-llms.txt`
- Unity full docs (large): `https://adapty.io/docs/unity-llms-full.txt`
- All Adapty docs index: `https://adapty.io/docs/llms.txt`
