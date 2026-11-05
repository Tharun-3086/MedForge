# Local testing

The maintained setup and acceptance instructions are in [README.md](README.md) and [TESTING.md](TESTING.md). Deployment boundaries and backup operations are in [DEPLOYMENT.md](DEPLOYMENT.md).

The frontend, backend, worker, database and Redis run on the same laptop. No friend's frontend or Tailscale connection is required. Android uses emulator Chrome and `adb reverse tcp:3000 tcp:3000`; this repository does not contain a native APK release.
