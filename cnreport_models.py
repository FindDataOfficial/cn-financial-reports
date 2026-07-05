"""SQLAlchemy ORM models for cnreport-mcp.

Extracted from the shared mcp `models` module so this package is self-contained
and publishable to PyPI without the local mcp-models path dependency.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReportDocument(Base):
    """One fetched annual report. report_id is a stable hash of source+company+year."""
    __tablename__ = "report_documents"
    __table_args__ = (UniqueConstraint("report_id", name="uq_report_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(128), nullable=False, index=True)
    source = Column(String(2048), nullable=False)
    company = Column(String(255), nullable=True, index=True)
    stock_code = Column(String(32), nullable=True, index=True)
    year = Column(Integer, nullable=True, index=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    raw_path = Column(String(2048), nullable=True)
    parse_status = Column(String(16), default="ok")  # ok | partial | failed

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "source": self.source,
            "company": self.company,
            "stock_code": self.stock_code,
            "year": self.year,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "raw_path": self.raw_path,
            "parse_status": self.parse_status,
        }


class ReportSection(Base):
    """One outline node extracted from a report. Idempotent on report_id+ordinal."""
    __tablename__ = "report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "ordinal", name="uq_report_section_ordinal"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(128), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False)
    level = Column(Integer, default=1)
    title = Column(String(512), nullable=False)
    char_count = Column(Integer, default=0)
    parse_status = Column(String(16), default="ok")  # ok | missing | failed
    extracted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "ordinal": self.ordinal,
            "level": self.level,
            "title": self.title,
            "char_count": self.char_count,
            "parse_status": self.parse_status,
        }


class EsIndexMeta(Base):
    """Metadata for a cnreport-{year} Elasticsearch index."""
    __tablename__ = "es_index_meta"
    __table_args__ = (UniqueConstraint("index_name", name="uq_es_index_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_name = Column(String(128), nullable=False, index=True)
    doc_count = Column(Integer, default=0)
    mapping_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "index_name": self.index_name,
            "doc_count": self.doc_count,
            "mapping_hash": self.mapping_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
