"""화면 B — 액션 후보 목록 (프로젝트 최종 산출물).

설계 근거: outputs/reports/dashboard_design.md 2장
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard import common, theme
from src import metrics

marts, mode, C = common.page("액션 후보", "무엇부터 처리할 것인가")

action = marts["action"]
st.divider()

# --------------------------------------------------------------------------
# B-1. 후보 테이블 — 판정 5분류·291건은 색으로 구분할 범위를 넘으므로 테이블이 맞다
# --------------------------------------------------------------------------
counts = action["정책판정"].value_counts()
k1, k2, k3, k4 = st.columns(4)
for col, 판정 in zip([k1, k2, k3, k4], metrics.ACTION_TABS):
    n = int(counts.get(판정, 0))
    금액 = action.loc[action["정책판정"] == 판정, "inventory_value"].sum()
    col.metric(f"{metrics.JUDGMENT_ICON[판정]} {판정}", f"{n:,}건", common.eok(금액), delta_color="off")

st.subheader("후보 목록")
st.caption(
    f"총 {len(action):,}건 · 재고금액 내림차순 · "
    "**원인과 액션이 달라 판정별로 탭을 나눴습니다**"
)

tabs = st.tabs([f"{metrics.JUDGMENT_ICON[j]} {j} ({int(counts.get(j, 0))})" for j in metrics.ACTION_TABS])
for tab, 판정 in zip(tabs, metrics.ACTION_TABS):
    with tab:
        if 판정 == "리오더":
            st.warning(
                "**발주 중단 상태입니다.** 2026년 6~7월 발주가 0건이므로 이 목록은 "
                "발주 재개 시 우선순위 후보이지 즉시 실행 지시가 아닙니다. (결정 D16)"
            )
        df = metrics.action_candidates(action, 판정)
        st.dataframe(
            df, hide_index=True, use_container_width=True, height=340,
            column_config={
                "inventory_value": st.column_config.NumberColumn("재고금액", format="%,d"),
                "available_qty": st.column_config.NumberColumn("재고수량", format="%d"),
                "재고주수": st.column_config.NumberColumn("재고주수", format="%.1f"),
                "판매속도_주": st.column_config.NumberColumn("주간 판매속도", format="%.2f"),
                "기존액션여부": st.column_config.CheckboxColumn("기존 액션"),
            },
        )
        st.download_button(
            f"{판정} 목록 CSV 내려받기",
            df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"action_{판정}.csv", mime="text/csv", key=f"dl_{판정}",
        )
        if 판정 == "무판매":
            st.caption("재고주수는 판매속도가 0이라 산출되지 않습니다 (결정 D14). 빈값이 정상입니다.")

st.divider()

# --------------------------------------------------------------------------
# B-2. 재고금액 × 재고주수 — 산점도. 모든 점이 인접할 수 있어 색은 3분류가 상한
# --------------------------------------------------------------------------
st.subheader("재고금액 × 재고주수")
st.caption(
    "**금액도 크고 안 팔리기까지 하는 SKU**가 우상단에 모입니다 · "
    "색은 3분류(소진·리오더·무판매)까지만 사용합니다 · 무판매는 재고주수가 없어 제외됩니다"
)

sc = metrics.action_scatter(action).dropna(subset=["재고주수"])
fig = go.Figure()
for 판정 in ["소진", "리오더"]:
    d = sc[sc["정책판정"] == 판정]
    fig.add_trace(go.Scatter(
        x=d["재고주수"], y=d["inventory_value"], mode="markers",
        name=f"{metrics.JUDGMENT_ICON[판정]} {판정}",
        marker=dict(color=theme.STATUS[판정], size=9, opacity=0.85,
                    line=dict(width=2, color=C["surface"])),
        customdata=d[["sku_id", "상품명", "available_qty"]].to_numpy(),
        hovertemplate="%{customdata[0]} %{customdata[1]}<br>재고주수 %{x:.1f}주<br>"
                      "재고금액 %{y:,.0f}원 · 수량 %{customdata[2]}개<extra></extra>",
    ))
top5 = sc.nlargest(5, "inventory_value")
fig.add_trace(go.Scatter(
    x=top5["재고주수"], y=top5["inventory_value"], mode="text",
    text=top5["sku_id"], textposition="middle right",
    textfont=dict(color=C["ink2"], size=10), showlegend=False, hoverinfo="skip",
))
fig.update_layout(**theme.layout(mode, height=420, showlegend=True,
                                 legend=dict(orientation="h", y=1.08, x=0, font=dict(color=C["ink2"]))))
fig.update_xaxes(title_text="재고주수 (주)", title_font=dict(color=C["muted"]))
fig.update_yaxes(title_text="재고금액 (원)", title_font=dict(color=C["muted"]))
st.plotly_chart(fig, use_container_width=True)
st.caption("상위 5개 SKU만 직접 라벨을 붙였습니다. 나머지는 마우스를 올려 확인하세요.")

with st.expander("표로 보기"):
    st.dataframe(metrics.action_candidates(action), hide_index=True, use_container_width=True)

common.footer("`data/marts/05_action_candidates.csv`")
