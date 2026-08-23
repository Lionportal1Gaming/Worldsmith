# Contributing to Project Worldsmith

## Workflow

1. Create or select a Linear issue in the Project Worldsmith project.
2. Use a branch named `feature/LINEAR-ID-short-description`, `fix/LINEAR-ID-short-description`, `docs/LINEAR-ID-short-description`, or `chore/LINEAR-ID-short-description`.
3. Make focused commits using Conventional Commits: `type(optional-scope): imperative summary`.
4. Open a pull request with the supplied template.
5. Merge only after review, required checks, and any owner approval appropriate to the change.

## Priorities and dependencies

- P1: urgent security, data-loss, release, or production-blocking work
- P2: committed work for the active gate
- P3: planned work
- P4: backlog or research

Use Linear blocker relations for dependencies. A blocked issue must name the blocking identifier in its description and link the relation.

## Cycles

Use two-week cycles after Gate B approval. Phase 0 and gate-governance work remain milestone-managed until then.

## Safety

Never commit credentials, private keys, save files, local environments, generated build output, or unlicensed assets. Run relevant tests before requesting review and document data/save compatibility effects in the pull request.
