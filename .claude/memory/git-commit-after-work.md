---
name: git-commit-after-work
description: Always git commit file changes after completing a task
metadata:
  type: feedback
---

After completing any task that modifies files, always run `git add` and `git commit` without being asked. Include all changed files from the task in a single commit with a descriptive message. Use Co-Authored-By trailer.

**Why:** User expects commits to happen automatically as part of the workflow, not as a separate request.

**How to apply:** At the end of every task involving file edits, check `git diff --stat`, stage relevant files, and commit with a clear message summarizing the changes.
