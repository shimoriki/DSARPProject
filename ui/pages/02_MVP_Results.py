"""MVP scope and measured results — what works, what doesn't, and why the numbers hold."""
import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("📊 MVP results")
st.caption("What DSARP can refactor today, what it deliberately will not, and the measured "
           "outcome on every repository analysed.")

# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #
st.subheader("Scope")
IN_SCOPE = [
    ("Cyclic Dependency", "Merge Package", "ChangePackage (stock)"),
    ("Unstable Dependency", "Move Class", "ChangeType (stock)"),
    ("God Component", "Split Package", "ChangeType (stock)"),
    ("Deficient Encapsulation", "Encapsulate Field", "ReduceFieldVisibility (DSARP)"),
    ("Missing / Wide Hierarchy", "Introduce Supertype", "IntroduceSupertype (DSARP)"),
    ("Rebellious Hierarchy", "Extract Interface", "ExtractInterfaceForClass (DSARP)"),
    ("Unutilized Abstraction", "Remove Dead Code", "DeleteSourceFiles (stock, zero-ref only)"),
    ("Insufficient Modularization / Multifaceted Abstraction", "Extract Class",
     "ExtractStaticHelpers (DSARP, LST)"),
]
st.dataframe([{"smell": s, "refactoring": r, "recipe": c} for s, r, c in IN_SCOPE],
             use_container_width=True, hide_index=True)

with st.expander("Deliberately out of scope — and the reason for each"):
    st.dataframe([
        {"smell": "Broken Modularization",
         "why not": "needs move-method with real type attribution; the index is regex-based"},
        {"smell": "Broken Hierarchy",
         "why not": "replacing inheritance with delegation rewrites the public API and every "
                    "call site"},
        {"smell": "Dense Structure",
         "why not": "a property of the whole system; no local refactoring reduces it"},
    ], use_container_width=True, hide_index=True)
    st.caption("These are reported as `requires_source_inspection`, never silently dropped. "
               "Closing them means rebuilding the source index on OpenRewrite's LST — a "
               "rewrite, not an increment.")

# --------------------------------------------------------------------------- #
# How to read the numbers
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("How to read the numbers")
st.info("**Judge a run on the smell types it targeted, not the grand total.** Splitting a God "
        "Component creates a new package, which Designite then reports as Feature "
        "Concentration. A refactoring that removed exactly what it aimed at can therefore make "
        "the overall count look worse. Targeted deltas and side effects are reported "
        "separately.")

# --------------------------------------------------------------------------- #
# Measured results across every analysed repo
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Measured results")
out = data_dir() / "outputs"
rows = []
if out.exists():
    for p in sorted(out.iterdir()):
        r = read_json(p / "openrewrite_loop_report.json")
        if not r:
            continue
        plans = r.get("plans") or []
        types = sorted({x["smell_type"] for x in plans if x.get("applicable")})
        rows.append({
            "repository": p.name,
            "verification": r.get("verification_status", "—"),
            "build after": r.get("build_after_refactoring", "—"),
            "smell types refactored": len(types),
            "files rewritten": len(r.get("changed_files") or []),
            "targeted": ", ".join(types) or "—",
        })
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.warning("No analysed repositories yet.")
    st.code("py -m dsarp.cli refactor-openrewrite --repo apache-commons-validator "
            "--detector both", language="bash")

# --------------------------------------------------------------------------- #
# The verification gate
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("First verified smell reduction")
st.success("**commons-validator — both tools, compiling build.** "
           "Arcan 20 → 13 (−7), Designite 91 → 86 (−5). "
           "Unstable Dependency −7, Cyclic Dependency −4, God Component −1, "
           "Scattered Functionality −1.")
st.markdown("""
Designite's own total **fell**. Every earlier strategy made it rise, because splits created
packages it then flagged as Feature Concentration.

What unblocked it was an **ordering rule**, not a new refactoring. An extracted helper stays in
its origin package and keeps referring to that package's types; a God Component split in the
same pass was relocating those types out from under it. Extract Class now claims its whole
package first. The result is fewer, non-conflicting plans — 28 files changed instead of 50 —
and a real reduction rather than churn.
""")

st.divider()
st.subheader("The verification gate — why these numbers can be trusted")
st.markdown("""
Three times during development a change *looked* like a large improvement and was actually a
**measurement failure**. Each was caught, and each is now a permanent guard.

| what it claimed | what was really happening | the guard now |
|---|---|---|
| Arcan `20 → 0`, "all cycles removed" | the refactored code never compiled, so there was no bytecode for Arcan to read | no bytecode ⇒ `UNMEASURABLE`, run marked `unverified_build_broken`; only tools that measured **both** sides may claim a delta |
| iterative loop, "13.2% reduction" | the build broke, Arcan dropped out, and the score was recomputed over fewer tools | accepting a pass requires `build_after_refactoring == "compiled"`, not just `verified` |
| an LLM proposed deleting a class | its own reasoning said the class was still referenced | closed loop returned `verdict: rejected` — the code did not compile; a pre-check now refuses it before running |

This is the core contribution: **a measurement failure is never scored as success.**
""")

# --------------------------------------------------------------------------- #
# AI-proposed recipes
# --------------------------------------------------------------------------- #
trials = None
if out.exists():
    for p in sorted(out.iterdir()):
        t = read_json(p / "ai_recipe_trials.json")
        if t:
            trials = t
            break
if trials:
    st.divider()
    st.subheader("AI-proposed recipes")
    c = st.columns(4)
    c[0].metric("Model", str(trials.get("model", "—")).split(":")[-1])
    c[1].metric("Smells asked", trials.get("smells_asked"))
    c[2].metric("Valid proposals", trials.get("proposals_valid"))
    c[3].metric("Declined", trials.get("proposals_declined", 0))
    st.caption("A local 3B model declines more often than it proposes usefully — the safe "
               "failure mode, but not a useful one. The harness is model-agnostic "
               "(`--model`, `--provider`, `--base-url`), so the open question is whether "
               "capability rather than scaffolding is the limit.")
    if trials.get("verdicts"):
        st.write("**Verdicts from executed proposals:**", trials["verdicts"])
