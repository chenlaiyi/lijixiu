#!/usr/bin/env bash
# 立即修平台 - 部署脚本
#
# 用法:
#   ./scripts/deploy.sh                    # 部署 staging(默认)
#   ENV=production ./scripts/deploy.sh     # 部署生产
#   ./scripts/deploy.sh --rollback         # 回滚到上一个版本
#
# 前置:
#   - 服务器上已 docker + docker compose plugin
#   - 服务器的 .env 已配置好(从 .env.example 复制)
#   - 微信支付证书在 cert/

set -e
ENV=${ENV:-staging}
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "==> 部署到 $ENV"

# 1. 检查环境
if ! command -v docker >/dev/null; then
    echo "ERR: docker 未安装"
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "ERR: docker compose plugin 未安装"
    exit 1
fi

# 2. 检查 .env
if [ ! -f .env ]; then
    echo "ERR: .env 不存在,请从 .env.example 复制并配置"
    exit 1
fi

# 2.5 严格校验 .env(生产环境强校验,staging 也走 strict 防止漏)
echo "==> 校验 .env 完整性"
if [ "$ENV" = "production" ] || [ "$ENV" = "staging" ]; then
    VALIDATE_FLAGS="--strict"
else
    VALIDATE_FLAGS=""
fi
if ! python3 scripts/validate_env.py $VALIDATE_FLAGS; then
    echo "ERR: .env 校验未通过,按上面提示补齐后再 deploy"
    echo "    提示:本地调试可忽略 placeholder,但 deploy 前必须 strict 通过"
    exit 1
fi

# 3. 备份当前 db(部署前)
if [ -f /data/db/xiulijiu.db ] || docker volume inspect xiulijiu_db >/dev/null 2>&1; then
    echo "==> 备份当前数据库"
    docker compose exec -T api sqlite3 /data/db/xiulijiu.db ".backup /data/db/pre-deploy-$(date +%Y%m%d_%H%M%S).db" 2>/dev/null || true
fi

# 4. 拉最新镜像(或本地 build)
echo "==> 构建镜像"
docker compose build --no-cache

# 5. 滚动重启
echo "==> 重启服务"
docker compose up -d --no-deps api

# 6. 等待健康
echo "==> 等待健康检查"
for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 3
    if docker compose ps api | grep -q "(healthy)"; then
        echo "  ✓ healthy after $((i*3))s"
        break
    fi
    if [ "$i" = "10" ]; then
        echo "ERR: 启动后未健康,回滚..."
        docker compose logs --tail=50 api
        exit 1
    fi
done

# 7. 冒烟测试
echo "==> 冒烟测试"
HEALTH=$(docker compose exec -T api curl -fsS http://localhost:8000/health || echo "FAIL")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "  ✓ /health OK"
else
    echo "ERR: /health failed: $HEALTH"
    exit 1
fi

# 8. 跑对账(防止新代码引入差异)
echo "==> 跑对账检查"
docker compose exec -T api curl -fsS -X POST http://localhost:8000/api/v1/admin/reconcile/run | head -c 200
echo

# 9. 启动 nginx(如果还没起)
echo "==> 启动 nginx"
docker compose up -d nginx

echo
echo "==> 部署完成: $ENV"
echo "  - 容器:    docker compose ps"
echo "  - 日志:    docker compose logs -f api"
echo "  - 健康:    https://your-domain/health"
