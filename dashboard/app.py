"""가나 스윔 시즌 중간 진단 대시보드 — 엔트리.

화면 구성 근거: outputs/reports/dashboard_design.md
대시보드는 계산하지 않는다. data/marts를 읽고 src/metrics.py를 호출만 한다.

실행:
    .venv/bin/streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(page_title="가나 스윔 시즌 중간 진단", layout="wide")

st.navigation(
    [
        st.Page("pages/1_재고_건전성.py", title="재고 건전성", icon=":material/inventory_2:", default=True),
        st.Page("pages/2_액션_후보.py", title="액션 후보", icon=":material/checklist:"),
        st.Page("pages/3_상품_성과.py", title="상품 성과", icon=":material/trending_up:"),
        st.Page("pages/4_추세.py", title="추세", icon=":material/show_chart:"),
    ]
).run()
