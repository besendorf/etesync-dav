"""Generate a deterministic SHA-256 checksum manifest for release artifacts."""

import argparse
import hashlib
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    checksum_path = args.directory / "SHA256SUMS"
    artifacts = sorted(path for path in args.directory.iterdir() if path.is_file() and path != checksum_path)
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
