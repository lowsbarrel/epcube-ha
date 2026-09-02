# Documentation

Long-form explanations behind the terse contract in [`../AGENTS.md`](../AGENTS.md).
Written for people and AI agents alike: every claim should hold against the code,
and a change that alters behaviour updates its doc in the same commit.

| Doc | What's inside |
| --- | --- |
| [setup.md](setup.md) | Installing the integration, configuring it, and setting up for development |
| [architecture.md](architecture.md) | The two layers, why the client is async-only, the write path, sign conventions |
| [api-endpoints.md](api-endpoints.md) | All 118 routes recovered from the app, what's verified, how to explore the rest |
| [testing.md](testing.md) | The verification bar, what the offline suite protects, testing against real hardware |
| [deploy.md](deploy.md) | Trunk-based branching, CI, cutting a release, the HACS bundle |

## Conventions for docs

- **One home per concept.** A fact lives in exactly one doc; the others link to it.
- **Short and current** beats long and stale. Delete what stops being true.
- **Say why, not just what.** The what is in the code; the why is why the doc exists.
