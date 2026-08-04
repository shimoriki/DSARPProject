"""Import the real Arcan + Designite outputs (DSARP dataset/) into data/raw/.

Maps each of the 5 provided repositories to its canonical DSARP project_id (matching the
git clone directory convention) and imports:
  Arcan     smell-characteristics.csv   -> data/raw/arcan/<pid>.json
  Designite ArchitectureSmells.csv      -> data/raw/designite/<pid>.json

These findings then flow into the EvidenceCase (via prepare_evidence / normalize), where
they MERGE with the structural detector's smells and raise tool-agreement confidence.

Cassandra is imported too, but ONLY for the UNSEEN evaluation — the leakage guard keeps it
out of every training split.

Usage: python scripts/import_arcan_designite.py
"""
from __future__ import annotations

from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.config import load_config
from dsarp.tools.arcan import ArcanAdapter
from dsarp.tools.designite import DesigniteAdapter
from dsarp.util import write_json

DATASET = Path(__file__).resolve().parent.parent / "DSARP dataset"

# canonical project_id -> (Arcan folder, Designite folder). Both may contain per-module
# sub-folders (e.g. Karaf/{jaas,jdbc,jms,Main}_Output) that are globbed and combined.
REPOS = {
    "apache-tika":            ("Arcan/Tika",         "Designite/Tika"),
    "apache-struts":          ("Arcan/Struts",       "Designite/struts"),
    "apache-logging-log4j2":  ("Arcan/Loggin_log4j", "Designite/logging_log4j"),
    "apache-karaf":           ("Arcan/Karaf",        "Designite/Karaf"),
    "apache-cassandra":       ("Arcan/Cassandra",    "Designite/cassandra"),
}


def main() -> int:
    cfg = load_config("local")
    arcan, des = ArcanAdapter(), DesigniteAdapter()
    for pid, (arc_dir, des_dir) in REPOS.items():
        a = []
        for f in (DATASET / arc_dir).rglob("smell-characteristics.csv"):
            a.extend(arcan.import_findings(f))
        d = []
        for f in (DATASET / des_dir).rglob("ArchitectureSmells.csv"):
            d.extend(des.import_findings(f))
        write_json(cfg.data_dir / "raw" / "arcan" / f"{pid}.json", [f.__dict__ for f in a])
        write_json(cfg.data_dir / "raw" / "designite" / f"{pid}.json", [f.__dict__ for f in d])
        tag = " (UNSEEN - eval only)" if "cassandra" in pid else ""
        print(f"[import] {pid}: Arcan={len(a)} Designite={len(d)}{tag}")
    print("[import] done. Re-run evidence prep to merge these into the training data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
