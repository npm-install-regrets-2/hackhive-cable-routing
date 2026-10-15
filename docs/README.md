# Development documentation

Use this folder as the running record of project work. `PROJECT_PLAN.md` defines the intended system; `CONTEXT.md` defines domain terms; `shared/schema/common.schema.json` defines the development data contract. Progress logs record what actually happened.

## Update after each meaningful step

Before finishing a coding session or commit, append an entry to your own log:

- Harshit: `docs/progress/harshit.md`
- Priyanshu: `docs/progress/priyanshu.md`

A meaningful step is a completed or attempted deliverable such as a parser, validation rule, routing method, fixture, experiment, or interface change. Record unsuccessful attempts when they affect the next decision. Group tiny edits that serve the same deliverable into one entry.

For each entry, include the date, short title, status (`done`, `in progress`, or `blocked`), files or interfaces changed, the reason for the approach, how it was checked and its result, unresolved assumptions or blockers, and the next action. Link to the relevant commit or pull request when one exists. Write facts that another developer could use to continue the work; keep entries brief and append them in chronological order.

If a step changes a shared field, constraint, formula, or interpretation of the challenge rules, update the authoritative file in the same change, record the step in your log, and link a shared decision note when the tradeoff needs explanation. Do not make a progress entry the only source of a rule.

## Entry template

```md
## YYYY-MM-DD — Short title

- Status: done | in progress | blocked
- Changed: paths or interface names
- Why: reason or tradeoff
- Checked: command, fixture, or manual check and result
- Open: assumptions, blockers, or none
- Next: concrete next action
- Commit/PR: link or pending
```
