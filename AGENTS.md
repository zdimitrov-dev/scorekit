# AGENTS.md

Guidance for AI coding agents working in this repository.

## Start here

Read `PROJECT_CONTEXT.md` before making changes. It is the source of truth for the
architecture, data model, current state and open questions.

## Keep the context doc updated

`PROJECT_CONTEXT.md` must stay in sync with the code. When you change the project's
state or direction, update it in the same commit: the status table when something moves
from stub to built, the roadmap when a phase starts or finishes, open questions as they
resolve, and the date at the top.

Record the reasoning behind a decision, not the narrative of how it was reached.

## Conventions

- **Commit locally, do not push.** The maintainer reviews and pushes. Say when a change
  is committed and ready.
- Concise imperative commit subject; the body explains the why when it is not obvious.
- Never commit secrets. They live only in `.env`, which is gitignored.
- No emoji in code, comments or documentation.
- Comments explain why, not what. Keep them proportionate; do not narrate the debugging
  history that led to a line.
