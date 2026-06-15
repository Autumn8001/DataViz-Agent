from pathlib import Path
from typing import Any

import pandas as pd


def _read_table(file_path: str) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    suffix = Path(file_path).suffix.lower()

    if suffix == ".csv":
        try:
            return pd.read_csv(file_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(file_path, encoding="gb18030")

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)

    raise ValueError(f"不支持的文件格式: {suffix}")


def get_columns(file_path: str) -> dict[str, Any]:
    """Return column names for the uploaded dataset."""
    df = _read_table(file_path)
    return {
        "columns": df.columns.tolist(),
        "row_count": len(df),
        "column_count": len(df.columns),
    }


def get_missing_summary(file_path: str) -> dict[str, Any]:
    """Return missing value counts and ratios for each column."""
    df = _read_table(file_path)
    total_rows = len(df)

    summary = []
    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        missing_ratio = round(missing_count / total_rows, 4) if total_rows else 0
        summary.append(
            {
                "column": column,
                "missing_count": missing_count,
                "missing_ratio": missing_ratio,
            }
        )

    return {
        "row_count": total_rows,
        "missing_summary": summary,
    }


def preview_rows(file_path: str, n: int = 5) -> dict[str, Any]:
    """Return the first n rows as records."""
    df = _read_table(file_path)
    safe_n = max(1, min(n, 20))
    return {
        "rows": df.head(safe_n).to_dict(orient="records"),
        "row_count": len(df),
        "preview_count": safe_n,
    }