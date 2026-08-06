"""Real closed loop: Arcan + Designite -> OpenRewrite -> re-detect.

Shows the measured smell counts BEFORE and AFTER OpenRewrite actually rewrote the source,
per tool and per smell type. Everything on this page comes from a real tool run recorded in
data/outputs/<repo>/openrewrite_loop_report.json — nothing is simulated.
"""
import re

import streamlit as st
from _common import cfg, data_dir, default_index
from dsarp.util import read_json

st.title("🔁 Real tool loop — Arcan + Designite → OpenRewrite → re-detect")
st.caption("The closed loop with REAL tools on both ends: detect architectural smells, generate "
           "OpenRewrite recipes, run `mvn rewrite:run` to actually rewrite the source, then run the "
           "SAME tools again on the refactored code and compare.")

out = data_dir() / "outputs"
projects = sorted([p.name for p in out.iterdir()
                   if p.is_dir() and (p / "openrewrite_loop_report.json").exists()]) \
    if out.exists() else []

if not projects:
    st.info("No real tool loop has been run yet.\n\n"
            "```\npy -m dsarp.cli refactor-openrewrite --repo apache-commons-validator --detector both\n"
            "```\n\nOr analyse any repository by git URL:\n\n"
            "```\npy -m dsarp.cli refactor-openrewrite --repo-url https://github.com/apache/commons-text --detector both\n```")
    st.stop()

def _base(name: str) -> str:
    """Strip the pass and run labels so every pass of one repository groups together."""
    return re.split(r"__(pass\d+|bysmell\d*)", name)[0]


def _gain(dir_name: str):
    """(smells removed, report) for a pass, or None when it cannot be judged.

    A pass whose build broke is not a candidate however good its numbers look — that is the
    same rule the loop itself applies before accepting anything.
    """
    r = read_json(out / dir_name / "openrewrite_loop_report.json", default=None)
    if not r or r.get("build_after_refactoring") != "compiled":
        return None
    b, a = r.get("smells_before"), r.get("smells_after")
    if b is None or a is None:
        return None
    return (b - a, r)


# One row per repository, not per pass. 166 raw reports is mostly noise: what matters is the
# best VERIFIED pass and how far it moved the baseline.
groups = {}
for d in projects:
    groups.setdefault(_base(d), []).append(d)

sel_base = st.selectbox("Project", sorted(groups),
                        index=default_index(sorted(groups)))
candidates = [(g[0], g[1], d) for d in groups[sel_base] if (g := _gain(d))]
if candidates:
    removed, rep, sel = max(candidates, key=lambda t: t[0])
    st.success(f"Showing the best VERIFIED pass of {len(groups[sel_base])} recorded for this "
               f"repository — `{sel}` — which removed **{removed}** smells "
               f"({rep.get('smells_before')} → {rep.get('smells_after')}). Passes that did not "
               "compile are excluded, since the loop would not accept them either.")
else:
    sel = sorted(groups[sel_base])[0]
    rep = read_json(out / sel / "openrewrite_loop_report.json", default=None)
    st.warning(f"No pass of this repository both compiled and produced a measured "
               f"before/after pair. Showing `{sel}` so the attempt is still inspectable.")
if not rep:
    st.error("Report could not be read.")
    st.stop()

st.subheader(f"Detector: {rep.get('tool', rep.get('detector', '—'))}")
st.caption(f"Refactoring strategy: `{rep.get('strategy', 'class')}` "
           f"({'ChangePackage — whole packages relocated' if rep.get('strategy') == 'package' else 'ChangeType — individual classes relocated'})")

# --------------------------------------------------------------------------- #
# Verification gate — a broken build means the after-state is UNMEASURED, not clean
# --------------------------------------------------------------------------- #
if rep.get("verification_status") == "unverified_build_broken":
    st.error(
        f"**Unverified — the refactored code did not build** "
        f"(`{rep.get('build_after_refactoring')}`).\n\n"
        "Arcan reads compiled bytecode, so with no classes it reports nothing. That is "
        "**not** evidence the smells were removed, and it is deliberately not counted as such.")
elif rep.get("verification_status") == "not_applicable_no_safe_refactoring":
    d = rep.get("diagnosis") or {}
    st.warning(f"**No compile-safe refactoring applies to this repository.**\n\n{d.get('note','')}")
    c = st.columns(3)
    c[0].metric("Cyclic smells found", d.get("cyclic_findings", 0))
    c[1].metric("Cross-package cycles", d.get("cross_package_cycles", 0))
    c[2].metric("Intra-package cycles", d.get("intra_package_cycles", 0))
    if d.get("blocked_merges"):
        st.caption("Merges the safety guards rejected:")
        st.dataframe([{"rejected merge": b} for b in d["blocked_merges"]],
                     use_container_width=True, hide_index=True)
    st.info("This is a real finding, not a failure: the detector found smells that this "
            "refactoring family provably cannot fix, so the system reports "
            "`requires_source_inspection` instead of applying a change that would not help.")

