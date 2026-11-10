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



import itertools
def comps_of(owner):
    return sccs(package_graph(owner))
base_comps = sorted(comps, key=len)
print("SCCs", [(len(c), sorted(c)[:3]) for c in base_comps])
for comp in base_comps:
    if len(comp) > 15:
        continue
    ms = sorted({c for c in classes if pkg(c) in comp})
    inc = defaultdict(set)
    for (x, y) in class_edges:
        inc[x].add(pkg(y)); inc[y].add(pkg(x))
    moves = [(c, d) for c in ms for d in inc[c] & comp if d != pkg(c)]
    def remaining(owner):
        """Packages of this SCC still in any SCC."""
        return sum(len(k & comp) for k in comps_of(owner))
    def others(owner):
        return sum(len(k - comp) for k in comps_of(owner))
    base_o = others({})
    best = []
    for c, d in moves:
        best.append((remaining({c: d}), others({c: d}) - base_o, c, d))
    best.sort()
    print("SCC size", len(comp), "classes", len(ms), "moves", len(moves), "best single", [(r, o, c.rsplit(".", 1)[1], d.replace("org.apache.", "")) for r, o, c, d in best[:3]])
    owner = {}; path = []
    for step in range(8):
        now = remaining(owner)
        if now == 0: break
        cand = []
        for c, d in moves:
            if c in owner: continue
            o = {**owner, c: d}
            cand.append((remaining(o), others(o) - base_o, c, d))
        cand.sort()
        if not cand or cand[0][0] >= now: break
        owner[cand[0][2]] = cand[0][3]; path.append(cand[0][2].rsplit(".", 1)[1])
    print("   greedy", len(owner), "moves ->", remaining(owner), "of", len(comp), "left; new outside pkgs in cycles", others(owner) - base_o, path)
    edges_inside = sorted(((base[a][b], a.replace("org.apache.", ""), b.replace("org.apache.", "")) for a in comp for b in base.get(a, {}) if b in comp))
    print("   lightest edges", edges_inside[:4], "total", len(edges_inside))
