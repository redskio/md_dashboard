# 기초 EDA 리포트

- 대상: `data/converted/` CSV **17개** (원본 `ganaswim_dataset.xlsx`의 데이터 시트)
- 총 행수: **40,349행** / 총 열수: **165열**
- 분석 기준일: **2026-07-31** (CLAUDE.md 확정 규칙)
- 생성: `.venv/bin/python -m src.eda`

> 값을 수정·대체·삭제하지 않았다. 극단값도 오류로 확정하지 않고 관찰 사실로만 기록한다.

---

## 1. 테이블 수준

| 테이블                | 관측단위                  |   행수 |   열수 | PK 후보                           |   PK 중복 |   PK 결측 | FK 후보                                                                                          | 날짜 범위                                                | 갱신 주기              |
|:----------------------|:--------------------------|-------:|-------:|:----------------------------------|----------:|----------:|:-------------------------------------------------------------------------------------------------|:---------------------------------------------------------|:-----------------------|
| action_log            | 액션 1건 (상품 단위)      |     32 |     13 | action_id                         |         0 |         0 | product_id→product_master.product_id; sku_id→sku_master.sku_id                                   | decision_date: 2026-04-13 ~ 2026-07-03                   | 발생 시점 (비정기)     |
| category_master       | 카테고리 1개              |     19 |      6 | category_id                       |         0 |         0 | —                                                                                                | —                                                        | 마스터 (비주기)        |
| channel_master        | 판매 채널 1개             |      5 |      6 | channel_id                        |         0 |         0 | —                                                                                                | —                                                        | 마스터 (비주기)        |
| inventory_policy      | 카테고리별 재고 정책 1건  |     19 |     11 | policy_id                         |         0 |         0 | category_id→category_master.category_id                                                          | effective_from: 2026-02-01 ~ 2026-02-01                  | 정책 개정 시           |
| inventory_snapshot    | 시점×창고×SKU 재고 1줄    |  12369 |     10 | snapshot_date+warehouse_id+sku_id |         0 |         0 | sku_id→sku_master.sku_id; warehouse_id→warehouse_master.warehouse_id                             | snapshot_date: 2026-02-01 ~ 2026-07-31                   | 스냅샷 (주 1회 + 월말) |
| order_attribution     | 주문×채널 귀속 1줄        |   7470 |      7 | attribution_id                    |         0 |         0 | order_id→orders.order_id; channel_id→channel_master.channel_id                                   | attributed_at: 2026-02-01 08:35:13 ~ 2026-07-31 22:58:56 | 발생 시점 (연속)       |
| order_item            | 주문 내 SKU 1줄           |   8831 |     20 | order_item_id                     |         0 |         0 | order_id→orders.order_id; sku_id→sku_master.sku_id; warehouse_id→warehouse_master.warehouse_id   | cancel_date: 2026-02-06 ~ 2026-08-02                     | 발생 시점 (연속)       |
| orders                | 주문 1건                  |   7044 |      9 | order_id                          |         0 |         0 | channel_id→channel_master.channel_id                                                             | 주문일시: 2026-02-01 08:35:13 ~ 2026-07-31 22:58:56      | 발생 시점 (연속)       |
| product_master        | 상품 1개                  |     58 |     14 | product_id                        |         0 |         0 | category_id→category_master.category_id                                                          | 출시일: 2025-10-03 ~ 2026-07-17                          | 마스터 (비주기)        |
| promotion             | 프로모션 1건              |      4 |      9 | promotion_id                      |         0 |         0 | —                                                                                                | 시작일: 2026-03-06 ~ 2026-07-13                          | 이벤트 발생 시         |
| promotion_application | 프로모션 적용 1줄         |   1300 |      6 | application_id                    |         0 |         0 | promotion_id→promotion.promotion_id; order_item_id→order_item.order_item_id                      | applied_at: 2026-03-06 08:54:09 ~ 2026-07-19 22:47:44    | 발생 시점 (연속)       |
| purchase_order        | 발주 1건 (PO×SKU)         |    741 |     10 | po_id                             |         0 |         0 | sku_id→sku_master.sku_id                                                                         | 발주일: 2026-02-01 ~ 2026-05-31                          | 발생 시점 (연속)       |
| receipt               | 입고 1건 (PO 단위)        |    741 |      9 | receipt_id                        |         0 |         0 | po_id→purchase_order.po_id; sku_id→sku_master.sku_id; warehouse_id→warehouse_master.warehouse_id | 실입고일: 2026-03-07 ~ 2026-06-23                        | 발생 시점 (연속)       |
| returns               | 반품 1건 (주문상세 단위)  |    410 |     12 | return_id                         |         0 |         0 | order_item_id→order_item.order_item_id                                                           | 접수일: 2026-02-05 ~ 2026-07-31                          | 발생 시점 (연속)       |
| sku_master            | SKU(상품×색상×사이즈) 1개 |    399 |      9 | sku_id                            |         0 |         0 | product_id→product_master.product_id                                                             | —                                                        | 마스터 (비주기)        |
| traffic_daily         | 일자×채널 1줄             |    905 |      9 | date+channel_id                   |         0 |         0 | channel_id→channel_master.channel_id                                                             | date: 2026-02-01 ~ 2026-07-31                            | 일 단위                |
| warehouse_master      | 창고 1개                  |      2 |      5 | warehouse_id                      |         0 |         0 | —                                                                                                | —                                                        | 마스터 (비주기)        |

