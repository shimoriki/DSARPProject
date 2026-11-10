"""Bytecode graph (jdeps) vs regex graph; simulate Move Class on the package graph."""
import json, re, statistics, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

root, jdeps = Path(sys.argv[1]), sys.argv[2]
l4j = root / "l4j"
dirs = sorted(p for p in l4j.glob("*/target/classes") if any(p.rglob("*.class")))
LINE = re.compile(r"^\s+(\S+)\s+->\s+(\S+)")
PROJECT = re.compile(r"^org\.apache\.(logging\.|log4j)")


def top(name):
    return name.split("$")[0]


def pkg(name):
    return name.rsplit(".", 1)[0]


class_edges, module_of = Counter(), {}
for d in dirs:
    module = d.parts[-3]
    out = subprocess.run([jdeps, "-v", "-cp", ";".join(str(x) for x in dirs), str(d)],
                         capture_output=True, text=True, errors="replace").stdout
    for line in out.splitlines():
        m = LINE.match(line)
        if m and PROJECT.match(m.group(1)):
            a, b = top(m.group(1)), top(m.group(2))
            module_of.setdefault(a, module)
            if PROJECT.match(b) and a != b:
                class_edges[(a, b)] += 1
classes = {c for e in class_edges for c in e}
print("modules", len(dirs), "classes", len(classes), "class edges", len(class_edges))


def package_graph(owner):
    g = defaultdict(Counter)
    for (a, b), n in class_edges.items():
        pa, pb = owner.get(a, pkg(a)), owner.get(b, pkg(b))
        if pa != pb:
            g[pa][pb] += 1
    return g


def sccs(g):
    nodes = set(g) | {v for vs in g.values() for v in vs}
    index, low, on, stack, out, n = {}, {}, set(), [], [], 0
    for start in nodes:
        if start in index:
            continue
        work = [(start, iter(g.get(start, ())))]
        index[start] = low[start] = n; n += 1; stack.append(start); on.add(start)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = n; n += 1; stack.append(w); on.add(w)
                    work.append((w, iter(g.get(w, ()))))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    c = set()
                    while True:
                        w = stack.pop(); on.discard(w); c.add(w)
                        if w == v:
                            break
                    if len(c) > 1:
                        out.append(c)
    return out


def summary(g):
    comps = sccs(g)
    inside = sum(1 for a in g for b in g[a] for c in comps if a in c and b in c)
    pairs = {tuple(sorted((a, b))) for a in g for b in g[a] if a in g.get(b, {})}
    return {"sccs": len(comps), "cyclic_pkgs": sum(map(len, comps)), "largest": max(map(len, comps), default=0),
            "edges_in_sccs": inside, "reciprocal_pairs": len(pairs), "pkg_edges": sum(len(v) for v in g.values())}


base = package_graph({})
b = summary(base)
print("baseline bytecode", b, "packages", len(set(base) | {v for x in base.values() for v in x}))
comps = sccs(base)
print("scc sizes", sorted(map(len, comps), reverse=True))

# regex graph, same packages
sys.path.insert(0, str(root / "dsarp-or"))
spec_path = root / "dsarp-or/openrewrite/generate_recipes.py"
import importlib.util
s = importlib.util.spec_from_file_location("gr", spec_path); gr = importlib.util.module_from_spec(s); sys.modules["gr"] = gr; s.loader.exec_module(gr)
types, _ = gr.parse_repository(l4j)
prod = {t.qualified_name: t for t in types.values() if t.source_set == "main"}
regex = defaultdict(set)
for t in prod.values():
    for i in t.imports:
        target = gr.imported_type(i, types)
        if target and target.source_set == "main" and target.package != t.package:
            regex[t.package].add(target.package)
scope = {p for p in set(base) | {v for x in base.values() for v in x}}
be = {(a, x) for a in base for x in base[a]}
re_e = {(a, x) for a in regex for x in regex[a] if a in scope and x in scope}
print("pkg edges bytecode", len(be), "regex", len(re_e), "both", len(be & re_e), "bytecode-only", len(be - re_e), "regex-only", len(re_e - be))
print("bytecode-only sample", sorted(be - re_e)[:6])

# reciprocal pairs: thin back edges
wt = []
for a in base:
    for x in base[a]:
        if a < x and a in base.get(x, {}):
            wt.append(min(base[a][x], base[x][a]))
print("reciprocal pairs", len(wt), "lighter-direction class edges: =1", sum(w == 1 for w in wt), "<=2", sum(w <= 2 for w in wt),
      "<=5", sum(w <= 5 for w in wt), "median", statistics.median(wt))


def simulate(t, dest, before=b):
    g = package_graph({t: dest})
    return summary(g), g


