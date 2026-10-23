# Android Gateway Setup & Installation Guide

This guide walks you through building, installing, configuring, and operating the **SMS Gateway** Android mobile application.

---

## 1. Prerequisites

### Hardware & Operating System
- **Physical Device (Recommended)**: Any physical Android smartphone running Android 8.0 (API 26) through Android 14 (API 34) with an active SIM card inserted and airtime/SMS bundle balance.
- **Development Emulator**: Android Emulator running API 30+ with Google APIs (e.g. `Flutter_API_30` or Android Virtual Device). *Note: Emulators can verify UI, navigation, networking, pairing, and Room database operations, but cannot transmit real cellular radio signals.*
- **Android SDK & Tools**:
  - Android SDK installed (`platforms/android-34`, `build-tools/34.0.0`)
  - Java Development Kit (JDK 17 or higher)
  - Android Debug Bridge (`adb`)

---

## 2. Permissions & Security Model

The Android app requires sensitive telephony permissions because it interacts directly with the cellular hardware:

| Permission | Android API Level | Purpose & Necessity |
| :--- | :--- | :--- |
| `android.permission.SEND_SMS` | All versions | Required by `SmsManager` to dispatch real SMS messages through the phone's SIM card. |
| `android.permission.RECEIVE_SMS` | All versions | Required by `IncomingSmsReceiver` to intercept incoming SMS messages and forward them to the backend. |
| `android.permission.READ_PHONE_STATE` | All versions | Required to detect SIM readiness, carrier name, and cellular radio status. |
| `android.permission.POST_NOTIFICATIONS` | Android 13+ (API 33+) | Required to display the continuous Foreground Service status notification. |
| `android.permission.FOREGROUND_SERVICE` | Android 9+ (API 28+) | Required to run ongoing background polling without Android OS killing the process. |
| `android.permission.FOREGROUND_SERVICE_DATA_SYNC`| Android 14+ (API 34+) | Required type declaration for ongoing network synchronization. |
| `android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | Android 6+ (API 23+) | Allows user to exempt the gateway from aggressive Android Doze battery optimizations. |

All credentials (server URL, device ID, device token) are encrypted in hardware-backed storage via `EncryptedSharedPreferences` utilizing the Android Keystore system.

---

## 3. Building the Application

### Option A: Command Line Build (Gradle)
```bash
cd android-app

# Build debug APK
./gradlew assembleDebug

# Run unit tests
./gradlew testDebugUnitTest
```
The compiled APK will be output to:
`android-app/app/build/outputs/apk/debug/app-debug.apk`

### Option B: Android Studio
1. Launch Android Studio.
2. Select **Open an Existing Project** and navigate to `sim-sms-gateway/android-app`.
3. Wait for Gradle sync to complete.
4. Select `app` run configuration and click **Run** (green triangle) or press `Shift + F10`.

---

## 4. Installing the App via ADB

Connect your phone via USB with **USB Debugging** enabled (in Android Developer Options):

```bash
# Check connected devices
adb devices

# Install APK onto phone
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## 5. Pairing the Phone with the Backend

1. **Start the Python Backend**:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Generate a Device Pairing Code**:
   In the backend directory, run:
   ```bash
   python -m app.cli create-pairing-code --name "WarehousePixel" --phone "+255712345678" --carrier "Vodacom"
   ```
   This generates an 8-character single-use code (e.g. `K9X2M4PQ`).

3. **Open the SMS Gateway App on the Phone**:
   - On first launch, the Splash screen transitions to the Welcome & Onboarding guide.
   - Tap **Get Started**.
   - Enter your Server URL:
     - Local Workstation (physical phone on same Wi-Fi): `http://192.168.1.50:8000`
     - Android Emulator: `http://10.0.2.2:8000`
     - Production Server: `https://sms.yourdomain.com`
   - Enter the 8-character Pairing Code.
   - Tap **Connect & Register Device**.

4. **Grant Runtime Permissions**:
   - Tap **Allow** when Android requests `SEND_SMS`, `RECEIVE_SMS`, and `READ_PHONE_STATE`.

5. **Verify Operation**:
   - The Dashboard will display a green `CONNECTED` badge.
   - The SIM status will show `READY`.
   - The app begins background polling for queued SMS jobs and sending heartbeats.

---

## 6. Ensuring Uninterrupted Background Operation

Android implements aggressive battery saver mechanisms (Doze mode, App Standby buckets) that can throttle background network operations:

1. **Persistent Foreground Service**: The SMS Gateway app automatically starts `GatewayForegroundService` upon pairing, keeping an active notification in the Android notification shade.
2. **Battery Optimization Exemption**:
   - Go to phone **Settings** > **Apps** > **SMS Gateway** > **Battery**.
   - Change battery usage from **Optimized** to **Unrestricted**.
3. **Keep Device Powered**: For production gateway duty, connect the Android smartphone to a reliable USB wall charger with constant Wi-Fi or LTE data enabled.
