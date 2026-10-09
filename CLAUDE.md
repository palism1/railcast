# Working rules for Claude in this repo

This project is built with Claude Code as a coding assistant. These rules apply to every Claude Code session here.

## Commit authorship

Commits are authored by Mikko. Before the first commit in a session, run:

```sh
git config user.name "Mikko Palis"
git config user.email "165722979+palism1@users.noreply.github.com"
```

Keep the `Co-Authored-By: Claude ...` trailer on commits Claude writes. The `commit-author` CI check enforces the author.

## Ownership

- `docs/decisions.md` is maintained by Mikko. Don't edit it.
- Don't merge PRs.
