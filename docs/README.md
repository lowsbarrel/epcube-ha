# Documentation

Long-form explanations that back the terse contract in
[`../AGENTS.md`](../AGENTS.md). Docs are written for both people and AI agents:
keep every claim true against the code, and update the doc in the same change
that alters the behavior it describes.

| Doc                                    | What's inside                                          |
| -------------------------------------- | ------------------------------------------------------ |
| [setup.md](setup.md)                   | Template → your project, and local dev bootstrap       |
| [architecture.md](architecture.md)     | Repo layout and the shape of the code                  |
| [testing.md](testing.md)               | What to test and how the verification bar is defined   |
| [deploy.md](deploy.md)                 | Releasing, CI/CD, and repo policy as code              |

## Conventions for docs

- **One home per concept.** A fact lives in exactly one doc; others link to it.
- **Short and current** beats long and stale. Delete what's no longer true.
