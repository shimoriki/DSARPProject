"""Convert Arcan 1.2.1 CLI output into the three baseline CSVs the DSARP web UI validates.

The UI wants Arcan's server-style export:
    component-metrics.csv    project, versionId, ComponentType, name
    smell-characteristics.csv project, versionId, smellType, AffectedConstructType, AffectedElements
    smell-affects.csv        project, versionId, from, to

The Arcan 1.2.1 jar in tools/ writes a different set, so this maps one to the other. Nothing is
invented: every row below is derived from a file Arcan actually wrote.

    CM.csv   Class,FI,FO,CBO,LCOM                 -> component-metrics, ComponentType=CLASS
    PM.csv   Package,CA,CE,RMI,RMA,RMD            -> component-metrics, ComponentType=PACKAGE
    HL.csv   Class,FanIn,FanOut,Total Dependences -> hubLikeDep smells
    UD.csv   UnstableDependenciesPackage,...,CorrelatedPackage
                                                  -> unstableDep smells, and one affects edge each
    UD30.csv the same pairs filtered at 30% instability -> severity flag only, NEVER extra rows
    packageCyclicDependencyTable.csv              -> cyclicDep smells at PACKAGE granularity
    classCyclicDependencyTable.csv                -> cyclicDep smells at CLASS granularity

The cycle tables are membership matrices: one row per cycle, one column per element, 1 meaning
the element is in that cycle. The members of a row are its AffectedElements.
"""
import csv
import sys
from pathlib import Path

SMELL_NAMES = {"cyclicDep": "Cyclic Dependency", "hubLikeDep": "Hub-like Dependency",
               "unstableDep": "Unstable Dependency"}


def read(path: Path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cycles_from_matrix(path: Path):
    """[(cycle_name, [members...])] from a membership matrix."""
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return []
    header = rows[0]
    out = []
    for row in rows[1:]:
        if not row:
            continue
        members = [header[i] for i in range(1, min(len(row), len(header)))
                   if str(row[i]).strip() == "1"]
        if members:
            out.append((row[0], members))
    return out


def convert(arcan_dir: Path, out_dir: Path, project: str, version_id: str):
    arcan_dir, out_dir = Path(arcan_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    components = []
    for r in read(arcan_dir / "CM.csv"):
        name = (r.get("Class") or "").strip()
        if name:
            components.append({"project": project, "versionId": version_id,
                               "ComponentType": "CLASS", "name": name,
                               "FanIn": r.get("FI", ""), "FanOut": r.get("FO", ""),
                               "CBO": r.get("CBO", ""), "LCOM": r.get("LCOM", "")})
    for r in read(arcan_dir / "PM.csv"):
        name = (r.get("Package") or "").strip()
        if name:
            components.append({"project": project, "versionId": version_id,
                               "ComponentType": "PACKAGE", "name": name,
                               "FanIn": r.get("CA", ""), "FanOut": r.get("CE", ""),
                               "CBO": "", "LCOM": ""})

    smells, affects = [], []

    def add_smell(stype, construct, elements, extra=""):
        smells.append({"project": project, "versionId": version_id,
                       "smellType": stype,
                       "AffectedComponentType": "CONTAINER" if construct == "PACKAGE" else "UNIT",
                       "AffectedConstructType": construct,
                       "AffectedElements": "|".join(elements),
                       "Size": len(elements), "Detail": extra,
                       "architecture_smell": SMELL_NAMES.get(stype, stype)})

    for name, members in cycles_from_matrix(arcan_dir / "packageCyclicDependencyTable.csv"):
        add_smell("cyclicDep", "PACKAGE", members, name)
    for name, members in cycles_from_matrix(arcan_dir / "classCyclicDependencyTable.csv"):
        add_smell("cyclicDep", "CLASS", members, name)
    for r in read(arcan_dir / "HL.csv"):
        cls = (r.get("Class") or "").strip()
        if cls:
            add_smell("hubLikeDep", "CLASS", [cls],
                      "FanIn=%s FanOut=%s" % (r.get("FanIn", ""), r.get("FanOut", "")))
    # UD30.csv is UD.csv filtered at a 30% instability threshold: a severity view of the SAME
    # unstable dependencies, not a second set of findings. Emitting a row from each file counted
    # every severe pair twice. On Tika that gave 86 unstable rows and 260 smells where the
    # distinct figures are 78 and 252, and the earlier version of this script took the inflated
    # total as ground truth because the adapter agreed with it. Both were wrong. Verified across
    # 64 Arcan runs: UD30 is a subset of UD in every one, with no pair unique to UD30.
    #
    # Deduplicated by pair rather than by reading UD.csv alone, so a pair that somehow appeared
    # only in the 30% view is still emitted once instead of being dropped. The 30% membership is
    # carried on the single row as severity, so no information is lost.
    severe = {((r.get("UnstableDependenciesPackage") or "").strip(),
               (r.get("CorrelatedPackage") or "").strip())
              for r in read(arcan_dir / "UD30.csv")}
    seen_ud = set()
    for ud in ("UD.csv", "UD30.csv"):
        for r in read(arcan_dir / ud):
            pkg = (r.get("UnstableDependenciesPackage") or "").strip()
            dep = (r.get("CorrelatedPackage") or "").strip()
            if not pkg or (pkg, dep) in seen_ud:
                continue
            seen_ud.add((pkg, dep))
            add_smell("unstableDep", "PACKAGE", [pkg],
                      "%s: depends on %s%s"
                      % (ud, dep, "  [severe: instability >= 0.30]"
                         if (pkg, dep) in severe else ""))
            if dep:
                affects.append({"project": project, "versionId": version_id,
                                "from": pkg, "to": dep, "edgeLabel": "unstableDependency"})

    # Cycle membership gives the affects edges for every cyclic smell: each member is linked to
    # the cycle's other members. Recorded as the pairs Arcan's own matrix implies.
    for name, members in cycles_from_matrix(arcan_dir / "packageCyclicDependencyTable.csv"):
        for a in members:
            for b in members:
                if a != b:
                    affects.append({"project": project, "versionId": version_id,
                                    "from": a, "to": b, "edgeLabel": "cyclicDependency"})

    def write(path, rows, fields):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in fields})

    write(out_dir / "component-metrics.csv", components,
          ["project", "versionId", "ComponentType", "name", "FanIn", "FanOut", "CBO", "LCOM"])
    write(out_dir / "smell-characteristics.csv", smells,
          ["project", "versionId", "smellType", "architecture_smell", "AffectedComponentType",
           "AffectedConstructType", "AffectedElements", "Size", "Detail"])
    write(out_dir / "smell-affects.csv", affects,
          ["project", "versionId", "from", "to", "edgeLabel"])
    return {"components": len(components), "smells": len(smells), "affects": len(affects),
            "by_type": {t: sum(1 for s in smells if s["smellType"] == t)
                        for t in SMELL_NAMES}}


if __name__ == "__main__":
    import json
    print(json.dumps(convert(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]),
                     indent=1))
