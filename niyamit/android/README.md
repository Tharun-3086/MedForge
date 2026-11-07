# Niyamit Android app (debug/demo)

An installable Android application reusing the existing patient and clinic web interfaces in a native WebView shell. It is not a native UI rewrite. The backend remains on your laptop or hosted server; internet/server availability is required. No backend credentials are embedded.

## Included

- Niyamit launcher icon, Android activity, Home/Reload controls and Back navigation.
- Shared Patient/Clinic interface and role-based backend access.
- First-party sessions, file/gallery upload and camera capture through the system camera.
- Microphone runtime permission granted only to the configured Niyamit origin and only for audio capture.
- External links open outside the app; there is no JavaScript native bridge. TLS errors use Android's default blocking behavior. Mixed-content and file access are disabled.
- Downloaded originals go to app-specific external Downloads. Device file access and camera/microphone quality still need manual acceptance.

Minimum Android 10 (API 29); target API 36; compile SDK 37.0. This is a debug APK signed with a development identity, not a Play Store release. iPhone support is separate future work requiring macOS/Xcode.

## Build now on this Windows laptop

The SDK-only debug build avoids downloading a Gradle distribution:

```powershell
cd D:\niyamit\MedForge-Git\niyamit\android
.\build-debug.ps1
```

Defaults: SDK D:/Android/Sdk, JDK D:/androidstd/jbr, Build Tools 36.0.0, platform android-37.0. Override -Sdk and -Jdk on another machine. Output: build/Niyamit-debug.apk. The script uses official SDK aapt2, javac, d8, zipalign and apksigner and verifies the final signature. Build output and debug signing keys are ignored by Git.

The current demo version is `0.2-demo` (version code `2`). The SDK script accepts `-VersionCode` and `-VersionName` overrides. Keep the same local debug keystore to install an update over the previous demo APK.

For the hosted demo:

```powershell
.\build-debug.ps1 -AppUrl "https://niyamit-app.onrender.com/"
```

The login page defaults to India (+91); a complete valid mobile number enables the SMS button. A failed login-service connection offers an explicit retry without sending SMS automatically. These are hosted frontend changes: merge and redeploy the frontend to deliver them to existing and new APK installations. Rebuilding the shell alone does not bundle frontend changes.

## Emulator

```powershell
& "D:\Android\Sdk\platform-tools\adb.exe" reverse tcp:3000 tcp:3000
& "D:\Android\Sdk\platform-tools\adb.exe" install -r .\build\Niyamit-debug.apk
& "D:\Android\Sdk\platform-tools\adb.exe" shell am start -n com.niyamit.app/.MainActivity
```

Run the existing Docker web stack first. Default app URL is http://localhost:3000/ through adb reverse. Local HTTP is restricted to localhost and 10.0.2.2 in the network configuration. A physical phone requires its own adb reverse connection or a reachable HTTPS deployment.

For a reachable HTTPS test server, rebuild with:

```powershell
.\build-debug.ps1 -AppUrl "https://YOUR-APP-HOST/"
```

A temporary tunnel stops when its host stops and its address may change; each change requires rebuilding this test APK. The native shell does not provide hosting. Prefer the stable hosted demo once prepared. Never embed Twilio/AI/database keys or patient access tokens in the APK.

## Android Studio / Gradle

Open this android/ folder in Android Studio compatible with AGP 9.2. The official Gradle 9.4.1 wrapper is included with verified wrapper/distribution checksums. Keep Gradle caches on D: with GRADLE_USER_HOME if needed. Set the SDK using local.properties or Android Studio (local.properties is ignored). Source URL is app/src/main/res/values/config.xml. The debug script overrides it only in generated build resources.

```powershell
$env:JAVA_HOME="D:\androidstd\jbr"
$env:GRADLE_USER_HOME="D:\Android\GradleCache"
.\gradlew.bat assembleDebug
```

The SDK-only build was executed here; Gradle/Android Studio build files are provided but their full dependency-download build has not been validated yet. Release tasks reject a non-HTTPS source URL; production additionally needs stable hosting, release signing, security/privacy acceptance and store review. Debug WebView inspection is enabled only for debuggable builds.

## Acceptance

Verify fresh launch, Patient OTP, Clinic login, role isolation, file upload, camera capture, audio recording, denied microphone permission, Listen playback, original download, Back, logout and offline Retry on a real device. Check invite/caregiver links externally as normal web links; universal/app links are not configured. Emulator launch/login checks do not prove microphone/camera hardware quality or iPhone compatibility.
