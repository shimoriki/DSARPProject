"""Baseline facts + fidelity of the regex parser used by generate_recipes.py."""
import ast, csv, importlib.util, json, re, sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
repo, l4j = root / "dsarp-or", root / "l4j"
csv.field_size_limit(10**9)
rows = list(csv.DictReader((repo / "baseline_csv/smell-characteristics.csv").open(encoding="utf-8-sig")))
print("smell rows", len(rows), Counter(r["project"] for r in rows), Counter(r["versionId"][:10] for r in rows))
print(Counter((r["smellType"], r["AffectedConstructType"]) for r in rows))
print("columns", list(rows[0].keys()))
sizes = [int(r["Size"]) for r in rows if r["smellType"] == "cyclicDep" and r["AffectedConstructType"] == "PACKAGE"]
print("pkg cycle sizes", len(sizes), "min/med/max", min(sizes), sorted(sizes)[len(sizes)//2], max(sizes), Counter(sizes).most_common(6))
print("shapes", Counter(r["Shape"] for r in rows if r["smellType"] == "cyclicDep"))
aff = list(csv.reader((repo / "baseline_csv/smell-affects.csv").open(encoding="utf-8-sig")))
print("affects head", aff[0], aff[1], "edge labels", Counter(r[5] for r in aff[1:]).most_common(5))
cm = list(csv.DictReader((repo / "baseline_csv/component-metrics.csv").open(encoding="utf-8-sig")))
print("component metrics", len(cm), Counter(r["ComponentType"] for r in cm), list(cm[0].keys())[:30])

spec = importlib.util.spec_from_file_location("gr", repo / "openrewrite/generate_recipes.py")
gr = importlib.util.module_from_spec(spec); sys.modules["gr"] = gr; spec.loader.exec_module(gr)
types, packages = gr.parse_repository(l4j)
files = list(gr.java_files(l4j))
print("java files", len(files), "types parsed", len(types), "packages", len(packages))
mismatch = [t for t in types.values() if Path(t.path).stem != t.simple_name and Path(t.path).stem not in ("package-info", "module-info")]
print("primary-type name != filename", len(mismatch), [(t.simple_name, Path(t.path).name) for t in mismatch[:12]])
print("not public (excl mismatch)", sum(1 for t in types.values() if not t.is_public and t not in mismatch))
fqn = Counter()
for p in files:
    match = gr.PACKAGE_RE.search(p.read_text("utf-8", "replace"))
    if match:
        fqn[match.group(1) + "." + p.stem] += 1
print("duplicate FQN across modules", sum(1 for c in fqn.values() if c > 1), [k for k, c in fqn.items() if c > 1][:6])
wild = fq = nested = 0
for p in files:
    t = p.read_text("utf-8", "replace")
    wild += len(re.findall(r"^\s*import\s+(?:static\s+)?[\w.]+\.\*;", t, re.M))
    nested += len(re.findall(r"^\s+(?:public |protected |private |static |final |abstract )*(?:class|interface|enum|record)\s+\w+", t, re.M))
    body = re.sub(r"^\s*(?:import|package)\s.*$", "", t, flags=re.M)
    body = re.sub(r"/\*.*?\*/|//.*?$", "", body, flags=re.S | re.M)
    fq += len(re.findall(r"\borg\.apache\.logging\.[a-z.]+\.[A-Z]\w+", body))
print("wildcard imports", wild, "nested type decls", nested, "FQN refs outside imports", fq)

# reproduce generator: every smell row, Move Class first (matches the documented model collapse)
out = root / "analysis/pred.csv"
with out.open("w", newline="", encoding="utf-8") as h:
    w = csv.DictWriter(h, ["architecture_smell", "affected_elements", "suggestions"]); w.writeheader()
    for r in rows:
        el = re.findall(r"[\w.$]+", r["AffectedElements"])
        w.writerow({"architecture_smell": r["smellType"], "affected_elements": "|".join(el), "suggestions": "Move Class (0.9)"})
from argparse import Namespace
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    gr.generate(Namespace(repository=l4j, predictions=out, output_dir=root / "analysis/gen",
                          smell_column="architecture_smell", elements_column="affected_elements",
                          suggestions_column="suggestions", elements_separator="|"))
m = json.loads((root / "analysis/gen/manifest.json").read_text())
print("generator status", m["status_counts"], "records", m["record_count"])
print("reasons", Counter(re.sub(r":.*", "", r["reason"])[:60] for r in m["records"] if r["status"] != "ready_for_dry_run").most_common(8))
print("risk", Counter(r["risk_level"] for r in m["records"] if r["status"] == "ready_for_dry_run"))
print("smells of ready", Counter(r["architecture_smell"] for r in m["records"] if r["status"] == "ready_for_dry_run"))
