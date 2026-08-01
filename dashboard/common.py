"""화면 공통 요소 — 로드 가드, 헤더, 테마 전환.

대시보드는 계산하지 않는다. 여기서도 마트를 읽고 src/metrics.py를 호출만 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import theme
from src import config, metrics


@st.cache_data
def _load():
    return metrics.load_marts()


def page(title: str, subtitle: str) -> tuple[dict, str, dict]:
    """마트 로드 + 헤더 + 다크 모드 전환. 마트가 없으면 안내 후 중단한다."""
    miss = metrics.missing_marts()
    if miss:
        st.title(title)
        st.error("마트 파일이 없습니다.")
        st.markdown(
            "먼저 아래를 실행하세요.\n\n"
            "```bash\n.venv/bin/python -m src.convert_xlsx\n"
            ".venv/bin/python -m src.run_pipeline\n```\n\n"
            f"없는 파일: `{'`, `'.join(miss)}`"
        )
        st.stop()

    marts = _load()
    st.title(title)
    left, right = st.columns([4, 1])
    with left:
        st.caption(
            f"{subtitle} · 분석 기준일 **{config.ANALYSIS_DATE}** (실행일 아님) · "
            "교육용 합성 데이터이므로 절대 수치의 업무적 타당성은 검증되지 않았습니다"
        )
    with right:
        mode = "dark" if st.toggle("다크 모드", value=False, key=f"dark_{title}") else "light"

    C = theme.CHROME[mode]
    # 차트만 다크로 바꾸면 페이지 표면과 어긋나 텍스트가 읽히지 않는다. 표면도 함께 전환한다.
    st.markdown(
        f"""<style>
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
            background-color: {C['plane']};
        }}
        .stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{ color: {C['ink']}; }}
        hr {{ border-color: {C['grid']}; }}
        </style>""",
        unsafe_allow_html=True,
    )
    return marts, mode, C


def footer(sources: str) -> None:
    st.divider()
    st.caption(
        f"출처 {sources} · 계산 규칙은 `outputs/reports/metric_definitions.md` (D1~D16) · "
        "차트 구성 근거는 `outputs/reports/dashboard_design.md`"
    )


def money(v: float) -> str:
    return f"{v:,.0f}원"


def million(v: float) -> str:
    return f"{v/1e6:.1f}M" if abs(v) < 1e7 else f"{v/1e6:.0f}M"


def eok(v: float) -> str:
    """KPI 타일용 축약 표기. 원 단위 전체 자릿수는 타일 폭을 넘어 잘린다."""
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}억원"
    if abs(v) >= 1e4:
        return f"{v/1e4:,.0f}만원"
    return f"{v:,.0f}원"
