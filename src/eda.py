"""data/converted의 CSV 전체에 대한 기초 EDA.

원칙 (CLAUDE.md 데이터 처리 규칙):
- 값을 수정·대체·삭제하지 않는다. 읽고 세기만 한다
- 극단값을 오류로 확정하지 않는다. 관찰된 사실과 판단을 분리해 기록한다
- 산출물은 outputs/reports/eda_report.md 하나뿐이다

실행:
    .venv/bin/python -m src.eda
"""

from __future__ import annotations

import re

import pandas as pd

from src import config

# 테이블별 관측단위(행 1개가 무엇을 뜻하는지)와 갱신 성격
OBSERVATION_UNIT = {
    "category_master": ("카테고리 1개", "마스터 (비주기)"),
    "product_master": ("상품 1개", "마스터 (비주기)"),
    "sku_master": ("SKU(상품×색상×사이즈) 1개", "마스터 (비주기)"),
    "channel_master": ("판매 채널 1개", "마스터 (비주기)"),
    "warehouse_master": ("창고 1개", "마스터 (비주기)"),
    "promotion": ("프로모션 1건", "이벤트 발생 시"),
    "inventory_policy": ("카테고리별 재고 정책 1건", "정책 개정 시"),
    "orders": ("주문 1건", "발생 시점 (연속)"),
    "order_item": ("주문 내 SKU 1줄", "발생 시점 (연속)"),
    "order_attribution": ("주문×채널 귀속 1줄", "발생 시점 (연속)"),
    "returns": ("반품 1건 (주문상세 단위)", "발생 시점 (연속)"),
    "promotion_application": ("프로모션 적용 1줄", "발생 시점 (연속)"),
    "purchase_order": ("발주 1건 (PO×SKU)", "발생 시점 (연속)"),
    "receipt": ("입고 1건 (PO 단위)", "발생 시점 (연속)"),
    "inventory_snapshot": ("시점×창고×SKU 재고 1줄", "스냅샷 (주 1회 + 월말)"),
    "action_log": ("액션 1건 (상품 단위)", "발생 시점 (비정기)"),
    "traffic_daily": ("일자×채널 1줄", "일 단위"),
}

# PK 후보 (복합키 포함)
PK_CANDIDATES = {
    "category_master": ["category_id"],
    "product_master": ["product_id"],
    "sku_master": ["sku_id"],
    "channel_master": ["channel_id"],
    "warehouse_master": ["warehouse_id"],
    "promotion": ["promotion_id"],
    "inventory_policy": ["policy_id"],
    "orders": ["order_id"],
    "order_item": ["order_item_id"],
    "order_attribution": ["attribution_id"],
    "returns": ["return_id"],
    "promotion_application": ["application_id"],
    "purchase_order": ["po_id"],
    "receipt": ["receipt_id"],
    "inventory_snapshot": ["snapshot_date", "warehouse_id", "sku_id"],
    "action_log": ["action_id"],
    "traffic_daily": ["date", "channel_id"],
}

