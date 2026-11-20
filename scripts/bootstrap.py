#!/usr/bin/env python3
"""Generate local demo secrets without overwriting existing credentials."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parents[1]
directory = root / "secrets"
directory.mkdir(mode=0o700, exist_ok=True)
for name in ("recovery_token", "grafana_password"):
    path = directory / name
    try:
        with path.open("x") as handle:
            handle.write(secrets.token_urlsafe(32) + "\n")
        # Compose file-based secrets preserve host permissions; Grafana runs as UID 472.
        # Keep files readable to the selected containers, inside a private host directory.
        os.chmod(path, 0o644)
        print("Created local secret file:", path.relative_to(root))
    except FileExistsError:
        print("Retained existing local secret:", path.relative_to(root))
print("Grafana username: cloudguard. Read secrets/grafana_password locally for the password.")
