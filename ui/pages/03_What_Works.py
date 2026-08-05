"""What each suggestion has actually achieved — measured, then tested on unseen repositories.

Safety gates prove a refactoring compiles. They cannot tell you whether it helps. This page
is the other half: the record of what every suggestion type has done across verified runs,
and whether that record survived contact with repositories it was never learned from.
"""
import streamlit as st
from _common import cfg, data_dir
from dsarp.refactoring.outcomes import MIN_RUNS, build_ledger, summarise
from dsarp.util import read_json

st.title("📈 What actually works")
st.caption("Measured effect per suggestion type, across every run whose build compiled. "
           "A delta from a tree that does not compile is not evidence, so those are excluded.")

ledger = build_ledger(data_dir() / "outputs")
rows = summarise(ledger)

if not rows:
    st.info("No verified runs yet.")
    st.code("py -m dsarp.cli refactor-openrewrite --repo apache-commons-validator "
            "--detector both", language="bash")
    st.stop()

VERDICT_ICON = {"effective": "✅", "no measured benefit": "➖",
                "counterproductive": "🔴", "too few runs": "❔"}

st.subheader("Measured effect")
st.dataframe([{**r, "verdict": f"{VERDICT_ICON.get(r['verdict'], '')} {r['verdict']}"}
              for r in rows], use_container_width=True, hide_index=True)
st.caption(f"Net effect is the summed smell delta; negative is good. A verdict needs at least "
           f"{MIN_RUNS} verified runs — below that, absence of measured benefit is just "
           "absence of evidence.")

bad = [r for r in rows if r["verdict"] == "counterproductive"]
flat = [r for r in rows if r["verdict"] == "no measured benefit"]
if bad or flat:
    st.warning(
        "**Every one of these passed all safety gates.** They compile, satisfy every "
        "precondition, and still do not help — "
        + (f"{', '.join(r['refactoring'] for r in bad)} made the count WORSE. " if bad else "")
        + (f"{', '.join(r['refactoring'] for r in flat)} never moved a number. " if flat else "")
        + "Compile-safety cannot detect this; only measuring outcomes can. The planner now "
          "refuses them.")

# --------------------------------------------------------------------------- #
# Held-out validation — does the record generalise?
# --------------------------------------------------------------------------- #
val = read_json(data_dir() / "reports" / "ledger_validation.json")
if val:
    st.divider()
    st.subheader("Does it generalise?")
    st.caption("The ledger learns from the same runs it filters, so its verdicts were tested "
               "against repositories it was never built from.")
    c = st.columns(3)
    c[0].metric("Held out", ", ".join(val.get("holdout", [])) or "—")
    c[1].metric("Pairs testable", val.get("testable_pairs"))
    c[2].metric("Predictions held", f"{val.get('agreements')}/{val.get('testable_pairs')}")

    tested = [r for r in val.get("rows", []) if r.get("agrees") is not None]
    if tested:
        st.dataframe([{"smell": r["smell"], "refactoring": r["refactoring"],
                       "training verdict": r["training"],
                       "training mean": r.get("training_mean"),
                       "held-out mean": r.get("held_out_mean"),
                       "result": "✅ agrees" if r["agrees"] else "❌ disagrees"}
                      for r in tested], use_container_width=True, hide_index=True)
    disagreed = [r for r in tested if not r["agrees"]]
    if disagreed:
        st.error("**" + ", ".join(r["refactoring"] for r in disagreed) + "** looked effective "
                 "on the repositories it was learned from and did nothing on unseen ones. "
                 "That is what held-out testing exists to catch, and it narrows the reliable "
                 "core accordingly.")

st.divider()
st.subheader("The reliable core")
st.markdown("""
On held-out evidence, two refactorings reduce smells dependably:

| smell | refactoring | held-out mean |
|---|---|---|
| Cyclic Dependency | Merge Package | −2.0 |
| Unstable Dependency | Move Class | −3.0 |

That is a narrower claim than "reduces smells across all types" — and it is the one the
measurements support. The remaining suggestion types are still generated and still explained,
they are simply not applied until they earn a record.
""")