### FK 후보 검사 (참조 무결성)

| 관계                                                            |   검사행 |   결측(검사제외) |   고아행 |   고아값종류 |
|:----------------------------------------------------------------|---------:|-----------------:|---------:|-------------:|
| product_master.category_id → category_master.category_id        |       58 |                0 |        0 |            0 |
| sku_master.product_id → product_master.product_id               |      399 |                0 |        0 |            0 |
| inventory_policy.category_id → category_master.category_id      |       19 |                0 |        0 |            0 |
| orders.channel_id → channel_master.channel_id                   |     7044 |                0 |        0 |            0 |
| order_item.order_id → orders.order_id                           |     8831 |                0 |        0 |            0 |
| order_item.sku_id → sku_master.sku_id                           |     8831 |                0 |        0 |            0 |
| order_item.warehouse_id → warehouse_master.warehouse_id         |     8831 |                0 |        0 |            0 |
| order_attribution.order_id → orders.order_id                    |     7470 |                0 |        0 |            0 |
| order_attribution.channel_id → channel_master.channel_id        |     7470 |                0 |        0 |            0 |
| returns.order_item_id → order_item.order_item_id                |      410 |                0 |        0 |            0 |
| promotion_application.promotion_id → promotion.promotion_id     |     1300 |                0 |        0 |            0 |
| promotion_application.order_item_id → order_item.order_item_id  |     1300 |                0 |        0 |            0 |
| purchase_order.sku_id → sku_master.sku_id                       |      741 |                0 |        0 |            0 |
| receipt.po_id → purchase_order.po_id                            |      741 |                0 |        0 |            0 |
| receipt.sku_id → sku_master.sku_id                              |      741 |                0 |        0 |            0 |
| receipt.warehouse_id → warehouse_master.warehouse_id            |      741 |                0 |        0 |            0 |
| inventory_snapshot.sku_id → sku_master.sku_id                   |    12369 |                0 |        0 |            0 |
| inventory_snapshot.warehouse_id → warehouse_master.warehouse_id |    12369 |                0 |        0 |            0 |
| action_log.product_id → product_master.product_id               |       32 |                0 |        0 |            0 |
| action_log.sku_id → sku_master.sku_id                           |       11 |               21 |        0 |            0 |
| traffic_daily.channel_id → channel_master.channel_id            |      905 |                0 |        0 |            0 |

---

## 2. 열 수준

### 2-1. 결측이 있는 열

| 테이블             | 열              | 자료형   |   결측수 |   결측율 |   고유값수 |
|:-------------------|:----------------|:---------|---------:|---------:|-----------:|
| order_item         | cancel_reason   | 문자열   |     8647 |     97.9 |          5 |
| order_item         | cancel_date     | 날짜     |     8625 |     97.7 |        120 |
| purchase_order     | 메모            | 문자열   |      715 |     96.5 |          1 |
| action_log         | result_note     | 문자열   |       28 |     87.5 |          2 |
| orders             | 쿠폰코드        | 문자열   |     6011 |     85.3 |          3 |
| action_log         | completed_date  | 날짜     |       27 |     84.4 |          5 |
| action_log         | sku_id          | 문자열   |       21 |     65.6 |         11 |
| action_log         | decision_date   | 날짜     |       12 |     37.5 |         20 |
| returns            | 반품사유        | 문자열   |       66 |     16.1 |          5 |
| orders             | customer_id     | 문자열   |     1008 |     14.3 |       3035 |
| returns            | 처리일          | 날짜     |       32 |      7.8 |        152 |
| receipt            | 송장번호        | 문자열   |       12 |      1.6 |        729 |
| sku_master         | 보관로케이션    | 문자열   |        1 |      0.3 |        190 |
| order_item         | 주문시_상품명   | 문자열   |       20 |      0.2 |         58 |
| inventory_snapshot | last_count_date | 날짜     |        1 |      0   |          7 |

