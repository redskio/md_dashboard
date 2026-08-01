"""화면 D — 추세.

설계 근거: outputs/reports/dashboard_design.md 4장
매출(원)과 재고(개)는 스케일이 달라 **이중축을 쓰지 않는다.** x축을 공유하는 별도 차트로 세로 정렬한다.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard import common, theme
from src import metrics

marts, mode, C = common.page("추세", "지금 흐름이 좋아지고 있는가")

weekly, product = marts["weekly"], marts["product"]
full, partial = metrics.weekly_totals(weekly)
st.divider()

peak = full.loc[full["순매출"].idxmax()]
last = full.iloc[-1]
k1, k2, k3 = st.columns(3)
k1.metric("마지막 완전주 순매출", common.eok(last["순매출"]),
          f"직전 주 대비 {(last['순매출']/full.iloc[-2]['순매출']-1)*100:+.1f}%")
k2.metric(f"{len(full)}주 최고 순매출", common.eok(peak["순매출"]), str(peak["week_end"])[:10], delta_color="off")
k3.metric("마지막 주 재고", f"{int(last['재고']):,}개", str(last["week_end"])[:10], delta_color="off")

st.divider()

# --------------------------------------------------------------------------
# D-1. 주별 순매출 — 라인 1개(범례 없음, 제목이 계열명을 대신한다)
#      부분주는 라인에 잇지 않고 별도 점으로 찍는다. 이으면 급락으로 오독된다
# --------------------------------------------------------------------------
st.subheader("주별 순매출")
st.caption(
    f"완전주 {len(full)}개 · **부분주 {len(partial)}개(첫 주 1일치·마지막 주 5일치)는 라인에서 제외**하고 "
    "회색 점으로 분리했습니다 · 이으면 급등·급락으로 오독됩니다"
)

line = go.Figure()
line.add_trace(go.Scatter(
    x=full["week_end"], y=full["순매출"], mode="lines", name="순매출",
    line=dict(color=C["accent"], width=2),
    hovertemplate="%{x|%Y-%m-%d} 주<br>순매출 %{y:,.0f}원<extra></extra>",
))
# 최고점과 마지막 주가 같으면 라벨이 겹치므로 하나만 찍는다
marks = [(peak, f"최고 {peak['순매출']/1e6:.1f}M", "top center")]
if peak["week_end"] != last["week_end"]:
    marks.append((last, f"마지막 {last['순매출']/1e6:.1f}M", "bottom center"))
for r, label, pos in marks:
    line.add_trace(go.Scatter(
        x=[r["week_end"]], y=[r["순매출"]], mode="markers+text", text=[label], textposition=pos,
        marker=dict(color=C["accent"], size=9, line=dict(width=2, color=C["surface"])),
        textfont=dict(color=C["ink2"], size=10), showlegend=False, hoverinfo="skip",
    ))
for _, p in partial.iterrows():
    line.add_trace(go.Scatter(
        x=[p["week_end"]], y=[p["순매출"]], mode="markers+text",
        text=["부분주"], textposition="bottom center",
        marker=dict(color=C["muted"], size=9, symbol="circle-open", line=dict(width=2)),
        textfont=dict(color=C["muted"], size=10), showlegend=False,
        hovertemplate="부분주 %{x|%Y-%m-%d}<br>순매출 %{y:,.0f}원<extra></extra>",
    ))
line.update_layout(**theme.layout(mode, height=300, hovermode="x unified"))
line.update_yaxes(title_text="순매출 (원)", title_font=dict(color=C["muted"]))
st.plotly_chart(line, use_container_width=True)

# --------------------------------------------------------------------------
# D-2. 주별 재고량 — 별도 차트, x축 범위를 D-1과 맞춰 세로 정렬
# --------------------------------------------------------------------------
st.subheader("주별 재고량")
st.caption(
    "**이중축을 쓰지 않습니다.** 매출(원)과 재고(개)는 스케일이 달라 한 플롯에 겹치면 "
    "두 축의 정렬이 임의가 되어 없는 상관관계를 만들어냅니다 · "
    "스냅샷 간격이 불균등(주 1회 + 월말)하므로 마커가 실제 측정 시점입니다"
)
stock = go.Figure(go.Scatter(
    x=full["week_end"], y=full["재고"], mode="lines+markers",
    line=dict(color=C["accent"], width=2),
    marker=dict(size=8, color=C["accent"], line=dict(width=2, color=C["surface"])),
    hovertemplate="%{x|%Y-%m-%d} 주<br>재고 %{y:,}개<extra></extra>",
))
stock.update_layout(**theme.layout(mode, height=280, hovermode="x unified"))
stock.update_xaxes(range=[full["week_end"].min(), full["week_end"].max()])
stock.update_yaxes(title_text="가용재고 (개)", title_font=dict(color=C["muted"]))
st.plotly_chart(stock, use_container_width=True)

with st.expander("표로 보기"):
    st.dataframe(full[["week_end", "순매출", "순판매수량", "가용공헌이익", "재고"]],
                 hide_index=True, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# D-3. 상품별 WoW 증감 — 다이버징 막대 (따뜻/차가운 2색 + 중립 회색 중간점)
# --------------------------------------------------------------------------
movers, last_week = metrics.wow_movers(weekly)
names = metrics.product_names(product)
movers = movers.assign(상품명=movers["product_id"].map(names))
D = theme.DIVERGING[mode]

st.subheader("상품별 주간 증감 (WoW)")
st.caption(
    f"기준 주 **{last_week}** · 갑자기 꺾이거나 튄 상품 감지 · 상·하위 8개씩 · "
    "**주간 등락이 원래 ±20% 수준이므로 단주 변동을 추세로 읽지 마세요**"
)
d = go.Figure(go.Bar(
    y=movers["상품명"], x=movers["순매출_WoW"], orientation="h",
    marker=dict(color=[D["up"] if v > 0 else D["down"] for v in movers["순매출_WoW"]], cornerradius=4),
    hovertemplate="%{y}<br>WoW %{x:,.0f}원<extra></extra>",
))
d.add_vline(x=0, line=dict(color=C["axis"], width=1, dash="solid"))
d.update_layout(**theme.layout(mode, height=460, bargap=0.3))
d.update_xaxes(title_text="직전 주 대비 순매출 증감 (원)", title_font=dict(color=C["muted"]))
d.update_yaxes(tickfont=dict(color=C["ink2"], size=11))
st.plotly_chart(d, use_container_width=True)
st.caption(
    f"오른쪽(증가)은 따뜻한 색, 왼쪽(감소)은 차가운 색, 0은 중립입니다. "
    f"이 주의 증가 {int((movers['순매출_WoW'] > 0).sum())}개 / 감소 {int((movers['순매출_WoW'] < 0).sum())}개."
)

with st.expander("표로 보기"):
    st.dataframe(movers[["상품명", "순매출", "순매출_WoW"]].sort_values("순매출_WoW", ascending=False),
                 hide_index=True, use_container_width=True)

common.footer("`data/marts/04_weekly_product_trend.csv`")
