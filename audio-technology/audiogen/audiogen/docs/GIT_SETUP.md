# Git setup for this repository

## Current layout

| Branch | Purpose |
|--------|---------|
| `main` | Song-upgrade Phases A–C, audits, docs, tests (stable track) |
| `wip/markov-audio-refactor` | Large Markov / audio / composition WIP (`main` + snapshot) |

There is **no `origin` remote** until you add one. The placeholder  
`https://github.com/YOUR_USER/YOUR_REPO.git` was removed — it caused auth errors.

## 1. Create the GitHub repository

On GitHub: **New repository** → name it (e.g. `LLM_AudioGen_Markov_FineTune_01`) → **do not** add README/license/gitignore (this repo already has them).

## 2. SSH key (recommended)

Your Mac has **no default SSH key** for GitHub (`Permission denied (publickey)`).

```bash
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
pbcopy < ~/.ssh/id_ed25519.pub   # paste into GitHub → Settings → SSH and GPG keys
ssh -T git@github.com            # expect: "Hi <user>! You've successfully authenticated..."
```

## 3. Add remote and push

Replace `YOUR_USER` and `YOUR_REPO`:

```bash
cd /path/to/LLM_AudioGen_Markov_FineTune_01

./scripts/setup_git_remote.sh git@github.com:YOUR_USER/YOUR_REPO.git

git push -u origin main
git push -u origin wip/markov-audio-refactor
```

Or use the helper with HTTPS (requires a **Personal Access Token**, not your GitHub password):

```bash
./scripts/setup_git_remote.sh https://github.com/YOUR_USER/YOUR_REPO.git
```

## 4. HTTPS token (if not using SSH)

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained** or **Classic** with `repo` scope.
2. On push, username = GitHub username, password = **token**.

Optional macOS keychain:

```bash
git config --global credential.helper osxkeychain
```

(Use `--global` only if you want this for all repos.)

## 5. Verify

```bash
git remote -v
git branch -vv
git status
```

## Common errors

| Error | Fix |
|-------|-----|
| `remote origin already exists` | `git remote set-url origin <correct-url>` |
| `Invalid username or token` | Wrong URL or password — use PAT, not account password |
| `Permission denied (publickey)` | Add SSH key (step 2) or switch to HTTPS + PAT |
| `YOUR_USER/YOUR_REPO` in URL | Replace with your real GitHub path |
