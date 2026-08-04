"""Loop 8 — train the local preference ranker (LightGBM/sklearn/fallback)."""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.config import load_config
from dsarp.scripts_support import train_ranker


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--dataset", default=None)
    args = ap.parse_args()
    cfg = load_config(args.profile)
    out = train_ranker(cfg, Path(args.dataset) if args.dataset else None)
    print("ranker ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
