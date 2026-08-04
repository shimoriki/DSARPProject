"""Loop 1 — clone/update repositories listed in a config (or --repo)."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.config import load_config, load_repo_list
from dsarp.repositories.manager import RepositoryManager


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", help="repos_*.yaml kind, e.g. train/validation/test")
    ap.add_argument("--repo", help="single org/name slug")
    ap.add_argument("--depth", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config(args.profile)
    rm = RepositoryManager(cfg.data_dir)
    slugs = [args.repo] if args.repo else load_repo_list(
        args.config.replace("configs/repos_", "").replace(".yaml", "") if args.config else "train")
    for slug in slugs:
        st = rm.clone(slug, depth=args.depth)
        print(f"{slug}: exists={st.exists} head={st.head} {st.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
