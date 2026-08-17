#!/usr/bin/env bash
# H5 体验版同步脚本 (Linux/macOS) — SCP 本地 H5 改动到远端服务器
#
# 用法:
#   # 1) 交互式
#   ./scripts/upload_h5.sh
#
#   # 2) 环境变量模式
#   H5_SSH_HOST=8.134.99.53 H5_SSH_USER=root H5_REMOTE_DIR=/opt/xiulijiu/website/h5 \
#     ./scripts/upload_h5.sh
#
#   # 3) Dry-run
#   ./scripts/upload_h5.sh --dry-run
#
# 前置:本机已安装 openssh-client (scp)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
H5_DIR="$PROJECT_ROOT/h5"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# ---------- 读取配置 ----------
HOST="${H5_SSH_HOST:-}";   [[ -z "$HOST"   ]] && read -rp "服务器 IP/域名: " HOST
USER="${H5_SSH_USER:-}";   [[ -z "$USER"   ]] && read -rp "SSH 用户名: " USER
PORT="${H5_SSH_PORT:-22}"
REMOTE="${H5_REMOTE_DIR:-}"; [[ -z "$REMOTE" ]] && read -rp "远端 h5 目录 (例如 /opt/xiulijiu/website/h5): " REMOTE
KEY="${H5_SSH_KEY:-}"

SSH_OPTS=(-P "$PORT")
[[ -n "$KEY" ]] && SSH_OPTS+=(-i "$KEY")

FILES=(index.html app.js styles.css)

# ---------- 检查文件 ----------
for f in "${FILES[@]}"; do
  if [[ ! -f "$H5_DIR/$f" ]]; then
    echo "❌ 本地缺少文件: h5/$f" >&2
    exit 1
  fi
done

# ---------- 上传 ----------
echo
echo "==> 准备同步 ${#FILES[@]} 个文件到 ${USER}@${HOST}:${REMOTE}"
echo

FAILED=0
for f in "${FILES[@]}"; do
  TARGET="${USER}@${HOST}:${REMOTE}/$f"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "[DRY-RUN] scp ${SSH_OPTS[*]} $H5_DIR/$f $TARGET"
  else
    printf "  → %s ..." "$f"
    if scp "${SSH_OPTS[@]}" "$H5_DIR/$f" "$TARGET" 2>/dev/null; then
      echo " OK"
    else
      echo " FAILED"
      FAILED=1
    fi
  fi
done

[[ $DRY_RUN -eq 1 ]] && { echo; echo "Dry-run 完成"; exit 0; }
[[ $FAILED -eq 1 ]] && { echo; echo "❌ 部分文件上传失败"; exit 1; }

# ---------- 验证 ----------
echo
echo "==> 验证远端文件可访问"
for u in \
  https://x.iddg.cn/h5/index.html \
  https://x.iddg.cn/h5/app.js \
  https://x.iddg.cn/h5/styles.css; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code} %{size_download}" --max-time 8 -I "$u" || echo "ERR")
  echo "  $u  $STATUS"
done

echo
echo "==> 完成!"
echo "  体验版地址: https://x.iddg.cn/h5/"
echo "  提示:浏览器可能缓存,推荐用 Ctrl+Shift+R 强刷,或加 ?v=\$(date +%Y%m%d%H%M)"
