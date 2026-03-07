"""Build helper for Vercel static assets."""

from __future__ import annotations

from pathlib import Path
import shutil


def main() -> None:
    root = Path(__file__).resolve().parent
    source = root / "src" / "hex6" / "web" / "static"
    target = root / "public" / "static"

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    print(f"Copied static assets to {target}")


if __name__ == "__main__":
    main()