### 2-2. 범주 표기 차이 (공백·대소문자만 다른 값)

**표기 차이 발견 없음.** 문자열 열 전체에서 앞뒤 공백·대소문자·내부 공백만 다른 동일 값이 검출되지 않았다.

### 2-3. 수량·금액 열의 분위수

| 테이블                | 열                      |      최소 |          P25 |       중위 |            P75 |            최대 |   음수건수 |   0건수 |
|:----------------------|:------------------------|----------:|-------------:|-----------:|---------------:|----------------:|-----------:|--------:|
| channel_master        | 수수료율                |     0.025 |      0.029   |      0.058 |      0.105     |      0.16       |          0 |       0 |
| inventory_snapshot    | on_hand_qty             |     0     |     12       |     22     |     36         |    104          |          0 |     621 |
| inventory_snapshot    | available_qty           |     0     |     12       |     21     |     35         |    104          |          0 |     669 |
| inventory_snapshot    | reserved_qty            |     0     |      0       |      0     |      0         |      2          |          0 |    9621 |
| inventory_snapshot    | in_transit_qty          |     0     |      0       |      0     |      0         |      0          |          0 |   12369 |
| inventory_snapshot    | damaged_qty             |     0     |      0       |      0     |      0         |      1          |          0 |   12270 |
| inventory_snapshot    | inventory_value         |     0     | 285000       | 533400     | 969000         |      3.5409e+06 |          0 |     621 |
| order_item            | 수량                    |     1     |      1       |      1     |      1         |      2          |          0 |       0 |
| order_item            | 정상가                  | 15000     |  50000       |  61000     |  78000         |  90000          |          0 |       0 |
| order_item            | 판매단가                | 12800     |  47300       |  60000     |  77000         |  90000          |          0 |       0 |
| order_item            | 상품할인액              |     0     |      0       |      0     |      0         |  26600          |          0 |    6638 |
| order_item            | 쿠폰할인액              |     0     |      0       |      0     |      0         |   8800          |          0 |    7203 |
| order_item            | 배송비배부액            |     0     |      0       |      0     |   3000         |   3000          |          0 |    6536 |
| order_item            | 채널수수료액            |   353     |   1666.5     |   2407     |   4741.5       |  28160          |          0 |       0 |
| order_item            | canceled_qty            |     0     |      0       |      0     |      0         |      2          |          0 |    8625 |
| order_item            | canceled_amount         |     0     |      0       |      0     |      0         | 172000          |          0 |    8625 |
| order_item            | payment_fee_amount      |     0     |   1044.5     |   1402     |   1806         |   4482          |          0 |     205 |
| order_item            | fulfillment_cost_amount |     0     |   2200       |   2200     |   2200         |   2550          |          0 |     205 |
| order_item            | packaging_cost_amount   |     0     |    450       |    450     |    450         |    550          |          0 |     205 |
| product_master        | 정상가                  | 15000     |  31500       |  50000     |  63750         |  90000          |          0 |       0 |
| product_master        | 기준원가                |  7300     |  14575       |  22000     |  29275         |  41500          |          0 |       0 |
| promotion             | 할인값                  |     0.1   |      0.115   |      0.135 |      0.1575    |      0.18       |          0 |       0 |
| promotion             | 예산                    |     7e+06 |      8.5e+06 |      1e+07 |      1.275e+07 |      1.8e+07    |          0 |       0 |
| promotion_application | discount_amount         |  1200     |   4900       |   6900     |   9025         |  26600          |          0 |       0 |
| purchase_order        | 발주수량                |     8     |     14       |     20     |     26         |     32          |          0 |       0 |
| purchase_order        | 단위원가                |  7300     |  22300       |  27300     |  34600         |  41500          |          0 |       0 |
| receipt               | 입고수량                |     8     |     14       |     20     |     26         |     32          |          0 |       0 |
| receipt               | 검수불량수량            |     0     |      0       |      0     |      0         |      2          |          0 |     711 |
| returns               | 반품수량                |     1     |      1       |      1     |      1         |      1          |          0 |       0 |
| returns               | 환불금액                | 14200     |  50000       |  62000     |  77000         |  90000          |          0 |       0 |
| returns               | return_shipping_cost    |     0     |      0       |      0     |   3000         |   3000          |          0 |     257 |
| returns               | return_handling_cost    |     0     |   1309.5     |   1492.5   |   1705         |   1899          |          0 |      32 |
| traffic_daily         | ad_spend                |     0     |  89089       | 162059     | 263557         | 620390          |          0 |     181 |

