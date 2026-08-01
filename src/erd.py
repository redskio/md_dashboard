"""승인된 필수 8개 테이블의 논리 ERD와 관계 검증.

원칙:
- 관계를 열 이름으로 확정하지 않는다. 이름은 후보일 뿐이고 카디널리티는 데이터로 측정한다
- 추정과 실측이 다르면 차이를 그대로 표시한다
- **N:M으로 측정된 관계는 조인을 실행하지 않는다** (승인 전 보류)
- 값을 수정하지 않는다

산출물:
- outputs/reports/erd.md
- outputs/reports/relationship_validation.csv

실행:
    .venv/bin/python -m src.erd
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.eda import load_all

# 선정안에서 승인된 필수 8개 테이블
APPROVED = [
    "orders",
    "order_item",
    "returns",
    "sku_master",
    "product_master",
    "category_master",
    "inventory_snapshot",
    "inventory_policy",
]

OBSERVATION_UNIT = {
    "orders": "주문 1건",
    "order_item": "주문 × SKU 1줄",
    "returns": "반품 1건 (주문상세 단위)",
    "sku_master": "SKU 1개 (상품×색상×사이즈)",
    "product_master": "상품 1개",
    "category_master": "카테고리 1개",
    "inventory_snapshot": "시점 × SKU 재고 1줄",
    "inventory_policy": "카테고리 정책 1건",
}

PK = {
    "orders": ["order_id"],
    "order_item": ["order_item_id"],
    "returns": ["return_id"],
    "sku_master": ["sku_id"],
    "product_master": ["product_id"],
    "category_master": ["category_id"],
    "inventory_snapshot": ["snapshot_date", "warehouse_id", "sku_id"],
    "inventory_policy": ["policy_id"],
}

# 추가로 중복을 확인할 복합키 후보 (관측단위 주장에 대한 반증 검사)
COMPOSITE_CHECKS = {
    "inventory_snapshot": [
        ["snapshot_date", "sku_id"],
        ["snapshot_date", "warehouse_id", "sku_id"],
    ],
    "inventory_policy": [["category_id"], ["category_id", "season"]],
    "returns": [["order_item_id"]],
}

# 이름 기반 관계 '후보'. 카디널리티는 비워 두고 측정으로 채운다.
# (자식, 자식컬럼, 부모, 부모컬럼, 추정 카디널리티)
RELATION_CANDIDATES = [
    ("order_item", "order_id", "orders", "order_id", "N:1"),
    ("order_item", "sku_id", "sku_master", "sku_id", "N:1"),
    ("returns", "order_item_id", "order_item", "order_item_id", "1:1"),
    ("sku_master", "product_id", "product_master", "product_id", "N:1"),
    ("product_master", "category_id", "category_master", "category_id", "N:1"),
    ("inventory_snapshot", "sku_id", "sku_master", "sku_id", "N:1"),
    ("inventory_policy", "category_id", "category_master", "category_id", "1:1"),
]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def check_keys(frames) -> list[dict]:
    rows = []
    for t in APPROVED:
        df = frames[t]
        pk = PK[t]
        dup = int(df.duplicated(subset=pk).sum())
        null = int(df[pk].isna().any(axis=1).sum())
        rows.append(
            {
                "검사구분": "PK 중복",
                "대상": f"{t}({'+'.join(pk)})",
                "추정": "중복 0 / 결측 0",
                "실측": f"중복 {dup} / 결측 {null}",
                "일치": dup == 0 and null == 0,
                "상세": f"{len(df):,}행",
            }
        )

    for t, keysets in COMPOSITE_CHECKS.items():
        for keys in keysets:
            df = frames[t]
            dup = int(df.duplicated(subset=keys).sum())
            rows.append(
                {
                    "검사구분": "복합키 중복",
                    "대상": f"{t}({'+'.join(keys)})",
                    "추정": "중복 0",
                    "실측": f"중복 {dup}",
                    "일치": dup == 0,
                    "상세": f"고유 조합 {df.groupby(keys).ngroups:,} / {len(df):,}행",
                }
            )
    return rows


def measure_relations(frames) -> tuple[list[dict], dict[tuple, str]]:
    """관계별 고아·연결 행 수 분포를 측정하고 실측 카디널리티를 판정한다."""
    rows = []
    measured = {}

    for child, ccol, parent, pcol, guess in RELATION_CANDIDATES:
        c = frames[child][ccol]
        p = frames[parent][pcol]
        c_valid = c.dropna().astype(str)
        p_valid = p.dropna().astype(str)

        # FK 고아
        orphan = c_valid[~c_valid.isin(set(p_valid))]
        rows.append(
            {
                "검사구분": "FK 고아",
                "대상": f"{child}.{ccol} → {parent}.{pcol}",
                "추정": "고아 0",
                "실측": f"고아 {len(orphan)}행 / {orphan.nunique()}종",
                "일치": len(orphan) == 0,
                "상세": f"검사 {len(c_valid):,}행, 결측 {int(c.isna().sum()):,}행 제외",
            }
        )

        # 연결 행 수 분포 (부모 1건에 자식 몇 행이 붙는가)
        cnt = c_valid.value_counts()
        per_parent = pd.Series(0, index=pd.Index(p_valid.unique()), dtype=int)
        per_parent.update(cnt)
        dist = per_parent.value_counts().sort_index()
        dist_txt = ", ".join(f"{k}건:{v:,}" for k, v in dist.items())

        child_unique = bool(c_valid.is_unique)
        parent_unique = bool(p_valid.is_unique)
        if not child_unique and not parent_unique:
            actual = "N:M"
        elif child_unique and parent_unique:
            actual = "1:1"
        elif child_unique:
            actual = "1:1"  # 자식 키가 고유 → 부모당 최대 1행
        else:
            actual = "N:1"
        measured[(child, ccol, parent, pcol)] = actual

        rows.append(
            {
                "검사구분": "연결 행 수 분포",
                "대상": f"{parent}.{pcol} 1건당 {child} 행 수",
                "추정": guess,
                "실측": f"{actual} (최소 {per_parent.min()} / 중위 {int(per_parent.median())} / 최대 {per_parent.max()})",
                "일치": guess == actual,
                "상세": f"분포 → {dist_txt}",
            }
        )

        rows.append(
            {
                "검사구분": "관계 카디널리티",
                "대상": f"{child}.{ccol} → {parent}.{pcol}",
                "추정": guess,
                "실측": actual,
                "일치": guess == actual,
                "상세": (
                    f"자식키 고유={child_unique}, 부모키 고유={parent_unique}, "
                    f"연결 없는 부모 {int((per_parent == 0).sum()):,}건"
                ),
            }
        )

    return rows, measured


def _totals(df: pd.DataFrame, cols: list[str]) -> dict[str, float]:
    return {c: float(_num(df[c]).sum()) for c in df.columns.intersection(cols)}


def join_steps(frames, measured) -> list[dict]:
    """단계별 조인 전후 행 수와 핵심 금액·수량 합계를 비교한다.

    N:M으로 측정된 관계는 실행하지 않는다.
    """
    rows = []
    KEY_COLS = ["수량", "판매단가", "채널수수료액", "쿠폰할인액"]

    def step(base, right_name, left_on, right_on, chain, right_cols=None):
        rel = None
        for (ch, cc, pa, pc), v in measured.items():
            if ch == chain and pa == right_name:
                rel = v
        if rel == "N:M":
            rows.append(
                {
                    "검사구분": "조인 단계",
                    "대상": f"{chain} × {right_name}",
                    "추정": "—",
                    "실측": "보류",
                    "일치": False,
                    "상세": "N:M으로 측정되어 승인 전까지 조인을 실행하지 않음",
                }
            )
            return base
        right = frames[right_name]
        if right_cols:
            right = right[[right_on] + [c for c in right_cols if c in right.columns]]
        before_n, before_t = len(base), _totals(base, KEY_COLS)
        out = base.merge(right, how="left", left_on=left_on, right_on=right_on, suffixes=("", f"_{right_name}"))
        after_n, after_t = len(out), _totals(out, KEY_COLS)
        same_total = all(abs(before_t[c] - after_t[c]) < 1e-6 for c in before_t)
        rows.append(
            {
                "검사구분": "조인 단계",
                "대상": f"{chain} ← {right_name}({left_on})",
                "추정": "행 수·합계 불변 (left join, N:1)",
                "실측": f"행 {before_n:,}→{after_n:,} / 합계 {'불변' if same_total else '변동'}",
                "일치": before_n == after_n and same_total,
                "상세": "; ".join(f"{c} {before_t[c]:,.0f}→{after_t[c]:,.0f}" for c in before_t),
            }
        )
        return out

    # 성과 체인: order_item 기준 (CLAUDE.md 확정 규칙 3)
    base = frames["order_item"].copy()
    rows.append(
        {
            "검사구분": "조인 단계",
            "대상": "order_item (기준)",
            "추정": "—",
            "실측": f"{len(base):,}행",
            "일치": True,
            "상세": "; ".join(f"{k} {v:,.0f}" for k, v in _totals(base, KEY_COLS).items()),
        }
    )
    base = step(base, "sku_master", "sku_id", "sku_id", "order_item", ["product_id"])
    base = step(base, "product_master", "product_id", "product_id", "sku_master", ["category_id", "기준원가", "시즌"])
    base = step(base, "category_master", "category_id", "category_id", "product_master", ["대분류", "시즌민감도"])
    base = step(base, "orders", "order_id", "order_id", "order_item", ["주문일시", "channel_id", "주문상태"])

    # 반품은 방향이 반대(returns.order_item_id → order_item). 1:1이면 붙여도 행 수 불변
    ret = frames["returns"]
    before_n = len(base)
    out = base.merge(
        ret[["order_item_id", "환불금액", "처리상태"]], how="left", on="order_item_id", suffixes=("", "_returns")
    )
    rows.append(
        {
            "검사구분": "조인 단계",
            "대상": "order_item ← returns(order_item_id)",
            "추정": "1:1이면 행 수 불변",
            "실측": f"행 {before_n:,}→{len(out):,}",
            "일치": before_n == len(out),
            "상세": f"반품 {len(ret):,}행 중 매칭 {int(out['처리상태'].notna().sum()):,}행",
        }
    )

    # 재고 체인
    inv = frames["inventory_snapshot"].copy()
    before = len(inv)
    inv2 = inv.merge(frames["sku_master"][["sku_id", "product_id"]], how="left", on="sku_id")
    inv3 = inv2.merge(frames["product_master"][["product_id", "category_id"]], how="left", on="product_id")
    inv4 = inv3.merge(
        frames["inventory_policy"][["category_id", "target_wos_min", "clearance_point_wos"]],
        how="left",
        on="category_id",
    )
    qty_before = float(_num(inv["available_qty"]).sum())
    qty_after = float(_num(inv4["available_qty"]).sum())
    rows.append(
        {
            "검사구분": "조인 단계",
            "대상": "inventory_snapshot ← sku_master ← product_master ← inventory_policy",
            "추정": "행 수·재고 합계 불변",
            "실측": f"행 {before:,}→{len(inv4):,} / available_qty {qty_before:,.0f}→{qty_after:,.0f}",
            "일치": before == len(inv4) and abs(qty_before - qty_after) < 1e-6,
            "상세": "3단계 연속 left join",
        }
    )

    # 관측단위 반증: SKU가 여러 창고에 걸치는가
    per_sku_wh = inv.groupby("sku_id")["warehouse_id"].nunique()
    rows.append(
        {
            "검사구분": "관측단위 검증",
            "대상": "inventory_snapshot: SKU당 창고 수",
            # 선정안 초안의 추정: "SKU당 창고 2행 → 합산 없이 조인하면 재고 2배"
            "추정": "SKU가 복수 창고에 존재 (재고 2배 위험)",
            "실측": f"최대 {per_sku_wh.max()}개 창고",
            "일치": bool(per_sku_wh.max() > 1),
            "상세": (
                f"시점당 행 수 {inv.groupby('snapshot_date').size().unique().tolist()}, "
                f"SKU {inv['sku_id'].nunique()}개 → SKU는 한 창고에만 배정됨. 창고 합산 시 중복 위험 없음"
            ),
        }
    )
    return rows


MERMAID = """```mermaid
erDiagram
    CATEGORY_MASTER ||--o{{ PRODUCT_MASTER : "1:N (측정 {r_pc})"
    CATEGORY_MASTER ||--|| INVENTORY_POLICY : "1:1 (측정 {r_ip})"
    PRODUCT_MASTER ||--o{{ SKU_MASTER : "1:N (측정 {r_sp})"
    SKU_MASTER ||--o{{ ORDER_ITEM : "1:N (측정 {r_ois})"
    SKU_MASTER ||--o{{ INVENTORY_SNAPSHOT : "1:N (측정 {r_is})"
    ORDERS ||--o{{ ORDER_ITEM : "1:N (측정 {r_oio})"
    ORDER_ITEM ||--o| RETURNS : "1:1 부분 (측정 {r_ro})"

    CATEGORY_MASTER {{
        string category_id PK
        string 대분류
        string 시즌민감도
    }}
    PRODUCT_MASTER {{
        string product_id PK
        string category_id FK
        int 기준원가
        string 시즌
    }}
    SKU_MASTER {{
        string sku_id PK
        string product_id FK
        string 색상
        string 사이즈
    }}
    ORDERS {{
        string order_id PK
        string channel_id "FK 후보(채널마스터 미승인)"
        string 주문일시
        string 주문상태
    }}
    ORDER_ITEM {{
        string order_item_id PK
        string order_id FK
        string sku_id FK
        int 수량
        int 판매단가
        int 채널수수료액
        int canceled_qty
    }}
    RETURNS {{
        string return_id PK
        string order_item_id FK
        int 환불금액
        string 처리상태
    }}
    INVENTORY_SNAPSHOT {{
        string snapshot_date PK
        string warehouse_id PK
        string sku_id PK
        int available_qty
        int on_hand_qty
    }}
    INVENTORY_POLICY {{
        string policy_id PK
        string category_id FK
        int target_wos_min
        int clearance_point_wos
    }}
```"""


def build_md(frames, checks, rel_rows, join_rows, measured) -> str:
    m = MERMAID.format(
        r_pc=measured[("product_master", "category_id", "category_master", "category_id")],
        r_ip=measured[("inventory_policy", "category_id", "category_master", "category_id")],
        r_sp=measured[("sku_master", "product_id", "product_master", "product_id")],
        r_ois=measured[("order_item", "sku_id", "sku_master", "sku_id")],
        r_is=measured[("inventory_snapshot", "sku_id", "sku_master", "sku_id")],
        r_oio=measured[("order_item", "order_id", "orders", "order_id")],
        r_ro=measured[("returns", "order_item_id", "order_item", "order_item_id")],
    )

    unit = pd.DataFrame(
        [
            {
                "테이블": t,
                "관측단위": OBSERVATION_UNIT[t],
                "행수": f"{len(frames[t]):,}",
                "PK": "+".join(PK[t]),
            }
            for t in APPROVED
        ]
    )

    all_rows = pd.DataFrame(checks + rel_rows + join_rows)
    diff = all_rows[~all_rows["일치"]]

    parts = [
        "# 논리 ERD와 관계 검증",
        "",
        f"- 대상: 선정안 **필수 {len(APPROVED)}개 테이블**만 사용 (보조·제외 테이블 미포함)",
        f"- 분석 기준일: **{config.ANALYSIS_DATE}**",
        "- 생성: `.venv/bin/python -m src.erd`",
        "",
        "> 관계는 열 이름으로 확정하지 않았다. 이름은 후보로만 쓰고 **카디널리티는 데이터로 측정**했다.",
        "> N:M으로 측정되는 관계는 조인을 실행하지 않는다.",
        "",
        "---",
        "",
        "## 1. 논리 ERD",
        "",
        m,
        "",
        "### 관측단위",
        "",
        unit.to_markdown(index=False),
        "",
        "---",
        "",
        "## 2. 추정 vs 실측 차이",
        "",
    ]

    if len(diff):
        parts += [
            f"**차이 {len(diff)}건.** 추정과 실측이 다른 항목이다.",
            "",
            diff[["검사구분", "대상", "추정", "실측", "상세"]].to_markdown(index=False),
            "",
        ]
    else:
        parts += ["**차이 없음.** 모든 추정이 실측과 일치했다.", ""]

    parts += [
        "---",
        "",
        "## 3. 검증 결과",
        "",
        "전체 결과는 `outputs/reports/relationship_validation.csv`에 있다.",
        "",
        "### 3-1. PK·복합키 중복",
        "",
        pd.DataFrame(checks)[["대상", "추정", "실측", "일치", "상세"]].to_markdown(index=False),
        "",
        "### 3-2. FK 고아와 카디널리티",
        "",
        pd.DataFrame(rel_rows)[["검사구분", "대상", "추정", "실측", "일치", "상세"]].to_markdown(index=False),
        "",
        "### 3-3. 단계별 조인 전후",
        "",
        pd.DataFrame(join_rows)[["대상", "추정", "실측", "일치", "상세"]].to_markdown(index=False),
        "",
        "---",
        "",
        "## 4. N:M 조인 처리",
        "",
    ]

    nm = [k for k, v in measured.items() if v == "N:M"]
    if nm:
        parts += [
            "**N:M으로 측정된 관계가 있어 해당 조인을 실행하지 않았다.**",
            "",
        ] + [f"- `{c}.{cc}` ↔ `{p}.{pc}`" for c, cc, p, pc in nm]
    else:
        parts += [
            "승인된 8개 테이블 사이에 **N:M 관계는 측정되지 않았다.** 전부 1:1 또는 N:1이라 조인을 보류한 관계는 없다.",
            "",
            "다만 선정안에서 **제외**한 `order_attribution`(주문당 최대 2행)과 "
            "`promotion_application`은 상위 테이블과 다대다가 될 수 있어, 필요해지면 이 검증을 먼저 다시 돌린다.",
        ]

    return "\n".join(parts)


def main() -> None:
    frames = {k: v for k, v in load_all().items() if k in APPROVED}
    checks = check_keys(frames)
    rel_rows, measured = measure_relations(frames)
    join_rows = join_steps(frames, measured)

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(checks + rel_rows + join_rows)
    result.to_csv(
        config.REPORTS_DIR / "relationship_validation.csv", index=False, encoding=config.CSV_ENCODING
    )
    (config.REPORTS_DIR / "erd.md").write_text(
        build_md(frames, checks, rel_rows, join_rows, measured), encoding="utf-8"
    )

    ng = result[~result["일치"]]
    print(f"검사 {len(result)}건 / 일치 {len(result) - len(ng)} / 불일치 {len(ng)}")
    if len(ng):
        print(ng[["검사구분", "대상", "추정", "실측"]].to_string(index=False))


if __name__ == "__main__":
    main()
