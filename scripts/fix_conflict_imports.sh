#!/bin/bash
# scripts/fix_conflict_imports.sh

# ============================================================
# Conflict-related import path migration script
# 프로젝트 루트 자동 감지 → 절대경로 의존 없음
# ============================================================

# 프로젝트 루트 자동 감지
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT" || exit 1

echo "🔄 Starting Conflict import migration..."
echo "📁 Project Root: $PROJECT_ROOT"
echo ""

# --------------------------------------------------------------------
# 1. ConflictRecord import 변경
# --------------------------------------------------------------------
find backend/ -name "*.py" -type f -exec sed -i '' \
  's/from backend\.api\.models import ConflictRecord/from backend.models import ConflictRecord/g' {} +

# --------------------------------------------------------------------
# 2. ConflictDetection import 변경
# --------------------------------------------------------------------
find backend/ -name "*.py" -type f -exec sed -i '' \
  's/from backend\.api\.models import ConflictDetection/from backend.models import ConflictDetection/g' {} +

# --------------------------------------------------------------------
# 3. ConflictResolution import 변경
# --------------------------------------------------------------------
find backend/ -name "*.py" -type f -exec sed -i '' \
  's/from backend\.api\.models import ConflictResolution/from backend.models import ConflictResolution/g' {} +

echo "✅ Conflict imports fixed!"
echo ""

# 변경된 파일 목록 출력
echo "📝 Modified files:"
git diff --name-only