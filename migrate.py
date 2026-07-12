"""Create the cnreport tables in mcp/daas.db.

Run:  cd mcp/fd-cn-report && uv run python migrate.py
Idempotent — Base.metadata.create_all only adds missing tables.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine  # noqa: E402

from cnreport_models import Base  # noqa: E402
from cnreport_database import _DEFAULT_DB_PATH  # noqa: E402


def main() -> None:
    url = os.environ.get("DAAS_DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    print(f"cnreport tables ensured at {url}")


if __name__ == "__main__":
    main()