# --------------------------------------------------------------------------- #
# Headline: before -> after
# --------------------------------------------------------------------------- #
before, after = rep.get("smells_before"), rep.get("smells_after")
if before is not None and after is not None:
    removed = before - after
    c = st.columns(4)
    c[0].metric("Smells before", before)
    c[1].metric("Smells after", after, delta=-removed if removed else 0,
                delta_color="inverse")
    c[2].metric("Removed", removed)
    c[3].metric("Files rewritten", len(rep.get("changed_files") or []))
elif before is not None:
    c = st.columns(2)
    c[0].metric("Smells before", before)
    c[1].metric("Smells after", "unmeasured")

# per-tool split when both ran
per_tool = rep.get("per_tool") or {}
if per_tool:
    st.markdown("**Per tool** — each ran before *and* after the refactoring:")
    st.dataframe([{"tool": t,
                   "before": v.get("before"),
                   "after": v.get("after") if v.get("measured") else "unmeasurable",
                   "removed": v.get("removed") if v.get("measured") else "—",
                   "note": v.get("note") or ""} for t, v in per_tool.items()],
                 use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------- #
# Coverage: which smell types got a refactoring, which could not, and why
# --------------------------------------------------------------------------- #
plans = rep.get("plans") or []
if plans:
    st.divider()
    st.subheader("Smell-type coverage — what was refactored and what wasn't")
    by_smell = {}
    for p in plans:
        e = by_smell.setdefault(p["smell_type"], {"applicable": 0, "skipped": 0,
                                                  "refactoring": p.get("refactoring"),
                                                  "reason": "", "ops": 0})
        if p.get("applicable"):
            e["applicable"] += 1
            e["ops"] += p.get("operations", 0)
            e["refactoring"] = p.get("refactoring")
        else:
            e["skipped"] += 1
            e["reason"] = e["reason"] or p.get("reason", "")
    rows = [{"smell type": k,
             "status": "✅ refactored" if v["applicable"] else "⚠️ not automatable",
             "refactoring": v["refactoring"], "plans": v["applicable"] or v["skipped"],
             "recipe ops": v["ops"] or "—",
             "why not": "" if v["applicable"] else v["reason"]}
            for k, v in sorted(by_smell.items(),
                               key=lambda kv: (-kv[1]["applicable"], kv[0]))]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    done = sum(1 for v in by_smell.values() if v["applicable"])
    st.caption(f"{done} of {len(by_smell)} detected smell types had an automated, "
               "compile-safe refactoring. The rest state exactly what they would need — "
               "usually a NEW type (extract class/interface), which no stock OpenRewrite "
               "recipe can synthesise.")

# --------------------------------------------------------------------------- #
# Smell detection BEFORE vs AFTER, by type
# --------------------------------------------------------------------------- #
b_by = rep.get("by_type_before") or {}
a_by = rep.get("by_type_after") or {}
if b_by or a_by:
    st.divider()
    st.subheader("Smell detection before vs after OpenRewrite")
    types = sorted(set(b_by) | set(a_by))
    rows = []
    for t in types:
        b, a = b_by.get(t, 0), a_by.get(t, 0)
        rows.append({"smell type": t, "before": b, "after": a, "delta": a - b,
                     "result": "✅ reduced" if a < b else ("⚠️ increased" if a > b else "— unchanged")})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.bar_chart({"before": [b_by.get(t, 0) for t in types],
                  "after": [a_by.get(t, 0) for t in types]}, height=300)
    st.caption("Bars are indexed in the same order as the table above.")

# --------------------------------------------------------------------------- #
# What to do NEXT — suggestions re-planned against the refactored code
# --------------------------------------------------------------------------- #
nxt = rep.get("next_suggestions") or {}
if nxt:
    st.divider()
    st.subheader("🔮 Next suggestions — planned against the REFACTORED code")
    st.caption("Knowing what was removed is only half the answer. These are re-planned on the "
               "rewritten source, so they also reveal smells the refactoring itself introduced.")
    cov = nxt.get("coverage") or {}
    c = st.columns(3)
    c[0].metric("Actionable now", len(nxt.get("actionable") or []))
    c[1].metric("Smell types actionable", cov.get("smell_types_refactored", 0))
    c[2].metric("Need human inspection", len(nxt.get("requires_source_inspection") or []))

    if nxt.get("introduced_smell_types"):
        st.warning("**Introduced by this refactoring:** "
                   + ", ".join(nxt["introduced_smell_types"])
                   + " — splitting a package commonly creates a new one that the detector "
                     "then flags. Reported rather than hidden.")

    if nxt.get("actionable"):
        st.markdown("**Run the loop again to apply these**")
        st.dataframe([{"smell": p["smell_type"], "refactoring": p["refactoring"],
                       "components": ", ".join(p["components"][:2]),
                       "operations": p.get("operations"),
                       "why": p.get("reason", "")} for p in nxt["actionable"]],
                     use_container_width=True, hide_index=True)
        st.code("py -m dsarp.cli refactor-iterative --repo <name> --detector both",
                language="bash")
    else:
        st.success("No further automated refactoring applies to this code — the remaining "
                   "smells all need human design input.")

# --------------------------------------------------------------------------- #
# Step-by-step evidence
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Every step, with its real command status")
for s in rep.get("steps", []):
    name = s.get("step")
    icon = {"detect": "🔍", "plan_moves": "🧭", "plan_refactorings": "🧭", "openrewrite": "🛠️",
            "re-detect": "🔁", "compare": "📊", "next_suggestions": "🔮",
            "create_supertypes": "🏗️", "prepare_imports": "📦"}.get(name, "•")
    ok = s.get("status") in ("ok", "changed", "compiled")
    with st.expander(f"{icon} {name} — {s.get('tool','')} · `{s.get('status')}`", expanded=not ok):
        if name in ("detect", "re-detect"):
            st.write(f"**{s.get('smells')} smells** detected")
            if s.get("compile"):
                st.caption(f"Arcan needs bytecode — Maven compile: `{s.get('compile')}`")
            if s.get("by_tool"):
                st.json(s["by_tool"], expanded=False)
            elif s.get("by_type"):
                st.json(s["by_type"], expanded=False)
        elif name == "plan_refactorings":
            st.write(f"**{s.get('plans_applicable')} applicable refactoring plans** covering "
                     f"**{s.get('smell_types_actionable')} of {s.get('smell_types_detected')}** "
                     f"detected smell types → **{s.get('recipe_operations')}** recipe operations")
            plans = s.get("plans") or []
            app = [p for p in plans if p.get("applicable")]
            skip = [p for p in plans if not p.get("applicable")]
            if app:
                st.markdown("**Refactorings that will be executed**")
                st.dataframe([{"smell": p["smell_type"], "refactoring": p["refactoring"],
                               "operations": p.get("operations"),
                               "stock recipes": "✅" if p.get("stock_recipes") else "custom",
                               "why": p.get("reason", "")} for p in app],
                             use_container_width=True, hide_index=True)
            if skip:
                st.markdown("**Not automatable — with the evidence-based reason**")
                st.caption("These are reported, never silently dropped. Each says what would be "
                           "needed to fix it.")
                seen, rows = set(), []
                for p in skip:
                    if p["smell_type"] in seen:
                        continue
                    seen.add(p["smell_type"])
                    rows.append({"smell": p["smell_type"],
                                 "would need": p.get("refactoring"),
                                 "count": sum(1 for q in skip
                                              if q["smell_type"] == p["smell_type"]),
                                 "reason": p.get("reason", "")})
                st.dataframe(rows, use_container_width=True, hide_index=True)
        elif name == "plan_moves":
            st.write(f"**{s.get('count')} class moves** derived from `{s.get('derived_from')}`")
            for m in (s.get("moves") or [])[:20]:
                st.code(m, language="text")
        elif name == "openrewrite":
            st.write(f"**{s.get('changed_count', 0)} source files rewritten** by `mvn rewrite:run`")
            if s.get("note"):
                st.warning(s["note"])
            files = s.get("changed_files") or []
            if files:
                st.dataframe([{"changed file": f} for f in files],
                             use_container_width=True, hide_index=True, height=260)
            if s.get("recipe_path"):
                st.caption(f"Generated recipe: `{s['recipe_path']}`")
        elif name == "next_suggestions":
            st.write(f"**{s.get('actionable')} actionable suggestion(s)** for the refactored "
                     f"code across {s.get('smell_types_actionable')} smell type(s)")
            if s.get("top"):
                st.dataframe(s["top"], use_container_width=True, hide_index=True)
        elif name == "compare":
            st.write(f"**{s.get('removed')} smells removed** overall")
            if s.get("per_tool"):
                st.json(s["per_tool"], expanded=False)
            st.json(s.get("delta_by_type", {}), expanded=False)

# --------------------------------------------------------------------------- #
# Honest reading of the result
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("How to read this")
cyclic_pkg = [k for k in (rep.get("by_type_before") or {}) if "cyclic" in k.lower()]
delta = rep.get("delta_by_type") or {}
cyc_delta = sum(delta.get(k, 0) for k in cyclic_pkg)
if cyc_delta < 0:
    st.success(f"OpenRewrite's class relocations dissolved {abs(cyc_delta)} cyclic-dependency "
               "smell(s) — the package no longer depends back on the one it was tangled with.")
elif cyclic_pkg:
    st.warning(
        "Cyclic smells did **not** drop. `ChangeType` relocates a class but keeps its type "
        "references, so it dissolves a **package** cycle only when every crossing class moves. "
        "A class-level type cycle (Designite's *Cyclic-Dependent Modularization*) survives a "
        "package move — breaking it needs a dependency-inverting refactoring (extract an "
        "interface at the seam), which OpenRewrite has no stock recipe for.")
st.caption("Nothing here is simulated: the smell counts come from running the real tool binaries "
           "on the real source before and after `mvn rewrite:run`.")
