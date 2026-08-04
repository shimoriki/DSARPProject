import streamlit as st
from _common import cfg

st.title("🤖 Model & Ranker Training")
st.caption("Loop 8: local preference ranker (LightGBM/sklearn) + optional HPC LoRA.")

ranker = cfg().data_dir / "training" / "ranker.pkl"
st.metric("Local ranker trained", "yes" if ranker.exists() else "no")
st.code("dsarp-local ranker train --dataset data/training/candidates.jsonl", language="bash")

st.subheader("HPC / LoRA (optional)")
st.markdown(
    "- vLLM serving: `dsarp-hpc serve model --provider vllm --model Qwen2.5-Coder-32B-Instruct`\n"
    "- LoRA: `dsarp-hpc train lora --model Qwen2.5-Coder --dataset data/training/chat.jsonl`\n"
    "- Slurm scripts under `slurm/` (train_lora.slurm, train_ranker via build_dataset).\n\n"
    "MVP works without LoRA: RefactoringMiner dataset + graph/smell candidate generator + "
    "local preference ranker + local/HPC LLM explanation agent.")
st.info("The LLM critic never overrides the no-hallucination validators.")
