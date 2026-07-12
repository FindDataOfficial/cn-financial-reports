"""SQLAlchemy ORM models for fd-cn-report.

Extracted from the shared mcp `models` module so this package is self-contained
and publishable to PyPI without the local mcp-models path dependency.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class LlmRule(Base):
    """An LLM (non-script) indicator rule persisted in SQLite.

    Mirrors the demand's LLM-rule shape (``indicator``, ``instruction``,
    ``position``, ``document_type``) plus the metadata the extraction
    pipeline already consumes (``module``, ``applies_to``, ``source``,
    ...). Sourced from ``indicator_rules.json`` via the one-shot migration,
    or written by the generator skills.
    """
    __tablename__ = "llm_rules"
    __table_args__ = (
        UniqueConstraint("indicator", "document_type", name="uq_llm_rule_indicator_doc"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String(255), nullable=False, index=True)
    document_type = Column(String(64), nullable=False, index=True)
    module = Column(String(64), nullable=True, index=True)
    subgroup = Column(String(255), nullable=True)
    source_type = Column(String(32), nullable=True)
    extractor = Column(String(64), nullable=True)
    applies_to = Column(JSON, nullable=True)
    unit = Column(String(32), nullable=True)
    period_type = Column(String(32), nullable=True)
    value_range = Column(JSON, nullable=True)
    source = Column(JSON, nullable=True)
    aliases = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    direction = Column(String(32), nullable=True)
    # demand's derived convenience fields
    instruction = Column(Text, nullable=True)
    position = Column(Text, nullable=True)

    def to_rule_dict(self) -> dict:
        """Reconstruct the in-memory rule dict the pipeline expects.

        Maps DB ``indicator``→dict ``name`` and ``document_type``→dict
        ``report_type`` so callers (``applicable_rules``, ``resolve_rule``,
        ``_resolve_via_report``) see the same shape they got from
        ``indicator_rules.json`` before the migration.
        """
        return {
            "name": self.indicator,
            "indicator": self.indicator,
            "document_type": self.document_type,
            "report_type": self.document_type,
            "module": self.module,
            "subgroup": self.subgroup,
            "source_type": self.source_type,
            "extractor": self.extractor,
            "applies_to": self.applies_to,
            "unit": self.unit,
            "period_type": self.period_type,
            "value_range": self.value_range,
            "source": self.source,
            "aliases": self.aliases or [],
            "note": self.note or "",
            "direction": self.direction,
            "instruction": self.instruction or "",
            "position": self.position or "",
        }


class ScriptRule(Base):
    """A script (deterministic) indicator rule persisted in SQLite.

    Carries the demand's script-rule shape (``indicator``, ``extract_rule``,
    ``position``, ``document_type``) plus shared metadata. ``extract_rule``
    names a registered extractor in ``script_extractors``.
    """
    __tablename__ = "script_rules"
    __table_args__ = (
        UniqueConstraint("indicator", "document_type", name="uq_script_rule_indicator_doc"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String(255), nullable=False, index=True)
    document_type = Column(String(64), nullable=False, index=True)
    extract_rule = Column(String(128), nullable=False)
    position = Column(Text, nullable=True)
    module = Column(String(64), nullable=True, index=True)
    subgroup = Column(String(255), nullable=True)
    source_type = Column(String(32), nullable=True)
    applies_to = Column(JSON, nullable=True)
    unit = Column(String(32), nullable=True)
    period_type = Column(String(32), nullable=True)
    source = Column(JSON, nullable=True)
    aliases = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)

    def to_rule_dict(self) -> dict:
        return {
            "name": self.indicator,
            "indicator": self.indicator,
            "document_type": self.document_type,
            "report_type": self.document_type,
            "extract_rule": self.extract_rule,
            "position": self.position or "",
            "module": self.module,
            "subgroup": self.subgroup,
            "source_type": self.source_type,
            "applies_to": self.applies_to,
            "unit": self.unit,
            "period_type": self.period_type,
            "source": self.source,
            "aliases": self.aliases or [],
            "note": self.note or "",
        }


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
