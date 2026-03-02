#!/bin/sh
# 提交前检查：确保敏感文件未被加入暂存区
# 用法: 在 pre-commit 或 CI 中执行 ./scripts/check_no_secrets.sh
if git diff --cached --name-only | grep -E 'config/defaults\.json|\.env$|\.env\.local$'; then
  echo "ERROR: 敏感文件不应提交！请从暂存区移除：config/defaults.json, .env 等"
  exit 1
fi
exit 0
