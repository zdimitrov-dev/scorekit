# AGENTS.md

Guidance for AI coding agents working in this repository.

## Start here

Read **`PROJECT_CONTEXT.md`** in full before making any changes. It is the source of
truth for the architecture, data model, current state, and roadmap.

## Keep the context doc updated

`PROJECT_CONTEXT.md` must stay in sync with the code. Whenever you change the
project's state or direction, **update it in the same commit** — specifically:

- the **Status at a glance** table and **Current state in detail** when something
  moves from stub to built,
- the **Build phases roadmap** status column when a phase starts or finishes,
- **Open questions** as they are resolved,
- the **Last updated** date at the top.

If anything in the doc no longer matches the code, fix it.

## Conventions

- Commit style and secret handling are documented in `PROJECT_CONTEXT.md` →
  Conventions.
- Never commit secrets. They live only in `.env`, which is gitignored.
