# Unity SDK Integration Reference

Platform: Unity · Language: C# · Targets: iOS and Android from one project

## Prerequisites

- Unity 2022.3 or later (the `com.adapty.unity-sdk` package declares this as its minimum)
- Adapty Unity SDK **4.1+** for Flow Builder. 4.1 is the first stable release of the 4.x line; a project that cannot meet the requirements below must stay on 3.x, which has no Flow Builder
- **iOS 15.0+ for the whole app** on SDK 4.x — not just for builder-rendered screens. An Editor build validator fails the iOS build when the deployment target is lower
- External Dependency Manager for Unity (EDM4U / unity-jar-resolver) **1.2.188 or later** — this is the SDK's declared peer dependency, and earlier versions cannot resolve Swift Package Manager dependencies
- Android with Google Play Billing Library support (SDK 4.x uses Billing Library v8)

`com.unity.nuget.newtonsoft-json` is a hard dependency, pulled in automatically on the Package Manager install path.

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
- `CS0246` / type not found → `using AdaptySDK;` namespace missing, or the SDK package was not installed
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
- Implements `IAdaptyEventListener` for real-time subscription updates (no polling needed)
- Exposes a clean `IsPremiumUser` property for gating content throughout the game

```csharp
using UnityEngine;
using AdaptySDK;

public class AdaptyService : MonoBehaviour, IAdaptyEventListener
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
            // Required for Flow Builder: without it, CreateFlowView has no renderer to build with
            .SetActivateUI(true)
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

    // Required by IAdaptyEventListener since SDK 4.1. iOS only, and the event IS the purchase —
    // leaving the body empty drops a purchase the user started on the App Store product page.
    public void OnReceivePromotedPurchase(AdaptyPromotedProduct product)
    {
        Adapty.MakePromotedPurchase(product, (result, error) =>
        {
            if (error != null)
                Debug.LogError($"[Adapty] Promoted purchase error: {error.Message}");
        });
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
curl -s "https://adapty.io/docs/sdk-installation-unity.md?ref=skill-<sessionToken>"
```

Then guide the user through each step explicitly.

### Step 1: Install the SDK package

Two install paths. **Prefer the Package Manager one** — it resolves `com.unity.nuget.newtonsoft-json` for you and makes the version explicit in `manifest.json`, where the `.unitypackage` path leaves it implicit.

**Package Manager (Git URL) — preferred:**

