#!/usr/bin/env python3
"""Serve interactive industry rules dashboard with filtering and search.

Start the web dashboard to browse all 21,698 LLM rules across 31 申万 L1 industries.
Filter by industry, module, and keyword; sort by any column; paginated view.

CLI usage::

    python scripts/industry_rules_dashboard.py [port]

MCP / programmatic usage::

    from scripts.industry_rules_dashboard import start_dashboard
    start_dashboard(8888)  # blocking, Ctrl+C to stop
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import sys
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT.parent / ".env")  # root .env
load_dotenv(_REPO_ROOT / ".env", override=True)  # cnreport .env overrides

import rules_db
from cnreport_models import LlmRule

# Industry labels
SW_LABELS = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属",
    "801080": "电子", "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务", "801230": "综合",
    "801710": "建筑材料", "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备", "801950": "煤炭",
    "801960": "石油石化", "801970": "环保", "801980": "美容护理",
}

def load_data():
    with rules_db._session() as session:
        rows = session.query(LlmRule).filter(
            LlmRule.document_type.like('cn/8%/%/annual-report')
        ).order_by(LlmRule.document_type, LlmRule.module, LlmRule.indicator).all()
    data = []
    for r in rows:
        sw = r.document_type.split('/')[1] if '/' in (r.document_type or '') else ''
        data.append({
            'sw': sw, 'label': SW_LABELS.get(sw, sw),
            'indicator': r.indicator, 'module': r.module or '',
            'subgroup': r.subgroup or '', 'position': r.position or '',
            'instruction': r.instruction or '', 'unit': r.unit or '',
        })
    return data

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/rules':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            data = load_data()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        elif parsed.path == '/api/summary':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            data = load_data()
            modules = sorted(set(r['module'] for r in data if r['module']))
            positions = sorted(set(r['position'] for r in data if r['position'] and len(r['position']) < 60))
            industries = []
            for sw in sorted(set(r['sw'] for r in data)):
                cnt = sum(1 for r in data if r['sw'] == sw)
                industries.append({'sw': sw, 'label': SW_LABELS.get(sw, sw), 'count': cnt})
            self.wfile.write(json.dumps({'modules': modules, 'positions': positions, 'industries': industries, 'total': len(data)}, ensure_ascii=False).encode())
        elif parsed.path == '/' or parsed.path == '':
            html = HTML_TEMPLATE
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            super().do_GET()

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>cnreport 行业规则仪表盘</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; }
.header { background: linear-gradient(135deg, #1a1a2e, #16213e); color: #fff; padding: 20px 30px; }
.header h1 { font-size: 22px; margin-bottom: 5px; }
.header p { opacity: 0.7; font-size: 13px; }
.filters { background: #fff; padding: 15px 30px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; border-bottom: 1px solid #e8e8e8; position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.filters label { font-size: 13px; font-weight: 600; color: #555; }
.filters select, .filters input { padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 13px; min-width: 140px; background: #fff; }
.filters input { min-width: 200px; }
.stats { display: flex; gap: 20px; margin: 20px 30px; }
.stat { background: #fff; padding: 15px 20px; border-radius: 8px; flex: 1; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.stat .num { font-size: 28px; font-weight: 700; color: #1a1a2e; }
.stat .label { font-size: 12px; color: #888; margin-top: 4px; }
.table-wrap { margin: 0 30px 30px; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #fafafa; padding: 10px 14px; text-align: left; font-weight: 600; color: #555; border-bottom: 2px solid #e8e8e8; white-space: nowrap; cursor: pointer; user-select: none; }
th:hover { background: #f0f0f0; }
td { padding: 8px 14px; border-bottom: 1px solid #f0f0f0; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
tr:hover td { background: #f5f7fa; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.tag-bs { background: #e6f7ff; color: #1890ff; }
.tag-is { background: #f6ffed; color: #52c41a; }
.tag-cf { background: #fff7e6; color: #fa8c16; }
.tag-fr { background: #f9f0ff; color: #722ed1; }
.tag-rs { background: #fff0f6; color: #eb2f96; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 8px; padding: 15px; }
.pagination button { padding: 6px 14px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; }
.pagination button:hover { border-color: #1a1a2e; color: #1a1a2e; }
.pagination button.active { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
.pagination span { font-size: 13px; color: #888; }
.loading { text-align: center; padding: 40px; color: #888; }
</style>
</head>
<body>
<div class="header">
  <h1>cnreport · 行业规则仪表盘</h1>
  <p>31 申万 L1 行业 · 规则覆盖定期报告所有章节</p>
</div>
<div class="filters">
  <label>行业</label>
  <select id="fIndustry"><option value="">全部行业</option></select>
  <label>模块</label>
  <select id="fModule"><option value="">全部模块</option></select>
  <label>章节</label>
  <select id="fPosition"><option value="">全部章节</option></select>
  <label>搜索</label>
  <input id="fSearch" placeholder="指标名称、关键词...">
</div>
<div class="stats" id="stats"></div>
<div class="table-wrap">
  <div class="loading" id="loading">加载中...</div>
  <table id="table" style="display:none">
    <thead>
      <tr>
        <th data-sort="sw">行业</th>
        <th data-sort="indicator">指标</th>
        <th data-sort="module">模块</th>
        <th data-sort="subgroup">分组</th>
        <th data-sort="position">定位</th>
        <th data-sort="instruction">提取指令</th>
        <th data-sort="unit">单位</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="pagination" id="pagination"></div>
</div>
<script>
let allData = [];
let filteredData = [];
let page = 1;
const pageSize = 50;
const swLabels = {};
const moduleColors = {balance_sheet:'tag-bs',income_statement:'tag-is',cashflow:'tag-cf',financial_ratio:'tag-fr'};

async function init() {
  const [rules, summary] = await Promise.all([
    fetch('/api/rules').then(r => r.json()),
    fetch('/api/summary').then(r => r.json())
  ]);
  allData = rules;
  summary.industries.forEach(i => { swLabels[i.sw] = i.label; });
  // Populate filters
  const fIndustry = document.getElementById('fIndustry');
  summary.industries.forEach(i => {
    const opt = document.createElement('option');
    opt.value = i.sw; opt.textContent = i.sw + ' ' + i.label;
    fIndustry.appendChild(opt);
  });
  const fModule = document.getElementById('fModule');
  summary.modules.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    fModule.appendChild(opt);
  });
  const fPosition = document.getElementById('fPosition');
  summary.positions.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p;
    fPosition.appendChild(opt);
  });
  // Events
  fIndustry.onchange = filter;
  fModule.onchange = filter;
  fPosition.onchange = filter;
  document.getElementById('fSearch').oninput = filter;
  document.querySelectorAll('th[data-sort]').forEach(th => th.onclick = () => sort(th.dataset.sort));
  filter();
}

function filter() {
  const sw = document.getElementById('fIndustry').value;
  const mod = document.getElementById('fModule').value;
  const pos = document.getElementById('fPosition').value;
  const q = document.getElementById('fSearch').value.toLowerCase();
  filteredData = allData.filter(r => {
    if (sw && r.sw !== sw) return false;
    if (mod && r.module !== mod) return false;
    if (pos && r.position !== pos) return false;
    if (q && !r.indicator.includes(q) && !r.module.includes(q) && !r.subgroup.includes(q) && !r.position.includes(q) && !r.instruction.includes(q)) return false;
    return true;
  });
  page = 1;
  render();
}

function sort(field) {
  filteredData.sort((a, b) => (a[field] || '').localeCompare(b[field] || '', 'zh'));
  render();
}

function render() {
  document.getElementById('loading').style.display = 'none';
  document.getElementById('table').style.display = '';
  const tbody = document.getElementById('tbody');
  const start = (page - 1) * pageSize;
  const pageData = filteredData.slice(start, start + pageSize);
  tbody.innerHTML = pageData.map(r => {
    const mc = moduleColors[r.module] || 'tag-rs';
    return `<tr>
      <td>${swLabels[r.sw] || r.sw} <small style="color:#aaa">${r.sw}</small></td>
      <td><strong>${r.indicator}</strong></td>
      <td><span class="tag ${mc}">${r.module}</span></td>
      <td>${r.subgroup}</td>
      <td title="${r.position}">${r.position}</td>
      <td title="${r.instruction}">${r.instruction}</td>
      <td>${r.unit}</td>
    </tr>`;
  }).join('');
  // Stats
  const modules = new Set(filteredData.map(r => r.module));
  const industries = new Set(filteredData.map(r => r.sw));
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="num">${filteredData.length}</div><div class="label">规则数</div></div>
    <div class="stat"><div class="num">${industries.size}</div><div class="label">行业</div></div>
    <div class="stat"><div class="num">${modules.size}</div><div class="label">模块</div></div>
  `;
  // Pagination
  const totalPages = Math.ceil(filteredData.length / pageSize);
  let pag = `<span>第 ${page}/${totalPages} 页</span>`;
  if (page > 1) pag += `<button onclick="goPage(${page-1})">上一页</button>`;
  for (let p = Math.max(1, page-2); p <= Math.min(totalPages, page+2); p++) {
    pag += `<button class="${p===page?'active':''}" onclick="goPage(${p})">${p}</button>`;
  }
  if (page < totalPages) pag += `<button onclick="goPage(${page+1})">下一页</button>`;
  document.getElementById('pagination').innerHTML = pag;
}

function goPage(p) { page = p; render(); }
init();
</script>
</body>
</html>'''


def start_dashboard(port: int = 8888) -> None:
    """Start the industry rules dashboard web server (blocking).

    Args:
        port: TCP port to listen on (default 8888).
    """
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'Industry Rules Dashboard: http://localhost:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        server.shutdown()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    start_dashboard(port)