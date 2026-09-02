# Architecture

> Fill this in for your project. Keep it a map, not a novel - enough that a new
> contributor (human or AI) knows where things live and why. The invariants that
> must always hold belong in [`../AGENTS.md`](../AGENTS.md); this doc explains the
> shape they enforce.

## Repo layout

```
.
├── .github/         CI, repo policy, issue/PR templates, CODEOWNERS
├── .githooks/       pre-commit gate (wired via git config core.hooksPath)
├── .vscode/         shared editor config and recommended extensions
├── docs/            this documentation
├── scripts/         verify.sh (the 'done' bar) + secret & placeholder guards
├── AGENTS.md        the engineering contract
└── {{ your source }}
```

## The shape of the code

Describe the request/data flow and the layers. State the boundaries plainly, e.g.:

- Where input enters and where it's validated.
- Where business logic lives (and where it must _not_ - keep transport/adapter
  layers thin).
- Where authorization happens.
- How errors propagate and how they surface to callers.

## Where things live

Mirror the "one home per concept" table from [`../AGENTS.md`](../AGENTS.md) with
the concrete paths for this project, so there's a single answer to "where does X
go?".
