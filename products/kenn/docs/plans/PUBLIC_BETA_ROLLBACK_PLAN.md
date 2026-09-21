# KENN Public Beta Rollback Plan

**Document Version**: `1.0.0-beta`

**Purpose**: Non-destructive operational procedure to revert code or knowledge base index deployments.

---

## 1. Zero-Destruction Code Rollback

If a critical flaw is identified in a deployment, roll back without using destructive git commands (`git reset --hard`, force-push):

```bash
# 1. Identify previous stable commit SHA
git log --oneline -n 10

# 2. Create a clean revert commit
git revert --no-edit <faulty-commit-sha>

# 3. Re-run CI verification
./scripts/ci_verification.sh

# 4. Restart server
./scripts/start_server.sh
```

---

## 2. Knowledge Base Index Rollback

Knowledge vector indexes are stored under `apps/backend/src/kenn/data/index/versions/`. If an updated knowledge note causes retrieval regressions:

```bash
# 1. List available index versions
ls -l apps/backend/src/kenn/data/index/versions/

# 2. Set environment variable to pin previous index version
export KENN_CHAT_INDEX_DIR="<LOCAL_VOLUME>/Shenrendao/KENN/apps/backend/src/kenn/data/index/versions/v-previous-hash"

# 3. Restart server
./scripts/start_server.sh
```
