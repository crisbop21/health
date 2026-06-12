import streamlit as st

from core import views
from core.auth import require_password

st.set_page_config(page_title="Today · Health & Training", layout="wide")
require_password()

views.render_today()
