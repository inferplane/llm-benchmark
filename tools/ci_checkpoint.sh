#!/usr/bin/env bash
# Commit and push benchmark progress from GitHub Actions so a timed-out or
# failed job resumes from the branch instead of paying for calls again.
# Usage: tools/ci_checkpoint.sh <branch> <message>
set -euo pipefail
branch="$1"; message="$2"
git add -A config.toml results validation docs
if git diff --cached --quiet; then
  echo "checkpoint: nothing to commit"
  exit 0
fi
git commit -q -m "$message"
for attempt in 1 2 3; do
  if git push -q origin "HEAD:refs/heads/${branch}"; then
    echo "checkpoint: pushed ${branch} ($message)"
    exit 0
  fi
  echo "checkpoint: push attempt ${attempt} failed; rebasing"
  git pull -q --rebase origin "${branch}" || true
  sleep $((attempt * 10))
done
echo "checkpoint: push failed" >&2
exit 1
