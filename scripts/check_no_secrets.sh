#!/bin/sh
# 提交前检查：确保敏感文件未被加入暂存区，且代码中无硬编码密钥
# 用法: 在 pre-commit 或 CI 中执行 ./scripts/check_no_secrets.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 1. 敏感文件不应提交
SENSITIVE_FILES="config/defaults\.json|config/users\.db|\.env$|\.env\.local$|.*\.pem$"
if git diff --cached --name-only 2>/dev/null | grep -E "$SENSITIVE_FILES"; then
  echo "ERROR: 敏感文件不应提交！请从暂存区移除：config/defaults.json, config/users.db, .env 等"
  exit 1
fi

# 2. 文件内容中不应包含疑似密钥（排除含 example/fake/test 的行）
# pre-commit: 检查暂存文件；CI: 检查所有 tracked 文件
FILES=$(git diff --cached --name-only 2>/dev/null | grep -E '\.(py|yaml|yml|json|txt|md|sh)$' || true)
[ -z "$FILES" ] && FILES=$(git ls-files | grep -E '\.(py|yaml|yml|json|txt|md|sh)$' || true)
for f in $FILES; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    CONTENT=$(git show ":$f" 2>/dev/null || cat "$f" 2>/dev/null)
    HIT=$(echo "$CONTENT" | grep -vE 'example|fake|test_|dummy|placeholder' | grep -E 'AIza[A-Za-z0-9_-]{20}|sk-[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{30}|gho_[A-Za-z0-9]{30}' || true)
    if [ -n "$HIT" ]; then
      echo "ERROR: 文件 $f 中可能包含硬编码密钥"
      exit 1
    fi
  fi
done
echo "check_no_secrets: OK"
exit 0
