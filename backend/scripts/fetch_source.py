"""Fetch an allowlisted documentation source and record its provenance.

    python scripts/fetch_source.py            # Salesforce CLI release notes (Apache-2.0)

Writes data/real/salesforce-cli/salesforce-cli-releasenotes.md and SOURCE.json (url, fetch time,
sha256, licence). Only URLs in app/ingestion/remote.ALLOWLIST can be fetched.
"""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.remote import fetch

URL = "https://raw.githubusercontent.com/forcedotcom/cli/main/releasenotes/README.md"
OUT = Path(__file__).resolve().parents[2] / "data" / "real" / "salesforce-cli"

if __name__ == "__main__":
    body, src = fetch(sys.argv[1] if len(sys.argv) > 1 else URL)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "salesforce-cli-releasenotes.md").write_bytes(body)
    meta = {
        "url": URL,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "license": src.license,
        "note": src.note,
    }
    (OUT / "SOURCE.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