# FK 후보: (자식컬럼, 부모테이블, 부모컬럼)
FK_CANDIDATES = {
    "product_master": [("category_id", "category_master", "category_id")],
    "sku_master": [("product_id", "product_master", "product_id")],
    "inventory_policy": [("category_id", "category_master", "category_id")],
    "orders": [("channel_id", "channel_master", "channel_id")],
    "order_item": [
        ("order_id", "orders", "order_id"),
        ("sku_id", "sku_master", "sku_id"),
        ("warehouse_id", "warehouse_master", "warehouse_id"),
    ],
    "order_attribution": [
        ("order_id", "orders", "order_id"),
        ("channel_id", "channel_master", "channel_id"),
    ],
    "returns": [("order_item_id", "order_item", "order_item_id")],
    "promotion_application": [
        ("promotion_id", "promotion", "promotion_id"),
        ("order_item_id", "order_item", "order_item_id"),
    ],
    "purchase_order": [("sku_id", "sku_master", "sku_id")],
    "receipt": [
        ("po_id", "purchase_order", "po_id"),
        ("sku_id", "sku_master", "sku_id"),
        ("warehouse_id", "warehouse_master", "warehouse_id"),
    ],
    "inventory_snapshot": [
        ("sku_id", "sku_master", "sku_id"),
        ("warehouse_id", "warehouse_master", "warehouse_id"),
    ],
    "action_log": [
        ("product_id", "product_master", "product_id"),
        ("sku_id", "sku_master", "sku_id"),
    ],
    "traffic_daily": [("channel_id", "channel_master", "channel_id")],
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
QTY_MONEY_RE = re.compile(r"(수량|금액|가$|원가|액$|예산|비$|cost|amount|qty|spend|value|할인값|수수료율)", re.I)


def load_all() -> dict[str, pd.DataFrame]:
    """converted CSV 전체를 문자열 그대로 읽는다. 타입 추론으로 값이 바뀌지 않게 한다."""
    frames = {}
    for path in sorted(config.CONVERTED_DIR.glob("*.csv")):
        frames[path.stem] = pd.read_csv(
            path, dtype=str, keep_default_na=False, na_values=[""], encoding=config.CSV_ENCODING
        )
    return frames


def classify(series: pd.Series) -> str:
    v = series.dropna().astype(str)
    if v.empty:
        return "전체공란"
    if v.map(lambda x: bool(DATE_RE.match(x))).all():
        return "날짜"
    if v.map(lambda x: bool(DATETIME_RE.match(x))).all():
        return "일시"
    num = pd.to_numeric(v, errors="coerce")
    if num.notna().all():
        return "정수" if (num % 1 == 0).all() else "실수"
    return "문자열"


def as_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def notation_variants(series: pd.Series) -> list[str]:
    """표기만 다른 범주값(앞뒤 공백, 대소문자, 내부 공백)을 찾는다. 수정하지 않고 보고만 한다."""
    v = series.dropna().astype(str)
    if v.empty:
        return []
    groups: dict[str, set[str]] = {}
    for x in v.unique():
        key = re.sub(r"\s+", "", x).lower()
        groups.setdefault(key, set()).add(x)
    return [" / ".join(sorted(s)) for s in groups.values() if len(s) > 1]


def table_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in frames.items():
        unit, cadence = OBSERVATION_UNIT.get(name, ("?", "?"))
        pk = PK_CANDIDATES.get(name, [])
        dup = int(df.duplicated(subset=pk).sum()) if pk else -1
        pk_null = int(df[pk].isna().any(axis=1).sum()) if pk else -1
        fk = "; ".join(f"{c}→{t}.{p}" for c, t, p in FK_CANDIDATES.get(name, [])) or "—"

        date_cols = [c for c in df.columns if classify(df[c]) in ("날짜", "일시")]
        rng = "—"
        if date_cols:
            main = date_cols[0]
            v = df[main].dropna().astype(str)
            rng = f"{main}: {v.min()} ~ {v.max()}"
        rows.append(
            {
                "테이블": name,
                "관측단위": unit,
                "행수": len(df),
                "열수": len(df.columns),
                "PK 후보": "+".join(pk) or "—",
                "PK 중복": dup,
                "PK 결측": pk_null,
                "FK 후보": fk,
                "날짜 범위": rng,
                "갱신 주기": cadence,
            }
        )
    return pd.DataFrame(rows)


def fk_orphans(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for child, rels in FK_CANDIDATES.items():
        for ccol, parent, pcol in rels:
            a = frames[child][ccol].dropna().astype(str)
            b = set(frames[parent][pcol].dropna().astype(str))
            miss = a[~a.isin(b)]
            rows.append(
                {
                    "관계": f"{child}.{ccol} → {parent}.{pcol}",
                    "검사행": len(a),
                    "결측(검사제외)": int(frames[child][ccol].isna().sum()),
                    "고아행": len(miss),
                    "고아값종류": miss.nunique(),
                }
            )
    return pd.DataFrame(rows)


def column_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in frames.items():
        for c in df.columns:
            s = df[c]
            kind = classify(s)
            n_null = int(s.isna().sum())
            row = {
                "테이블": name,
                "열": c,
                "자료형": kind,
                "결측수": n_null,
                "결측율": round(n_null / len(df) * 100, 1) if len(df) else 0.0,
                "고유값수": int(s.nunique(dropna=True)),
                "표기차이": " | ".join(notation_variants(s)) if kind == "문자열" else "",
            }
            if kind in ("정수", "실수") and QTY_MONEY_RE.search(str(c)):
                num = as_numeric(s)
                q = num.quantile([0, 0.25, 0.5, 0.75, 1.0])
                row.update(
                    {
                        "최소": q[0.0],
                        "P25": q[0.25],
                        "중위": q[0.5],
                        "P75": q[0.75],
                        "최대": q[1.0],
                        "음수건수": int((num < 0).sum()),
                        "0건수": int((num == 0).sum()),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def judgment_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """관찰된 사실을 4가지로 구분한다.

    구분은 해석이므로 근거가 되는 행 수를 함께 남긴다. 값은 손대지 않는다.
    """
    oi, o = frames["order_item"], frames["orders"]
    rt, al = frames["returns"], frames["action_log"]
    inv, td = frames["inventory_snapshot"], frames["traffic_daily"]
    po, rc, sku = frames["purchase_order"], frames["receipt"], frames["sku_master"]

    cancel_st = oi["order_item_status"].isin(["취소", "부분취소"])
    coupon_by_order = oi.assign(c=as_numeric(oi["쿠폰할인액"])).groupby("order_id")["c"].sum()
    code_orders = set(o.loc[o["쿠폰코드"].notna(), "order_id"])
    disc_orders = set(coupon_by_order[coupon_by_order > 0].index)

    rows = [
        # ---------- 정상 공란 ----------
        ("정상 공란", "order_item.cancel_date 결측",
         int(oi["cancel_date"].isna().sum()),
         "취소되지 않은 주문상세. 구매확정 8,625건과 정확히 일치"),
        ("정상 공란", "order_item.canceled_* = 0",
         int((as_numeric(oi["canceled_qty"]) == 0).sum()),
         "취소 수량이 없는 정상 건"),
        ("정상 공란", "returns.처리일 결측",
         int(rt["처리일"].isna().sum()),
         "처리상태='접수'(미완료) 32건과 정확히 일치. 완료건 중 처리일 없는 행 0건"),
        ("정상 공란", "action_log.completed_date 결측",
         int(al["completed_date"].isna().sum()),
         "완료 상태가 아닌 액션 27건과 정확히 일치"),
        ("정상 공란", "purchase_order.메모 결측",
         int(po["메모"].isna().sum()),
         "선택 입력 항목. 96.5%가 공란이라 필수 항목으로 보기 어려움"),
        ("정상 공란", "orders.쿠폰코드 결측",
         int(o["쿠폰코드"].isna().sum()),
         "쿠폰 미사용 주문. 단 아래 '확인 필요'의 쿠폰 불일치와 함께 볼 것"),
        ("정상 공란", "order_item 비용 3종 = 0",
         int((as_numeric(oi["fulfillment_cost_amount"]) == 0).sum()),
         "풀필먼트·포장·결제수수료가 0인 205건은 전부 status='취소'. 취소건 비용 미발생"),
        ("정상 공란", "inventory_snapshot.reserved/damaged = 0",
         int((as_numeric(inv["reserved_qty"]) == 0).sum()),
         "예약·불량 재고가 없는 정상 상태"),

        # ---------- 입력 누락 가능성 ----------
        ("입력 누락 가능성", "취소건인데 cancel_reason 없음",
         int((cancel_st & oi["cancel_reason"].isna()).sum()),
         "취소 206건 중 22건에 사유 없음. cancel_date는 206건 모두 있음"),
        ("입력 누락 가능성", "returns.반품사유 결측",
         int(rt["반품사유"].isna().sum()),
         "완료 반품 378건 중 63건, 접수 32건 중 3건에 사유 없음"),
        ("입력 누락 가능성", "order_item.주문시_상품명 결측",
         int(oi["주문시_상품명"].isna().sum()),
         "sku_id는 살아 있어 조인으로 확인 가능하나 원천 값은 비어 있음"),
        ("입력 누락 가능성", "receipt.송장번호 결측",
         int(rc["송장번호"].isna().sum()),
         "나머지 729건은 모두 고유값. 필수 항목으로 보이나 12건 누락"),
        ("입력 누락 가능성", "sku_master.보관로케이션 결측",
         int(sku["보관로케이션"].isna().sum()),
         "399개 SKU 중 1개만 로케이션 없음"),
        ("입력 누락 가능성", "inventory_snapshot.last_count_date 결측",
         int(inv["last_count_date"].isna().sum()),
         "12,369행 중 1행(2026-06-30/WH01/S00045)만 실사일 없음"),

        # ---------- 구조적 분석 한계 ----------
        ("구조적 분석 한계", "in_transit_qty 전 행 0",
         int((as_numeric(inv["in_transit_qty"]) == 0).sum()),
         "입고 예정 재고가 데이터에 존재하지 않음 → 이동 중 재고를 반영한 가용성 분석 불가"),
        ("구조적 분석 한계", "order_item.수량 값이 1~2뿐",
         len(oi),
         "수량 분포가 1(8,548) / 2(283)로 사실상 고정 → 수량 기반 구매 패턴 분석 의미 없음"),
        ("구조적 분석 한계", "action_log.sku_id 결측",
         int(al["sku_id"].isna().sum()),
         "액션 유형과 결측이 완전히 대응. SKU 단위 액션 분석 불가, 상품 단위로 통일 필요"),
        ("구조적 분석 한계", "action_log 표본 크기",
         len(al),
         "32건뿐이고 상태가 액션 유형으로 완전히 결정됨 → 실행률·효과 분석 불가"),
        ("구조적 분석 한계", "promotion 표본 크기",
         len(frames["promotion"]),
         "프로모션 4건 → 프로모션 간 효과 비교는 통계적으로 성립하지 않음"),
        ("구조적 분석 한계", "purchase_order 기간 단절",
         int((po["발주일"] >= "2026-06-01").sum()),
         "6~7월 발주 0건. CLAUDE.md 확정 규칙에 따라 발주 중단 상태로 해석 → 리드타임·리오더 실적 분석 범위는 5월까지"),
        ("구조적 분석 한계", "inventory_snapshot 간격 불균등",
         inv["snapshot_date"].nunique(),
         "31개 시점이 주 1회(일요일) + 월말 혼합 → 주간 비교 시 간격 보정 필요"),

        # ---------- 확인 필요 ----------
        ("확인 필요", "쿠폰코드와 쿠폰할인액 불일치 (코드 있음/할인 0)",
         len(code_orders - disc_orders),
         f"쿠폰코드 보유 주문 {len(code_orders)}건 중 할인액이 0"),
        ("확인 필요", "쿠폰코드와 쿠폰할인액 불일치 (코드 없음/할인 있음)",
         len(disc_orders - code_orders),
         f"쿠폰할인 발생 주문 {len(disc_orders)}건 중 코드가 비어 있음. 두 항목의 관계 정의 필요"),
        ("확인 필요", "orders.customer_id 결측",
         int(o["customer_id"].isna().sum()),
         "14.3%. 비회원 주문인지 수집 누락인지에 따라 신규·재구매 분석의 모수가 달라짐"),
        ("확인 필요", "traffic_daily.ad_spend = 0",
         int((as_numeric(td["ad_spend"]) == 0).sum()),
         "181건 전부 CH05. 해당 채널만 광고 미집행인지 데이터 미수집인지 확인 필요"),
        ("확인 필요", "action_log.result_note 결측",
         int(al["result_note"].isna().sum()),
         "완료 5건 중에도 결과 기록이 없는 건이 있는지 확인 필요"),
    ]
    return pd.DataFrame(rows, columns=["구분", "항목", "근거 행수", "근거"])


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def build_report(frames: dict[str, pd.DataFrame]) -> str:
    tbl = table_summary(frames)
    fk = fk_orphans(frames)
    col = column_summary(frames)

    qty = col[col["최소"].notna()] if "최소" in col else pd.DataFrame()
    neg = qty[qty["음수건수"] > 0] if len(qty) else pd.DataFrame()
    zero = qty[qty["0건수"] > 0] if len(qty) else pd.DataFrame()
    miss = col[col["결측수"] > 0].sort_values("결측율", ascending=False)
    notation = col[col["표기차이"] != ""]

    parts = [
        "# 기초 EDA 리포트",
        "",
        f"- 대상: `data/converted/` CSV **{len(frames)}개** (원본 `{config.RAW_XLSX.name}`의 데이터 시트)",
        f"- 총 행수: **{sum(len(d) for d in frames.values()):,}행** / 총 열수: **{sum(len(d.columns) for d in frames.values())}열**",
        f"- 분석 기준일: **{config.ANALYSIS_DATE}** (CLAUDE.md 확정 규칙)",
        "- 생성: `.venv/bin/python -m src.eda`",
        "",
        "> 값을 수정·대체·삭제하지 않았다. 극단값도 오류로 확정하지 않고 관찰 사실로만 기록한다.",
        "",
        "---",
        "",
        "## 1. 테이블 수준",
        "",
        _md(tbl),
        "",
        "### FK 후보 검사 (참조 무결성)",
        "",
        _md(fk),
        "",
        "---",
        "",
        "## 2. 열 수준",
        "",
        "### 2-1. 결측이 있는 열",
        "",
        _md(miss[["테이블", "열", "자료형", "결측수", "결측율", "고유값수"]]) if len(miss) else "결측 없음.",
        "",
        "### 2-2. 범주 표기 차이 (공백·대소문자만 다른 값)",
        "",
        _md(notation[["테이블", "열", "표기차이"]]) if len(notation) else "**표기 차이 발견 없음.** 문자열 열 전체에서 앞뒤 공백·대소문자·내부 공백만 다른 동일 값이 검출되지 않았다.",
        "",
        "### 2-3. 수량·금액 열의 분위수",
        "",
        _md(qty[["테이블", "열", "최소", "P25", "중위", "P75", "최대", "음수건수", "0건수"]]) if len(qty) else "해당 열 없음.",
        "",
        "### 2-4. 음수 값",
        "",
        _md(neg[["테이블", "열", "최소", "음수건수"]]) if len(neg) else "**수량·금액 열에서 음수 값 0건.**",
        "",
        "### 2-5. 0 값",
        "",
        _md(zero[["테이블", "열", "0건수", "중위"]]) if len(zero) else "0 값 없음.",
        "",
        "---",
        "",
        "## 3. 판단 분리",
        "",
        "관찰된 사실을 4가지로 구분한다. **구분은 해석이므로 근거 행 수를 함께 적는다.**",
        "값을 고치거나 극단값을 오류로 확정하지 않았다.",
        "",
    ]

    jm = judgment_summary(frames)
    labels = [
        ("정상 공란", "업무상 값이 없는 것이 맞는 경우. 결측을 오류로 처리하면 안 된다."),
        ("입력 누락 가능성", "값이 있어야 할 자리인데 비어 있는 경우. **원인 확인 전까지 채우지 않는다.**"),
        ("구조적 분석 한계", "데이터 구조상 특정 분석이 불가능한 경우. 보정이 아니라 **분석 범위를 좁혀야 한다.**"),
        ("확인 필요", "정상인지 오류인지 데이터만으로 판단할 수 없는 경우. **답을 받기 전까지 가정하지 않는다.**"),
    ]
    for i, (label, note) in enumerate(labels, start=1):
        sub = jm[jm["구분"] == label]
        parts += [f"### 3-{i}. {label}", "", note, "", _md(sub[["항목", "근거 행수", "근거"]]), ""]

    parts += [
        "---",
        "",
        "## 4. 전체 열 목록",
        "",
        _md(col[["테이블", "열", "자료형", "결측수", "결측율", "고유값수"]]),
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    frames = load_all()
    report = build_report(frames)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_DIR / "eda_report.md").write_text(report, encoding="utf-8")
    print(f"테이블 {len(frames)}개 EDA 완료 → {config.REPORTS_DIR / 'eda_report.md'}")


if __name__ == "__main__":
    main()
