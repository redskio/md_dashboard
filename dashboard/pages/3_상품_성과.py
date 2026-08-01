"""화면 C — 상품 성과.

설계 근거: outputs/reports/dashboard_design.md 3장
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard import common, theme
from src import metrics

marts, mode, C = common.page("상품 성과", "어떤 상품이 실제로 돈을 남기는가")

product_all = marts["product"]

f1, f2 = st.columns(2)
with f1:
    대분류 = st.multiselect("대분류", sorted(product_all["대분류"].dropna().unique()))
with f2:
    시즌 = st.multiselect("시즌", sorted(product_all["시즌"].dropna().unique()))
product = metrics.product_perf(product_all, 대분류, 시즌)
if product.empty:
    st.warning("필터 조건에 해당하는 상품이 없습니다.")
    st.stop()

st.divider()

k1, k2, k3, k4 = st.columns(4)
k1.metric("순매출", common.eok(product["순매출"].sum()), help=common.money(product["순매출"].sum()))
k2.metric("가용 공헌이익", common.eok(product["가용공헌이익"].sum()), help=common.money(product["가용공헌이익"].sum()))
k3.metric("이익률", f"{metrics.overall_margin(product)*100:.1f}%")
k4.metric("반품률", f"{metrics.overall_return_rate(product)*100:.1f}%",
          f"완료 반품 {int(product['완료반품수량'].sum()):,}건", delta_color="off")

st.divider()

# --------------------------------------------------------------------------
# C-1. 순매출 vs 공헌이익 — 산점도. 소표본은 색이 아니라 '형태'로 구분한다
# --------------------------------------------------------------------------
st.subheader("순매출 × 공헌이익")
st.caption(
    "**매출 상위와 이익 상위가 일치하는가** · 점 크기는 재고금액 · "
    f"속이 빈 마커는 판매 30개 미만의 소표본 상품({int(product['소표본경고'].sum())}개)입니다"
)

fig = go.Figure()
# 버블 크기는 면적 기준으로 스케일한다(지름에 값을 바로 넣으면 마커가 화면을 덮는다)
size_ref = 2.0 * max(product["재고금액"].max(), 1) / (34.0**2)
for 소표본, name, fillcolor in [(False, "일반", C["accent"]), (True, "소표본 (판매 30개 미만)", C["surface"])]:
    d = product[product["소표본경고"].astype(bool) == 소표본]
    if d.empty:
        continue
    fig.add_trace(go.Scatter(
        x=d["순매출"], y=d["가용공헌이익"], mode="markers", name=name,
        marker=dict(color=fillcolor, size=d["재고금액"], sizemode="area", sizeref=size_ref, sizemin=6,
                    line=dict(width=2, color=C["accent"] if 소표본 else C["surface"])),
        customdata=d[["상품명", "이익률", "유효판매수량", "재고금액"]].to_numpy(),
        hovertemplate="%{customdata[0]}<br>순매출 %{x:,.0f}원 · 공헌이익 %{y:,.0f}원<br>"
                      "이익률 %{customdata[1]:.1%} · 판매 %{customdata[2]:,}개<br>"
                      "재고금액 %{customdata[3]:,.0f}원<extra></extra>",
    ))
extreme = product.nlargest(3, "가용공헌이익")
fig.add_trace(go.Scatter(
    x=extreme["순매출"], y=extreme["가용공헌이익"], mode="text", text=extreme["상품명"],
    textposition="top center", textfont=dict(color=C["ink2"], size=10),
    showlegend=False, hoverinfo="skip",
))
fig.update_layout(**theme.layout(mode, height=430, showlegend=True,
                                 legend=dict(orientation="h", y=1.08, x=0, font=dict(color=C["ink2"]))))
fig.update_xaxes(title_text="순매출 (원)", title_font=dict(color=C["muted"]))
fig.update_yaxes(title_text="가용 공헌이익 (원)", title_font=dict(color=C["muted"]))
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

# --------------------------------------------------------------------------
# C-2. 카테고리별 순매출·공헌이익 — 그룹 막대. 같은 단위(원)라 한 축에 그린다
# --------------------------------------------------------------------------
with left:
    st.subheader("카테고리별 매출·이익")
    st.caption("매출과 이익은 같은 단위(원)라 한 축에 그립니다. 이익률(%)은 아래 표로 분리했습니다")
    cat = metrics.category_perf(product).sort_values("순매출")
    pal = theme.CATEGORICAL[mode]
    g = go.Figure()
    g.add_trace(go.Bar(y=cat["대분류"], x=cat["순매출"], orientation="h", name="순매출",
                       marker=dict(color=pal["여성"], cornerradius=4),
                       hovertemplate="%{y} 순매출 %{x:,.0f}원<extra></extra>"))
    g.add_trace(go.Bar(y=cat["대분류"], x=cat["가용공헌이익"], orientation="h", name="공헌이익",
                       marker=dict(color=pal["남성"], cornerradius=4),
                       hovertemplate="%{y} 공헌이익 %{x:,.0f}원<extra></extra>"))
    g.update_layout(**theme.layout(mode, height=330, barmode="group", bargap=0.3, bargroupgap=0.12,
                                   showlegend=True,
                                   legend=dict(orientation="h", y=1.12, x=0, font=dict(color=C["ink2"]))))
    g.update_xaxes(title_text="금액 (원)", title_font=dict(color=C["muted"]))
    g.update_yaxes(tickfont=dict(color=C["ink2"]))
    st.plotly_chart(g, use_container_width=True)
    with st.expander("표로 보기 (이익률 포함)"):
        st.dataframe(cat.sort_values("순매출", ascending=False), hide_index=True, use_container_width=True,
                     column_config={"이익률": st.column_config.NumberColumn("이익률", format="%.1%%")})

# --------------------------------------------------------------------------
# C-3. 이익률 하위 — 강조 막대. 적자 상품이 0개이므로 '하위 관찰'이 목적
# --------------------------------------------------------------------------
with right:
    st.subheader("이익률 하위 10")
    avg = metrics.overall_margin(product)
    st.caption(
        f"**공헌이익 적자 상품은 {int((product['가용공헌이익'] < 0).sum())}개**입니다. "
        "적자 탐지가 아니라 개선 여지 관찰이 목적입니다 · 강조된 막대는 소표본 상품"
    )
    bot = metrics.margin_bottom(product)
    colors = [C["accent"] if s else C["deemph"] for s in bot["소표본경고"].astype(bool)]
    b = go.Figure(go.Bar(
        y=bot["상품명"], x=bot["이익률"], orientation="h",
        marker=dict(color=colors, cornerradius=4),
        text=[f"{v:.1%} · 판매 {int(q)}개" for v, q in zip(bot["이익률"], bot["유효판매수량"])],
        textposition="outside", textfont=dict(color=C["ink2"], size=10),
        hovertemplate="%{y}<br>이익률 %{x:.1%}<extra></extra>",
    ))
    b.add_vline(x=avg, line=dict(color=C["muted"], width=1, dash="solid"),
                annotation_text=f"전사 평균 {avg:.1%}", annotation_position="top",
                annotation_font=dict(color=C["muted"], size=10))
    b.update_layout(**theme.layout(mode, height=330, bargap=0.35))
    b.update_xaxes(visible=False, range=[0, bot["이익률"].max() * 1.9])
    b.update_yaxes(tickfont=dict(color=C["ink2"], size=11))
    st.plotly_chart(b, use_container_width=True)
    st.caption("**막대 옆 판매수량을 함께 보세요.** 판매가 적은 상품의 이익률은 신뢰하기 어렵습니다.")

st.divider()

# --------------------------------------------------------------------------
# C-4. 반품률 — 표본 부족 상품은 제외하고 제외 수를 명시
# --------------------------------------------------------------------------
st.subheader("반품률 상위")
rr, excluded = metrics.return_rate_top(product)
base_rate = metrics.overall_return_rate(product)
st.caption(
    f"품질·사이즈 이슈 신호 · 전사 반품률 {base_rate:.1%} · "
    f"**완료 반품 {metrics.RETURN_MIN_BASE}건 미만 {excluded}개 상품은 표본 부족으로 제외**했습니다"
)
if rr.empty:
    st.info("표본 기준을 넘는 상품이 없습니다.")
else:
    r = go.Figure(go.Bar(
        y=rr["상품명"], x=rr["반품률"], orientation="h",
        marker=dict(color=C["accent"], cornerradius=4),
        text=[f"{v:.1%} · 반품 {int(n)}건 / 판매 {int(q)}개"
              for v, n, q in zip(rr["반품률"], rr["완료반품수량"], rr["유효판매수량"])],
        textposition="outside", textfont=dict(color=C["ink2"], size=10),
        hovertemplate="%{y}<br>반품률 %{x:.1%}<extra></extra>",
    ))
    r.add_vline(x=base_rate, line=dict(color=C["muted"], width=1, dash="solid"),
                annotation_text=f"전사 {base_rate:.1%}", annotation_position="top",
                annotation_font=dict(color=C["muted"], size=10))
    r.update_layout(**theme.layout(mode, height=340, bargap=0.35))
    r.update_xaxes(visible=False, range=[0, rr["반품률"].max() * 2.1])
    r.update_yaxes(tickfont=dict(color=C["ink2"], size=11))
    st.plotly_chart(r, use_container_width=True)
    st.caption("모든 비율에 분모(판매수량)를 함께 표시했습니다.")

with st.expander("상품 전체 표로 보기"):
    st.dataframe(
        product[["상품명", "대분류", "시즌", "유효판매수량", "순매출", "가용공헌이익", "이익률",
                 "반품률", "판매자귀책_반품률", "available_qty", "상품재고주수", "소표본경고"]]
        .sort_values("가용공헌이익", ascending=False),
        hide_index=True, use_container_width=True,
    )

common.footer("`data/marts/03_product_perf_asof.csv`")