# the generator's candidates
m = json.loads((root / "analysis/gen/manifest.json").read_text())
ready = [r for r in m["records"] if r["status"] == "ready_for_dry_run"]
res = Counter(); detail = []
for r in ready:
    t, src, dst = r["source_type"], r["source_package"], r["destination_package"]
    if t not in classes:
        res["not_in_compiled_scope"] += 1; continue
    a, g = simulate(t, dst)
    res["simulated"] += 1
    back_gone = src not in g.get(dst, {})     # destination no longer depends on source
    fwd_gone = dst not in g.get(src, {})
    res["reciprocal_pair_broken"] += int(back_gone or fwd_gone)
    res["scc_edges_reduced"] += int(a["edges_in_sccs"] < b["edges_in_sccs"])
    res["scc_edges_increased"] += int(a["edges_in_sccs"] > b["edges_in_sccs"])
    res["reciprocal_decreased"] += int(a["reciprocal_pairs"] < b["reciprocal_pairs"])
    res["reciprocal_increased"] += int(a["reciprocal_pairs"] > b["reciprocal_pairs"])
    res["cyclic_pkgs_reduced"] += int(a["cyclic_pkgs"] < b["cyclic_pkgs"])
    detail.append((a["reciprocal_pairs"] - b["reciprocal_pairs"], a["edges_in_sccs"] - b["edges_in_sccs"], t, dst))
print("generator candidates", dict(res))
print("best", sorted(detail)[:5]); print("worst", sorted(detail)[-5:])
fs = "org.apache.logging.log4j.core.appender.rolling.FileSize"
print("FileSize sim", simulate(fs, fs.rsplit(".", 1)[0] + ".action")[0], "vs", b)
rolling, action = pkg(fs), pkg(fs) + ".action"
print("rolling->action", base[rolling][action], "action->rolling", base[action][rolling],
      [e for e in class_edges if pkg(e[0]) == action and pkg(e[1]) == rolling][:10])

# causal search: exhaustive single Move Class over classes in SCCs, destinations = packages it already touches
incident = defaultdict(set)
for (x, y) in class_edges:
    incident[x].add(pkg(y)); incident[y].add(pkg(x))
cand = [(c, d) for c in classes for d in incident[c] if d != pkg(c) and any(pkg(c) in comp and d in comp for comp in comps)]
print("exhaustive single moves", len(cand))
good = []
for c, d in cand:
    if module_of.get(c) not in {module_of.get(o) for o in classes if pkg(o) == d}:
        continue                               # same-module only, as a build-safe filter
    a, _ = simulate(c, d)
    good.append((a["reciprocal_pairs"] - b["reciprocal_pairs"], a["edges_in_sccs"] - b["edges_in_sccs"], a["cyclic_pkgs"] - b["cyclic_pkgs"], c, d))
good.sort()
print("same-module moves simulated", len(good), "reduce reciprocal", sum(g[0] < 0 for g in good),
      "reduce scc edges", sum(g[1] < 0 for g in good), "shrink cyclic pkgs", sum(g[2] < 0 for g in good),
      "both better, none worse", sum(g[0] < 0 and g[1] < 0 and g[2] <= 0 for g in good))
print("top", good[:8])

def rec_pairs(g):
    return {tuple(sorted((a, x))) for a in g for x in g[a] if a in g.get(x, {})}
base_pairs = rec_pairs(base)
clean = set(); any_move = set()
top_moves = [(r, e, cp, c, d) for r, e, cp, c, d in good if r < 0 or e < 0]
for r, e, cp, c, d in top_moves:
    now = rec_pairs(package_graph({c: d}))
    gone, new = base_pairs - now, now - base_pairs
    any_move |= gone
    if not new:
        clean |= gone
print("pairs removable by one move", len(any_move), "with no new reciprocal pair", len(clean), "of", len(base_pairs))

# greedy sequence: objective = reciprocal pairs, then SCC edges; moves restricted to already-improving shortlist each step
owner = {}; current = summary(package_graph(owner)); trace = [current]
for step in range(12):
    best = None
    inc = defaultdict(set)
    for (x, y) in class_edges:
        inc[x].add(owner.get(y, pkg(y))); inc[y].add(owner.get(x, pkg(x)))
    cc = sccs(package_graph(owner))
    shortlist = [(c, d) for c in classes for d in inc[c] if d != owner.get(c, pkg(c)) and c not in owner
                 and any(owner.get(c, pkg(c)) in k and d in k for k in cc)]
    import random
    random.seed(step); random.shuffle(shortlist)
    for c, d in shortlist[:500]:
        a = summary(package_graph({**owner, c: d}))
        key = (a["reciprocal_pairs"], a["edges_in_sccs"], a["cyclic_pkgs"])
        if best is None or key < best[0]:
            best = (key, c, d, a)
    if not best or best[0] >= (current["reciprocal_pairs"], current["edges_in_sccs"], current["cyclic_pkgs"]):
        break
    owner[best[1]] = best[2]; current = best[3]; trace.append(current)
    print("step", step + 1, best[1].rsplit(".", 1)[1], "->", best[2].replace("org.apache.", ""), current)
