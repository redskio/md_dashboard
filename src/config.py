"""경로·상수 단일 관리. 모든 경로는 이 파일에서만 정의한다."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CONVERTED_DIR = DATA_DIR / "converted"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
TABLES_DIR = OUTPUTS_DIR / "tables"
FIGURES_DIR = OUTPUTS_DIR / "figures"
REPORTS_DIR = OUTPUTS_DIR / "reports"

RAW_XLSX = RAW_DIR / "ganaswim_dataset.xlsx"

# 분석 기준일 (CLAUDE.md 확정 규칙 1). 실행 시점의 오늘 날짜를 쓰지 않는다.
ANALYSIS_DATE = "2026-07-31"

# 변환 대상에서 제외하는 문서 시트 (데이터가 아니라 데이터에 대한 설명)
EXCLUDED_SHEETS = ("README", "data_dictionary")

CSV_ENCODING = "utf-8-sig"

# 문자열로 보존할 ID·코드 열 판별 패턴
ID_COLUMN_PATTERN = r"(_id$|^id$|바코드|코드$|송장번호)"
