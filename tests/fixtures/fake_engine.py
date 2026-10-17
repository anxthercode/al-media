"""Deterministic QProcess target for tests; no network or external service."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
if "-J" in args:
    if "failure.test" in args[-1]:
        print("ERROR: Unsupported URL", file=sys.stderr)
        sys.exit(1)
    if "bot.test" in args[-1]:
        print("WARNING: No title found in player responses", file=sys.stderr)
        print("ERROR: [youtube] Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"title": "Fixture", "extractor_key": "Fake", "duration": 61,
                      "formats": [{"vcodec": "h264", "acodec": "aac", "height": 720,
                                   "ext": "mp4"}]}))
else:
    if "slow.test" in args[-1]:
        time.sleep(60)
    folder = Path(args[args.index("--paths") + 1])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "Пример [id].mp4"
    path.write_bytes(b"fixture media")
    print("ALM_PROGRESS:download|5|10|NA|100|1|50", flush=True)
    print("ALM_PROGRESS:postprocess|NA|NA|NA|NA|NA|NA", flush=True)
    print("ALM_FILE:" + os.fspath(path), flush=True)
