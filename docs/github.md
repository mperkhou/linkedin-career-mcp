# GitHub Setup

After authenticating the GitHub CLI:

```bash
gh auth login
```

Create and push the repository:

```bash
cd /Users/mperkhou/Documents/Codex/linkedin-career-mcp
git init
git add .
git commit -m "Initial Python LinkedIn career MCP server"
gh repo create mperkhou/linkedin-career-mcp --private --source=. --remote=origin --push
```

Use `--public` instead of `--private` if you want the repository publicly visible.
