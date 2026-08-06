#!/usr/bin/env bash
# 一键更新并重新上线：重新生成数据 → commit → push → 等待 Render 自动部署
# 用法：bash deploy.sh "feat: 说明本次改动"
set -e
cd "$(dirname "$0")"
MSG="${1:-chore: 更新}"
URL="${RENDER_URL:-https://jobfinder-3d.onrender.com}"

echo "==> [1/4] 重新生成数据与内联版"
python -m scripts.build_seed_jobs

echo "==> [2/4] 提交并推送（Render 检测到 push 自动重新构建）"
git add -A
git commit -m "$MSG" || echo "    无新变更，跳过提交"
git push -u origin main

echo "==> [3/4] 等待部署完成（免费版构建约 1-3 分钟）"
LOCAL_SHA=$(sha1sum index.html | cut -d' ' -f1)
for i in $(seq 1 20); do
  sleep 15
  LIVE_SHA=$(curl -s --max-time 30 "$URL/" 2>/dev/null | sha1sum | cut -d' ' -f1)
  if [ "$LIVE_SHA" = "$LOCAL_SHA" ]; then
    echo "==> [4/4] ✅ 新版本已上线: $URL"
    exit 0
  fi
  echo "    [$((i*15))s] 尚未更新，继续等待…"
done
echo "==> ⚠️ 超时未确认，请到 Render 控制台 (dashboard.render.com) 查看构建日志"
exit 1
