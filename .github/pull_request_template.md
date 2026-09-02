## What & why

<!-- What changed and the reason. Link any issue (e.g. "Closes #123"). -->

## Checklist

- [ ] Title is Conventional Commits (`type(scope): summary`, ≤72 chars) - it becomes the squash subject
- [ ] `sh scripts/verify.sh` passes locally (secret scan + lint + tests - the "done" bar)
- [ ] Docs (`docs/`) and user-facing copy updated if behavior changed
- [ ] Verified in the real runtime (preview/staging), where one exists
