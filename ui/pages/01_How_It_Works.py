"""What the system does, which parts are real tool measurements, and what the limits are."""
import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("📘 How DSARP works")
st.caption("Read this first — it says exactly which numbers come from real tool runs and which "
           "steps are estimates, so nothing on the other pages is over-claimed.")

# --------------------------------------------------------------------------- #
# Tool availability on THIS machine
# --------------------------------------------------------------------------- #
st.subheader("Tools available on this machine")
from dsarp.verification.openrewrite_loop import available_detectors
from dsarp.openrewrite.runner import find_mvn
from dsarp.tools.arcan_runner import arcan_home

avail = available_detectors()
mvn = find_mvn()
rows = [
    {"tool": "Arcan 1.2.1", "role": "architectural smells (package cycles, unstable, hub-like)",
     "status": "✅ runnable" if avail["arcan"] else "❌ needs the FULL distribution (jar + lib/)",
     "path": str(arcan_home() or "—")},
    {"tool": "DesigniteJava", "role": "class-level design smells",
     "status": "✅ runnable" if avail["designite"] else "❌ put DesigniteJava.jar in tools/",
     "path": "tools/DesigniteJava.jar" if avail["designite"] else "—"},
    {"tool": "Maven + OpenRewrite", "role": "performs the actual source refactoring",
     "status": "✅ runnable" if mvn else "❌ not found", "path": mvn or "—"},
]
st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Custom OpenRewrite recipes")
from dsarp.openrewrite.runner import CUSTOM_RECIPE_GAV, CUSTOM_RECIPES, custom_recipes_installed

installed = custom_recipes_installed()
st.write(f"`{CUSTOM_RECIPE_GAV}` — " +
         ("✅ built and installed" if installed else "❌ not built"))
st.markdown("""
Stock `rewrite-java` ships some transformations only as **visitors**
(`ExtractInterface.CreateInterface`, `GenerateGetterAndSetterVisitor`), which cannot be named
from a declarative `rewrite.yml` — and it has **no field-visibility recipe at all**. DSARP's own
module closes that gap:

| recipe | fixes | why custom |
|---|---|---|
| `ReduceFieldVisibility` | Deficient Encapsulation | no stock `ChangeFieldAccessLevel` exists |
| `ExtractInterfaceForClass` | Rebellious Hierarchy, dependency inversion | wraps a stock visitor as a nameable Recipe; synthesises a **new type**, which relocation cannot |
""")
if not installed:
    st.code("mvn -f tools/dsarp-recipes/pom.xml install", language="bash")
else:
    st.caption("Passed to Maven as `-Drewrite.recipeArtifactCoordinates=" +
               CUSTOM_RECIPE_GAV + "`, so generated recipes can mix custom and stock entries.")

st.divider()
st.subheader("The closed loop")
st.markdown("""
```
 1. DETECT      Arcan (needs `mvn compile` first — it reads bytecode)
                + DesigniteJava (reads source)
 2. PLAN        turn the detected cycles into a concrete, compile-safe transformation
 3. REFACTOR    OpenRewrite `mvn rewrite:run` rewrites the REAL source on a copy
 4. RE-DETECT   run the SAME tools again on the refactored code
 5. COMPARE     per-tool, per-smell-type delta
```
""")

st.info("**The whole point of step 4** is that the after-state is *measured*, not predicted. "
        "A suggestion only counts as effective if a real tool re-run says the smell is gone.")

st.divider()
st.subheader("Two refactoring strategies, and why the default is what it is")
st.markdown("""
| strategy | OpenRewrite recipe | what it does | trade-off |
|---|---|---|---|
| `merge_package` *(default)* | `ChangePackage` | relocates an **entire** package | compile-safe: every class moves together, so intra-package references still resolve |
| `move_classes` | `ChangeType` | relocates **individual** classes | smaller diff, but a moved class loses its implicit same-package references and the build often breaks |

`merge_package` also applies two hard guards before proposing anything:

* **simple-name collision** — Java forbids two types of the same name in one package. In
  commons-validator, `validator.ISBNValidator` and `validator.routines.ISBNValidator` both
  exist, so merging those two packages is rejected outright.
* **sub-package conflict** — `ChangePackage` rewrites the whole package prefix, so merging a
  package that has descendants would dangle every reference to them.
""")

st.divider()
st.subheader("Honesty rules enforced in code")
st.markdown("""
* **A failed build is never a clean bill of health.** Arcan reads compiled bytecode; if the
  refactored code does not compile there are no `.class` files and Arcan reports nothing.
  That is recorded as `UNMEASURABLE`, and `verification_status` becomes
  `unverified_build_broken` — it is *not* counted as "all smells removed".
* **Only tools that measured both sides may claim a delta.** Per-tool before/after counts are
  kept separate so one tool's failure cannot inflate the other's result.
* Every step stores the real command it ran and its exit status.
""")

# --------------------------------------------------------------------------- #
# Latest measured result
# --------------------------------------------------------------------------- #
out = data_dir() / "outputs"
runs = sorted([p.name for p in out.iterdir()
               if p.is_dir() and (p / "openrewrite_loop_report.json").exists()]) if out.exists() else []
if runs:
    st.divider()
    st.subheader("Latest verified runs")
    rows = []
    for name in runs:
        r = read_json(out / name / "openrewrite_loop_report.json", default={}) or {}
        rows.append({
            "repo": name,
            "verification": r.get("verification_status", "—"),
            "build after": r.get("build_after_refactoring", "—"),
            "smells before": r.get("smells_before"),
            "smells after": r.get("smells_after") if r.get("verification_status") == "verified"
            else "unmeasured",
            "files rewritten": len(r.get("changed_files") or []),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.page_link("pages/22_Real_Tool_Loop.py", label="Open the full loop report →")

st.divider()
st.subheader("Run it on any repository")
st.code("py -m dsarp.cli refactor-openrewrite --repo-url https://github.com/apache/commons-codec "
        "--detector both --strategy merge_package", language="bash")
st.caption("…or paste a git URL into the **Analyze Repo** page.")
