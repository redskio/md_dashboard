"""화면 A — 재고 건전성.

설계 근거: outputs/reports/dashboard_design.md 1장
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import common, theme
from src import metrics

marts, mode, C = common.page("재고 건전성", "지금 재고에 문제가 있는가, 있다면 돈이 어디에 묶여 있는가")
inv_all, weekly = marts["inventory"], marts["weekly"]

f1, f2, f3, f4 = st.columns(4)
with f1:
    대분류 = st.multiselect("대분류", sorted(inv_all["대분류"].dropna().unique()))
with f2:
    시즌 = st.multiselect("시즌", sorted(inv_all["시즌"].dropna().unique()))
with f3:
    민감도 = st.multiselect("시즌민감도", sorted(inv_all["시즌민감도"].dropna().unique()))
with f4:
    판정 = st.multiselect("정책판정", [j for j in metrics.JUDGMENT_ORDER if j in set(inv_all["정책판정"])])

inv = metrics.apply_filters(inv_all, 대분류, 시즌, 민감도, 판정)
if inv.empty:
    st.warning("필터 조건에 해당하는 SKU가 없습니다.")
    st.stop()

st.divider()

# --------------------------------------------------------------------------
# A-1. KPI 행 — 값이 하나뿐인 수치는 막대 1개짜리 차트로 그리지 않는다
# --------------------------------------------------------------------------
k = metrics.kpi_summary(inv)
c1, c2, c3, c4 = st.columns([1.4, 1, 1, 1])

with c1:
    st.markdown(
        f"<div style='font-size:13px;color:{C['muted']}'>전사 재고주수</div>"
        f"<div style='font-size:52px;line-height:1.1;color:{C['ink']}'>{k['재고주수']:.1f}"
        f"<span style='font-size:20px;color:{C['ink2']}'> 주</span></div>"
        f"<div style='font-size:12px;color:{C['muted']}'>지금 속도로 팔면 재고 소진까지</div>",
        unsafe_allow_html=True,
    )
    ws = metrics.weekly_wos_series(weekly)
    spark = go.Figure(go.Scatter(x=ws["week_end"], y=ws["재고주수"], mode="lines",
                                 line=dict(color=C["accent"], width=2), hoverinfo="skip"))
    spark.update_layout(**theme.layout(mode, height=60, margin=dict(l=0, r=0, t=4, b=0)))
    spark.update_xaxes(visible=False)
    spark.update_yaxes(visible=False)
    st.plotly_chart(spark, use_container_width=True, config={"displayModeBar": False})

c2.metric("총 재고금액", common.eok(k["재고금액"]), help=f"기준일 가용재고 기준 · {common.money(k['재고금액'])}")
c3.metric("소진 대상 금액", common.eok(k["소진금액"]), f"전체의 {k['소진비중']*100:.1f}%", delta_color="inverse")
c4.metric("액션 후보 SKU", f"{k['후보SKU수']:,}건", f"전체 {k['전체SKU수']:,}건 중", delta_color="off")

st.progress(min(k["소진비중"], 1.0), text=f"재고금액 중 소진 대상 비중 {k['소진비중']*100:.1f}%")

st.divider()

# --------------------------------------------------------------------------
# A-2. 판정별 재고금액 — 가로 막대, 단일 색 + 아이콘
#      상태색 5개를 나란히 두면 주의·소진이 구분되지 않으므로 색으로 구분시키지 않는다
# --------------------------------------------------------------------------
left, right = st.columns([1.15, 1])

with left:
    st.subheader("정책 판정별 재고금액")
    st.caption("어느 판정 구간에 자본이 묶여 있는가 · 막대 길이는 금액, 상태는 아이콘과 라벨로 읽습니다")
    pj = metrics.policy_by_judgment(inv)
    labels = [f"{r.아이콘} {r.정책판정}" for r in pj.itertuples()]
    fig = go.Figure(
        go.Bar(
            x=pj["재고금액"], y=labels, orientation="h",
            marker=dict(color=C["accent"], cornerradius=4),
            text=[f"{v:,.0f}원 ({p*100:.1f}%)" for v, p in zip(pj["재고금액"], pj["금액비중"])],
            textposition="outside", textfont=dict(color=C["ink2"]),
            customdata=pj[["SKU수", "재고수량"]].to_numpy(),
            hovertemplate="%{y}<br>재고금액 %{x:,.0f}원<br>SKU %{customdata[0]}건 · 수량 %{customdata[1]:,}개<extra></extra>",
        )
    )
    fig.update_layout(**theme.layout(mode, height=300, bargap=0.35))
    fig.update_xaxes(visible=False, range=[0, pj["재고금액"].max() * 1.35])
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=C["ink2"], size=13))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "SKU 수가 비슷해도 금액은 크게 다를 수 있습니다. 아래 표에서 두 값을 함께 확인하세요."
    )
    with st.expander("표로 보기"):
        st.dataframe(
            pj[["아이콘", "정책판정", "SKU수", "재고수량", "재고금액", "금액비중", "중위재고주수"]],
            hide_index=True, use_container_width=True,
        )

# --------------------------------------------------------------------------
# A-4. 카테고리 × 판정 — 히트맵 (시퀀셜 단일 색조, 셀 값 직접 표기)
# --------------------------------------------------------------------------
with right:
    st.subheader("카테고리 × 판정 재고금액")
    st.caption("재고 문제가 특정 카테고리에 몰려 있는가")
    m = metrics.category_judgment_matrix(inv)
    hm = go.Figure(
        go.Heatmap(
            z=m.values, x=list(m.columns), y=list(m.index),
            colorscale=[[i / (len(theme.SEQUENTIAL) - 1), c] for i, c in enumerate(theme.SEQUENTIAL)],
            texttemplate="%{text}",
            text=[[("" if not v else f"{v/1e6:.1f}M" if v < 1e7 else f"{v/1e6:.0f}M") for v in row]
                  for row in m.values],
            textfont=dict(size=11),
            colorbar=dict(title="재고금액", tickfont=dict(color=C["muted"])),
            hovertemplate="%{y} · %{x}<br>재고금액 %{z:,.0f}원<extra></extra>",
            xgap=2, ygap=2,
        )
    )
    hm.update_layout(**theme.layout(mode, height=300))
    hm.update_xaxes(side="top", tickfont=dict(color=C["ink2"]))
    # Plotly는 y축을 아래에서 위로 그리므로, 금액 큰 카테고리가 위에 오도록 뒤집는다
    hm.update_yaxes(autorange="reversed", tickfont=dict(color=C["ink2"]))
    st.plotly_chart(hm, use_container_width=True)
    st.caption("단위 M = 백만원. 색만으로 값을 읽지 않도록 셀에 금액을 함께 표시했습니다.")
    with st.expander("표로 보기"):
        st.dataframe(m.style.format("{:,.0f}"), use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# A-3. 재고주수 분포 — 히스토그램 + 임계선(실선 hairline). 점선은 '예측'으로 읽히므로 쓰지 않는다
# --------------------------------------------------------------------------
st.subheader("재고주수 분포")
dist, meta = metrics.wos_distribution(inv)
st.caption(
    f"정책 임계선을 얼마나 벗어나는가 · 표본 {meta['표본']}개 SKU · "
    f"**판매속도 0인 {meta['무판매제외']}개(무판매)는 재고주수 미산출로 제외** · "
    f"**{meta['cap']:.0f}주 이상 {meta['over_cap']}개는 마지막 구간에 묶음**"
)

h = go.Figure(
    go.Histogram(
        x=dist["재고주수"], nbinsx=40,
        marker=dict(color=C["accent"], line=dict(width=2, color=C["surface"])),
        hovertemplate="재고주수 %{x}<br>SKU %{y}건<extra></extra>",
    )
)
# 임계선은 카테고리별 3조합이라 그룹당 여러 개다. 라벨은 그룹의 첫 선에만 붙이고
# 위/아래로 나눠 배치해 겹치지 않게 한다 (점선은 '예측'으로 읽히므로 실선 hairline)
for key, label, color, pos, yshift in [
    ("reorder", "리오더 임계", theme.STATUS["리오더"], "top left", 0),
    ("target_min", "정상 하한", C["muted"], "top left", -16),
    ("target_max", "정상 상한", C["muted"], "top right", -16),
    ("clearance", "소진 임계", theme.STATUS["소진"], "top right", 0),
]:
    for i, v in enumerate(meta["thresholds"][key]):
        line = dict(color=color, width=1, dash="solid")
        if i == 0:
            h.add_vline(x=v, line=line, annotation_text=label, annotation_position=pos,
                        annotation_yshift=yshift, annotation_font=dict(color=color, size=10))
        else:
            h.add_vline(x=v, line=line)
h.update_layout(**theme.layout(mode, height=340, bargap=0.05))
h.update_xaxes(title_text=f"재고주수 (주) — {meta['cap']:.0f} 이상은 묶음", title_font=dict(color=C["muted"]))
h.update_yaxes(title_text="SKU 수", title_font=dict(color=C["muted"]))
st.plotly_chart(h, use_container_width=True)
st.caption(
    "임계선이 카테고리별로 3가지 조합이라 선이 여러 개 표시됩니다. "
    "임계선 사이의 빈 구간에 들어간 SKU가 「주의」로 분류됩니다."
)
with st.expander("표로 보기"):
    st.dataframe(
        inv[["sku_id", "상품명", "대분류", "정책판정", "available_qty", "재고주수", "판매속도_주",
             "reorder_point_wos", "target_wos_min", "target_wos_max", "clearance_point_wos"]]
        .sort_values("재고주수", ascending=False),
        hide_index=True, use_container_width=True,
    )

st.divider()

# --------------------------------------------------------------------------
# A-5. 임계값 민감도 — 라인 + 현재 지점 강조
# --------------------------------------------------------------------------
st.subheader("임계값 민감도")
st.caption(
    "소진 대상 건수가 얼마나 견고한가 · 원본 README가 "
    "\"정책 테이블은 교육용 승인 기준이며 정답이 아님\"이라고 명시하고 있습니다"
)
sens = metrics.policy_sensitivity(inv)
cur = sens[sens["현재값"]].iloc[0]

s = go.Figure()
s.add_trace(go.Scatter(
    x=sens["조정폭"], y=sens["소진SKU수"], mode="lines",
    line=dict(color=C["accent"], width=2), name="소진 대상 SKU",
    hovertemplate="임계값 %{x:+d}주<br>소진 대상 %{y}건<extra></extra>",
))
s.add_trace(go.Scatter(
    x=[cur["조정폭"]], y=[cur["소진SKU수"]], mode="markers+text",
    marker=dict(color=C["accent"], size=11, line=dict(width=2, color=C["surface"])),
    text=[f"현재 {int(cur['소진SKU수'])}건"], textposition="top center",
    textfont=dict(color=C["ink"]), hoverinfo="skip",
))
s.update_layout(**theme.layout(mode, height=300))
s.update_xaxes(title_text="임계값 조정폭 (주)", title_font=dict(color=C["muted"]),
               tickvals=list(range(-5, 6)), ticktext=[f"{v:+d}" for v in range(-5, 6)])
s.update_yaxes(title_text="소진 대상 SKU 수", title_font=dict(color=C["muted"]))
st.plotly_chart(s, use_container_width=True)

lo, hi = sens["소진SKU수"].min(), sens["소진SKU수"].max()
st.caption(
    f"임계값을 ±5주 움직이면 소진 대상이 **{lo}~{hi}건**으로 변합니다. "
    "판정 결과는 액션 후보이지 확정 지시가 아닙니다."
)
with st.expander("표로 보기"):
    st.dataframe(sens[["조정폭", "소진SKU수", "소진금액", "리오더SKU수"]],
                 hide_index=True, use_container_width=True)

common.footer("`data/marts/02_inventory_sku_asof.csv`, `04_weekly_product_trend.csv`")