1. In Unity: **Window → Package Manager**.
2. Click **+** (top-left) → **Add package from git URL...**.
3. Enter the URL, pinned to a version tag, and click **Add**:
   ```
   https://github.com/adaptyteam/AdaptySDK-Unity.git?path=/Packages/com.adapty.unity-sdk#4.1.1
   ```
   Pin the tag rather than tracking the branch, so a later release cannot change the build under the user. Check the [releases page](https://github.com/adaptyteam/AdaptySDK-Unity/releases) for the current version and use that instead of `4.1.1` if it is newer.
4. Verify: **Adapty Unity SDK** appears in the Package Manager list, and the `AdaptySDK` namespace resolves in C#.

**Unity package (alternative):** download `adapty-unity-plugin-*.unitypackage` from the [releases page](https://github.com/adaptyteam/AdaptySDK-Unity/releases) and import it with **Assets → Import Package → Custom Package...** → **Import All**. On this path Newtonsoft.Json is not pulled in automatically; the SDK ships an Editor validator that reports the problem if it is missing or unreadable.

### Step 2: Import the External Dependency Manager (EDM4U)

EDM4U resolves the Android Gradle dependencies and, on SDK 4.x, adds the native iOS SDK to the generated Xcode project as a **remote Swift package**.

1. Download and import the [External Dependency Manager plugin](https://github.com/googlesamples/unity-jar-resolver), version **1.2.188 or later**. This is the SDK's declared peer dependency and it is a hard floor: earlier versions have no Swift Package Manager support, and Unity warns when the installed one is older.
2. Resolve Android dependencies: **Assets → External Dependency Manager → Android Resolver → Force Resolve**.
3. Verify: no resolver errors in the Console.

**Do not run the iOS Resolver's "Install Cocoapods" step, and do not tell the user to open `Unity-iPhone.xcworkspace`.** Both belong to SDK 3.x. On 4.x the native iOS SDK is a Swift package that EDM adds to the generated Xcode project automatically, so there is no Podfile and no workspace — build `Unity-iPhone.xcodeproj`.

### Step 3: Set the iOS deployment target to 15.0+

**Edit → Project Settings → Player → iOS tab → Other Settings → Target minimum iOS Version** → `15.0` or later.

This applies to the whole app on SDK 4.x, not only to screens the builder renders. The SDK ships an Editor build validator that stops the iOS build when the target is lower, so getting this wrong surfaces as a failed build rather than a runtime problem.

### Step 3.5: Add Kotlin plugin for Android (only if the Android build crashes)

If the app crashes on Android when a flow is displayed, the Kotlin plugin is missing from the Gradle configuration. Add it:

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

The SDK key comes from `AppConstants` — already set up in the recommended architecture step above, which already carries `.SetActivateUI(true)`. Leave it in: without it the SDK activates without its renderer, and `CreateFlowView` fails at the point where the user expects a screen.

**Wait for the `Activate` completion callback before calling any other Adapty SDK method** — including `GetFlow`. See https://adapty.io/docs/unity-sdk-call-order.md for the full sequence.

**Checkpoint:** Switch to Unity Editor. No red errors in Console. After entering Play mode, Console shows `[Adapty] SDK activated successfully.`

**Gotcha:** "Public API key is missing" or silent activation failure → the placeholder string `"YOUR_PUBLIC_SDK_KEY"` was not replaced with the real key from the dashboard.

**Gotcha:** `AdaptySDK` namespace not found → the package was not installed, or the `.unitypackage` import was incomplete (try re-importing).

**Gotcha:** `AdaptyService` does not compile against `AdaptyEventListener` → on SDK 4.1 the listener interfaces follow the C# I-prefix convention. Implement `IAdaptyEventListener`, and note it requires `OnReceivePromotedPurchase` — a member that did not exist in 3.x.

---

## Stage 2: Show paywalls and handle purchases

Choose the section matching the user's paywall approach.

### Flow Builder

Read before writing code:
```bash
curl -s https://adapty.io/docs/unity-quickstart-paywalls.md
curl -s https://adapty.io/docs/unity-get-pb-paywalls.md
curl -s https://adapty.io/docs/unity-present-paywalls.md
curl -s https://adapty.io/docs/unity-handling-events.md
curl -s https://adapty.io/docs/unity-handle-paywall-actions.md
```

**v4 API names.** Flow Builder uses `GetFlow` / `AdaptyFlow` / `AdaptyUI.CreateFlowView` / `AdaptyUIFlowView` / `IAdaptyFlowsEventsListener`. The same APIs also render existing Paywall Builder paywalls — no dashboard changes are needed for a user moving from Paywall Builder. There is no `GetPaywall`, no `AdaptyUI.CreatePaywallView` and no `AdaptyUIPaywallView` on 4.x; they were removed rather than deprecated, so v3 code does not compile. `GetFlow` takes no `locale` parameter — pass a locale to `CreateFlowView` instead. Listener callbacks are renamed `PaywallView...` → `FlowView...`, `PaywallViewDidFailRendering` → `FlowViewDidReceiveError`, and products are still `AdaptyPaywallProduct`.

**Key implementation pattern:**

```csharp
using AdaptySDK;
using UnityEngine;

public class FlowPresenter : MonoBehaviour, IAdaptyFlowsEventsListener
{
    void Start()
    {
        Adapty.SetFlowsEventsListener(this);
    }

    public void ShowFlow()
    {
        Adapty.GetFlow(AppConstants.PlacementId, (flow, error) =>
        {
            if (error != null)
            {
                Debug.LogError($"[Adapty] GetFlow error: {error.Message}");
                return;
            }

            AdaptyUI.CreateFlowView(flow, (view, viewError) =>
            {
                if (viewError != null)
                {
                    // Most often: the flow has no view configured ("Show on device" is off)
                    Debug.LogError($"[Adapty] CreateFlowView error: {viewError.Message}");
                    return;
                }
                view.Present(null);
            });
        });
    }

    // Purchases and restores are performed by the SDK, but it dismisses nothing for you.
    public void FlowViewDidPerformAction(AdaptyUIFlowView view, AdaptyUIUserAction action)
    {
        switch (action.Type)
        {
            case AdaptyUIUserActionType.Close:
                view.Dismiss(null);
                break;
            case AdaptyUIUserActionType.OpenUrl:
                // Use the SDK's opener, not Application.OpenURL, and pass action.OpenIn —
                // that is where the flow said it wants the link opened (in-app vs external
                // browser). The docs example hardcodes ExternalBrowser, which silently
                // discards that setting.
                AdaptyUI.OpenUrl(
                    action.Value,
                    action.OpenIn ?? AdaptyWebPresentation.ExternalBrowser,
                    null);
                break;
        }
    }

    public void FlowViewDidFinishPurchase(
        AdaptyUIFlowView view,
        AdaptyPaywallProduct product,
        AdaptyPurchaseResult purchasedResult)
    {
        // Nothing closes the flow on its own — dismiss it once the user has access.
        if (purchasedResult.Type != AdaptyPurchaseResultType.UserCancelled)
            view.Dismiss(null);
    }

    // IAdaptyFlowsEventsListener has no default implementations: every member must be present,
    // even if the body is empty. Implement the rest (FlowViewDidAppear, FlowViewDidDisappear,
    // FlowViewDidSelectProduct, FlowViewDidStartPurchase, FlowViewDidFailPurchase,
    // FlowViewDidStartRestore, FlowViewDidFinishRestore, FlowViewDidFailRestore,
    // FlowViewDidReceiveError, FlowViewDidFailLoadingProducts,
    // FlowViewDidFinishWebPaymentNavigation, FlowViewDidReceiveAnalyticEvent)
    // or the class will not compile.
}
```

**The v4 defaults changed and none of it is a compile error — verify these by running the flow, not by reading the diff:**

- **A flow stays open after a successful purchase or an error.** In v3 the view dismissed itself. Dismiss it yourself in `FlowViewDidFinishPurchase`, or the user completes a purchase and stays staring at the paywall.
- **The Android system back button no longer closes a flow.** It arrives at `FlowViewDidPerformAction` as a `SystemBack` action and does nothing on its own. Give the user an explicit way out — a Close button in the flow, or dismiss on that action — or the flow is a dead end on Android.
- **A view is single-use.** After `Dismiss` it is destroyed; call `CreateFlowView` again to show the flow a second time.

**Checkpoint:** Flow appears on screen with configured products. Tapping a product triggers the sandbox purchase dialog. Tapping Close dismisses it, and on Android the back gesture behaves the way you decided above.

**Gotcha:** Blank flow, or `GetFlow` returns an error → placement ID doesn't match the dashboard exactly (case-sensitive), or the placement has no audience assigned.

**Gotcha:** `CreateFlowView` returns an error where `GetFlow` succeeded → the **Show on device** toggle is off for that flow in the Flow Builder. `AdaptyFlow.HasViewConfiguration` does still exist on Unity (unlike the React Native and Capacitor SDKs, where it was removed), but handling `CreateFlowView`'s error is the documented path and covers strictly more failures.

**Gotcha:** `CreateFlowView` fails on every flow → `.SetActivateUI(true)` is missing from the configuration builder (Stage 1, Step 4).

**Gotcha:** App crashes on Android when displaying a flow → Kotlin plugin was not added (Stage 1, Step 3.5).

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
        // v4 note: even a hand-built paywall fetches with GetFlow — the fetch call follows the
        // SDK major version, not the paywall approach. Products are still AdaptyPaywallProduct,
        // and GetPaywallProducts keeps its name, now taking an AdaptyFlow.
        Adapty.GetFlow(AppConstants.PlacementId, (flow, error) =>
        {
            if (error != null) { /* handle */ return; }

            Adapty.GetPaywallProducts(flow, (products, productsError) =>
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

> **When to use:** Only if replacing an existing purchase infrastructure is not feasible (e.g., deeply embedded legacy in-app-purchase code). Observer mode gives you analytics and integrations, but you lose paywall management, A/B testing, and Adapty-driven paywalls entirely. For new Unity projects or projects where purchases aren't yet implemented, use Flow Builder or Custom paywall instead.
>
> **Limitations:**
> - No paywall management, Flow Builder, or Paywall Builder support
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
- Call `Adapty.Identify("your-user-id", callback)` after `Activate()` and before `GetFlow()`
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

**Gotcha:** Profile shows anonymous ID even after `Identify()` → `Identify()` was called after `GetFlow()`, so the purchase was attributed to the anonymous profile. Correct order: `Activate()` → `Identify()` → `GetFlow()`.

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

**SDK 4.1 renamed the external-attribution APIs with no deprecated aliases**, so a v3 call site stops compiling: `Adapty.UpdateAttribution(data, source, ...)` → `Adapty.UpdateExternalAttribution(data, provider, ...)`, and `AdaptyProfile.AppliedAttributionSources` → `AppliedExternalAttributionProviders`. Separately, **Adapty Attribution is off by default from 4.1** (it was automatic below it) — if the user relies on Adapty's own install attribution, add `.SetAdaptyAttributionEnabled(true)` to the configuration builder, or the SDK registers no installs and delivers no installation details, silently.

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
- Kotlin plugin not applied → revisit Stage 1, Step 3.5
- Duplicate class / Gradle conflicts → check `baseProjectTemplate.gradle` for version conflicts
- `launchMode` warning → ensure the main Activity uses `standard` or `singleTop` launch mode in `Assets/Plugins/Android/AndroidManifest.xml`

---

## Before you can test: manual steps

Unity targets both iOS and Android. Testing setup differs per platform.

### iOS testing

Follow `references/testing-setup-ios.md` (in this skill directory) for:
1. Creating products in App Store Connect
2. Connecting App Store to Adapty (Bundle ID, In-App Purchase Key, Server Notifications)
3. Designing the flow in Flow Builder — template, AI generator, or from scratch *(Flow Builder only)*
4. Sandbox testing — creating a sandbox account, switching device to sandbox, making a test purchase

If you received this playbook on its own, without this skill's directory, that checklist file is not available to you — fetch https://adapty.io/docs/app-store-connection-configuration.md, https://adapty.io/docs/enable-app-store-server-notifications.md and https://adapty.io/docs/app-store-test.md instead. They cover the connection, notification and sandbox-testing steps; creating the store products and designing the paywall are console and dashboard work with no docs substitute.

Note: When building for iOS from Unity, always open `Unity-iPhone.xcworkspace` in Xcode, never `Unity-iPhone.xcodeproj`.

### Android testing

Follow `references/testing-setup-android.md` (in this skill directory) for:
1. Creating products in Google Play Console
2. Connecting Google Play to Adapty (Service Account key, Package name) and enabling Real-Time Developer Notifications
3. Designing the flow in Flow Builder — template, AI generator, or from scratch *(Flow Builder only)*
4. Sandbox testing — adding a license tester, uploading to a closed track, making a test purchase, verifying results

If you received this playbook on its own, without this skill's directory, that checklist file is not available to you — fetch https://adapty.io/docs/google-play-store-connection-configuration.md, https://adapty.io/docs/enable-real-time-developer-notifications-rtdn.md and https://adapty.io/docs/testing-on-android.md instead. They cover the connection, notification and sandbox-testing steps; creating the store products and designing the paywall are console and dashboard work with no docs substitute.

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
> 4. **Onboardings** — build them as flows in Flow Builder. On SDK 4.x the legacy `GetOnboarding` API still compiles but is deprecated in favour of `GetFlow` and will be removed
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
| Onboardings (Flow Builder) | `unity-quickstart-paywalls`, `adapty-flow-builder` |
| Flow screen-view analytics | `unity-flow-screen-views` |
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
- Sample app (SDK-team maintained, close to real usage — open it when a docs page doesn't show how the pieces fit together in a real app; take API usage from it, not the sample's app architecture): https://github.com/adaptyteam/AdaptySDK-Unity/tree/main/Assets/Scripts
