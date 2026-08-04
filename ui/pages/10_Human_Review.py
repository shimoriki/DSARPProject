import streamlit as st
from _common import cfg, list_projects, load_suggestions
from dsarp.schemas import HGRS_WEIGHTS, HGRSReview
from dsarp.util import append_jsonl, read_jsonl

st.title("🧑‍⚖️ Human Review (HGRS)")
st.caption("Loop 12: score each suggestion; feedback re-enters the dataset/ranker.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
sugs = load_suggestions(sel)
reviews_path = cfg().data_dir / "outputs" / sel / "hgrs_reviews.jsonl"

if not sugs:
    st.info("No suggestions to review.")
else:
    labels = {f"#{s['rank']} {s['smell_type']} → {s['recommended_refactoring']}": s for s in sugs}
    pick = st.selectbox("Suggestion", list(labels))
    s = labels[pick]
    st.write("**Reasoning:**", s.get("reasoning"))
    st.write("**Evidence:**", s.get("evidence_used"))

    reviewer = st.text_input("Reviewer", "anonymous")
    scores = {}
    st.subheader("Scores (0–1)")
    for dim, w in HGRS_WEIGHTS.items():
        scores[dim] = st.slider(f"{dim} ({int(w*100)}%)", 0.0, 1.0, 0.6, 0.05)
    would = st.checkbox("Would try it")
    preferred = st.checkbox("Preferred among candidates")
    halluc = st.text_input("Hallucination flags (comma-separated)", "")
    notes = st.text_area("Reviewer notes", "")

    review = HGRSReview(suggestion_id=s["suggestion_id"], reviewer=reviewer, scores=scores,
                        would_try_it=would, preferred=preferred, notes=notes,
                        hallucination_flags=[h.strip() for h in halluc.split(",") if h.strip()])
    review.recompute()
    st.metric("Weighted HGRS", review.weighted_score)

    if st.button("💾 Save review"):
        append_jsonl(reviews_path, review.model_dump())
        st.success(f"Saved HGRS review (weighted={review.weighted_score}).")

    existing = list(read_jsonl(reviews_path))
    if existing:
        st.subheader(f"Existing reviews ({len(existing)})")
        st.table([{"suggestion": r["suggestion_id"][:8], "reviewer": r["reviewer"],
                   "hgrs": r["weighted_score"], "would_try": r["would_try_it"]}
                  for r in existing[-20:]])
