"""원본 XLSX의 데이터 시트를 CSV로 변환하고 결과를 검증한다.

- 원본 XLSX는 읽기 전용으로만 접근한다 (변환 전후 해시 비교로 확인)
- 시트명·열 순서를 그대로 유지한다
- ID·코드 열은 문자열로 보존한다
- 값 수정·열 이름 표준화는 하지 않는다 (구조 변환만)

실행:
    .venv/bin/python -m src.convert_xlsx
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd

from src import config


def _file_fingerprint(path) -> tuple[int, str]:
    """파일 크기와 SHA-256. 원본 미수정 확인용."""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return path.stat().st_size, h


def _is_id_column(name: str) -> bool:
    return bool(re.search(config.ID_COLUMN_PATTERN, str(name), re.IGNORECASE))


def read_sheet(xlsx_path, sheet: str) -> pd.DataFrame:
    """시트 하나를 원본 타입 그대로 읽는다. ID 열은 문자열로 고정한다."""
    df = pd.read_excel(xlsx_path, sheet_name=sheet, dtype=object)
    for col in df.columns:
        if _is_id_column(col):
            df[col] = df[col].map(lambda v: v if pd.isna(v) else str(v))
    return df


def target_sheets(xlsx_path) -> list[str]:
    """변환 대상 데이터 시트. 문서 시트는 제외하고 원본 순서를 유지한다."""
    with pd.ExcelFile(xlsx_path) as xl:
        return [s for s in xl.sheet_names if s not in config.EXCLUDED_SHEETS]


def convert(xlsx_path=None, out_dir=None) -> dict[str, "pd.DataFrame"]:
    """데이터 시트를 CSV로 변환하고 {시트명: 원본 DataFrame}을 반환한다.

    재실행 가능하다. 같은 입력이면 같은 CSV를 다시 만든다(덮어쓰기).
    """
    xlsx_path = xlsx_path or config.RAW_XLSX
    out_dir = out_dir or config.CONVERTED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    before = _file_fingerprint(xlsx_path)
    frames = {}
    for sheet in target_sheets(xlsx_path):
        df = read_sheet(xlsx_path, sheet)
        df.to_csv(out_dir / f"{sheet}.csv", index=False, encoding=config.CSV_ENCODING)
        frames[sheet] = df

    after = _file_fingerprint(xlsx_path)
    if before != after:
        raise RuntimeError(f"원본 XLSX가 변경되었다: {xlsx_path}")

    return frames


def _normalize(series: pd.Series) -> pd.Series:
    """XLSX 값과 CSV 재읽기 값을 같은 기준으로 비교하기 위한 문자열 정규화."""

    def one(v):
        if pd.isna(v):
            return ""
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v).strip()

    return series.map(one)


def validate(frames, out_dir=None) -> pd.DataFrame:
    """변환 결과를 시트별로 검증한다. 불일치가 있으면 상태를 '실패'로 둔다."""
    out_dir = out_dir or config.CONVERTED_DIR
    rows = []

    for sheet, src in frames.items():
        csv_path = out_dir / f"{sheet}.csv"
        issues = []

        if not csv_path.exists():
            rows.append(
                {"시트명": sheet, "상태": "실패", "불일치_원인": "CSV 파일 없음"}
            )
            continue

        # 헤더 원문을 그대로 읽어 인덱스 열 혼입 여부를 본다
        raw_header = csv_path.read_text(encoding=config.CSV_ENCODING).split("\n", 1)[0]
        out = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding=config.CSV_ENCODING)

        row_match = len(src) == len(out)
        col_match = len(src.columns) == len(out.columns)
        order_match = list(map(str, src.columns)) == list(map(str, out.columns))

        # 불필요한 인덱스 열
        no_index_col = not (
            raw_header.startswith(",")
            or any(str(c).startswith("Unnamed:") for c in out.columns)
        )

        # 한글 깨짐: 헤더·값에 대체문자(U+FFFD)가 없고, 원본 한글 문자열이 그대로 보존되는지
        blob = raw_header + "".join(out.head(50).astype(str).to_numpy().ravel().tolist())
        hangul_ok = "�" not in blob
        kor_cols = [c for c in src.columns if re.search(r"[가-힣]", str(c))]
        if kor_cols and not set(map(str, kor_cols)).issubset(set(map(str, out.columns))):
            hangul_ok = False

        # ID 표본: 첫 ID 열의 앞 3개 값
        id_cols = [c for c in src.columns if _is_id_column(c)]
        id_col = id_cols[0] if id_cols else None
        id_src = id_dst = ""
        id_match = True
        if id_col is not None and order_match:
            id_src = "|".join(_normalize(src[id_col]).head(3))
            id_dst = "|".join(out[str(id_col)].head(3).astype(str).str.strip())
            id_match = id_src == id_dst

        # 전체 값 대조
        value_match = True
        if row_match and order_match:
            for c in src.columns:
                if not _normalize(src[c]).equals(_normalize(out[str(c)])):
                    value_match = False
                    issues.append(f"값 불일치: {c}")
                    break

        if not row_match:
            issues.append(f"행수 불일치 {len(src)}→{len(out)}")
        if not col_match:
            issues.append(f"열수 불일치 {len(src.columns)}→{len(out.columns)}")
        if not order_match:
            issues.append("열 순서 불일치")
        if not no_index_col:
            issues.append("인덱스 열 혼입")
        if not hangul_ok:
            issues.append("한글 깨짐")
        if not id_match:
            issues.append(f"ID 표본 불일치 {id_src}→{id_dst}")

        rows.append(
            {
                "시트명": sheet,
                "xlsx_행수": len(src),
                "csv_행수": len(out),
                "행수_일치": row_match,
                "xlsx_열수": len(src.columns),
                "csv_열수": len(out.columns),
                "열수_일치": col_match,
                "열순서_일치": order_match,
                "ID_열": id_col or "",
                "ID_표본_xlsx": id_src,
                "ID_표본_csv": id_dst,
                "ID_일치": id_match,
                "한글_정상": hangul_ok,
                "인덱스열_없음": no_index_col,
                "전체값_일치": value_match,
                "상태": "성공" if not issues else "실패",
                "불일치_원인": "; ".join(issues),
            }
        )

    result = pd.DataFrame(rows)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(
        config.REPORTS_DIR / "conversion_validation.csv",
        index=False,
        encoding=config.CSV_ENCODING,
    )
    return result


def main() -> None:
    frames = convert()
    result = validate(frames)
    failed = result[result["상태"] != "성공"]
    print(f"변환 시트 {len(result)}개 / 성공 {len(result) - len(failed)} / 실패 {len(failed)}")
    if len(failed):
        print(failed[["시트명", "불일치_원인"]].to_string(index=False))


if __name__ == "__main__":
    main()
