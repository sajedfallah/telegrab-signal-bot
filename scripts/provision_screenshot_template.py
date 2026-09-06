"""Install only a sanitized MT5 screenshot template.

Templates are terminal-specific artifacts, so the canonical visual template is
kept outside the repository until it has passed this guard.  This utility is
deliberately copy-only: it never reads or changes a user's normal template and
rejects Expert sections or strings that can carry credentials.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


FORBIDDEN_MARKERS = (
    "<expert>",
    "</expert>",
    "admin token",
    "admin_token",
    "api token",
    "api_token",
    "bot_token",
    "password",
    "secret",
    "credential",
)


def validate_template(path: Path) -> None:
    if path.suffix.lower() != ".tpl":
        raise ValueError("template must use the .tpl extension")
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    if not raw.strip():
        raise ValueError("template is empty")
    lowered = raw.lower()
    found = [marker for marker in FORBIDDEN_MARKERS if marker in lowered]
    if found:
        raise ValueError(f"template contains forbidden marker(s): {', '.join(found)}")


def provision(source: Path, destination_dir: Path) -> Path:
    validate_template(source)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "NEXUS_Screenshot.tpl"
    shutil.copyfile(source, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and install NEXUS_Screenshot.tpl")
    parser.add_argument("--source", required=True, type=Path, help="approved sanitized .tpl file")
    parser.add_argument("--destination-dir", required=True, type=Path, help="MT5 Profiles\\Templates directory")
    args = parser.parse_args()
    result = provision(args.source, args.destination_dir)
    print(f"Installed sanitized screenshot template: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
