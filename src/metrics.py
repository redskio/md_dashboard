"""지표 계산 함수. 대시보드는 계산하지 않고 이 모듈을 호출한다 (CLAUDE.md 코드 원칙).

계산 규칙은 outputs/reports/metric_definitions.md의 결정 D1~D16을 따른다.
마트는 src/run_pipeline.py가 생성한 data/marts/*.csv를 읽는다.
"""

from __future__ import annotations

import pandas as pd

from src import config

MARTS_DIR = config.DATA_DIR / "marts"

MART_FILES = {
    "sales": "01_sales_line.csv",
    "inventory": "02_inventory_sku_asof.csv",
    "product": "03_product_perf_asof.csv",
    "weekly": "04_weekly_product_trend.csv",
    "action": "05_action_candidates.csv",
}

# 정책 판정 표시 순서 (심각도 순). 색은 대시보드 테마에서 지정한다.
JUDGMENT_ORDER = ["리오더", "소진", "주의", "무판매", "정상"]
JUDGMENT_ICON = {"리오더": "▲", "소진": "●", "주의": "◆", "무판매": "○", "정상": "—"}


class MartsMissing(FileNotFoundError):
    """마트 파일이 없을 때. 대시보드는 크래시 대신 안내를 띄운다."""


def missing_marts() -> list[str]:
    return [f for f in MART_FILES.values() if not (MARTS_DIR / f).exists()]


def load_marts() -> dict[str, pd.DataFrame]:
    miss = missing_marts()
    if miss:
        raise MartsMissing(", ".join(miss))
    out = {}
    for key, fname in MART_FILES.items():
        out[key] = pd.read_csv(MARTS_DIR / fname, encoding=config.CSV_ENCODING)
    return out


def apply_filters(inv: pd.DataFrame, 대분류=None, 시즌=None, 시즌민감도=None, 판정=None) -> pd.DataFrame:
    df = inv
    for col, sel in [("대분류", 대분류), ("시즌", 시즌), ("시즌민감도", 시즌민감도), ("정책판정", 판정)]:
        if sel:
            df = df[df[col].isin(sel)]
    return df


# --------------------------------------------------------------------------
# A-1. KPI
# --------------------------------------------------------------------------
def kpi_summary(inv: pd.DataFrame) -> dict:
    """전사 재고주수·재고금액·소진 비중·액션 후보 수."""
    재고수량 = inv["available_qty"].sum()
    속도 = inv["최근28일_순판매수량"].sum() / 4          # D11·D12
    소진금액 = inv.loc[inv["정책판정"] == "소진", "inventory_value"].sum()
    총금액 = inv["inventory_value"].sum()
    return {
        "재고주수": 재고수량 / 속도 if 속도 > 0 else float("nan"),   # D13·D14
        "재고수량": int(재고수량),
        "재고금액": float(총금액),
        "소진금액": float(소진금액),
        "소진비중": 소진금액 / 총금액 if 총금액 else float("nan"),
        "후보SKU수": int((inv["정책판정"] != "정상").sum()),
        "전체SKU수": int(len(inv)),
    }


def weekly_wos_series(weekly: pd.DataFrame) -> pd.DataFrame:
    """전사 재고주수 추세(스파크라인용). 직전 4주 평균 판매속도를 분모로 쓴다."""
    w = weekly[~weekly["is_partial_week"].astype(bool)]
    g = w.groupby("week_end", as_index=False).agg(
        재고=("available_qty", "sum"), 순판매수량=("순판매수량", "sum")
    ).sort_values("week_end")
    g["속도_4주평균"] = g["순판매수량"].rolling(4, min_periods=1).mean()
    g["재고주수"] = (g["재고"] / g["속도_4주평균"]).where(g["속도_4주평균"] > 0)
    return g


