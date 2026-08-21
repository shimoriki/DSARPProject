"""Five agents over one blackboard, and what each contributed.

Two refactoring agents propose against the same severity-ranked findings: the evidence-gated
rule planners, and a separately-trained transformer read from its predictions CSV. They agree
on WHAT to fix, not how — the transformer names method-level refactorings while the rule
agent relocates packages, so matching on refactoring name would agree essentially never.
"""
import glob
from pathlib import Path

import streamlit as st
from _common import cfg, data_dir, default_index
from dsarp.util import read_json

st.title("🕸️ Multi-agent pipeline")
st.caption("ingestion → graph → {rule agent, transformer agent} → validator, with the "
           "orchestrator carrying what each run learned into the next.")

runs = sorted(glob.glob(str(data_dir() / "outputs" / "*" / "multiagent" /
                            "orchestrator_memory.json")))
if not runs:
    st.info("No multi-agent run recorded yet.")
    st.code("py -m dsarp.cli multiagent --repo apache-logging-log4j2 --detector both "
            "--require-consensus", language="bash")
    st.stop()

names = [Path(r).parent.parent.name for r in runs]
sel = st.selectbox("Project", names, index=default_index(names))
m = read_json(Path(runs[names.index(sel)])) or {}

c = st.columns(4)
c[0].metric("Findings", m.get("findings"))
c[1].metric("Rule agent — applicable", m.get("rule_applicable"))
c[2].metric("Transformer predictions", m.get("transformer_predictions"))
con = m.get("consensus") or {}
c[3].metric("Both agents agreed", con.get("agreed"))

st.subheader("Validator")
v = st.columns(3)
v[0].metric("Verification", m.get("verification_status") or "—")
v[1].metric("Build", m.get("build") or "—")
before, after = m.get("smells_before"), m.get("smells_after")
v[2].metric("Smells", f"{before} → {after}" if after is not None else f"{before} → unmeasured")

if m.get("ai_trials"):
    st.caption("Second validator strategy (LLM proposals, same allowlist and same gate): "
               + ", ".join(m["ai_trials"]))

st.divider()
st.subheader("How the two refactoring agents relate")
st.markdown(f"""
| agent | proposes | executable |
|---|---|---|
| rule planners | package/class relocation, field narrowing, splits | **yes** — OpenRewrite recipes |
| transformer | refactoring *type* names with confidence (`Move And Rename Method (0.51)`) | no — advisory |

They are matched on **smell type + affected component**, not on refactoring name. In the
log4j2 prediction set, 658 of 716 top picks are *Move And Rename Method* — a method-level
transformation the rule agent never emits — so name-matching would agree on nothing while
component-matching finds the packages both models independently flagged.

`--require-consensus` restricts execution to those agreed smells. It is **off by default**:
the transformer only covers repositories it was trained on, and an empty prediction file
would otherwise silently execute nothing.

**Orchestrator memory** is the outcome ledger ({m.get('ledger_entries', 0)} entries), which
already aggregates measured effect per (smell, refactoring) across every verified run and is
consulted by plan ranking. Recording a second store here would only create something that
could disagree with it.
""")
