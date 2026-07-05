"""Pure helpers for cnreport-mcp: fetch, outline parse, section select,
LLM extraction, Elasticsearch store/search. No FastMCP here — server.py
registers the @app.tool wrappers that call these.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Optional

# ponytail: fetch via httpx + pypdf directly; scrapling delegation deferred
# for JS/anti-bot pages (rare for static cninfo/sse annual-report downloads).

# ── outline parsing ──────────────────────────────────────────────

# Common Chinese annual-report heading patterns: 第三节, 第三章, 一、, （一）, 1.
_HEADING_RE = re.compile(
    r"^\s*("
    r"第[一二三四五六七八九十百零〇\d]+[章节部分编篇]"
    r"|[\(（][一二三四五六七八九十百\d]+[\)）]"
    r"|[一二三四五六七八九十百]+、"
    r"|\d+[\.、]"
    r")\s*(.+?)\s*\.{3,}?\s*\d*\s*$"  # optional dot-leader + page no
)
# looser fallback: heading token alone on a line
_HEADING_LOOSE_RE = re.compile(
    r"^\s*(第[一二三四五六七八九十百零〇\d]+[章节部分编篇]|[一二三四五六七八九十百]+、|\d+[\.、])\s*(\S.*?)\s*$"
)


def strip_html(html: str) -> str:
    """Crude HTML → text: drop tags/scripts, collapse whitespace."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?s)<[^>]+>", "", html)
    # entities ponytail: handle the few that matter
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    html = html.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"[ \t]+", " ", html).strip()


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a text-layer PDF via pypdf."""
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def fetch_source(source: str, fetcher: str = "uv") -> str:
    """Fetch a report as text. URL via httpx (html/pdf), local path read directly.

    fetcher is accepted for forward-compat; v1 ignores it (httpx/pypdf only).
    """
    return fetch_source_with_bytes(source, fetcher)[0]


def fetch_source_with_bytes(source: str, fetcher: str = "uv") -> tuple[str, Optional[bytes]]:
    """Fetch a report as ``(text, raw_bytes)``.

    For URL sources, ``raw_bytes`` is the downloaded response body so callers
    (the report cache) can persist the original PDF. For local-path sources,
    ``raw_bytes`` is ``None`` — the file is already on disk and need not be
    re-cached.
    """
    if _looks_like_url(source):
        import httpx

        resp = httpx.get(source, follow_redirects=True, timeout=60.0)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype or source.lower().endswith(".pdf"):
            return extract_pdf_text(resp.content), resp.content
        if "html" in ctype:
            return strip_html(resp.text), resp.content
        return resp.text, resp.content
    # local path
    path = os.path.abspath(source)
    if not os.path.exists(path):
        raise FileNotFoundError(f"source not found and not a URL: {source}")
    if path.lower().endswith(".pdf"):
        with open(path, "rb") as fh:
            return extract_pdf_text(fh.read()), None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(), None


def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def parse_outline(text: str) -> list[dict]:
    """Parse 目录/bookmarks into a flat list of {level, title, ordinal}.

    level: 1 for 第X章/节, 2 for 一、, 3 for （一）/1.
    """
    entries: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _HEADING_RE.match(line) or _HEADING_LOOSE_RE.match(line)
        if not m:
            continue
        token, title = m.group(1), m.group(2)
        title = title.strip().strip(".").strip()
        if not title or len(title) > 80:
            continue
        level = _heading_level(token)
        key = f"{token}{title}"
        if key in seen:
            continue
        seen.add(key)
        entries.append({"level": level, "title": f"{token} {title}".strip(), "ordinal": len(entries) + 1})
    return entries


def _heading_level(token: str) -> int:
    if re.match(r"第[一二三四五六七八九十百零〇\d]+[章节部分编篇]", token):
        return 1
    if re.match(r"[一二三四五六七八九十百]+、", token):
        return 2
    return 3  # （一）/1.


def resolve_selector(outline: list[dict], selector: str) -> Optional[dict]:
    """Resolve a selector (ordinal int | exact title | regex | normalized substring) to an outline entry.

    Matching passes, in order: ordinal (1-based), exact title, normalized
    leading-keyword substring, regex. The normalized substring pass lets
    descriptive selectors like ``"资产负债表 — 一、资产"`` or
    ``"管理层讨论与分析 — 财务概要"`` (sourced from indicators_position.csv)
    match real TOC titles like ``"合并资产负债表"`` / ``"管理层讨论与分析"``:
    the leading keyword (text before the first em-dash) is matched as a
    substring against the normalized outline title.
    """
    # ordinal (1-based)
    if isinstance(selector, int) or (isinstance(selector, str) and selector.isdigit()):
        idx = int(selector)
        for e in outline:
            if e["ordinal"] == idx:
                return e
        return None
    # exact title
    for e in outline:
        if e["title"] == selector:
            return e
    # normalized leading-keyword substring (tolerant of ordinals/em-dashes/whitespace)
    sel_key = _normalize_section_title(_leading_keyword(selector))
    if sel_key:
        for e in outline:
            if sel_key in _normalize_section_title(e["title"]):
                return e
    # regex
    try:
        pat = re.compile(selector)
    except re.error:
        return None
    for e in outline:
        if pat.search(e["title"]):
            return e
    return None


# ordinals a section title may carry: "一、", "（一）", "1、" — stripped for tolerant matching.
_SECTION_ORDINAL_RE = re.compile(r"[一二三四五六七八九十百]+、|（[一二三四五六七八九十百]+）|\d+、|第[一二三四五六七八九十百]+节")
# em-dashes / hyphens used as section delimiters in the CSV (e.g. "资产负债表 — 一、资产").
_SECTION_DASH_RE = re.compile(r"[—–\-]")


def _leading_keyword(selector: str) -> str:
    """Return the text before the first em-dash/hyphen (the section keyword)."""
    s = selector or ""
    for sep in ("—", "–", "-"):
        if sep in s:
            return s.split(sep, 1)[0].strip()
    return s.strip()


def _normalize_section_title(s: str) -> str:
    """Strip ordinals, em-dashes, slashes, and whitespace for tolerant matching."""
    s = _SECTION_ORDINAL_RE.sub("", s or "")
    s = _SECTION_DASH_RE.sub("", s)
    return re.sub(r"[\s／/、，,。.：:（）()]+", "", s)


# ── three major financial statements (三大报表) ─────────────────────
# Each statement tried consolidated-first, then un-prefixed. Matched via
# resolve_selector (regex search), so token-prefixed TOC titles like
# "1、 合并资产负债表" resolve correctly. Parent-only titles (母公司…)
# never contain the consolidated substring, so they're skipped on the first
# pass and only matched as a last-resort fallback on the un-prefixed pass.
STATEMENT_MATCHERS: dict[str, list[str]] = {
    "income_statement": ["合并利润表", "利润表"],
    "balance_sheet": ["合并资产负债表", "资产负债表"],
    "cashflow": ["合并现金流量表", "现金流量表"],
}


def resolve_statement(outline: list[dict], key: str) -> Optional[dict]:
    """Return the first outline entry matching a statement key, or None.

    Tries each target title in order (consolidated before un-prefixed) via
    ``resolve_selector`` (exact, then regex substring).
    """
    for target in STATEMENT_MATCHERS.get(key, []):
        entry = resolve_selector(outline, target)
        if entry is not None:
            return entry
    return None


# Bank quarterly reports use "合并及公司资产负债表–按中国会计准则编制" etc.
# These are matched by the un-prefixed title as a substring.
# The boundary regex finds the NEXT statement title (excluding continuation
# pages marked 续) or a 第X节 chapter heading. Statement rows like "一、营业
# 收入" are intentionally NOT matched — they are content, not boundaries.
_STATEMENT_NEXT_BOUNDARY_RE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百零〇\d]+[章节部分编篇]"
    r"|\s*合并.*(?:资产负债表|利润表|现金流量表)(?!.*续)"
    r"|\s*合并及公司.*(?:资产负债表|利润表|现金流量表)(?!.*续)"
    r")",
    re.MULTILINE,
)


def find_statement_in_text(text: str, module: str) -> Optional[tuple[int, int, str]]:
    """Locate a financial statement in raw report text by its canonical title.

    Used as the body-text fallback when the outline lacks statement titles
    (the quarterly-report case). Tries each canonical title for ``module``
    (consolidated → un-prefixed) via ``_find_section_start`` (skips TOC rows).
    Returns ``(start, end, matched_title)`` where ``start``/``end`` are char
    offsets slicing the statement body, or ``None`` when no title is found.

    The end boundary is the next statement title or the next top-level
    numbered heading (``第X节`` / ``一、``) appearing after the title line.
    """
    targets = STATEMENT_MATCHERS.get(module, [])
    for title in targets:
        pos = _find_section_start(text, title)
        if pos == -1:
            continue
        # start of the line containing the title
        line_start = text.rfind("\n", 0, pos) + 1
        # end = next boundary (statement title or top-level heading) after this line
        body_start = text.find("\n", pos)
        if body_start == -1:
            body_start = len(text)
        end = len(text)
        for m in _STATEMENT_NEXT_BOUNDARY_RE.finditer(text, body_start):
            # skip the title we're currently slicing (boundary must be after the title line)
            if m.start() > body_start:
                end = m.start()
                break
        return line_start, end, title
    return None


def extract_statement_text(text: str, module: str) -> Optional[str]:
    """Return the sliced body text for a statement module, or ``None``.

    Thin wrapper around ``find_statement_in_text`` returning the string slice.
    """
    found = find_statement_in_text(text, module)
    if found is None:
        return None
    start, end, _title = found
    return text[start:end]


def _find_section_start(text: str, title: str) -> int:
    """Find the body occurrence of `title`, skipping 目录 (dot-leader) rows."""
    idx = 0
    while True:
        pos = text.find(title, idx)
        if pos == -1:
            return -1
        after = text[pos + len(title): pos + len(title) + 8]
        # 目录 rows look like "title ......... 12"; body headings are followed by \n
        if re.match(r"\s*\.{2,}", after):
            idx = pos + 1
            continue
        return pos


def extract_section_text(text: str, outline: list[dict], entry: dict) -> str:
    """Slice body text from entry's title to the next outline entry's title."""
    start = _find_section_start(text, entry["title"])
    if start == -1:
        # title may have been normalized; try a fuzzy prefix match on the token
        token = entry["title"].split()[0] if entry["title"] else entry["title"]
        start = _find_section_start(text, token)
    if start == -1:
        return ""
    start = text.find("\n", start)
    if start == -1:
        start = len(text)
    # next sibling = next entry whose body title appears after `start`
    end = len(text)
    for e in outline:
        if e["ordinal"] <= entry["ordinal"]:
            continue
        pos = _find_section_start(text, e["title"])
        if pos != -1 and pos >= start:
            end = pos
            break
    return text[start:end].strip()


# ── LLM extraction ───────────────────────────────────────────────


def llm_config() -> dict:
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "").rstrip("/"),
        "api_key": os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o")),
    }


def call_llm_json(system: str, user: str) -> str:
    """Call the OpenAI-compatible chat/completions endpoint, return raw content."""
    import httpx

    cfg = llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("LLM_API_KEY is not configured")
    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    resp = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {cfg['api_key']}"},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def validate_against_schema(data, schema: dict) -> Optional[str]:
    """Return None if valid, else a short error string."""
    try:
        import jsonschema

        jsonschema.validate(instance=data, schema=schema)
        return None
    except ImportError:
        return None  # ponytail: no jsonschema installed → skip validation
    except Exception as e:
        return str(e)


# ── Elasticsearch ────────────────────────────────────────────────

CNREPORT_MAPPING = {
    "properties": {
        "report_id": {"type": "keyword"},
        "company": {"type": "keyword"},
        "stock_code": {"type": "keyword"},
        "year": {"type": "integer"},
        "section": {"type": "keyword"},
        "section_id": {"type": "keyword"},
        "text": {"type": "text", "analyzer": "ik_smart"},
        "fields": {"type": "object", "dynamic": True},
        "indexed_at": {"type": "date"},
    }
}
CNREPORT_MAPPING_FALLBACK = {
    # ponytail: standard analyzer when ik plugin is absent
    "properties": {
        **CNREPORT_MAPPING["properties"],
        "text": {"type": "text", "analyzer": "standard"},
    }
}


def es_client():
    """Build an Elasticsearch client from env. Raises if ES_URL unset."""
    from elasticsearch import Elasticsearch

    url = os.environ.get("ES_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("ES_URL is not configured")
    api_key = os.environ.get("ES_API_KEY")
    if api_key:
        return Elasticsearch(url, api_key=api_key)
    user = os.environ.get("ES_USERNAME")
    pwd = os.environ.get("ES_PASSWORD")
    if user:
        return Elasticsearch(url, basic_auth=(user, pwd or ""))
    return Elasticsearch(url)


def index_name_for(year: int) -> str:
    return f"cnreport-{year}"


def mapping_hash(mapping: dict) -> str:
    return hashlib.sha1(json.dumps(mapping, sort_keys=True).encode()).hexdigest()[:16]


def ensure_index(es, year: int) -> tuple[str, dict]:
    """Create cnreport-{year} if missing. Tries ik_smart, falls back to standard.

    Returns (index_name, mapping_used).
    """
    name = index_name_for(year)
    if es.indices.exists(index=name):
        return name, CNREPORT_MAPPING  # assume ik; hash still recorded
    try:
        es.indices.create(index=name, mappings=CNREPORT_MAPPING)
        return name, CNREPORT_MAPPING
    except Exception:
        # ik analyzer not installed → retry with standard
        es.indices.create(index=name, mappings=CNREPORT_MAPPING_FALLBACK)
        return name, CNREPORT_MAPPING_FALLBACK


def records_to_docs(records: list[dict], report_id: str, section_id: str) -> list[dict]:
    """Map extracted records to ES docs. Each record carries its own fields."""
    docs = []
    for i, rec in enumerate(records):
        docs.append(
            {
                "_id": f"{report_id}:{section_id}:{i}",
                "report_id": report_id,
                "section_id": section_id,
                "section": section_id,
                "fields": rec,
                "text": json.dumps(rec, ensure_ascii=False),
            }
        )
    return docs


# ── company API (edgartools-style) ───────────────────────────────
# Thin wrappers over cninfo_client + financials_client. All errors return
# {"error": ...} instead of raising, matching the edgartools-mcp pattern.


def _tool_safe(fn):
    """Decorator: convert any exception to {'error': '<type>: <msg>'}."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — tool boundary
            return {"error": f"{type(e).__name__}: {e}"}
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