### 2-4. 음수 값

**수량·금액 열에서 음수 값 0건.**

### 2-5. 0 값

| 테이블             | 열                      |   0건수 |     중위 |
|:-------------------|:------------------------|--------:|---------:|
| inventory_snapshot | on_hand_qty             |     621 |     22   |
| inventory_snapshot | available_qty           |     669 |     21   |
| inventory_snapshot | reserved_qty            |    9621 |      0   |
| inventory_snapshot | in_transit_qty          |   12369 |      0   |
| inventory_snapshot | damaged_qty             |   12270 |      0   |
| inventory_snapshot | inventory_value         |     621 | 533400   |
| order_item         | 상품할인액              |    6638 |      0   |
| order_item         | 쿠폰할인액              |    7203 |      0   |
| order_item         | 배송비배부액            |    6536 |      0   |
| order_item         | canceled_qty            |    8625 |      0   |
| order_item         | canceled_amount         |    8625 |      0   |
| order_item         | payment_fee_amount      |     205 |   1402   |
| order_item         | fulfillment_cost_amount |     205 |   2200   |
| order_item         | packaging_cost_amount   |     205 |    450   |
| receipt            | 검수불량수량            |     711 |      0   |
| returns            | return_shipping_cost    |     257 |      0   |
| returns            | return_handling_cost    |      32 |   1492.5 |
| traffic_daily      | ad_spend                |     181 | 162059   |

---

## 3. 판단 분리

관찰된 사실을 4가지로 구분한다. **구분은 해석이므로 근거 행 수를 함께 적는다.**
값을 고치거나 극단값을 오류로 확정하지 않았다.

### 3-1. 정상 공란

업무상 값이 없는 것이 맞는 경우. 결측을 오류로 처리하면 안 된다.

| 항목                                    |   근거 행수 | 근거                                                                          |
|:----------------------------------------|------------:|:------------------------------------------------------------------------------|
| order_item.cancel_date 결측             |        8625 | 취소되지 않은 주문상세. 구매확정 8,625건과 정확히 일치                        |
| order_item.canceled_* = 0               |        8625 | 취소 수량이 없는 정상 건                                                      |
| returns.처리일 결측                     |          32 | 처리상태='접수'(미완료) 32건과 정확히 일치. 완료건 중 처리일 없는 행 0건      |
| action_log.completed_date 결측          |          27 | 완료 상태가 아닌 액션 27건과 정확히 일치                                      |
| purchase_order.메모 결측                |         715 | 선택 입력 항목. 96.5%가 공란이라 필수 항목으로 보기 어려움                    |
| orders.쿠폰코드 결측                    |        6011 | 쿠폰 미사용 주문. 단 아래 '확인 필요'의 쿠폰 불일치와 함께 볼 것              |
| order_item 비용 3종 = 0                 |         205 | 풀필먼트·포장·결제수수료가 0인 205건은 전부 status='취소'. 취소건 비용 미발생 |
| inventory_snapshot.reserved/damaged = 0 |        9621 | 예약·불량 재고가 없는 정상 상태                                               |

### 3-2. 입력 누락 가능성

값이 있어야 할 자리인데 비어 있는 경우. **원인 확인 전까지 채우지 않는다.**

