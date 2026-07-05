"""akshare-backed financials client for cnreport-mcp.

Single entry point for `get_financials`. Lazy-imports akshare so the MCP
server starts even when akshare is uninstalled — `MissingDependencyError`
is raised at call time instead, and the tool layer converts it to a
`{"error": ...}` response.

`stock_financial_report_sina` returns one DataFrame per statement covering
ALL reporting periods (annual + interim + quarterly). We post-filter:
  period="annual"    → keep rows where 报告日 ends with "-12-31"
  period="quarterly" → keep all rows
"""
from __future__ import annotations

from typing import Any


class MissingDependencyError(RuntimeError):
    """Raised when akshare cannot be imported."""


# Sina's symbol param for the three statements.
_STATEMENT_SINA_PARAM = {
    "income_statement": "利润表",
    "balance_sheet": "资产负债表",
    "cashflow": "现金流量表",
}


def _sina_stock(stock_code: str, exchange: str = "") -> str:
    """600519 → sh600519; 000001 → sz000001; 830799 → bj830799.

    Falls back to leading-digit heuristic when exchange is empty.
    """
    code = stock_code.strip()
    if exchange == "sse":
        return f"sh{code}"
    if exchange == "szse":
        return f"sz{code}"
    if exchange == "bse":
        return f"bj{code}"
    if code.startswith("6") or code.startswith("9"):
        return f"sh{code}"
    if code.startswith("8") or code.startswith("4"):
        return f"bj{code}"
    return f"sz{code}"


def _serialize_df(df: Any) -> dict:
    """Convert a pandas DataFrame to {columns, data} with NaN→None."""
    if df is None:
        return {"columns": [], "data": []}
    # Replace NaN with None for JSON-safety.
    cleaned = df.where(df.notna(), None)
    payload = cleaned.to_dict(orient="split")
    payload.pop("index", None)
    payload["columns"] = [str(c) for c in payload["columns"]]
    return payload


def _filter_period(df: Any, period: str) -> Any:
    """Filter rows by the 报告日 column when `period == 'annual'`."""
    if period != "annual":
        return df
    # akshare returns 报告日 as the date column for sina statements.
    for col in ("报告日", "报告期", "日期"):
        if col in df.columns:
            mask = df[col].astype(str).str.endswith("-12-31") | df[col].astype(str).str.endswith("1231")
            return df[mask]
    return df


def get_statements(stock_code: str, *, period: str = "annual", exchange: str = "") -> dict[str, dict]:
    """Return income/balance/cashflow statements for a CN A-share company.

    Raises `MissingDependencyError` if akshare is not installed. Network
    failures propagate as the underlying httpx/akshare exception.
    """
    try:
        import akshare as ak  # noqa: WPS433 (lazy import is the point)
    except ImportError as e:
        raise MissingDependencyError(
            "akshare not installed. Run: uv sync --directory mcp/cnreport-mcp"
        ) from e

    sina_stock = _sina_stock(stock_code, exchange)
    out: dict[str, dict] = {}
    for key, sina_param in _STATEMENT_SINA_PARAM.items():
        df = ak.stock_financial_report_sina(stock=sina_stock, symbol=sina_param)
        df = _filter_period(df, period)
        out[key] = _serialize_df(df)
    return out
