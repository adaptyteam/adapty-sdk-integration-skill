# Android Testing Setup: Before Your First Sandbox Purchase

All code is written and builds. Before you can test purchases, several external things must be configured. Work through them in order — each step depends on the previous one.

Present this entire checklist to the user with the **exact product IDs and placement IDs from Phase 3 already filled in**. The user follows the steps; you answer questions.

---

## Part 1: Create products in Google Play Console

Adapty products need matching products in Google Play Console before purchases work.

1. Open [Google Play Console](https://play.google.com/console) → your app → **Monetize → Products**.

2. For **subscriptions**, go to **Subscriptions → Create subscription**:

   | What to enter | Value |
   |---|---|
   | Product ID | *(the exact `--android-product-id` used in Phase 3)* |
   | Name | Any name (e.g. "Monthly Premium") |
   | Description | Short description |

   After creating the subscription:
   - Add a **base plan** — the base plan ID must match the `--android-base-plan-id` used in Phase 3
   - Set a billing period matching the `--period` used in Phase 3
   - Set a price (any price works for testing)
   - Activate the base plan

3. For **one-time products (non-consumable)**, go to **In-app products → Create product**:

   | What to enter | Value |
   |---|---|
   | Product ID | *(the exact `--android-product-id` used in Phase 3)* |
   | Name | Any name |
   | Price | Any price |

   Activate the product after creation.

---

## Part 2: Connect Google Play to Adapty

This is required for Adapty to validate purchases and receive subscription events. Complete both sub-steps.

### Step 2a: Upload a Google Play Service Account key

Adapty uses a Service Account key to communicate with Google Play. If you don't have one:

1. Open [Google Cloud Console](https://console.cloud.google.com) → select or create the project linked to your Google Play account.
2. Go to **IAM & Admin → Service Accounts → Create Service Account**.
3. Give it a name (e.g. "Adapty"), click **Create and Continue**.
4. Skip role assignment → click **Done**.
5. In the service account list, click the account you just created → **Keys → Add Key → Create new key → JSON → Create**.
6. The `.json` file downloads automatically. Save it — you'll upload it to Adapty.
7. In [Google Play Console → Setup → API access](https://play.google.com/console/developers/api-access):
   - Link to the Google Cloud project from step 1 (if not already linked)
   - Under **Service accounts**, find the account you created → click **Grant access**
   - Grant these permissions: **View financial data**, **Manage orders and subscriptions**
   - Click **Apply**
8. In [Adapty Dashboard → App settings → Android SDK](https://app.adapty.io/settings/android-sdk):
   - Upload the `.json` key file
   - Click **Save**

### Step 2b: Enable Real-Time Developer Notifications (RTDN)

RTDN is required for subscription events (renewals, cancellations, refunds) to reach Adapty.

1. In [Adapty Dashboard → App settings → Android SDK](https://app.adapty.io/settings/android-sdk), copy the **Google Cloud Pub/Sub topic** value.
2. In [Google Play Console → Monetize → Monetization setup](https://play.google.com/console/developers/app/monetize-setup):
   - Paste the topic into the **Real-time developer notifications** field
   - Click **Send test notification** to verify the connection → you should see a success message
   - Click **Save**

> If "Send test notification" returns an error, the Service Account likely doesn't have Pub/Sub permissions. In Google Cloud Console → IAM, add the `Pub/Sub Publisher` role to the service account.

---

## Part 3: Design the paywall in Adapty *(Paywall Builder only — skip for Custom paywall)*

The paywall must have a design and the "Show on device" toggle must be on before it renders. Without this, `hasViewConfiguration` returns `false` and the paywall will not render even if `getPaywall` succeeds.

### Option A: Use a template (fastest)

1. In [Adapty Dashboard → Paywalls](https://app.adapty.io/paywalls), open your paywall.
2. Click **Paywall Builder**.
3. Click **Change template** in Layout settings.
4. Browse the template gallery and select one.
5. Click **Choose** to apply it.
6. Update:
   - **Headline** — your app's value proposition (e.g. "Unlock Premium")
   - **Product buttons** — verify your products appear; if not, add them from the products panel
   - **App icon / logo** — replace the placeholder with your brand asset
7. Enable the **Show on device** toggle.
8. Click **Save**.

### Option B: Generate with AI

1. In Paywall Builder, click **Change template → Generate template**, or click **Generate paywall** from the Builder & Generator tab.
2. Write a prompt describing the visual style. Tips:
   - **Good**: "Create a modern, minimalistic paywall with a dark background and rounded buttons."
   - Describe visuals and text style, not layout structure or your app's features.
3. Choose one of the generated designs → click **Pick & Open in Builder**.
4. Review and adjust text and products as needed.
5. Enable the **Show on device** toggle.
6. Click **Save**.

---

## Part 4: Set up sandbox testing

Android sandbox testing requires the app to be uploaded to a closed testing track. Emulators can be used, but a real device gives a more complete test.

### Step 1: Add a license tester

License testers can make purchases without being charged.

1. In [Google Play Console → Setup → License testing](https://play.google.com/console/developers/license-testing).
2. Add the Gmail address you'll use for testing.
3. Set the license response to **RESPOND_NORMALLY**.
4. Click **Save changes**.

> The test account must be a Google account that is signed in on your test device. It cannot be the same account as the developer account.

### Step 2: Upload a signed APK to a closed track

Google Play sandbox purchases only work for apps uploaded to Play — local debug builds won't trigger the Google Play billing flow.

1. Build a **release APK or AAB** signed with your upload key:
   ```bash
   ./gradlew bundleRelease   # or assembleRelease for APK
   ```
2. In [Google Play Console → Testing → Closed testing](https://play.google.com/console/app/closed-testing) → create a track if none exists (e.g. "Internal testing").
3. Click **Create new release** → upload the APK/AAB → click **Save** → **Review release** → **Start rollout**.

### Step 3: Add tester and get the opt-in URL

1. In the closed track → **Testers** tab → add the Gmail address from Step 1.
2. Copy the **opt-in URL** shown on the testers page.
3. Open the opt-in URL on the test device and accept the invitation.

> The opt-in must happen on the device where you'll test. After accepting, the tester account is linked to the closed track build.

### Step 4: Install and test

1. Install the app on the test device from Google Play (search for it after accepting the opt-in, or use the Play Console internal app sharing link).

   > Alternatively, you can sideload the APK for faster iteration — but the tester Gmail must still be signed in on the device for billing to work.

2. Open the app and trigger the paywall.
3. Tap a subscription product — the **Google Play purchase sheet** should appear with your product's name and price.
4. Complete the purchase — no real charges occur for license testers.

### Step 5: Verify results

- **Adapty Dashboard → [Event Feed](https://app.adapty.io/event-feed)**: the purchase event should appear within ~10 minutes.
- **In the app**: `isPremiumUser` (via `profile.accessLevels["premium"]?.isActive`) should return `true`.

> Sandbox subscriptions on Android renew on an accelerated schedule: monthly = 5 min, annual = 30 min.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Paywall doesn't appear / blank screen | `hasViewConfiguration` is false | Part 3: enable "Show on device" in Paywall Builder and save |
| Google Play purchase sheet doesn't appear | App not installed from Play or tester not opted in | Complete Steps 2–3: upload to closed track, add tester, open opt-in URL |
| Products show but prices are missing | Products not activated in Google Play Console | Activate the subscription base plan and/or one-time product |
| Purchase succeeds but no event in Adapty | RTDN not configured or Service Account missing Pub/Sub permission | Re-check Step 2b; try "Send test notification" to diagnose |
| Empty products list | Product ID or base plan ID mismatch (case-sensitive) | Verify `--android-product-id` and `--android-base-plan-id` match exactly what's in Google Play Console |
| "Item already owned" error | Previous test purchase not consumed | In Google Play Console → Order management, cancel/refund the previous order, or create a new product ID |
| Event feed shows no data after 10 min | Service Account not linked to Play Console or wrong permissions | Re-check Step 2a: grant **View financial data** and **Manage orders and subscriptions** |
