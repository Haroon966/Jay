# Jay – Android App

## Build

**Option A – Run from Android Studio (USB)**  
Open the `android/` folder in Android Studio, connect the phone with USB debugging on, select the device, and click Run (green play button). Min SDK 24, target 34.

**Option B – Build APK and install on phone (no cable after)**  
1. In Android Studio: open `android/`, then **Build → Build Bundle(s) / APK(s) → Build APK(s)**.  
2. When the build finishes, click **locate** in the notification, or open:  
   `android/app/build/outputs/apk/debug/app-debug.apk`  
3. Put the APK on your phone any way you like:
   - **USB:** Copy `app-debug.apk` to the phone (e.g. Download folder), then on the phone open **Files** → tap the APK → **Install** (allow “Install unknown apps” for that app if asked).
   - **Cloud / link:** Upload the APK to Google Drive (or similar), open the link on the phone, download, then open the APK and install.
   - **ADB (phone connected once):**  
     `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`  
     (from the project root; `-r` allows reinstall/update.)

**Option C – Wireless debugging (Android 11+)**  
1. On the phone: **Settings → Developer options → Wireless debugging** → turn on.  
2. Tap **Pair device with pairing code** and note the IP:port and 6‑digit code.  
3. In Android Studio: **Run → Device Manager** (or run config) → **Pair devices over Wi‑Fi** and enter the code.  
4. After pairing, you can choose the phone over Wi‑Fi and run/install without a cable.

## Permissions

The app requests at runtime: BLUETOOTH_SCAN, BLUETOOTH_CONNECT, BLUETOOTH_ADVERTISE, RECORD_AUDIO, POST_NOTIFICATIONS (Android 13+). Grant all for intercom to work.

## First-run intercom checklist (fast onboarding)

Use this flow to keep startup friction low and consistent across phones:

1. Enable Bluetooth and grant all runtime permissions on first launch.
2. Pair once with the target peer (`Helmet-*` or second phone) from system Bluetooth settings.
3. Open Jay. The foreground service auto-starts after permissions are granted (no tap required).
4. Confirm connection status in-app, then speak to verify both directions.
5. If connection drops, keep the app open; reconnect runs automatically with bounded backoff.

## Protocol

Uses standard SPP UUID `00001101-...` so the app can connect to ESP32 firmware (default SPP server). Packet format: 2-byte length (little-endian) + payload. See [protocol/SPEC.md](../protocol/SPEC.md).

## Codec

Current implementation is **Opus-first** using `AndroidOpusCodec` (16 kHz, mono, 20 ms frames). If Opus init fails, PCM capture remains local only and is not sent over SPP because a 20 ms PCM frame (640 bytes) exceeds the protocol `MAX_PAYLOAD_LEN` (512).

## Noisy-environment tuning targets

For rider/team use, treat these as acceptance targets:

- Keep end-to-end latency under 200 ms in moving/noisy conditions.
- Prioritize stable duplex speech over maximum bitrate.
- Add DSP/noise-suppression stage before encode (SpeexDSP or RNNoise) as a follow-up integration.
- Validate mic gain and AGC settings with helmet-mounted microphones, not only indoor phone tests.