| 항목                                    |   근거 행수 | 근거                                                          |
|:----------------------------------------|------------:|:--------------------------------------------------------------|
| 취소건인데 cancel_reason 없음           |          22 | 취소 206건 중 22건에 사유 없음. cancel_date는 206건 모두 있음 |
| returns.반품사유 결측                   |          66 | 완료 반품 378건 중 63건, 접수 32건 중 3건에 사유 없음         |
| order_item.주문시_상품명 결측           |          20 | sku_id는 살아 있어 조인으로 확인 가능하나 원천 값은 비어 있음 |
| receipt.송장번호 결측                   |          12 | 나머지 729건은 모두 고유값. 필수 항목으로 보이나 12건 누락    |
| sku_master.보관로케이션 결측            |           1 | 399개 SKU 중 1개만 로케이션 없음                              |
| inventory_snapshot.last_count_date 결측 |           1 | 12,369행 중 1행(2026-06-30/WH01/S00045)만 실사일 없음         |

### 3-3. 구조적 분석 한계

데이터 구조상 특정 분석이 불가능한 경우. 보정이 아니라 **분석 범위를 좁혀야 한다.**

| 항목                           |   근거 행수 | 근거                                                                                                        |
|:-------------------------------|------------:|:------------------------------------------------------------------------------------------------------------|
| in_transit_qty 전 행 0         |       12369 | 입고 예정 재고가 데이터에 존재하지 않음 → 이동 중 재고를 반영한 가용성 분석 불가                            |
| order_item.수량 값이 1~2뿐     |        8831 | 수량 분포가 1(8,548) / 2(283)로 사실상 고정 → 수량 기반 구매 패턴 분석 의미 없음                            |
| action_log.sku_id 결측         |          21 | 액션 유형과 결측이 완전히 대응. SKU 단위 액션 분석 불가, 상품 단위로 통일 필요                              |
| action_log 표본 크기           |          32 | 32건뿐이고 상태가 액션 유형으로 완전히 결정됨 → 실행률·효과 분석 불가                                       |
| promotion 표본 크기            |           4 | 프로모션 4건 → 프로모션 간 효과 비교는 통계적으로 성립하지 않음                                             |
| purchase_order 기간 단절       |           0 | 6~7월 발주 0건. CLAUDE.md 확정 규칙에 따라 발주 중단 상태로 해석 → 리드타임·리오더 실적 분석 범위는 5월까지 |
| inventory_snapshot 간격 불균등 |          31 | 31개 시점이 주 1회(일요일) + 월말 혼합 → 주간 비교 시 간격 보정 필요                                        |

### 3-4. 확인 필요

정상인지 오류인지 데이터만으로 판단할 수 없는 경우. **답을 받기 전까지 가정하지 않는다.**

| 항목                                               |   근거 행수 | 근거                                                                         |
|:---------------------------------------------------|------------:|:-----------------------------------------------------------------------------|
| 쿠폰코드와 쿠폰할인액 불일치 (코드 있음/할인 0)    |         803 | 쿠폰코드 보유 주문 1033건 중 할인액이 0                                      |
| 쿠폰코드와 쿠폰할인액 불일치 (코드 없음/할인 있음) |        1350 | 쿠폰할인 발생 주문 1580건 중 코드가 비어 있음. 두 항목의 관계 정의 필요      |
| orders.customer_id 결측                            |        1008 | 14.3%. 비회원 주문인지 수집 누락인지에 따라 신규·재구매 분석의 모수가 달라짐 |
| traffic_daily.ad_spend = 0                         |         181 | 181건 전부 CH05. 해당 채널만 광고 미집행인지 데이터 미수집인지 확인 필요     |
| action_log.result_note 결측                        |          28 | 완료 5건 중에도 결과 기록이 없는 건이 있는지 확인 필요                       |

---

## 4. 전체 열 목록

