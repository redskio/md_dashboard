"""대시보드 색·차트 크롬 토큰.

값은 dashboard_design.md의 검증 통과 팔레트를 그대로 옮긴 것이다.
- 카테고리 6색: light/dark 모두 검증 통과 (색각 이상 최저 인접쌍 ΔE 9.1 / 8.4)
- 정책 판정: 상태색. `주의`와 `소진`의 정상 시야 ΔE가 13.6이라 **색 단독 사용 금지**.
  아이콘·라벨을 항상 동반하고, 두 색이 맞닿는 형태(누적 막대)를 쓰지 않는다.
"""

from __future__ import annotations

# 대분류 고정 슬롯 (색은 대상을 따른다 — 필터로 계열이 빠져도 색이 바뀌지 않는다)
CATEGORICAL = {
    "light": {"여성": "#2a78d6", "남성": "#eb6834", "아동": "#1baf7a",
              "장비": "#eda100", "용품": "#e87ba4", "스킨케어": "#008300"},
    "dark": {"여성": "#3987e5", "남성": "#d95926", "아동": "#199e70",
             "장비": "#c98500", "용품": "#d55181", "스킨케어": "#008300"},
}

# 상태색 (예약 — 일반 계열 색으로 재사용하지 않는다)
STATUS = {
    "리오더": "#d03b3b",   # critical — 품절 위험
    "소진": "#ec835a",     # serious  — 자본이 묶임
    "주의": "#fab219",     # warning  — 정책 구간 밖
    "정상": "#0ca30c",     # good
    "무판매": "#898781",   # muted    — 판매 신호 없음
}

# 시퀀셜 단일 색조 (블루 램프, 밝음 → 어두움)
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]

CHROME = {
    "light": {
        "surface": "#fcfcfb", "plane": "#f9f9f7", "ink": "#0b0b0b",
        "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
        "accent": "#2a78d6", "deemph": "#c3c2b7",
    },
    "dark": {
        "surface": "#1a1a19", "plane": "#0d0d0d", "ink": "#ffffff",
        "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
        "accent": "#3987e5", "deemph": "#52514e",
    },
}


def layout(mode: str, height: int = 320, **kw) -> dict:
    """Plotly 공통 레이아웃. 얇은 마크, hairline 실선 그리드, 여백 넉넉하게."""
    c = CHROME[mode]
    base = dict(
        paper_bgcolor=c["surface"],
        plot_bgcolor=c["surface"],
        font=dict(color=c["ink2"], size=12),
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        xaxis=dict(gridcolor=c["grid"], griddash="solid", linecolor=c["axis"],
                   zerolinecolor=c["axis"], tickfont=dict(color=c["muted"])),
        yaxis=dict(gridcolor=c["grid"], griddash="solid", linecolor=c["axis"],
                   zerolinecolor=c["axis"], tickfont=dict(color=c["muted"])),
        hoverlabel=dict(bgcolor=c["surface"], font_color=c["ink"]),
        showlegend=False,
    )
    base.update(kw)
    return base


# 다이버징 (증감) — 따뜻한/차가운 대비 + 중립 회색 중간점
DIVERGING = {
    "light": {"up": "#d03b3b", "down": "#2a78d6", "mid": "#f0efec"},
    "dark": {"up": "#e66767", "down": "#3987e5", "mid": "#383835"},
}
