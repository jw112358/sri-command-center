"""Create the offline Jeff user grant used by the Legal Agent OS runner.

The resulting file contains secrets, is ignored by git, and must be copied only
into the production secret manager.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to the Google OAuth Desktop client JSON",
    )
    parser.add_argument(
        "--output",
        default="./credentials/legal-google-user-token.json",
        help="Ignored local destination for the authorized-user JSON",
    )
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, SCOPES)
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        prompt="consent",
        access_type="offline",
        success_message="Legal Agent OS authorization complete. You may close this tab.",
    )
    output.write_text(credentials.to_json(), encoding="utf-8")
    os.chmod(output, 0o600)
    print(f"Authorized-user grant saved securely to: {output}")


if __name__ == "__main__":
    main()
