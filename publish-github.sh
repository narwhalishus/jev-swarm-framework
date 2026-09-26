#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v gh >/dev/null 2>&1; then
  echo 'Install GitHub CLI first: brew install gh'
  exit 1
fi
gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web
account=$(gh api user --jq .login)
if [ "$account" != 'narwhalishus' ]; then
  echo "Signed in as $account. Switch to narwhalishus with gh auth switch first."
  exit 1
fi
if [ ! -d .git ]; then
  git init -b main
fi
if ! git config user.name >/dev/null; then git config user.name narwhalishus; fi
if ! git config user.email >/dev/null; then git config user.email narwhalishus@users.noreply.github.com; fi
git add README.md pyproject.toml .gitignore .env.example jev_swarm examples tests publish-github.sh
if ! git diff --cached --quiet; then
  git commit -m 'Build Jev swarm framework with Bedrock supervision and trace explorer'
fi
if gh repo view narwhalishus/jev-swarm-framework >/dev/null 2>&1; then
  echo 'Repository already exists. No changes pushed; inspect its contents before adding this project.'
  exit 1
fi
gh repo create narwhalishus/jev-swarm-framework --public --source=. --remote=origin --push \
  --description 'Headless Jev decision swarms, bounded lookahead, Bedrock supervision, and interactive traces'
echo 'Repository: https://github.com/narwhalishus/jev-swarm-framework'
