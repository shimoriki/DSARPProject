import streamlit as st
from pathlib import Path
from _common import list_projects, load_suggestions

st.title("🍳 OpenRewrite Recipes")
st.caption("Loop 11: recipe drafts/plans. Marked draft until dry-run/build/test pass.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
sugs = load_suggestions(sel)
possible = [s for s in sugs if s.get("openrewrite_recipe_plan", {}).get("recipe_possible")]
st.metric("Recipe-possible suggestions", len(possible))
for s in sugs:
    plan = s.get("openrewrite_recipe_plan", {})
    with st.expander(f"{s.get('recommended_refactoring')} · status={plan.get('recipe_status')} · "
                     f"type={plan.get('recipe_type')}"):
        st.write("Applicable:", plan.get("recipe_possible"))
        st.write("Manual steps:")
        for m in plan.get("required_manual_steps", []):
            st.write("-", m)
        rp = plan.get("recipe_path")
        if rp and Path(rp).exists():
            st.code(Path(rp).read_text(encoding="utf-8"))
        st.caption(f"Verification — dry_run={s.get('verification', {}).get('openrewrite_dry_run')}, "
                   f"build={s.get('verification', {}).get('build')}, "
                   f"tests={s.get('verification', {}).get('tests')}")
