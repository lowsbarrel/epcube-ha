# Testing

## The verification bar

"Done" has one definition: everything `scripts/verify.sh` runs. The pre-commit
hook and CI run the same script, so a green local run predicts a green PR.

```sh
sh scripts/verify.sh   # secret scan + lint + tests
```

The bar lives in [`../scripts/verify.sh`](../scripts/verify.sh) - one home. The
pre-commit hook and [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
both call it, so "done" can't mean two different things.

Out of the box it runs the secret scan plus `lint`/`test` steps that just print a
reminder. Wire them to your real tools as your first setup step.

## What to test

Fill this in for your stack. A useful default hierarchy:

- **Unit** - pure logic, fast, no I/O. The bulk of the tests.
- **Integration** - real boundaries (database, HTTP, filesystem) against real or
  faithful test doubles.
- **End-to-end** - the critical user paths through the whole system.

## Guidance

- Test behavior, not implementation - assert on outcomes a user or caller cares
  about.
- A bug fix comes with a test that fails before the fix and passes after.
- Keep tests isolated: no shared mutable state between tests; clean up what you
  create.
- The mechanical checks (`check-secrets`, `check-placeholders`) catch slips only;
  they are not a substitute for tests or review.
