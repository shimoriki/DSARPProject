import streamlit as st
from pathlib import Path
from _common import cfg

st.title("🖥️ HPC Job Monitor")
st.caption("Slurm scripts + collected logs. Submission is guarded (dsarp-hpc demo submit --yes).")

root = Path(__file__).resolve().parent.parent.parent
slurm = root / "slurm"
st.subheader("Slurm scripts")
scripts = sorted(slurm.glob("*.slurm")) if slurm.exists() else []
for s in scripts:
    with st.expander(s.name):
        st.code(s.read_text(encoding="utf-8"), language="bash")

st.subheader("Logs")
logs_dir = root / "logs"
logs = sorted(logs_dir.glob("*.out")) if logs_dir.exists() else []
if not logs:
    st.info("No Slurm logs yet (logs/ populated on the cluster).")
for lg in logs[-10:]:
    with st.expander(lg.name):
        st.code(lg.read_text(encoding="utf-8")[-4000:])

st.subheader("HPC plan")
st.code("dsarp-hpc demo plan     # prints plan, submits nothing\n"
        "dsarp-hpc demo submit --yes   # submits job chain (needs sbatch)", language="bash")
