#!/usr/bin/env python3
"""Web dashboard for browsing & editing indicator_rules.json.

Usage:
    uv run python scripts/rules_dashboard.py
    # → open http://127.0.0.1:8899

API endpoints:
    GET  /api/rules          → full rules JSON
    POST /api/rules          → save updated rules array (body: {"rules": [...]})
    POST /api/rules/reset    → reload from disk, discarding unsaved changes
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_RULES_PATH = _REPO_ROOT / "indicator_rules.json"

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Indicator Rules Dashboard</title>
<style>
  :root { --bg: #f5f5f5; --card: #fff; --border: #ddd; --text: #333; --text2: #666; --accent: #1a73e8; --danger: #d93025; --success: #188038; --radius: 8px; }
  *, *::before, *::after { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: var(--bg); color: var(--text); font-size: 14px; }
  h1 { margin: 0 0 8px; font-size: 22px; display: flex; align-items: center; gap: 12px; }
  h1 small { font-size: 13px; font-weight: 400; color: var(--text2); }

  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; padding: 12px 16px; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); }
  .toolbar input, .toolbar select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; }
  .toolbar .search { flex: 1; min-width: 180px; }
  .toolbar .stats { margin-left: auto; font-size: 13px; color: var(--text2); white-space: nowrap; }
  .toolbar button { padding: 6px 14px; border: none; border-radius: 4px; font-size: 13px; cursor: pointer; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-outline { background: transparent; border: 1px solid var(--border); }
  .btn-primary:hover { opacity: .85; }
  .btn-danger:hover { opacity: .85; }
  .btn-outline:hover { background: #eee; }
  .btn:disabled { opacity: .5; cursor: not-allowed; }

  .status { padding: 8px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; display: none; }
  .status.success { display: block; background: #e6f4ea; color: var(--success); border: 1px solid #ceead6; }
  .status.error { display: block; background: #fce8e6; color: var(--danger); border: 1px solid #f5c6cb; }

  .table-wrap { overflow-x: auto; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); }
  table { width: 100%; border-collapse: collapse; white-space: nowrap; }
  th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #eee; }
  th { position: sticky; top: 0; background: #fafafa; font-weight: 600; font-size: 12px; color: var(--text2); cursor: pointer; user-select: none; }
  th:hover { background: #f0f0f0; }
  th .sort { margin-left: 4px; opacity: .4; }
  th .sort.active { opacity: 1; }
  tr:hover { background: #f8fbff; }
  tr.deleted td { opacity: .4; text-decoration: line-through; }
  td[contenteditable="true"] { cursor: text; background: #fffbe6; min-width: 40px; }
  td[contenteditable="true"]:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  td .tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 500; }
  .tag-akshare { background: #e3f2fd; color: #1565c0; }
  .tag-report { background: #fce4ec; color: #c62828; }
  .tag-computed { background: #e8f5e9; color: #2e7d32; }
  .tag-external { background: #f3e5f5; color: #7b1fa2; }
  .tag-llm { background: #fff3e0; color: #e65100; }
  .tag-python { background: #e0f7fa; color: #00695c; }

  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 100; align-items: center; justify-content: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: var(--card); border-radius: var(--radius); padding: 24px; min-width: 400px; max-width: 640px; max-height: 80vh; overflow-y: auto; }
  .modal h2 { margin: 0 0 16px; font-size: 18px; }
  .modal label { display: block; margin-bottom: 4px; font-weight: 500; font-size: 13px; }
  .modal input, .modal select, .modal textarea { width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; margin-bottom: 12px; }
  .modal textarea { min-height: 60px; font-family: monospace; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }

  .indicator-detail { white-space: normal; font-size: 12px; color: var(--text2); max-width: 300px; }
  .indicator-detail code { font-size: 11px; background: #f5f5f5; padding: 1px 4px; border-radius: 2px; }
</style>
</head>
<body>

<h1>📊 Indicator Rules Dashboard <small id="fileInfo"></small></h1>

<div id="status" class="status"></div>

<div class="toolbar">
  <input class="search" id="search" type="text" placeholder="搜索 indicator name / alias..." oninput="render()">
  <select id="filterModule" onchange="render()"><option value="">所有模块</option></select>
  <select id="filterSource" onchange="render()"><option value="">所有来源</option></select>
  <select id="filterExtractor" onchange="render()"><option value="">所有提取器</option></select>
  <button class="btn-primary" onclick="addRule()">+ 新增</button>
  <button class="btn-danger" onclick="deleteSelected()">🗑 删除选中</button>
  <button class="btn-outline" onclick="resetRules()">↻ 重置</button>
  <button class="btn-primary" onclick="saveRules()" id="saveBtn">💾 保存</button>
  <span class="stats" id="stats"></span>
</div>

<div class="table-wrap">
<table>
<thead><tr>
  <th style="width:28px"><input type="checkbox" id="selectAll" onchange="toggleAll()"></th>
  <th onclick="sortBy('name')">名称 <span class="sort" id="s-name">▼</span></th>
  <th onclick="sortBy('module')">模块 <span class="sort" id="s-module">▼</span></th>
  <th onclick="sortBy('subgroup')">分组 <span class="sort" id="s-subgroup">▼</span></th>
  <th onclick="sortBy('source_type')">来源 <span class="sort" id="s-source_type">▼</span></th>
  <th onclick="sortBy('extractor')">提取器 <span class="sort" id="s-extractor">▼</span></th>
  <th>单元 / 详情</th>
  <th style="width:60px">操作</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>

<!-- Add/Edit modal -->
<div class="modal-overlay" id="modal">
<div class="modal">
  <h2 id="modalTitle">新增指标规则</h2>
  <label>名称 *</label><input id="f_name">
  <label>别名 (逗号分隔)</label><input id="f_aliases" placeholder="不良率, NPL ratio">
  <label>模块</label>
  <select id="f_module">
    <option value="balance_sheet">balance_sheet</option>
    <option value="income_statement">income_statement</option>
    <option value="cashflow">cashflow</option>
    <option value="financial_ratio">financial_ratio</option>
    <option value="report_section">report_section</option>
    <option value="market_data">market_data</option>
  </select>
  <label>分组</label><input id="f_subgroup" placeholder="e.g. 一、资产">
  <label>来源类型 *</label>
  <select id="f_source_type" onchange="toggleSourceFields()">
    <option value="akshare">akshare</option>
    <option value="report">report (PDF)</option>
    <option value="computed">computed (公式)</option>
    <option value="external">external (外部)</option>
  </select>
  <div id="sourceFields"></div>
  <label>提取器</label><input id="f_extractor" placeholder="llm / python:table_row / auto">
  <label>单位</label><input id="f_unit" placeholder="元 / % / 倍">
  <label>报告类型</label>
  <select id="f_report_type">
    <option value="年报/半年报/季报">年报/半年报/季报</option>
    <option value="年报/半年报">年报/半年报</option>
    <option value="年报">年报</option>
  </select>
  <label>适用行业</label>
  <select id="f_industry">
    <option value="*">所有行业</option>
    <option value="bank">银行</option>
  </select>
  <label>备注</label><textarea id="f_note" rows="2"></textarea>
  <div class="modal-actions">
    <button class="btn-outline" onclick="closeModal()">取消</button>
    <button class="btn-primary" id="modalSaveBtn" onclick="saveRuleFromModal()">保存</button>
  </div>
</div>
</div>

<script>
let allRules = [];
let sortField = 'name', sortDir = 1;
let selectedIds = new Set();
let editingIndex = -1;

async function load() {
  try {
    const r = await fetch('/api/rules');
    const data = await r.json();
    allRules = data.rules || [];
    document.getElementById('fileInfo').textContent = `${allRules.length} 条规则`;
    populateFilters();
    render();
  } catch(e) { showStatus('加载失败: '+e.message, 'error'); }
}

function populateFilters() {
  const modules = [...new Set(allRules.map(r => r.module).filter(Boolean))].sort();
  const sources = [...new Set(allRules.map(r => r.source_type).filter(Boolean))].sort();
  const extractors = [...new Set(allRules.map(r => r.extractor || (r.source||{}).extractor || 'llm').filter(Boolean))].sort();

  const sel = id => document.getElementById(id);
  sel('filterModule').innerHTML = '<option value="">所有模块</option>' + modules.map(m => `<option>${m}</option>`).join('');
  sel('filterSource').innerHTML = '<option value="">所有来源</option>' + sources.map(s => `<option>${s}</option>`).join('');
  sel('filterExtractor').innerHTML = '<option value="">所有提取器</option>' + extractors.map(e => `<option>${e}</option>`).join('');
}

function getFiltered() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const mod = document.getElementById('filterModule').value;
  const src = document.getElementById('filterSource').value;
  const ext = document.getElementById('filterExtractor').value;
  return allRules.map((r,i) => [r,i]).filter(([r]) => {
    if (q && ![r.name, ...(r.aliases||[])].some(a => (a||'').toLowerCase().includes(q))) return false;
    if (mod && r.module !== mod) return false;
    if (src && r.source_type !== src) return false;
    if (ext) { const e = r.extractor || (r.source||{}).extractor || 'llm'; if (e !== ext) return false; }
    return true;
  });
}

function render() {
  const filtered = getFiltered();
  const sorted = [...filtered].sort((a,b) => {
    const va = (a[0][sortField]||''), vb = (b[0][sortField]||'');
    return sortDir * va.localeCompare(vb, 'zh');
  });

  document.getElementById('stats').textContent = `${sorted.length} / ${allRules.length} 条`;

  document.getElementById('selectAll').checked = false;

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = sorted.map(([r, idx]) => {
    const sel = selectedIds.has(idx) ? 'checked' : '';
    const ext = r.extractor || (r.source||{}).extractor || 'llm';
    const st = r.source_type;
    const detail = detailCell(r);
    return `<tr data-idx="${idx}" class="${r._deleted ? 'deleted' : ''}">
      <td><input type="checkbox" ${sel} onchange="toggleRow(${idx})"></td>
      <td contenteditable="true" onblur="editField(${idx},'name',this.textContent)">${esc(r.name||'')}</td>
      <td><select onchange="editField(${idx},'module',this.value)">${modOpts(r.module)}</select></td>
      <td contenteditable="true" onblur="editField(${idx},'subgroup',this.textContent)">${esc(r.subgroup||'')}</td>
      <td><span class="tag tag-${st}">${st}</span></td>
      <td><span class="tag tag-${ext.startsWith('python')?'python':ext}">${ext}</span></td>
      <td class="indicator-detail">${detail}</td>
      <td><button class="btn-outline" style="padding:2px 8px;font-size:11px" onclick="openEdit(${idx})">✎</button></td>
    </tr>`;
  }).join('');

  // Sort indicators
  document.querySelectorAll('.sort').forEach(el => el.classList.remove('active'));
  const sortEl = document.getElementById('s-'+sortField);
  if (sortEl) { sortEl.classList.add('active'); sortEl.textContent = sortDir > 0 ? '▲' : '▼'; }
}

function detailCell(r) {
  const parts = [];
  if (r.source_type === 'akshare') parts.push(`<code>${r.source?.statement||'?'}.${r.source?.field||'?'}</code>`);
  else if (r.source_type === 'report') parts.push((r.source?.selectors||[]).map(s => `<code>${s.section||'?'}</code>`).join(' → '));
  else if (r.source_type === 'computed') parts.push(`<code>${(r.source?.formula||'').slice(0,40)}</code>`);
  else if (r.source_type === 'external') parts.push('外部数据');
  if (r.unit) parts.push(`<b>${r.unit}</b>`);
  if (r.report_type) parts.push(r.report_type);
  return parts.join(' ') || '—';
}

function modOpts(v) {
  return ['balance_sheet','income_statement','cashflow','financial_ratio','report_section','market_data']
    .map(m => `<option ${m===v?'selected':''}>${m}</option>`).join('');
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function sortBy(field) {
  if (sortField === field) sortDir = -sortDir;
  else { sortField = field; sortDir = 1; }
  render();
}

function toggleAll() { const v = document.getElementById('selectAll').checked;
  const filtered = getFiltered();
  filtered.forEach(([r,idx]) => { if (v) selectedIds.add(idx); else selectedIds.delete(idx); });
  render();
}
function toggleRow(idx) { if (selectedIds.has(idx)) selectedIds.delete(idx); else selectedIds.add(idx); render(); }

function editField(idx, field, value) {
  if (idx < 0 || idx >= allRules.length) return;
  allRules[idx][field] = value;
  if (field === 'module') render();
  markDirty();
}

function markDirty() { document.getElementById('saveBtn').disabled = false; }

async function saveRules() {
  const btn = document.getElementById('saveBtn'); btn.disabled = true;
  try {
    const clean = allRules.map(({_deleted, ...r}) => r);
    const r = await fetch('/api/rules', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({rules: clean})});
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    showStatus(`✅ 已保存 ${data.count} 条规则`, 'success');
    selectedIds.clear();
    await load();
  } catch(e) { showStatus('保存失败: '+e.message, 'error'); btn.disabled = false; }
}

async function resetRules() {
  if (!confirm('重置将丢弃所有未保存的修改，确定？')) return;
  try {
    const r = await fetch('/api/rules/reset', {method:'POST'});
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    showStatus('已重置', 'success');
    await load();
  } catch(e) { showStatus('重置失败: '+e.message, 'error'); }
}

function deleteSelected() {
  if (selectedIds.size === 0) return;
  if (!confirm(`确定删除 ${selectedIds.size} 条规则？`)) return;
  for (const idx of selectedIds) allRules[idx]._deleted = true;
  selectedIds.clear();
  render();
  markDirty();
}

function addRule() {
  editingIndex = -1;
  document.getElementById('modalTitle').textContent = '新增指标规则';
  ['f_name','f_aliases','f_subgroup','f_extractor','f_unit','f_note'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('f_module').value = 'balance_sheet';
  document.getElementById('f_source_type').value = 'report';
  document.getElementById('f_report_type').value = '年报/半年报/季报';
  document.getElementById('f_industry').value = '*';
  toggleSourceFields();
  document.getElementById('modal').classList.add('active');
  document.getElementById('modalSaveBtn').textContent = '新增';
}

function openEdit(idx) {
  editingIndex = idx;
  const r = allRules[idx];
  document.getElementById('modalTitle').textContent = '编辑: ' + (r.name||'');
  document.getElementById('f_name').value = r.name||'';
  document.getElementById('f_aliases').value = (r.aliases||[]).join(', ');
  document.getElementById('f_module').value = r.module||'';
  document.getElementById('f_subgroup').value = r.subgroup||'';
  document.getElementById('f_source_type').value = r.source_type||'report';
  document.getElementById('f_extractor').value = r.extractor||(r.source||{}).extractor||'';
  document.getElementById('f_unit').value = r.unit||'';
  document.getElementById('f_report_type').value = r.report_type||'年报/半年报/季报';
  document.getElementById('f_industry').value = (r.applies_to||{}).industry||'*';
  document.getElementById('f_note').value = r.note||'';
  toggleSourceFields();
  // Fill source fields
  fillSourceFields(r);
  document.getElementById('modal').classList.add('active');
  document.getElementById('modalSaveBtn').textContent = '更新';
}

function closeModal() { document.getElementById('modal').classList.remove('active'); }

function toggleSourceFields() {
  const st = document.getElementById('f_source_type').value;
  const div = document.getElementById('sourceFields');
  if (st === 'akshare') div.innerHTML = `
    <label>Statement</label><input id="sf_statement" placeholder="balance_sheet / income_statement / cashflow">
    <label>Field</label><input id="sf_field" placeholder="资产总计">`;
  else if (st === 'report') div.innerHTML = `
    <label>Section selectors (逗号分隔, 按优先级)</label>
    <input id="sf_selectors" placeholder="客户存款, 资产负债表" value="客户存款">
    <label>Schema hint (JSON)</label>
    <textarea id="sf_schema_hint" rows="2" placeholder='{"indicator":"客户存款","period":"本年"}'></textarea>`;
  else if (st === 'computed') div.innerHTML = `
    <label>Formula</label><input id="sf_formula" placeholder="不良贷款余额 / 贷款和垫款总额 * 100">
    <label>Inputs (逗号分隔)</label>
    <input id="sf_inputs" placeholder="不良贷款余额, 贷款和垫款总额">`;
  else div.innerHTML = '';
}

function fillSourceFields(r) {
  const src = r.source||{};
  const st = r.source_type;
  if (st === 'akshare') {
    document.getElementById('sf_statement').value = src.statement||'';
    document.getElementById('sf_field').value = src.field||'';
  } else if (st === 'report') {
    document.getElementById('sf_selectors').value = (src.selectors||[]).map(s => s.section).filter(Boolean).join(', ');
    document.getElementById('sf_schema_hint').value = JSON.stringify(src.schema_hint||{}, null, 2);
  } else if (st === 'computed') {
    document.getElementById('sf_formula').value = src.formula||'';
    document.getElementById('sf_inputs').value = (src.inputs||[]).join(', ');
  }
}

function collectSource() {
  const st = document.getElementById('f_source_type').value;
  if (st === 'akshare') return {statement: document.getElementById('sf_statement').value, field: document.getElementById('sf_field').value};
  if (st === 'report') {
    const selStr = document.getElementById('sf_selectors').value;
    const selectors = selStr.split(',').map(s => s.trim()).filter(Boolean).map(section => ({section}));
    let schema_hint = {};
    try { const v = document.getElementById('sf_schema_hint').value.trim(); if (v) schema_hint = JSON.parse(v); } catch {}
    return {selectors, schema_hint, extractor: document.getElementById('f_extractor').value || 'llm'};
  }
  if (st === 'computed') return {
    formula: document.getElementById('sf_formula').value,
    inputs: document.getElementById('sf_inputs').value.split(',').map(s => s.trim()).filter(Boolean)
  };
  return {};
}

function saveRuleFromModal() {
  const name = document.getElementById('f_name').value.trim();
  if (!name) { alert('名称不能为空'); return; }
  const aliases = document.getElementById('f_aliases').value.split(',').map(s => s.trim()).filter(Boolean);
  const module = document.getElementById('f_module').value;
  const subgroup = document.getElementById('f_subgroup').value.trim();
  const source_type = document.getElementById('f_source_type').value;
  const extractor = document.getElementById('f_extractor').value.trim() || (source_type === 'report' ? 'llm' : source_type === 'computed' ? 'computed' : 'auto');
  const unit = document.getElementById('f_unit').value.trim();
  const report_type = document.getElementById('f_report_type').value;
  const industry = document.getElementById('f_industry').value;
  const note = document.getElementById('f_note').value.trim();

  const rule = {
    name, aliases, module, subgroup,
    applies_to: {industry, sub_types: ['*'], companies: ['*'], exclude_companies: []},
    source_type, source: collectSource(),
    extractor, unit, period_type: 'annual', direction: 'none', note, report_type
  };

  if (editingIndex >= 0) {
    allRules[editingIndex] = rule;
  } else {
    allRules.push(rule);
  }
  closeModal();
  render();
  markDirty();
}

function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg; el.className = 'status ' + type;
  setTimeout(() => { el.className = 'status'; }, 4000);
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
load();
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def _send(self, data: str, ct: str = "application/json", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode("utf-8"))

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _load_data(self) -> dict:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))

    def _save_data(self, data: dict):
        backup = _RULES_PATH.with_suffix(".json.bak")
        import shutil
        shutil.copy2(str(_RULES_PATH), str(backup))
        _RULES_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def do_GET(self):
        if self.path == "/":
            self._send(HTML, "text/html;charset=utf-8")
        elif self.path == "/api/rules":
            data = self._load_data()
            self._send(json.dumps(data, ensure_ascii=False))
        else:
            self._send('{"error":"not found"}', status=404)

    def do_POST(self):
        if self.path == "/api/rules":
            body = json.loads(self._read_body())
            rules = body.get("rules", [])
            data = self._load_data()
            data["rules"] = rules
            self._save_data(data)
            self._send(json.dumps({"ok": True, "count": len(rules)}))
        elif self.path == "/api/rules/reset":
            import indicators_client
            indicators_client.invalidate_rules_cache()
            data = self._load_data()
            n = len(data.get("rules", []))
            self._send(json.dumps({"ok": True, "count": n}))
        else:
            self._send('{"error":"not found"}', status=404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Dashboard: http://127.0.0.1:{port}")
    print(f"Rules file: {_RULES_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
