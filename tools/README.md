# Pinned external tools

`dependencies.json` pins official yt-dlp and Deno releases and a named BtbN LGPL FFmpeg Windows build. SHA-256 values are from the corresponding release asset pages. `scripts/fetch-tools.ps1` fails on any mismatch and copies only the needed executables. The FFmpeg archive's license files must be retained for distribution. See `THIRD_PARTY_NOTICES.md`.
