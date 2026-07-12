#!/usr/bin/env bash
# 模拟从 PyPI 安装 fd-cn-report 并验证核心模块能否正常导入。
#
# 用法:
#   ./scripts/verify_pypi_install.sh          # 用本地 dist/ 的 wheel 安装（默认，等价于 PyPI 产物）
#   ./scripts/verify_pypi_install.sh --pypi   # 真正从 PyPI 安装（需已发布）
#
# 可选环境变量:
#   PY_VERSION  Python 版本，默认 3.12
#   VENV_DIR    临时 venv 路径，默认 /tmp/cnr_verify_<pid>
#
# 退出码: 0 = 全部通过; 非 0 = 有失败
set -euo pipefail

PKG="fd-cn-report"
PKG_NORM="fd_cn_report"
PY_VERSION="${PY_VERSION:-3.12}"
VENV_DIR="${VENV_DIR:-/tmp/cnr_verify_$$}"
SOURCE="local"

if [[ "${1:-}" == "--pypi" ]]; then
  SOURCE="pypi"
elif [[ -n "${1:-}" ]]; then
  echo "未知参数: $1" >&2
  echo "用法: $0 [--pypi]" >&2
  exit 2
fi

cd "$(dirname "$0")/.."

cleanup() { rm -rf "$VENV_DIR"; }
trap cleanup EXIT

echo "==> 安装来源: $SOURCE"
echo "==> 临时 venv: $VENV_DIR (python $PY_VERSION)"

echo "==> 创建干净 venv"
uv venv "$VENV_DIR" --python "$PY_VERSION" >/dev/null
PYTHON="$VENV_DIR/bin/python"

if [[ "$SOURCE" == "pypi" ]]; then
  echo "==> 从 PyPI 安装 $PKG"
  uv pip install --python "$PYTHON" "$PKG"
else
  WHEEL="$(ls -1 dist/${PKG_NORM}-*.whl 2>/dev/null | tail -1 || true)"
  if [[ -z "$WHEEL" ]]; then
    echo "==> dist/ 无 wheel，先构建..."
    uv build >/dev/null
    WHEEL="$(ls -1 dist/${PKG_NORM}-*.whl | tail -1)"
  fi
  echo "==> 从本地 wheel 安装: $WHEEL"
  uv pip install --python "$PYTHON" "$WHEEL"
fi

echo "==> 在干净环境中验证导入（项目目录不在 sys.path）"
"$PYTHON" <<'PYEOF'
import importlib
import importlib.util
import sys

# 所有打包的顶层模块（与 pyproject.toml 的 py-modules 一致）
MODULES = [
    "server",
    "cnreport_models",
    "cnreport_database",
    "cnreport_tools",
    "cninfo_client",
    "financials_client",
    "indicators_client",
    "indicators_extractors",
    "indicators_csv_migration",
    "report_cache",
    "selfcheck",
    "selfcheck_cache",
    "migrate",
]

ok, fail = [], []
for m in MODULES:
    try:
        importlib.import_module(m)
        ok.append(m)
        print(f"  OK   {m}")
    except Exception as e:
        fail.append(m)
        print(f"  FAIL {m}: {e}")

# 自包含性检查：models 模块不应存在（证明不再依赖 mcp-models）
models_present = importlib.util.find_spec("models") is not None
print(f"\n  models 模块存在（预期 False）: {models_present}")
if models_present:
    fail.append("models-should-not-exist")

# ORM 表校验
from cnreport_models import Base
tables = sorted(t.name for t in Base.metadata.sorted_tables)
expected = ["es_index_meta", "report_documents", "report_sections"]
print(f"  cnreport_models 表: {tables}")
if tables != expected:
    fail.append("tables-mismatch")

# 关键函数
from cnreport_database import make_report_id
rid = make_report_id("src", "co", 2023)
print(f"  make_report_id('src','co',2023) -> {rid!r}")
if not isinstance(rid, str) or len(rid) < 8:
    fail.append("make_report_id-invalid")

print(f"\n==> {len(ok)}/{len(MODULES)} 个模块导入成功")
if fail:
    print(f"失败项: {fail}", file=sys.stderr)
    sys.exit(1)
print("全部检查通过")
PYEOF

echo "==> 完成"