@_tool_safe
def get_company(ticker_or_name: str) -> dict:
    """Resolve a CN-A-share company by 6-digit ticker or name fragment."""
    import cninfo_client  # late import keeps server.py boot light

    row = cninfo_client.lookup_company(ticker_or_name)
    if not row:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    return row


@_tool_safe
def list_filings(
    ticker_or_name: str,
    form: Optional[str] = None,
    category: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> list[dict] | dict:
    """List a company's disclosures, filtered by form or category and year.

    `form` and `category` are mutually exclusive. `form` accepts the four
    periodic report names or a free-text title substring. `category` accepts
    any CNINFO category code or Chinese name from the catalog (e.g. 招股说明书);
    an unknown category returns an error without a network call.
    """
    import cninfo_client

    if form and category:
        return {"error": "specify either form or category, not both"}
    if category is not None and not cninfo_client.resolve_category(category):
        return {"error": f"unknown CNINFO category: {category!r}"}

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    rows = cninfo_client.query_announcements(
        company["stock_code"],
        company["org_id"],
        form=form,
        category=category,
        year=year,
        limit=limit,
    )
    return rows


@_tool_safe
def get_filing(announcement_id: str, ticker_or_name: Optional[str] = None) -> dict:
    """Fetch one announcement's metadata + PDF URL by id."""
    import cninfo_client

    stock_code = org_id = None
    if ticker_or_name:
        company = cninfo_client.lookup_company(ticker_or_name)
        if company:
            stock_code = company["stock_code"]
            org_id = company["org_id"]
    row = cninfo_client.get_announcement(
        announcement_id, stock_code=stock_code, org_id=org_id,
    )
    if not row:
        return {"error": f"no announcement found: {announcement_id!r}"}
    return row


@_tool_safe
def get_financials(
    ticker_or_name: str,
    statement: Optional[str] = None,
    period: str = "annual",
) -> dict:
    """Return structured income/balance/cashflow statements via akshare."""
    import cninfo_client
    import financials_client

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    try:
        all_stmts = financials_client.get_statements(
            company["stock_code"],
            period=period,
            exchange=company["exchange"],
        )
    except financials_client.MissingDependencyError as e:
        return {"error": str(e)}

    if statement:
        if statement not in all_stmts:
            return {
                "error": (
                    f"unknown statement: {statement!r}; "
                    f"choose from {sorted(all_stmts)}"
                )
            }
        return {
            "stock_code": company["stock_code"],
            "company_name": company["name"],
            "period": period,
            "statement": statement,
            **{statement: all_stmts[statement]},
        }
    return {
        "stock_code": company["stock_code"],
        "company_name": company["name"],
        "period": period,
        **all_stmts,
    }


@_tool_safe
def get_section(
    ticker_or_name: str,
    year: int,
    section: str,
    form: str = "年度报告",
) -> dict:
    """Convenience: resolve filing PDF for (ticker, year, form) then extract a section.

    Reuses the cache-aware fetch path (report_cache.get_or_fetch) →
    parse_outline → resolve_selector → extract_section_text so no PDF is
    re-downloaded or re-parsed when the same report has been fetched before.
    """
    import cninfo_client
    import report_cache

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    filings = cninfo_client.query_announcements(
        company["stock_code"],
        company["org_id"],
        form=form,
        year=year,
        limit=5,
    )
    if not filings:
        return {
            "error": (
                f"no filing found for {company['stock_code']} "
                f"form={form!r} year={year}"
            )
        }
    top = filings[0]
    pdf = top["pdf_url"]
    text, _ = report_cache.get_or_fetch(
        pdf,
        stock_code=company["stock_code"],
        year=year,
        form=form,
        announcement_id=top.get("announcement_id") or "",
    )
    outline = parse_outline(text)
    entry = resolve_selector(outline, section)
    if entry is None:
        return {
            "error": "no section matched selector",
            "available": [e["title"] for e in outline],
            "pdf_url": pdf,
        }
    body = extract_section_text(text, outline, entry)
    return {
        "stock_code": company["stock_code"],
        "company_name": company["name"],
        "year": year,
        "form": form,
        "section": section,
        "pdf_url": pdf,
        "outline_entry": entry,
        "char_count": len(body),
        "text": body,
    }


@_tool_safe
def list_report_types(group: Optional[str] = None) -> dict:
    """Return the CNINFO disclosure category catalog.

    With no `group`, returns every group with its categories. With `group`,
    returns only that group's categories. Each category carries `name`, `code`,
    and `description`. The response includes a `count` of categories returned.
    """
    import cninfo_client

    catalog = cninfo_client.load_categories()
    groups = catalog.get("groups", [])
    if group is not None:
        matched = [g for g in groups if g.get("name") == group]
        if not matched:
            return {
                "error": f"unknown group: {group!r}",
                "available": [g.get("name") for g in groups],
            }
        cats = matched[0].get("categories", [])
        return {"group": group, "categories": cats, "count": len(cats)}
    all_cats: list[dict] = []
    for g in groups:
        all_cats.extend(g.get("categories", []))
    return {"groups": groups, "count": len(all_cats)}


@_tool_safe
def get_special_report(
    ticker_or_name: str,
    category: str,
    year: Optional[int] = None,
    section: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """Retrieve a special-type report for a company by CNINFO category.

    Resolves the company, lists filings of the given `category` (any catalog
    name like 招股说明书 / 增发 / 业绩预告, or a raw `category_*` code), and returns
    the top filing's metadata + pdf_url. When `section` is given, fetches the
    PDF (via the report cache) and extracts that section's body through the
    outline pipeline (parse_outline → resolve_selector → extract_section_text)
    — no PDF logic duplicated. When `section` is omitted, the PDF is NOT downloaded.
    """
    import cninfo_client
    import report_cache

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    if not cninfo_client.resolve_category(category):
        return {"error": f"unknown CNINFO category: {category!r}"}

    filings = cninfo_client.query_announcements(
        company["stock_code"],
        company["org_id"],
        category=category,
        year=year,
        limit=limit,
    )
    if not filings:
        return {
            "error": (
                f"no filing found for {company['stock_code']} "
                f"category={category!r} year={year}"
            )
        }
    top = filings[0]
    if section is None:
        return {
            "stock_code": company["stock_code"],
            "company_name": company["name"],
            "category": category,
            "year": year,
            "filings": filings,
            "pdf_url": top["pdf_url"],
        }
    # Section extraction — via the cache-aware fetch path (no duplication).
    pdf = top["pdf_url"]
    text, _ = report_cache.get_or_fetch(
        pdf,
        stock_code=company["stock_code"],
        year=year,
        form=category,
        announcement_id=top.get("announcement_id") or "",
    )
    outline = parse_outline(text)
    entry = resolve_selector(outline, section)
    if entry is None:
        return {
            "error": "no section matched selector",
            "available": [e["title"] for e in outline],
            "pdf_url": pdf,
        }
    body = extract_section_text(text, outline, entry)
    return {
        "stock_code": company["stock_code"],
        "company_name": company["name"],
        "category": category,
        "year": year,
        "section": section,
        "pdf_url": pdf,
        "outline_entry": entry,
        "char_count": len(body),
        "text": body,
    }


@_tool_safe
def get_financial_statements(
    ticker_or_name: str,
    year: int,
    form: str = "年度报告",
) -> dict:
    """Extract the three major financial statements (三大报表) as text.

    Resolves the company's filing PDF for ``(ticker, year, form)`` (via the
    report cache — no re-download on repeat), parses the table of contents,
    and returns the body text of each statement section:

      - income_statement (利润表)         — prefers 合并利润表
      - balance_sheet (资产负债表)         — prefers 合并资产负债表
      - cashflow (现金流量表)              — prefers 合并现金流量表

    Falls back to the un-prefixed title when no consolidated version is found.
    Returns section **text only** — never PDF bytes. Statements not located in
    the TOC are listed in ``missing`` (with the full ``available`` title list
    so the caller can fall back to ``get_section`` with a custom selector).
    """
    import cninfo_client
    import report_cache

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return {"error": f"no company matched: {ticker_or_name!r}"}
    filings = cninfo_client.query_announcements(
        company["stock_code"],
        company["org_id"],
        form=form,
        year=year,
        limit=5,
    )
    if not filings:
        return {
            "error": (
                f"no filing found for {company['stock_code']} "
                f"form={form!r} year={year}"
            )
        }
    top = filings[0]
    pdf = top["pdf_url"]
    text, cache_info = report_cache.get_or_fetch(
        pdf,
        stock_code=company["stock_code"],
        year=year,
        form=form,
        announcement_id=top.get("announcement_id") or "",
    )
    outline = parse_outline(text)
    statements: dict = {}
    missing: list[str] = []
    for key in ("income_statement", "balance_sheet", "cashflow"):
        entry = resolve_statement(outline, key)
        if entry is None:
            missing.append(key)
            continue
        body = extract_section_text(text, outline, entry)
        statements[key] = {
            "title": entry["title"],
            "outline_entry": entry,
            "char_count": len(body),
            "text": body,
        }
    result: dict = {
        "stock_code": company["stock_code"],
        "company_name": company["name"],
        "year": year,
        "form": form,
        "pdf_url": pdf,
        "cached": cache_info["cached"],
        "statements": statements,
        "missing": missing,
    }
    if missing:
        result["available"] = [e["title"] for e in outline]
    return result


# ── indicator rules engine (data-driven) ──────────────────────────
# Thin wrappers over indicators_client. Adding an indicator = editing
# indicator_rules.json (no code change), mirroring the cninfo_categories
# convention. Errors return {"error": ...}, never raise.


@_tool_safe
def list_indicators(
    module: Optional[str] = None,
    query: Optional[str] = None,
    company: Optional[str] = None,
) -> dict:
    """Browse the indicator rule set, optionally filtered.

    With no args returns every rule grouped by module/subgroup. `module`
    filters to one module; `query` does a normalized substring match over
    name+aliases; `company` (ticker or name) filters to the rules applicable
    to that company and includes the resolved `{industry, sub_type}` profile.
    """
    import indicators_client

    return indicators_client.list_rules(module=module, query=query, company=company)


@_tool_safe
def get_indicator(
    indicator: str,
    ticker_or_name: str,
    year: int,
    period: str = "annual",
) -> dict:
    """Resolve one named indicator to a value for a company + period.

    Routes per the rule's source_type: akshare line items, annual-report PDF
    section (LLM or registered Python extractor), or locally-computed ratio.
    Returns `{value, unit, source_type, extractor, source, period, provenance}`
    or `{error}`. Indicators whose rule does not apply to the company return an
    error without fetching the PDF.
    """
    import indicators_client

    return indicators_client.get_indicator(indicator, ticker_or_name, year, period=period)


@_tool_safe
def extract_indicators(
    ticker_or_name: str,
    year: int,
    indicators: Optional[list] = None,
    form: str = "年度报告",
    extractor_mode: str = "auto",
) -> dict:
    """Extract many indicators for one company/year in a single pass.

    Fetches the annual-report PDF once, groups report-rules by section (one LLM
    call per section), dispatches Python extractors individually, and computes
    derived ratios locally. Caches the resulting bundle to disk keyed by the
    applicable rule set. `extractor_mode` is `auto` (default), `llm` (force LLM
    for report rules), or `python` (skip report rules whose extractor is LLM).
    """
    import indicators_client

    return indicators_client.extract_indicators(
        ticker_or_name, year, indicators=indicators, form=form, extractor_mode=extractor_mode,
    )


@_tool_safe
def extract_indicators_by_position(
    ticker_or_name: str,
    year: int,
    csv_path: str = "docs/indicators_position.csv",
    extractor: str = "auto",
    indicators: Optional[list] = None,
) -> dict:
    """Extract the indicators named in a position CSV for one company/year.

    Reads the CSV's ``indicator`` column (default ``docs/indicators_position.csv``),
    intersects it with ``indicators`` if given, resolves each name to a rule, and
    routes ``report`` / ``akshare`` / ``computed`` rules through the batch engine.
    ``external`` (realtime / market-data) indicators are listed in ``skipped`` —
    they are not present in the report PDF and are never fetched or sent to the LLM.

    Returns: ``{stock_code, company_name, year, form, pdf_url, cached, indicators,
              missing, unresolved, skipped, csv_path}`` or ``{error}``.
    """
    import indicators_client

    return indicators_client.extract_indicators_by_position(
        ticker_or_name, year, csv_path=csv_path, extractor=extractor, indicators=indicators,
    )
