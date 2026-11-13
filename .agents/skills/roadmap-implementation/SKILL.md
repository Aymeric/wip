---
name: roadmap-implementation
description: "Choose and implement the next suitable GEX Options Trading System (gex-orchestrator) roadmap item by weighing ROADMAP.md against open GitHub issues, then verify the implementation and reconcile local roadmap status."
---

# Roadmap Implementation

Select one valuable, implementable item from the GEX Options Trading System (`gex-orchestrator`) roadmap and open GitHub issues, implement it end to end, and report the evidence for the selection and verification. Use this workflow when asked to work on the next roadmap item, pick the next feature, or continue planned quantitative/engineering work.

## Workflow

1. **Understand the current worktree and system rules.** Read `AGENTS.md`, `GEMINI.md`, and any more specific instructions relevant to candidate files. Run `git status --short` and inspect the current branch. Preserve all existing changes; do not overwrite, stage, or revert unrelated work. Read `ROADMAP.md` and enough nearby code and tests under `src/gex/` and `src/gex_engine.py` to understand existing architecture and conventions.

2. **Gather GitHub issue candidates.** Determine the repository from its configured Git remote rather than guessing its owner or name. When GitHub CLI access is available, list open issues with their titles, bodies, labels, URLs, milestones, and update times (for example, `gh issue list --state open --limit 1000 --json number,title,body,url,labels,milestone,updatedAt`). Otherwise use the available GitHub issue search/list tools. If issues cannot be accessed, say so and continue with the roadmap; do not imply the issue list was reviewed. Read candidate issue details and comments when needed to clarify scope, acceptance criteria, quantitative formulas, dependencies, and whether work is already underway.

3. **Build and rank a small candidate set.** Include unchecked, actionable roadmap tasks and relevant open issues. Treat a roadmap task and issue as one candidate when they describe the same work. Exclude completed items, closed issues, duplicates, blocked work, and proposals too vague to implement safely. Prefer candidates that are explicitly prioritized or unblock other work (e.g. Phase 5 advanced strategy milestones, backtesting foundations, risk controls), align with the current roadmap phase, have clear acceptance criteria, and can be delivered as one coherent change. Use roadmap order as a tie-breaker, not as a reason to select a much larger or less-ready item. Do not infer priority from issue age or popularity alone.

4. **Choose one item and state the rationale.** Before coding, briefly identify the selected roadmap entry and/or issue, its acceptance criteria, relevant dependencies, and why it is the best ready candidate. If no candidate is actionable, explain what is blocking progress rather than inventing a new system requirement. Ask the user via `ask_question` only when a material strategy, risk threshold, broker execution, or architectural decision is necessary; otherwise make conservative choices consistent with `AGENTS.md`, `GEMINI.md`, and existing codebase patterns.

5. **Implement only that item.** Inspect its owning code path and neighboring tests, then make the smallest complete change that satisfies the criteria:
   - Follow the modular package architecture under `src/gex/` (`core`, `quant`, `risk`, `screening`, `storage`, `presentation`) and CLI routing in `src/gex_engine.py`.
   - Maintain the **strict quantitative framework**: do not compute option Greeks, GEX levels, regime indicators, or position sizing with manual approximations; use deterministic Python implementations.
   - Maintain institutional risk safety: preserve Stop 1–5 hierarchy, account scoping (`--account ACCOUNT_NUMBER`), cash buying power bounds, and micro-account threshold rules ($10,000 net liq).
   - Do not silently expand scope into adjacent roadmap work.
   - Add or update focused unit tests in `tests/test_<feature>.py`.
   - Do not commit, push, deploy, or mutate remote GitHub issues (including closing or editing issues) unless explicitly requested.

6. **Reconcile local documentation.** Update `ROADMAP.md` only when the selected work corresponds to an entry and its completion is verified. Mark a task complete (`[x]`) and update the Summary Roadmap Matrix only when its stated scope is actually implemented and verified; do not mark a parent complete while child tasks remain. If the selected issue has no matching roadmap entry, do not invent a roadmap commitment. Do not change GitHub issue state or claim that it is resolved; report the implemented result and the issue reference so the user can decide whether to close it.

7. **Verify the change.** Run project quality gates for changed files:
   - Unit tests: `python3 -m unittest tests/test_<feature>.py` (and related domain test suites).
   - Core regression check: `python3 -m unittest discover -s tests -p "test_*.py"` or relevant multi-suite test run.
   - Performance benchmarks: `python3 tests/test_performance.py` (ensure Bolt optimizations and sub-millisecond latencies are maintained).
   - Multi-Harness Sync: `python3 scripts/sync_harnesses.py --check` (if agents or prompts were modified, run `python3 scripts/sync_harnesses.py --sync`).
   - Syntax validation: `python3 -m py_compile src/gex_engine.py src/gex/**/*.py`.
   Review the final diff and ensure unrelated worktree changes are untouched.

## Completion Report

Report the selected roadmap item and/or issue link, why it was chosen over the other ready candidates, the implementation details and any roadmap status update, checks run and their results, and any blockers or remaining work. Be explicit if GitHub issues could not be reviewed or if the issue itself was not changed.
