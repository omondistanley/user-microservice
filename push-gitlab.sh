#!/usr/bin/env bash
# Push current branch to GitLab using credentials from environment.
# Usage:
#   GITLAB_USER=your_username GITLAB_TOKEN=your_pat ./push-gitlab.sh
# Or export GITLAB_USER and GITLAB_TOKEN first, then run ./push-gitlab.sh
#
# Create a token at: https://gitlab.com/-/user_settings/personal_access_tokens
# Scope: write_repository

set -e
GITLAB_REPO="dimcked94-group/expense-tracker.git"
BRANCH="${1:-main}"

if [ -z "$GITLAB_USER" ] || [ -z "$GITLAB_TOKEN" ]; then
  echo "Usage: GITLAB_USER=your_username GITLAB_TOKEN=your_pat $0 [branch]"
  echo "Default branch: main. Create a token at https://gitlab.com/-/user_settings/personal_access_tokens (scope: write_repository)"
  exit 1
fi

# Push using token in URL for this request only (no storage in git config)
# Use -f only if GitLab allows force push on the branch (main is often protected)
REMOTE_URL="https://${GITLAB_USER}:${GITLAB_TOKEN}@gitlab.com/${GITLAB_REPO}"
git push "$REMOTE_URL" "$BRANCH"
echo "Pushed to GitLab (gitlab.com/${GITLAB_REPO}) branch $BRANCH"
