# iOS Testing Setup: Before Your First Sandbox Purchase

All code is written and builds. Before you can test purchases, three external things must be configured. Work through them in order — each step depends on the previous one.

Present this entire checklist to the user with the **exact product IDs and placement IDs from Phase 3 already filled in**. The user follows the steps; you answer questions.

---

## Part 1: Create products in App Store Connect

Adapty products need matching products in App Store Connect before purchases work.

1. Open [App Store Connect](https://appstoreconnect.apple.com) → your app → **Monetization → Subscriptions**.

2. Create a subscription group if none exists (e.g. "Premium").

3. For **each product** created in Phase 3, add a subscription in the group:

   | What to enter | Value |
   |---|---|
   | Reference Name | Any name (e.g. "Monthly Premium") |
   | Product ID | *(the exact `--ios-product-id` used in Phase 3)* |
   | Duration | *(matching the `--period` used in Phase 3)* |

   After creating each subscription:
   - Set a price (any price works for sandbox)
   - Add at least one localization (display name + description)

4. Wait for status to show **Ready to Submit** (usually immediate). No App Review needed for sandbox testing.

---

## Part 2: Connect App Store to Adapty

This is required for Adapty to validate purchases and receive subscription events. Complete all three sub-steps.

### Step 2a: Provide Bundle ID and Apple app ID

1. In App Store Connect → your app → **General → App Information**.
2. Copy the **Bundle ID** from the General Information section.
3. Open [Adapty Dashboard → App settings → iOS SDK](https://app.adapty.io/settings/ios-sdk).
4. Paste the Bundle ID into the **Bundle ID** field.
5. Back in App Store Connect, copy the **Apple ID** (numeric, also on the App Information page).
6. In Adapty Dashboard → iOS SDK, paste it into the **Apple app ID** field.

### Step 2b: Generate and upload In-App Purchase Key

1. In App Store Connect → [**Users and Access → Integrations → In-App Purchase**](https://appstoreconnect.apple.com/access/integrations/api/subs).
   *(Requires Admin or Account Holder role.)*
2. Click **+** next to **Active**.
3. Enter any key name → click **Generate**.
4. Click **Download In-App Purchase Key**. Save the `.p8` file — it can only be downloaded once.
5. Back in the same In-App Purchase list, note the **Key ID** for the key you just created.
6. Note the **Issuer ID** shown above the key list.
7. In [Adapty Dashboard → App settings → iOS SDK](https://app.adapty.io/settings/ios-sdk):
   - Paste the **Issuer ID**
   - Paste the **Key ID**
   - Upload the `.p8` file
8. Click **Save**.

### Step 2c: Enable App Store Server Notifications

Server notifications are required for subscription events (renewals, cancellations, refunds) to reach Adapty.

1. In [Adapty Dashboard → App settings → iOS SDK](https://app.adapty.io/settings/ios-sdk), copy the **URL for App Store server notification**.
2. In App Store Connect → your app → **General → App Information → App Store Server Notifications**.
3. Paste the URL into both:
   - **Production Server URL**
   - **Sandbox Server URL**
4. Save in App Store Connect.

---

## Part 3: Design the paywall in Adapty *(Paywall Builder only — skip for Custom paywall)*

The paywall must have a design and the "Show on device" toggle must be on before it renders. Without this, `hasViewConfiguration` returns `false` and the paywall view will not render even if `getPaywall` succeeds.

### Option A: Use a template (fastest)

1. In [Adapty Dashboard → Paywalls](https://app.adapty.io/paywalls), open your paywall.
2. Click **Paywall Builder**.
3. Click **Change template** in Layout settings.
4. Browse the template gallery and select one. Templates are professionally designed — pick one that fits your app's style.
5. Click **Choose** to apply it. Note: switching templates discards unsaved changes, so confirm before proceeding.
6. The template comes pre-populated with placeholder text and layout. Update:
   - **Headline** — your app's value proposition (e.g. "Unlock Premium")
   - **Product buttons** — verify your products appear; if not, add them from the products panel
   - **App icon / logo** — replace the placeholder with your brand asset
7. Enable the **Show on device** toggle.
8. Click **Save**.

### Option B: Generate with AI *(published apps only — requires Apple App ID set in App settings)*

The AI generator analyzes your app's App Store listing to generate relevant visuals and copy automatically.

1. In Paywall Builder, click **Change template → Generate template**, or click **Generate paywall** from the Builder & Generator tab.
2. Write a prompt describing the visual style. Tips:
   - **Good**: "Create a modern, minimalistic paywall with a light background, rounded buttons, and subtle gradients."
   - **Bad**: "Make my paywall look modern" (too vague)
   - Don't describe your app — Adapty pulls that from the App Store automatically.
   - Describe visuals and text, not layout structure.
3. Choose one of the five generated designs → click **Pick & Open in Builder**.
4. Review and adjust text and products as needed.
5. Enable the **Show on device** toggle.
6. Click **Save**.

---

## Part 4: Test in sandbox

> **Use a real device.** Sandbox purchases can run on simulators, but real devices are needed for full purchase flow testing including payment dialogs.

### Step 1: Create a Sandbox test account

Create a **new** account — do not reuse an existing one, as previous purchase history prevents re-purchasing the same products.

1. In App Store Connect → [**Users and Access → Sandbox → Test Accounts**](https://appstoreconnect.apple.com/access/users/sandbox) → click **+**.
2. Fill in the details. Set **Country or Region** to match where you plan to test (affects product availability and currency).
3. Click **Create**.

> Tip: Gmail/iCloud users can use plus addressing (e.g. `you+sandbox1@gmail.com`) to reuse an existing inbox.

### Step 2: Enable Developer mode on the test device

1. Connect your test device to a Mac running Xcode.
2. On the device: **Settings → Privacy & Security → Developer Mode** → turn on.

### Step 3: Switch to Sandbox account on device

1. On the device: **Settings → Your Apple Account → Media & Purchases** → **Sign Out**.
2. Go to **Settings → Developer → Sandbox Apple Account** → tap **Sign In**.
3. Sign in with the Sandbox test account credentials from Step 1.

### Step 4: Build and run

Build and run the app from Xcode on the connected device. The app launches with a debugging session.

### Step 5: Make a test purchase

1. Trigger the paywall in the app (tap a premium feature or navigate to the paywall screen).
2. Tap a product to purchase.
3. Complete the purchase — no real charges occur in sandbox.

### Step 6: Verify results

- **Adapty Dashboard → [Event Feed](https://app.adapty.io/event-feed)**: the purchase event should appear within ~10 minutes.
- **In the app**: `isPremiumUser` should return `true`.

> Sandbox subscriptions renew on an accelerated schedule: monthly = 5 min, annual = 1 hour, up to 12 renewals.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Paywall doesn't appear / blank screen | `hasViewConfiguration` is false | Part 3: enable "Show on device" in Paywall Builder and save |
| Product list is empty | Product ID mismatch (case-sensitive) | Verify `--ios-product-id` in Adapty exactly matches the Product ID in App Store Connect |
| Purchase succeeds but no event in Adapty | Server notifications not configured | Re-check Step 2c: both Production and Sandbox URLs must be set |
| Can't buy — "already purchased" | Reused sandbox account with purchase history | Create a new sandbox account (Step 1) or clear purchase history: **Settings → Developer → Sandbox Apple Account → Manage → Clear Purchase History** |
| Event feed shows no data after 10 min | Bundle ID or Apple app ID mismatch | Re-check Step 2a values in Adapty dashboard |
