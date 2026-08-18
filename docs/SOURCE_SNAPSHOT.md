# Canonical v7.0 Source Snapshot

The exact clean source payload for `NEXUS CORE v7.0.0` is stored in this repository under:

```text
.bootstrap/v7clean/part00
.bootstrap/v7clean/part01
.bootstrap/v7clean/part02
.bootstrap/v7clean/part03
.bootstrap/v7clean/part04
.bootstrap/v7clean/part05
```

These files are the Base64 representation of a compressed `tar.xz` source snapshot. The snapshot intentionally contains only the canonical source/test/runtime files and excludes secrets and local runtime data.

Archive SHA-256:

```text
b9d5c710245421b6d5c3f2f245b9a038d6f62fe7b3dfe5d8400623e14ab25c4c
```

Contained source paths include:

```text
app/
tests/
requirements.txt
run.py
setup_windows.bat
start_windows.bat
run_tests.bat
ARCHITECTURE_V7.md
README_V7_FA.md
BUILD_TEST_REPORT_V7_0.txt
```

## Materialize locally

After cloning the repository:

```cmd
materialize_v7_source.bat
```

or:

```bash
python scripts/materialize_v7_source.py
```

The materializer:

1. concatenates the six source parts,
2. Base64-decodes them,
3. verifies the SHA-256 checksum,
4. decompresses the XZ payload,
5. safely extracts the canonical v7.0 source into the repository working tree.

After extraction on Windows:

```cmd
setup_windows.bat
start_windows.bat
```

## Why this snapshot exists

The snapshot is a tamper-checkable handoff/backup of the exact v7.0 baseline. Future normal development should work with the materialized source tree and ordinary Git commits/PRs; the snapshot should remain unchanged as the historical v7.0 reference.
