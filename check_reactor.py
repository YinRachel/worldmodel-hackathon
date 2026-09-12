"""Check Reactor authentication without starting a generation session."""
import getpass
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


def safe_error(body, key):
    """Show diagnostics without echoing credentials or terminal control codes."""
    body = body.replace(key, "[REDACTED]")
    body = re.sub(r"rk_[A-Za-z0-9_-]+", "[REDACTED]", body)
    body = re.sub(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", body)
    return "".join(c for c in body if c.isprintable() or c == "\n")[:2000]


def main():
    key = os.environ.get("REACTOR_API_KEY")
    key_file = Path(__file__).resolve().parent / "api_key.txt"
    if not key and key_file.is_file():
        key = key_file.read_text(encoding="utf-8-sig").strip()
    if not key:
        key = getpass.getpass("Reactor API key (hidden): ")
    key = key.strip()
    if not key.strip():
        raise SystemExit("No key supplied.")
    if not re.fullmatch(r"rk_[A-Za-z0-9_-]+", key):
        raise SystemExit("Key format looks incorrect. Copy the raw key from Reactor, without quotes, spaces, or a backslash before the underscore.")
    payload = {
        "authorization_details": [{
            "type": "session",
            "resources": {"models": {"match": ["reactor/helios"]}},
            "constraints": {"max_sessions": 1},
        }]
    }
    request = urllib.request.Request(
        "https://api.reactor.inc/tokens",
        data=json.dumps(payload).encode(),
        headers={"Reactor-API-Key": key.strip(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = safe_error(exc.read(16384).decode("utf-8", errors="replace"), key)
        raise SystemExit(
            f"Token request failed (HTTP {exc.code}).\n"
            f"Reactor response: {detail or '(empty response)'}\n"
            "No generation session was started."
        ) from None
    except urllib.error.URLError:
        raise SystemExit("Cannot reach Reactor. Check your network connection.") from None
    if not result.get("jwt"):
        raise SystemExit("Unexpected response: no session token returned.")
    print("Authentication succeeded. Token received but not displayed or saved.")
    print("No generation session was started. Model availability still needs testing.")


if __name__ == "__main__":
    main()
