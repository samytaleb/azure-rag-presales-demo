"""Stage fictional B2B Markdown source documents as plain TXT for upstream ingestion.

Upstream's manual ingestion officially supports .txt; .md is not listed there.
This script never calls Azure and does not modify the Markdown originals.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "data"


def stage(output: Path, overwrite: bool = False) -> list[tuple[str, str]]:
    sources = sorted(DOCS.glob("*.md"))
    if len(sources) != 4:
        raise ValueError("Expected exactly four fictional source documents")
    output.mkdir(parents=True, exist_ok=True)
    decisions = []
    for source in sources:
        destination = output / (source.stem + ".txt")
        data = source.read_bytes()
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("Refusing to replace non-regular target: " + destination.name)
            if destination.read_bytes() == data:
                decisions.append((destination.name, "unchanged"))
                continue
            if not overwrite:
                raise FileExistsError("Target differs, use --force to replace: " + destination.name)
        # Don't follow symlinks in the output directory: resolved parents must agree.
        if destination.parent.resolve() != output.resolve():
            raise ValueError("Unsafe output directory")
        destination.write_bytes(data)
        decisions.append((destination.name, "staged"))
    return decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage synthetic documents for Azure TXT ingestion")
    parser.add_argument("--output", type=Path, default=Path("data"),
                        help="Staging directory (default: data/) for upstream prepdocs ingestion")
    parser.add_argument("--force", action="store_true",
                        help="Replace existing files only if their bytes differ")
    args = parser.parse_args(argv)
    try:
        for name, action in stage(args.output, overwrite=args.force):
            print(action + ": " + str(args.output / name))
    except (OSError, ValueError) as error:
        parser.exit(2, "Staging failed: " + type(error).__name__ + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
