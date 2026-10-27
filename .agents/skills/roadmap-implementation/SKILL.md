---
name: roadmap-implementation
description: "Choose and implement the next suitable Clinical Assistant roadmap item by weighing ROADMAP.md against open GitHub issues, then verify the implementation and reconcile local roadmap status."
---

# Roadmap Implementation

Select one valuable, implementable item from the Clinical Assistant roadmap and
open GitHub issues, implement it end to end, and report the evidence for the
selection and verification. Use this workflow when asked to work on the next
roadmap item, pick the next feature, or continue planned product work.

## Workflow

1. **Understand the current worktree and project rules.** Read `AGENTS.md` and
   any more specific instructions relevant to candidate files. Run
   `git status --short` and inspect the current branch. Preserve all existing
   changes; do not overwrite, stage, or revert unrelated work. Read `ROADMAP.md`
   and enough nearby code and tests to understand existing implementation and
   conventions.

2. **Gather GitHub issue candidates.** Determine the repository from its
   configured Git remote rather than guessing its owner or name. When GitHub CLI
   access is available, list open issues with their titles, bodies, labels,
   URLs, milestones, and update times (for example,
   `gh issue list --state open --limit 1000 --json number,title,body,url,labels,milestone,updatedAt`).
   Otherwise use the available GitHub issue search/list tools. If issues cannot
   be accessed, say so and continue with the roadmap; do not imply the issue
   list was reviewed. Read candidate issue details and comments when needed to
   clarify scope, acceptance criteria, dependencies, and whether work is
   already underway.

3. **Build and rank a small candidate set.** Include unchecked, actionable
   roadmap tasks and relevant open issues. Treat a roadmap task and issue as
   one candidate when they describe the same work. Exclude completed items,
   closed issues, duplicates, blocked work, and proposals too vague to
   implement safely. Prefer candidates that are explicitly prioritized or
   unblock other work, align with the current milestone, have clear acceptance
   criteria, and can be delivered as one coherent change. Use roadmap order as
   a tie-breaker, not as a reason to select a much larger or less-ready item.
   Do not infer priority from issue age or popularity alone.

4. **Choose one item and state the rationale.** Before coding, briefly identify
   the selected roadmap entry and/or issue, its acceptance criteria, relevant
   dependencies, and why it is the best ready candidate. If no candidate is
   actionable, explain what is blocking progress rather than inventing a new
   product requirement. Ask the user only when a material product, clinical,
   privacy, security, or compatibility decision is necessary; otherwise make
   conservative choices consistent with `PRODUCT.md` and nearby code.

5. **Implement only that item.** Inspect its owning code path and neighboring
   tests, then make the smallest complete change that satisfies the criteria.
   Follow existing architecture and UI conventions. Clinical behavior must
   remain descriptive and non-diagnostic; preserve record provenance and
   patient privacy. Do not silently expand scope into adjacent roadmap work.
   Add or update focused tests where appropriate. Do not commit, push, deploy,
   or mutate GitHub issues (including closing, editing, or creating issues)
   unless explicitly requested.

6. **Reconcile local documentation.** Update `ROADMAP.md` only when the
   selected work corresponds to an entry and its completion is verified. Mark
   a task complete only when its stated scope is actually implemented; do not
   mark a parent complete while child tasks remain. If the selected issue has
   no matching roadmap entry, do not invent a roadmap commitment. Do not change
   GitHub issue state or claim that it is resolved; report the implemented
   result and the issue reference so the user can decide whether to close it.

7. **Verify the change.** Run the narrowest relevant tests or checks first,
   then the required project gates for the changed files. For Dart/Flutter
   changes, follow `AGENTS.md`: format modified Dart files, run
   `dart format --output=none --set-exit-if-changed .`,
   `flutter analyze --fatal-infos --fatal-warnings`, and relevant tests. If
   connected to a running Flutter app, hot reload or hot restart after the
   change. If a required check cannot run, state why and what remains
   unverified. Review the final diff and ensure unrelated worktree changes are
   untouched.

## Completion Report

Report the selected roadmap item and/or issue link, why it was chosen over the
other ready candidates, the implementation and any roadmap status update,
checks run and their results, and any blockers or remaining work. Be explicit
if GitHub issues could not be reviewed or if the issue itself was not changed.