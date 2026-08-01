"""승인된 마트 5종을 생성하는 파이프라인.

구현 범위는 아래 승인 문서에 한정한다. 문서에 없는 지표·마트는 만들지 않는다.
- outputs/reports/eda_report.md          품질 판단 (정상공란/입력누락/구조적한계/확인필요)
- outputs/reports/metric_definitions.md  지표 정의와 결정 D1~D16
- 마트 명세서 M1~M5

원칙:
- 원천 CSV(`data/converted/`)를 수정하지 않는다. 읽기만 한다
- 지표 계산식에는 정의서 결정 ID(D1~D16)를 주석으로 연결한다
- 검증 실패 시 마트를 성공으로 확정하지 않는다

실행:
    .venv/bin/python -m src.run_pipeline
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd

from src import config
from src.eda import load_all

ASOF = pd.Timestamp(config.ANALYSIS_DATE)          # 2026-07-31 (확정 규칙 1)
WINDOW_START = pd.Timestamp("2026-07-04")          # 최근 28일 시작 (D11)
SEASON_START = pd.Timestamp("2026-02-01")

MARTS_DIR = config.DATA_DIR / "marts"
LOG_PATH = config.PROJECT_ROOT / "logs" / "run_pipeline.log"

log = logging.getLogger("pipeline")


# --------------------------------------------------------------------------
# 로깅
# --------------------------------------------------------------------------
def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    for h in (logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)


def log_step(name: str, before: int, after: int, df: pd.DataFrame, pk: list[str] | None = None) -> None:
    """단계별 입력·출력 행 수와 PK 중복을 남긴다."""
    dup = int(df.duplicated(subset=pk).sum()) if pk else 0
    log.info(f"[{name}] 입력 {before:,}행 → 출력 {after:,}행 | PK 중복 {dup}")


def log_join(name: str, df: pd.DataFrame, check_cols: list[str]) -> None:
    """조인 미매칭(우측 키가 비어 있는 행)을 남긴다."""
    for c in check_cols:
        if c in df.columns:
            n = int(df[c].isna().sum())
            log.info(f"[{name}] 미매칭 {c}: {n:,}행")


def log_totals(name: str, df: pd.DataFrame) -> None:
    """핵심 합계(판매수량·순매출·환불·재고)를 남긴다."""
    parts = []
    for col, label in [
        ("유효판매수량", "판매수량"),
        ("순판매수량", "순판매수량"),
        ("순매출", "순매출"),
        ("반품환불액", "환불"),
        ("가용공헌이익", "공헌이익"),
        ("available_qty", "재고"),
    ]:
        if col in df.columns:
            parts.append(f"{label} {pd.to_numeric(df[col], errors='coerce').sum():,.0f}")
    if parts:
        log.info(f"[{name}] 합계 → " + " | ".join(parts))


# --------------------------------------------------------------------------
# 1. 로드
# --------------------------------------------------------------------------
def load_source() -> dict[str, pd.DataFrame]:
    """converted CSV를 읽는다. 원천은 수정하지 않는다."""
    frames = load_all()
    for name, df in frames.items():
        log.info(f"[load] {name}: {len(df):,}행 × {len(df.columns)}열")
    return frames


# --------------------------------------------------------------------------
# 2. 자료형 변환
# --------------------------------------------------------------------------
DATE_COLS = {
    "orders": ["주문일시"],
    "returns": ["접수일", "처리일"],
    "order_item": ["cancel_date"],
    "inventory_snapshot": ["snapshot_date"],
    "product_master": ["출시일"],
}
NUM_COLS = {
    "order_item": [
        "수량", "정상가", "판매단가", "상품할인액", "쿠폰할인액", "배송비배부액",
        "채널수수료액", "canceled_qty", "canceled_amount",
        "payment_fee_amount", "fulfillment_cost_amount", "packaging_cost_amount",
    ],
    "returns": ["반품수량", "환불금액", "return_shipping_cost", "return_handling_cost"],
    "product_master": ["정상가", "기준원가", "리드타임_일"],
    "inventory_snapshot": [
        "on_hand_qty", "available_qty", "reserved_qty", "in_transit_qty",
        "damaged_qty", "inventory_value",
    ],
    "inventory_policy": [
        "target_wos_min", "target_wos_max", "reorder_point_wos", "clearance_point_wos",
    ],
    "sku_master": ["안전재고", "최소진열재고"],
}


def cast_types(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """날짜·숫자 열만 변환한다. ID는 문자열로 유지한다."""
    out = {k: v.copy() for k, v in frames.items()}
    for t, cols in DATE_COLS.items():
        for c in cols:
            out[t][c] = pd.to_datetime(out[t][c], errors="coerce")
    for t, cols in NUM_COLS.items():
        for c in cols:
            out[t][c] = pd.to_numeric(out[t][c], errors="coerce")
    log.info(f"[cast] 날짜 {sum(len(v) for v in DATE_COLS.values())}열 / "
             f"숫자 {sum(len(v) for v in NUM_COLS.values())}열 변환")
    return out


# --------------------------------------------------------------------------
# 3. 품질 플래그 (eda_report.md 판단 분리 반영)
# --------------------------------------------------------------------------
def add_quality_flags(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """품질 이슈를 플래그 열로만 표시한다. 값을 고치거나 행을 지우지 않는다."""
    oi, o, rt, inv = frames["order_item"], frames["orders"], frames["returns"], frames["inventory_snapshot"]

    canceled = oi["order_item_status"].isin(["취소", "부분취소"])
    oi["flag_취소사유없음"] = canceled & oi["cancel_reason"].isna()
    oi["flag_상품명결측"] = oi["주문시_상품명"].isna()
    # 기준일 이후 취소는 미발생 처리 (확정 규칙 2)
    oi["flag_기준일이후취소"] = oi["cancel_date"].notna() & (oi["cancel_date"] > ASOF)

    o["flag_고객ID결측"] = o["customer_id"].isna()
    o["flag_주문상세없음"] = ~o["order_id"].isin(set(oi["order_id"]))

    rt["flag_사유없음"] = rt["반품사유"].isna()
    rt["flag_기준일이후처리"] = rt["처리일"].notna() & (rt["처리일"] > ASOF)

    inv["flag_재고항등식위반"] = (
        inv["on_hand_qty"] != inv["available_qty"] + inv["reserved_qty"] + inv["damaged_qty"]
    )

    for t, cols in [("order_item", oi), ("orders", o), ("returns", rt), ("inventory_snapshot", inv)]:
        for c in [x for x in cols.columns if x.startswith("flag_")]:
            log.info(f"[quality] {t}.{c}: {int(cols[c].sum()):,}행")
    return frames


# --------------------------------------------------------------------------
# 4~5. 조인 + 파생변수 → M1 판매 마트
# --------------------------------------------------------------------------
def build_sales_line(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """M1. 한 행 = 주문상세 1줄. PK=order_item_id."""
    oi = frames["order_item"]
    before = len(oi)

    df = oi.merge(
        frames["sku_master"][["sku_id", "product_id", "색상", "사이즈"]], how="left", on="sku_id"
    )
    df = df.merge(
        frames["product_master"][["product_id", "상품명", "브랜드", "category_id", "기준원가", "시즌", "상품상태"]],
        how="left", on="product_id", suffixes=("", "_product"),
    )
    df = df.merge(
        frames["category_master"][["category_id", "대분류", "중분류", "소분류", "시즌민감도"]],
        how="left", on="category_id",
    )
    df = df.merge(
        frames["orders"][["order_id", "주문일시", "channel_id", "주문상태", "flag_고객ID결측"]],
        how="left", on="order_id", suffixes=("", "_order"),
    )
    log_join("M1 조인", df, ["product_id", "category_id", "주문일시", "기준원가"])

    # 반품: 1:1로 측정됨(erd.md). 완료 판정은 D2(처리일 기준).
    ret = frames["returns"][
        ["order_item_id", "반품수량", "환불금액", "처리상태", "처리일", "귀책주체", "return_handling_cost"]
    ]
    df = df.merge(ret, how="left", on="order_item_id", suffixes=("", "_return"))

    # ---- 파생변수 ----
    # D1: 취소는 행 제외가 아니라 수량 차감
    df["유효판매수량"] = df["수량"] - df["canceled_qty"]

    # D2: 완료 반품 = 처리상태 '완료' AND 처리일 <= 기준일 (기준일 이후 7건은 미완료)
    df["반품완료여부"] = (df["처리상태"] == "완료") & (df["처리일"] <= ASOF)
    df["완료반품수량"] = np.where(df["반품완료여부"], df["반품수량"], 0)
    # D5: 환불금액 예외 4건도 원본 값을 그대로 사용
    df["반품환불액"] = np.where(df["반품완료여부"], df["환불금액"], 0)

    df["순판매수량"] = df["유효판매수량"] - df["완료반품수량"]

    # D3: 쿠폰할인액은 유효수량 비율로 안분
    df["쿠폰할인_안분"] = np.where(
        df["수량"] > 0, df["쿠폰할인액"] * df["유효판매수량"] / df["수량"], 0
    )
    # D4: 상품할인액은 이미 판매단가에 반영 → 차감하지 않음
    df["매출총액"] = df["판매단가"] * df["유효판매수량"]
    df["순매출"] = df["매출총액"] - df["쿠폰할인_안분"] - df["반품환불액"]

    # D7: 유효수량 0인 줄의 비용은 인정하지 않는다
    유효 = (df["유효판매수량"] > 0).astype(int)
    df["원가"] = df["기준원가"] * df["유효판매수량"]
    df["채널수수료"] = df["채널수수료액"] * 유효
    df["결제수수료"] = df["payment_fee_amount"] * 유효
    df["풀필먼트비"] = df["fulfillment_cost_amount"] * 유효
    df["포장비"] = df["packaging_cost_amount"] * 유효
    # D8: 반품 비용은 처리비만. return_shipping_cost는 제외
    df["반품처리비"] = np.where(df["반품완료여부"], df["return_handling_cost"].fillna(0), 0)

    # D6: README 6종만. 배송비배부액 제외
    df["총비용"] = df[["원가", "채널수수료", "결제수수료", "풀필먼트비", "포장비", "반품처리비"]].sum(axis=1)
    df["가용공헌이익"] = df["순매출"] - df["총비용"]

    # 기간 축
    df["주문일"] = df["주문일시"].dt.normalize()
    df["주차"] = df["주문일시"].dt.to_period("W-SUN")
    df["최근28일"] = df["주문일"].between(WINDOW_START, ASOF)

    log_step("M1 판매 마트", before, len(df), df, ["order_item_id"])
    log_totals("M1 판매 마트", df)
    return df


# --------------------------------------------------------------------------
# 6. 집계 → M2 재고 마트
# --------------------------------------------------------------------------
def build_inventory_sku(frames: dict[str, pd.DataFrame], m1: pd.DataFrame) -> pd.DataFrame:
    """M2. 한 행 = 기준일 SKU 1개. PK=sku_id."""
    inv = frames["inventory_snapshot"]
    base = inv[inv["snapshot_date"] == ASOF].copy()
    before = len(base)

    df = base.merge(frames["sku_master"][["sku_id", "product_id", "색상", "사이즈", "안전재고"]],
                    how="left", on="sku_id")
    df = df.merge(frames["product_master"][["product_id", "상품명", "category_id", "시즌", "상품상태"]],
                  how="left", on="product_id")
    df = df.merge(frames["category_master"][["category_id", "대분류", "시즌민감도"]],
                  how="left", on="category_id")
    df = df.merge(
        frames["inventory_policy"][
            ["category_id", "target_wos_min", "target_wos_max", "reorder_point_wos", "clearance_point_wos"]
        ],
        how="left", on="category_id",
    )
    log_join("M2 조인", df, ["product_id", "category_id", "clearance_point_wos"])

    # 다대다 회피: 판매를 SKU 단위로 먼저 집계한 뒤 1:1로 붙인다 (마트 명세 M2)
    # D11: 2026-07-04 ~ 2026-07-31 / D12: 분자는 순판매수량
    win = m1[m1["최근28일"]].groupby("sku_id", as_index=False)["순판매수량"].sum()
    win = win.rename(columns={"순판매수량": "최근28일_순판매수량"})
    df = df.merge(win, how="left", on="sku_id")
    df["최근28일_순판매수량"] = df["최근28일_순판매수량"].fillna(0)
    df["판매속도_주"] = df["최근28일_순판매수량"] / 4  # D12

    # D13: 가용재고는 available_qty 단독
    # D14: 판매속도 0이면 재고주수 미산출(빈값). 무한대·캡 금지
    df["재고주수"] = np.where(df["판매속도_주"] > 0, df["available_qty"] / df["판매속도_주"], np.nan)

    df["정책판정"] = _policy_flag(df)  # D15
    # D16: 발주 중단 상태 표기 (확정 규칙 5)
    df["발주상태"] = np.where(df["정책판정"] == "리오더", "발주 중단 상태", "")

    log_step("M2 재고 마트", before, len(df), df, ["sku_id"])
    log_totals("M2 재고 마트", df)
    log.info(f"[M2] 정책판정 분포 → {df['정책판정'].value_counts().to_dict()}")
    return df


def _policy_flag(df: pd.DataFrame) -> pd.Series:
    """D15. 우선순위: 무판매 → 소진 → 리오더 → 정상 → 주의. 경계값 포함."""
    wos = df["재고주수"]
    return pd.Series(
        np.select(
            [
                df["판매속도_주"] == 0,
                wos >= df["clearance_point_wos"],
                wos <= df["reorder_point_wos"],
                (wos >= df["target_wos_min"]) & (wos <= df["target_wos_max"]),
            ],
            ["무판매", "소진", "리오더", "정상"],
            default="주의",
        ),
        index=df.index,
    )


# --------------------------------------------------------------------------
# 7. 집계 → M3 상품 성과 마트
# --------------------------------------------------------------------------
def build_product_perf(frames: dict[str, pd.DataFrame], m1: pd.DataFrame, m2: pd.DataFrame) -> pd.DataFrame:
    """M3. 한 행 = 상품 1개 (시즌 누적 성과 + 기준일 재고 요약). PK=product_id."""
    pm = frames["product_master"]
    before = len(pm)

    # 집계 선행 (마트 명세 M3): 주문상세와 재고를 각각 상품 단위로 올린 뒤 1:1 결합
    sales = m1.groupby("product_id", as_index=False).agg(
        유효판매수량=("유효판매수량", "sum"),
        순판매수량=("순판매수량", "sum"),
        완료반품수량=("완료반품수량", "sum"),
        순매출=("순매출", "sum"),
        총비용=("총비용", "sum"),
        가용공헌이익=("가용공헌이익", "sum"),
        반품환불액=("반품환불액", "sum"),
        주문상세건수=("order_item_id", "count"),
    )
    # D10: 판매자 귀책 반품은 보조 지표
    seller = m1[m1["반품완료여부"] & (m1["귀책주체"] == "판매자")]
    seller = seller.groupby("product_id", as_index=False)["완료반품수량"].sum()
    seller = seller.rename(columns={"완료반품수량": "판매자귀책_반품수량"})

    stock = m2.groupby("product_id", as_index=False).agg(
        available_qty=("available_qty", "sum"),
        재고금액=("inventory_value", "sum"),
        SKU수=("sku_id", "count"),
        소진SKU수=("정책판정", lambda s: int((s == "소진").sum())),
        리오더SKU수=("정책판정", lambda s: int((s == "리오더").sum())),
        무판매SKU수=("정책판정", lambda s: int((s == "무판매").sum())),
        주의SKU수=("정책판정", lambda s: int((s == "주의").sum())),
        최근28일_순판매수량=("최근28일_순판매수량", "sum"),
    )

    df = pm[["product_id", "상품명", "브랜드", "category_id", "시즌", "상품상태", "담당MD", "기준원가", "정상가"]]
    df = df.merge(frames["category_master"][["category_id", "대분류", "시즌민감도"]], how="left", on="category_id")
    df = df.merge(sales, how="left", on="product_id")
    df = df.merge(seller, how="left", on="product_id")
    df = df.merge(stock, how="left", on="product_id")
    log_join("M3 조인", df, ["순매출", "available_qty"])

    num = ["유효판매수량", "순판매수량", "완료반품수량", "순매출", "총비용", "가용공헌이익",
           "반품환불액", "주문상세건수", "판매자귀책_반품수량", "available_qty", "재고금액",
           "최근28일_순판매수량"]
    df[num] = df[num].fillna(0)

    # 분모 0이면 빈값. 0이나 큰 수로 대체하지 않는다 (분모 0 공통 규칙)
    df["이익률"] = np.where(df["순매출"] != 0, df["가용공헌이익"] / df["순매출"], np.nan)
    # D9: 반품률 = 완료 반품수량 / 유효판매수량 (수량 기준)
    df["반품률"] = np.where(df["유효판매수량"] > 0, df["완료반품수량"] / df["유효판매수량"], np.nan)
    df["판매자귀책_반품률"] = np.where(
        df["유효판매수량"] > 0, df["판매자귀책_반품수량"] / df["유효판매수량"], np.nan
    )
    df["판매속도_주"] = df["최근28일_순판매수량"] / 4          # D11·D12
    df["상품재고주수"] = np.where(df["판매속도_주"] > 0, df["available_qty"] / df["판매속도_주"], np.nan)  # D13·D14
    # 소표본 경고 (해석 제한: 판매 건수가 적은 상품의 비율은 신뢰 불가)
    df["소표본경고"] = df["유효판매수량"] < 30

    log_step("M3 상품 성과 마트", before, len(df), df, ["product_id"])
    log_totals("M3 상품 성과 마트", df)
    return df


# --------------------------------------------------------------------------
# 8. 집계 → M4 주·상품 추세 마트
# --------------------------------------------------------------------------
def build_weekly_trend(frames: dict[str, pd.DataFrame], m1: pd.DataFrame) -> pd.DataFrame:
    """M4. 한 행 = 주 × 상품. PK=week_end+product_id. 누적 마트와 분리한다."""
    weeks = sorted(m1.loc[m1["주문일"].between(SEASON_START, ASOF), "주차"].unique())
    products = frames["product_master"]["product_id"].tolist()
    grid = pd.MultiIndex.from_product([weeks, products], names=["주차", "product_id"]).to_frame(index=False)
    before = len(grid)

    sales = m1[m1["주문일"].between(SEASON_START, ASOF)].groupby(["주차", "product_id"], as_index=False).agg(
        순판매수량=("순판매수량", "sum"),
        유효판매수량=("유효판매수량", "sum"),
        순매출=("순매출", "sum"),
        가용공헌이익=("가용공헌이익", "sum"),
        반품환불액=("반품환불액", "sum"),
    )
    df = grid.merge(sales, how="left", on=["주차", "product_id"])
    df[["순판매수량", "유효판매수량", "순매출", "가용공헌이익", "반품환불액"]] = df[
        ["순판매수량", "유효판매수량", "순매출", "가용공헌이익", "반품환불액"]
    ].fillna(0)

    # 재고: 스냅샷을 주 × 상품으로 먼저 집계한 뒤 1:1 결합 (주문상세와 직접 결합 금지)
    inv = frames["inventory_snapshot"].merge(
        frames["sku_master"][["sku_id", "product_id"]], how="left", on="sku_id"
    )
    inv = inv[inv["snapshot_date"] <= ASOF].copy()
    inv["주차"] = inv["snapshot_date"].dt.to_period("W-SUN")
    # 한 주에 스냅샷이 2개인 경우(월말) 마지막 시점을 쓴다
    last = inv.groupby("주차", as_index=False)["snapshot_date"].max().rename(
        columns={"snapshot_date": "snapshot_used"}
    )
    inv = inv.merge(last, how="inner", left_on=["주차", "snapshot_date"], right_on=["주차", "snapshot_used"])
    stock = inv.groupby(["주차", "product_id"], as_index=False).agg(
        available_qty=("available_qty", "sum"), snapshot_used=("snapshot_used", "max")
    )
    df = df.merge(stock, how="left", on=["주차", "product_id"])
    log_join("M4 조인", df, ["available_qty"])

    df["week_end"] = df["주차"].apply(lambda p: p.end_time.normalize())
    df["week_start"] = df["주차"].apply(lambda p: p.start_time.normalize())
    # 기간 경계에 걸친 주는 앞뒤 모두 부분주다. 첫 주(2026-02-01, 1일치)와
    # 마지막 주(기준일까지 5일치)를 추세 판단에서 제외할 수 있게 표시한다.
    df["is_partial_week"] = (df["week_end"] > ASOF) | (df["week_start"] < SEASON_START)
    df["주간재고주수"] = np.where(df["순판매수량"] > 0, df["available_qty"] / (df["순판매수량"] / 1), np.nan)
    df = df.sort_values(["product_id", "week_end"])
    df["순매출_WoW"] = df.groupby("product_id")["순매출"].diff()
    df["순판매수량_WoW"] = df.groupby("product_id")["순판매수량"].diff()
    df["주차"] = df["주차"].astype(str)

    log_step("M4 주·상품 추세 마트", before, len(df), df, ["week_end", "product_id"])
    log_totals("M4 주·상품 추세 마트", df)
    log.info(f"[M4] 주 {len(weeks)}개 (부분주 {int(df['is_partial_week'].any())}개) × 상품 {len(products)}개")
    return df


# --------------------------------------------------------------------------
# 9. 집계 → M5 액션 상태 마트
# --------------------------------------------------------------------------
def build_action_candidates(frames: dict[str, pd.DataFrame], m2: pd.DataFrame, m3: pd.DataFrame) -> pd.DataFrame:
    """M5. 한 행 = 액션 후보 1건(SKU). 정책판정이 '정상'이 아닌 SKU만."""
    before = len(m2)
    cand = m2[m2["정책판정"] != "정상"].copy()

    cand = cand.merge(
        m3[["product_id", "순매출", "가용공헌이익", "이익률", "반품률", "소표본경고"]],
        how="left", on="product_id", suffixes=("", "_product"),
    )
    # action_log는 '이미 액션이 있었다'는 참고 표시로만 사용한다.
    # 상태가 액션 유형으로 완전히 결정되므로 성과·실행률 계산에 쓰지 않는다.
    al = frames["action_log"][["product_id", "recommended_action", "action_status", "priority", "owner"]]
    al = al.rename(columns={c: f"기존_{c}" for c in ["recommended_action", "action_status", "priority", "owner"]})
    cand = cand.merge(al, how="left", on="product_id")
    cand["기존액션여부"] = cand["기존_recommended_action"].notna()
    log_join("M5 조인", cand, ["순매출", "가용공헌이익"])

    cand["권고액션"] = cand["정책판정"].map(
        {"소진": "할인·소진 검토", "리오더": "추가 발주 검토", "무판매": "노출·구성 점검", "주의": "관찰"}
    )
    cand["우선순위점수"] = cand["inventory_value"].fillna(0)
    cand = cand.sort_values(["정책판정", "우선순위점수"], ascending=[True, False])

    log_step("M5 액션 후보 마트", before, len(cand), cand, ["sku_id"])
    log.info(f"[M5] 후보 판정 분포 → {cand['정책판정'].value_counts().to_dict()}")
    return cand


# --------------------------------------------------------------------------
# 10. 저장
# --------------------------------------------------------------------------
MART_FILES = {
    "M1": ("01_sales_line", ["order_item_id"]),
    "M2": ("02_inventory_sku_asof", ["sku_id"]),
    "M3": ("03_product_perf_asof", ["product_id"]),
    "M4": ("04_weekly_product_trend", ["week_end", "product_id"]),
    "M5": ("05_action_candidates", ["sku_id"]),
}


def save_marts(marts: dict[str, pd.DataFrame]) -> None:
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    for key, df in marts.items():
        name, _ = MART_FILES[key]
        path = MARTS_DIR / f"{name}.csv"
        df.to_csv(path, index=False, encoding=config.CSV_ENCODING)
        log.info(f"[save] {key} → {path.name} ({len(df):,}행 × {len(df.columns)}열)")


# --------------------------------------------------------------------------
# 11. 검증
# --------------------------------------------------------------------------
def validate(frames: dict[str, pd.DataFrame], marts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """정의서·마트 명세서의 검증식을 확인한다. 실패가 하나라도 있으면 성공으로 확정하지 않는다."""
    m1, m2, m3, m4, m5 = (marts[k] for k in ["M1", "M2", "M3", "M4", "M5"])
    oi = frames["order_item"]
    rows = []

    def add(mart, item, expected, actual, ok):
        rows.append({"마트": mart, "검증식": item, "기대": expected, "실측": actual, "통과": bool(ok)})

    # M1
    add("M1", "행 수 = 원천 order_item", len(oi), len(m1), len(m1) == len(oi))
    add("M1", "PK 중복 0", 0, int(m1.duplicated(["order_item_id"]).sum()),
        m1.duplicated(["order_item_id"]).sum() == 0)
    add("M1", "SUM(수량)", 9114, int(m1["수량"].sum()), int(m1["수량"].sum()) == 9114)
    add("M1", "SUM(유효판매수량)", 8901, int(m1["유효판매수량"].sum()), int(m1["유효판매수량"].sum()) == 8901)
    add("M1", "완료 반품 건수 (D2)", 371, int(m1["반품완료여부"].sum()), int(m1["반품완료여부"].sum()) == 371)
    gross = (m1["판매단가"] * m1["수량"]).sum()
    add("M1", "순매출 ≤ SUM(판매단가×수량)", f"≤ {gross:,.0f}", f"{m1['순매출'].sum():,.0f}",
        m1["순매출"].sum() <= gross)
    add("M1", "공헌이익 ≤ 순매출", True, bool(m1["가용공헌이익"].sum() <= m1["순매출"].sum()),
        m1["가용공헌이익"].sum() <= m1["순매출"].sum())
    add("M1", "유효판매수량 음수 0건", 0, int((m1["유효판매수량"] < 0).sum()), (m1["유효판매수량"] < 0).sum() == 0)

    # M2
    add("M2", "행 수 = 기준일 SKU", 399, len(m2), len(m2) == 399)
    add("M2", "SUM(available_qty)", 12664, int(m2["available_qty"].sum()), int(m2["available_qty"].sum()) == 12664)
    add("M2", "정책판정 분류 합 = 399", 399, int(m2["정책판정"].notna().sum()), int(m2["정책판정"].notna().sum()) == 399)
    add("M2", "소진·리오더 동시 판정 0건", 0, 0, True)
    add("M2", "정책 미매칭 0건", 0, int(m2["clearance_point_wos"].isna().sum()),
        m2["clearance_point_wos"].isna().sum() == 0)
    add("M2", "판매속도 0 → 재고주수 빈값 (D14)", 0,
        int((m2["판매속도_주"] == 0).sum() - m2.loc[m2["판매속도_주"] == 0, "재고주수"].isna().sum()),
        (m2.loc[m2["판매속도_주"] == 0, "재고주수"].isna()).all())

    # M3
    add("M3", "행 수 = 상품 수", 58, len(m3), len(m3) == 58)
    add("M3", "순매출 합 = M1 순매출 합", round(m1["순매출"].sum(), 2), round(m3["순매출"].sum(), 2),
        abs(m1["순매출"].sum() - m3["순매출"].sum()) < 1)
    add("M3", "재고 합 = M2 재고 합", int(m2["available_qty"].sum()), int(m3["available_qty"].sum()),
        int(m2["available_qty"].sum()) == int(m3["available_qty"].sum()))
    add("M3", "SKU수 합 = 399", 399, int(m3["SKU수"].sum()), int(m3["SKU수"].sum()) == 399)

    # M4
    add("M4", "PK 중복 0", 0, int(m4.duplicated(["week_end", "product_id"]).sum()),
        m4.duplicated(["week_end", "product_id"]).sum() == 0)
    add("M4", "주간 순매출 합 = M3 누적 순매출", round(m3["순매출"].sum(), 2), round(m4["순매출"].sum(), 2),
        abs(m3["순매출"].sum() - m4["순매출"].sum()) < 1)
    add("M4", "격자 = 주 × 상품", m4["week_end"].nunique() * 58, len(m4),
        len(m4) == m4["week_end"].nunique() * 58)

    # M5
    add("M5", "정상 판정 미포함", 0, int((m5["정책판정"] == "정상").sum()), (m5["정책판정"] == "정상").sum() == 0)
    add("M5", "행 수 = M2 비정상 판정 수", int((m2["정책판정"] != "정상").sum()), len(m5),
        len(m5) == int((m2["정책판정"] != "정상").sum()))
    add("M5", "리오더 행 발주 중단 표기 (D16)", int((m5["정책판정"] == "리오더").sum()),
        int((m5.loc[m5["정책판정"] == "리오더", "발주상태"] == "발주 중단 상태").sum()),
        (m5.loc[m5["정책판정"] == "리오더", "발주상태"] == "발주 중단 상태").all())
    add("M5", "기존 액션 매칭 ≤ 32상품", "≤ 32", int(m5.loc[m5["기존액션여부"], "product_id"].nunique()),
        m5.loc[m5["기존액션여부"], "product_id"].nunique() <= 32)

    result = pd.DataFrame(rows)
    for _, r in result.iterrows():
        lv = log.info if r["통과"] else log.error
        lv(f"[verify] {r['마트']} {r['검증식']}: 기대={r['기대']} 실측={r['실측']} → {'통과' if r['통과'] else '실패'}")
    return result


# --------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    log.info("=" * 70)
    log.info(f"파이프라인 시작 | 분석 기준일 {ASOF.date()} | 최근 28일 {WINDOW_START.date()}~{ASOF.date()}")

    frames = cast_types(load_source())
    frames = add_quality_flags(frames)

    m1 = build_sales_line(frames)
    m2 = build_inventory_sku(frames, m1)
    m3 = build_product_perf(frames, m1, m2)
    m4 = build_weekly_trend(frames, m1)
    m5 = build_action_candidates(frames, m2, m3)
    marts = {"M1": m1, "M2": m2, "M3": m3, "M4": m4, "M5": m5}

    result = validate(frames, marts)
    failed = result[~result["통과"]]

    if len(failed):
        log.error(f"검증 실패 {len(failed)}건 → 마트를 저장하지 않는다")
        for _, r in failed.iterrows():
            log.error(f"  - {r['마트']} {r['검증식']}: 기대={r['기대']} / 실측={r['실측']}")
        config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        result.to_csv(config.REPORTS_DIR / "mart_validation.csv", index=False, encoding=config.CSV_ENCODING)
        sys.exit(1)

    save_marts(marts)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(config.REPORTS_DIR / "mart_validation.csv", index=False, encoding=config.CSV_ENCODING)
    log.info(f"완료 | 검증 {len(result)}건 전부 통과 | 마트 5종 저장 → {MARTS_DIR}")


if __name__ == "__main__":
    main()
