# Third-party notices

This application's own code is under MIT (see `LICENSE`). This does not relicense bundled components.

- **PySide6 / Qt**: Qt for Python is distributed under LGPLv3/GPLv3 or commercial terms. Packaging must retain applicable licenses, notices and a route to replace LGPL libraries. Review [Qt licensing](https://www.qt.io/licensing) before public distribution.
- **yt-dlp**: official standalone executable from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases); core is Unlicense, with separately licensed bundled components. Retain its bundled notices.
- **FFmpeg / FFprobe**: [BtbN LGPL Windows build](https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-16-13-04), built from [FFmpeg](https://ffmpeg.org/legal.html). Build archive license files are copied into the package. Review linked library licenses and exact build configuration before redistribution.
- **Deno**: official [Deno v2.9.7](https://github.com/denoland/deno/releases/tag/v2.9.7), MIT and third-party licenses; retain notices from its distribution/source.

The pinned archive hashes and URLs are in `tools/dependencies.json`. The developer build script verifies downloaded tool files against the pinned SHA-256 values. The application has no updater. Public redistribution requires completing the component-specific license and source availability review described in docs/RELEASE.md.
