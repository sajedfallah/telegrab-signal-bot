from __future__ import annotations

import base64
import hashlib
import io
import lzma
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS_DIR = ROOT / ".bootstrap" / "v7clean"
EXPECTED_SHA256 = "b9d5c710245421b6d5c3f2f245b9a038d6f62fe7b3dfe5d8400623e14ab25c4c"


def main() -> None:
    parts = sorted(PARTS_DIR.glob("part[0-9][0-9]"))
    if not parts:
        raise SystemExit(f"No v7 source parts found in {PARTS_DIR}")

    encoded = b"".join(p.read_bytes().strip() for p in parts)
    archive = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(archive).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            "Source archive checksum mismatch. "
            f"Expected {EXPECTED_SHA256}, got {digest}."
        )

    raw_tar = lzma.decompress(archive)
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tf:
        # The archive is generated from the canonical v7 source tree and contains
        # only relative repository paths. Reject anything unexpected anyway.
        for member in tf.getmembers():
            dest = (ROOT / member.name).resolve()
            if ROOT.resolve() not in dest.parents and dest != ROOT.resolve():
                raise SystemExit(f"Unsafe archive path: {member.name}")
        tf.extractall(ROOT)

    print("NEXUS CORE v7.0 canonical source materialized successfully.")
    print(f"Verified archive SHA-256: {digest}")


if __name__ == "__main__":
    main()
