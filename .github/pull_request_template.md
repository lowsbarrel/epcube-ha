## What & why

## Checklist

- [ ] Title is Conventional Commits (`type(scope): summary`, ≤72 chars); it becomes the squash subject
- [ ] `sh scripts/verify.sh` passes (secrets, invariants, ruff, pyrefly, pytest at 100% coverage)
- [ ] Docs (`docs/`, both READMEs) updated if behaviour or user-facing copy changed
- [ ] Verified against a real system (`uv run epcube status` or a running Home Assistant) if the change touches the API
