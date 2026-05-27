import streamlit as st

from core.auth import require_password
from repositories import qa_log_repo
from services import qa_service

require_password()

st.title("Ask")
st.caption("Ask about your training and data. Answers are grounded in your goal, recent metrics, and this week's plan.")

question = st.text_input("Your question", placeholder="How is my training going?")
if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Thinking…"):
        result = qa_service.ask(question.strip())
    if result.get("ok"):
        st.markdown(result["answer"])
        st.caption(f"~${result.get('cost_usd') or 0:.3f}")
    else:
        st.error(result.get("error", "Question failed. See the Debug tab."))

st.subheader("History")
try:
    history = qa_log_repo.recent(25)
except Exception as exc:
    history = []
    st.error(f"Could not load history: {exc}")

if not history:
    st.info("No questions yet.")
for row in history:
    with st.expander(f"{(row.get('asked_at') or '')[:16]} · {row.get('question', '')[:80]}"):
        st.markdown(row.get("answer") or "")