| 테이블                | 열                      | 자료형   |   결측수 |   결측율 |   고유값수 |
|:----------------------|:------------------------|:---------|---------:|---------:|-----------:|
| action_log            | action_id               | 문자열   |        0 |      0   |         32 |
| action_log            | product_id              | 문자열   |        0 |      0   |         32 |
| action_log            | sku_id                  | 문자열   |       21 |     65.6 |         11 |
| action_log            | recommended_action      | 문자열   |        0 |      0   |          6 |
| action_log            | final_action            | 문자열   |        0 |      0   |          6 |
| action_log            | action_status           | 문자열   |        0 |      0   |          6 |
| action_log            | owner                   | 문자열   |        0 |      0   |          3 |
| action_log            | priority                | 문자열   |        0 |      0   |          3 |
| action_log            | decision_date           | 날짜     |       12 |     37.5 |         20 |
| action_log            | due_date                | 날짜     |        0 |      0   |         32 |
| action_log            | completed_date          | 날짜     |       27 |     84.4 |          5 |
| action_log            | expected_effect         | 문자열   |        0 |      0   |          4 |
| action_log            | result_note             | 문자열   |       28 |     87.5 |          2 |
| category_master       | category_id             | 문자열   |        0 |      0   |         19 |
| category_master       | 대분류                  | 문자열   |        0 |      0   |          6 |
| category_master       | 중분류                  | 문자열   |        0 |      0   |         10 |
| category_master       | 소분류                  | 문자열   |        0 |      0   |         18 |
| category_master       | 시즌민감도              | 문자열   |        0 |      0   |          3 |
| category_master       | 사용여부                | 문자열   |        0 |      0   |          1 |
| channel_master        | channel_id              | 문자열   |        0 |      0   |          5 |
| channel_master        | 채널명                  | 문자열   |        0 |      0   |          5 |
| channel_master        | 채널유형                | 문자열   |        0 |      0   |          4 |
| channel_master        | 수수료율                | 실수     |        0 |      0   |          5 |
| channel_master        | 정산주기_일             | 정수     |        0 |      0   |          5 |
| channel_master        | 운영상태                | 문자열   |        0 |      0   |          1 |
| inventory_policy      | policy_id               | 문자열   |        0 |      0   |         19 |
| inventory_policy      | category_id             | 문자열   |        0 |      0   |         19 |
| inventory_policy      | season                  | 문자열   |        0 |      0   |          2 |
| inventory_policy      | lifecycle_stage         | 문자열   |        0 |      0   |          1 |
| inventory_policy      | target_wos_min          | 정수     |        0 |      0   |          3 |
| inventory_policy      | target_wos_max          | 정수     |        0 |      0   |          3 |
| inventory_policy      | reorder_point_wos       | 정수     |        0 |      0   |          3 |
| inventory_policy      | clearance_point_wos     | 정수     |        0 |      0   |          3 |
| inventory_policy      | effective_from          | 날짜     |        0 |      0   |          1 |
| inventory_policy      | effective_to            | 날짜     |        0 |      0   |          1 |
| inventory_policy      | approved_by             | 문자열   |        0 |      0   |          2 |
| inventory_snapshot    | snapshot_date           | 날짜     |        0 |      0   |         31 |
| inventory_snapshot    | warehouse_id            | 문자열   |        0 |      0   |          2 |
| inventory_snapshot    | sku_id                  | 문자열   |        0 |      0   |        399 |
| inventory_snapshot    | on_hand_qty             | 정수     |        0 |      0   |        101 |
| inventory_snapshot    | available_qty           | 정수     |        0 |      0   |        103 |
| inventory_snapshot    | reserved_qty            | 정수     |        0 |      0   |          3 |
| inventory_snapshot    | in_transit_qty          | 정수     |        0 |      0   |          1 |
| inventory_snapshot    | damaged_qty             | 정수     |        0 |      0   |          2 |
| inventory_snapshot    | last_count_date         | 날짜     |        1 |      0   |          7 |
| inventory_snapshot    | inventory_value         | 정수     |        0 |      0   |       1901 |
| order_attribution     | attribution_id          | 문자열   |        0 |      0   |       7470 |
| order_attribution     | order_id                | 문자열   |        0 |      0   |       6905 |
| order_attribution     | channel_id              | 문자열   |        0 |      0   |          5 |
| order_attribution     | attribution_model       | 문자열   |        0 |      0   |          2 |
| order_attribution     | attribution_weight      | 실수     |        0 |      0   |          3 |
| order_attribution     | lookback_days           | 정수     |        0 |      0   |          1 |
| order_attribution     | attributed_at           | 일시     |        0 |      0   |       6903 |
| order_item            | order_item_id           | 문자열   |        0 |      0   |       8831 |
| order_item            | order_id                | 문자열   |        0 |      0   |       7041 |
| order_item            | sku_id                  | 문자열   |        0 |      0   |        398 |
| order_item            | 주문시_상품명           | 문자열   |       20 |      0.2 |         58 |
| order_item            | 수량                    | 정수     |        0 |      0   |          2 |
| order_item            | 정상가                  | 정수     |        0 |      0   |         42 |
| order_item            | 판매단가                | 정수     |        0 |      0   |        521 |
| order_item            | 상품할인액              | 정수     |        0 |      0   |        152 |
| order_item            | 쿠폰할인액              | 정수     |        0 |      0   |         55 |
| order_item            | 배송비배부액            | 정수     |        0 |      0   |          2 |
| order_item            | 채널수수료액            | 정수     |        0 |      0   |       1086 |
| order_item            | warehouse_id            | 문자열   |        0 |      0   |          2 |
| order_item            | order_item_status       | 문자열   |        0 |      0   |          3 |
| order_item            | canceled_qty            | 정수     |        0 |      0   |          3 |
| order_item            | canceled_amount         | 정수     |        0 |      0   |         72 |
| order_item            | cancel_date             | 날짜     |     8625 |     97.7 |        120 |
| order_item            | cancel_reason           | 문자열   |     8647 |     97.9 |          5 |
| order_item            | payment_fee_amount      | 정수     |        0 |      0   |       2074 |
| order_item            | fulfillment_cost_amount | 정수     |        0 |      0   |          4 |
| order_item            | packaging_cost_amount   | 정수     |        0 |      0   |          4 |
| orders                | order_id                | 문자열   |        0 |      0   |       7044 |
| orders                | 주문일시                | 일시     |        0 |      0   |       7042 |
| orders                | channel_id              | 문자열   |        0 |      0   |          5 |
| orders                | customer_id             | 문자열   |     1008 |     14.3 |       3035 |
| orders                | 주문상태                | 문자열   |        0 |      0   |          3 |
| orders                | 결제수단                | 문자열   |        0 |      0   |          4 |
| orders                | 쿠폰코드                | 문자열   |     6011 |     85.3 |          3 |
| orders                | 배송지역                | 문자열   |        0 |      0   |          8 |
| orders                | 주문수집일시            | 일시     |        0 |      0   |       2479 |
| product_master        | product_id              | 문자열   |        0 |      0   |         58 |
| product_master        | 상품명                  | 문자열   |        0 |      0   |         58 |
| product_master        | 브랜드                  | 문자열   |        0 |      0   |         10 |
| product_master        | category_id             | 문자열   |        0 |      0   |         19 |
| product_master        | 출시일                  | 날짜     |        0 |      0   |         24 |
| product_master        | 정상가                  | 정수     |        0 |      0   |         42 |
| product_master        | 기준원가                | 정수     |        0 |      0   |         53 |
| product_master        | 거래처_id               | 문자열   |        0 |      0   |         12 |
| product_master        | 리드타임_일             | 정수     |        0 |      0   |          5 |
| product_master        | 상품상태                | 문자열   |        0 |      0   |          2 |
| product_master        | 담당MD                  | 문자열   |        0 |      0   |          3 |
| product_master        | 시즌                    | 문자열   |        0 |      0   |          2 |
| product_master        | 등록일시                | 일시     |        0 |      0   |         24 |
| product_master        | 수정일시                | 일시     |        0 |      0   |          1 |
| promotion             | promotion_id            | 문자열   |        0 |      0   |          4 |
| promotion             | 프로모션명              | 문자열   |        0 |      0   |          4 |
| promotion             | 시작일                  | 날짜     |        0 |      0   |          4 |
| promotion             | 종료일                  | 날짜     |        0 |      0   |          4 |
| promotion             | 할인유형                | 문자열   |        0 |      0   |          1 |
| promotion             | 할인값                  | 실수     |        0 |      0   |          4 |
| promotion             | 적용채널                | 문자열   |        0 |      0   |          4 |
| promotion             | 예산                    | 정수     |        0 |      0   |          4 |
| promotion             | 담당자                  | 문자열   |        0 |      0   |          2 |
| promotion_application | application_id          | 문자열   |        0 |      0   |       1300 |
| promotion_application | promotion_id            | 문자열   |        0 |      0   |          4 |
| promotion_application | order_item_id           | 문자열   |        0 |      0   |       1300 |
| promotion_application | discount_amount         | 정수     |        0 |      0   |        147 |
| promotion_application | funded_by               | 문자열   |        0 |      0   |          2 |
| promotion_application | applied_at              | 일시     |        0 |      0   |       1041 |
| purchase_order        | po_id                   | 문자열   |        0 |      0   |        741 |
| purchase_order        | 발주일                  | 날짜     |        0 |      0   |         91 |
| purchase_order        | 거래처_id               | 문자열   |        0 |      0   |         12 |
| purchase_order        | sku_id                  | 문자열   |        0 |      0   |        388 |
| purchase_order        | 발주수량                | 정수     |        0 |      0   |         25 |
| purchase_order        | 단위원가                | 정수     |        0 |      0   |         53 |
| purchase_order        | 예정입고일              | 날짜     |        0 |      0   |          5 |
| purchase_order        | 발주상태                | 문자열   |        0 |      0   |          1 |
| purchase_order        | 발주담당자              | 문자열   |        0 |      0   |          2 |
| purchase_order        | 메모                    | 문자열   |      715 |     96.5 |          1 |
| receipt               | receipt_id              | 문자열   |        0 |      0   |        741 |
| receipt               | po_id                   | 문자열   |        0 |      0   |        741 |
| receipt               | 실입고일                | 날짜     |        0 |      0   |         35 |
| receipt               | warehouse_id            | 문자열   |        0 |      0   |          2 |
| receipt               | sku_id                  | 문자열   |        0 |      0   |        388 |
| receipt               | 입고수량                | 정수     |        0 |      0   |         25 |
| receipt               | 검수불량수량            | 정수     |        0 |      0   |          3 |
| receipt               | 입고담당자              | 문자열   |        0 |      0   |          2 |
| receipt               | 송장번호                | 문자열   |       12 |      1.6 |        729 |
| returns               | return_id               | 문자열   |        0 |      0   |        410 |
| returns               | order_item_id           | 문자열   |        0 |      0   |        410 |
| returns               | 접수일                  | 날짜     |        0 |      0   |        155 |
| returns               | 처리일                  | 날짜     |       32 |      7.8 |        152 |
| returns               | 반품수량                | 정수     |        0 |      0   |          1 |
| returns               | 반품사유                | 문자열   |       66 |     16.1 |          5 |
| returns               | 귀책주체                | 문자열   |        0 |      0   |          2 |
| returns               | 환불금액                | 정수     |        0 |      0   |        133 |
| returns               | 재판매가능              | 문자열   |        0 |      0   |          2 |
| returns               | 처리상태                | 문자열   |        0 |      0   |          2 |
| returns               | return_shipping_cost    | 정수     |        0 |      0   |          2 |
| returns               | return_handling_cost    | 정수     |        0 |      0   |        296 |
| sku_master            | sku_id                  | 문자열   |        0 |      0   |        399 |
| sku_master            | product_id              | 문자열   |        0 |      0   |         58 |
| sku_master            | 색상                    | 문자열   |        0 |      0   |         10 |
| sku_master            | 사이즈                  | 문자열   |        0 |      0   |         10 |
| sku_master            | 바코드                  | 정수     |        0 |      0   |        399 |
| sku_master            | 옵션상태                | 문자열   |        0 |      0   |          1 |
| sku_master            | 최소진열재고            | 정수     |        0 |      0   |          3 |
| sku_master            | 안전재고                | 정수     |        0 |      0   |          5 |
| sku_master            | 보관로케이션            | 문자열   |        1 |      0.3 |        190 |
| traffic_daily         | date                    | 날짜     |        0 |      0   |        181 |
| traffic_daily         | channel_id              | 문자열   |        0 |      0   |          5 |
| traffic_daily         | sessions                | 정수     |        0 |      0   |        799 |
| traffic_daily         | product_views           | 정수     |        0 |      0   |        851 |
| traffic_daily         | add_to_cart             | 정수     |        0 |      0   |        302 |
| traffic_daily         | checkout_start          | 정수     |        0 |      0   |        167 |
| traffic_daily         | attributed_order_credit | 실수     |        0 |      0   |        164 |
| traffic_daily         | ad_spend                | 정수     |        0 |      0   |        723 |
| traffic_daily         | new_customers           | 정수     |        0 |      0   |         39 |
| warehouse_master      | warehouse_id            | 문자열   |        0 |      0   |          2 |
| warehouse_master      | 창고명                  | 문자열   |        0 |      0   |          2 |
| warehouse_master      | 유형                    | 문자열   |        0 |      0   |          2 |
| warehouse_master      | 지역                    | 문자열   |        0 |      0   |          2 |
| warehouse_master      | 운영상태                | 문자열   |        0 |      0   |          1 |