# --------------------------------------------------------------------------
# A-2. 판정별 재고금액
# --------------------------------------------------------------------------
def policy_by_judgment(inv: pd.DataFrame) -> pd.DataFrame:
    g = inv.groupby("정책판정", as_index=False).agg(
        SKU수=("sku_id", "count"),
        재고수량=("available_qty", "sum"),
        재고금액=("inventory_value", "sum"),
        중위재고주수=("재고주수", "median"),
    )
    total = g["재고금액"].sum()
    g["금액비중"] = g["재고금액"] / total if total else float("nan")
    g["아이콘"] = g["정책판정"].map(JUDGMENT_ICON)
    return g.sort_values("재고금액", ascending=False)


# --------------------------------------------------------------------------
# A-3. 재고주수 분포
# --------------------------------------------------------------------------
WOS_CAP = 100.0


def wos_distribution(inv: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """히스토그램용. 100주 이상은 마지막 구간으로 묶고, 묶은 사실을 함께 돌려준다."""
    v = inv["재고주수"].dropna()
    capped = v.clip(upper=WOS_CAP)
    over = int((v > WOS_CAP).sum())
    무판매 = int(inv["재고주수"].isna().sum())      # D14: 판매속도 0은 미산출
    thresholds = {
        "reorder": sorted(inv["reorder_point_wos"].dropna().unique().tolist()),
        "target_min": sorted(inv["target_wos_min"].dropna().unique().tolist()),
        "target_max": sorted(inv["target_wos_max"].dropna().unique().tolist()),
        "clearance": sorted(inv["clearance_point_wos"].dropna().unique().tolist()),
    }
    meta = {"cap": WOS_CAP, "over_cap": over, "무판매제외": 무판매, "thresholds": thresholds,
            "표본": int(len(v))}
    return capped.to_frame("재고주수"), meta


# --------------------------------------------------------------------------
# A-4. 카테고리 × 판정
# --------------------------------------------------------------------------
def category_judgment_matrix(inv: pd.DataFrame, value: str = "inventory_value") -> pd.DataFrame:
    m = inv.pivot_table(index="대분류", columns="정책판정", values=value, aggfunc="sum", fill_value=0)
    cols = [c for c in JUDGMENT_ORDER if c in m.columns]
    return m[cols].loc[m.sum(axis=1).sort_values(ascending=False).index]


# --------------------------------------------------------------------------
# A-5. 임계값 민감도
# --------------------------------------------------------------------------
def policy_sensitivity(inv: pd.DataFrame, span: int = 5) -> pd.DataFrame:
    """임계값을 ±span주 움직였을 때 대상 SKU 수와 재고금액이 어떻게 변하는지.

    판정 규칙은 D15와 동일하다(경계 포함, 무판매 우선).
    """
    rows = []
    for off in range(-span, span + 1):
        wos = inv["재고주수"]
        무판매 = inv["판매속도_주"] == 0
        소진 = (~무판매) & (wos >= inv["clearance_point_wos"] + off)
        리오더 = (~무판매) & (~소진) & (wos <= inv["reorder_point_wos"] + off)
        rows.append(
            {
                "조정폭": off,
                "소진SKU수": int(소진.sum()),
                "소진금액": float(inv.loc[소진, "inventory_value"].sum()),
                "리오더SKU수": int(리오더.sum()),
                "현재값": off == 0,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 화면 B — 액션 후보
# --------------------------------------------------------------------------
ACTION_TABS = ["소진", "리오더", "무판매", "주의"]


def action_candidates(action: pd.DataFrame, 판정: str | None = None) -> pd.DataFrame:
    df = action if 판정 is None else action[action["정책판정"] == 판정]
    # 발주상태는 리오더 탭 상단 배너로 표시하므로 표에서는 뺀다(빈 값이 None으로 보인다)
    cols = ["sku_id", "상품명", "정책판정", "대분류", "색상", "사이즈",
            "available_qty", "inventory_value", "재고주수", "판매속도_주",
            "권고액션", "기존액션여부"]
    return df[[c for c in cols if c in df.columns]].sort_values("inventory_value", ascending=False)


def action_scatter(action: pd.DataFrame) -> pd.DataFrame:
    """재고금액 × 재고주수 산점도용. 색은 3분류까지만 쓴다(산점도는 모든 점이 인접 가능)."""
    return action[action["정책판정"].isin(["소진", "리오더", "무판매"])].copy()


# --------------------------------------------------------------------------
# 화면 C — 상품 성과
# --------------------------------------------------------------------------
def product_perf(product: pd.DataFrame, 대분류=None, 시즌=None) -> pd.DataFrame:
    df = product
    if 대분류:
        df = df[df["대분류"].isin(대분류)]
    if 시즌:
        df = df[df["시즌"].isin(시즌)]
    return df


def category_perf(product: pd.DataFrame) -> pd.DataFrame:
    g = product.groupby("대분류", as_index=False).agg(
        상품수=("product_id", "count"),
        순매출=("순매출", "sum"),
        가용공헌이익=("가용공헌이익", "sum"),
        유효판매수량=("유효판매수량", "sum"),
        완료반품수량=("완료반품수량", "sum"),
    )
    g["이익률"] = (g["가용공헌이익"] / g["순매출"]).where(g["순매출"] != 0)
    return g.sort_values("순매출", ascending=False)


def margin_bottom(product: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """이익률 하위. 공헌이익 적자 상품이 없으므로 '적자 탐지'가 아니라 '하위 관찰'이다."""
    df = product[product["순매출"] > 0].nsmallest(n, "이익률")
    return df.sort_values("이익률")


def overall_margin(product: pd.DataFrame) -> float:
    total = product["순매출"].sum()
    return product["가용공헌이익"].sum() / total if total else float("nan")


RETURN_MIN_BASE = 5


def return_rate_top(product: pd.DataFrame, n: int = 10) -> tuple[pd.DataFrame, int]:
    """반품률 상위. 완료 반품 5건 미만 상품은 표본 부족으로 제외하고 제외 수를 함께 돌려준다."""
    ok = product[product["완료반품수량"] >= RETURN_MIN_BASE]
    excluded = len(product) - len(ok)
    return ok.nlargest(n, "반품률").sort_values("반품률"), excluded


def overall_return_rate(product: pd.DataFrame) -> float:
    base = product["유효판매수량"].sum()
    return product["완료반품수량"].sum() / base if base else float("nan")


# --------------------------------------------------------------------------
# 화면 D — 추세
# --------------------------------------------------------------------------
def weekly_totals(weekly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """완전주 시계열과 부분주(기준일까지만 집계된 마지막 주)를 분리해 돌려준다."""
    g = weekly.groupby(["week_end", "is_partial_week"], as_index=False).agg(
        순매출=("순매출", "sum"),
        순판매수량=("순판매수량", "sum"),
        가용공헌이익=("가용공헌이익", "sum"),
        재고=("available_qty", "sum"),
    ).sort_values("week_end")
    full = g[~g["is_partial_week"].astype(bool)]
    partial = g[g["is_partial_week"].astype(bool)]
    return full, partial


def wow_movers(weekly: pd.DataFrame, n: int = 8) -> tuple[pd.DataFrame, str]:
    """마지막 완전주의 상품별 순매출 WoW 증감 상·하위."""
    full = weekly[~weekly["is_partial_week"].astype(bool)]
    last = full["week_end"].max()
    cur = full[full["week_end"] == last].dropna(subset=["순매출_WoW"])
    top = cur.nlargest(n, "순매출_WoW")
    bottom = cur.nsmallest(n, "순매출_WoW")
    out = pd.concat([bottom, top]).sort_values("순매출_WoW")
    return out[["product_id", "week_end", "순매출", "순매출_WoW"]], str(last)


def product_names(product: pd.DataFrame) -> dict[str, str]:
    return dict(zip(product["product_id"], product["상품명"]))
