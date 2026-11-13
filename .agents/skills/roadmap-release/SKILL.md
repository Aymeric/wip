---
name: roadmap-release
description: "Use when preparing a GEX Options Trading System (gex-orchestrator) release: review commits, choose a version, update release documentation and roadmap, reconcile GitHub issues, run project quality gates, and verify system integrity."
---

# Release

Prepare a GEX Options Trading System (`gex-orchestrator`) suite release from recent changes. Keep release notes, version metadata, roadmap status, and system integrity aligned with the implementation.

## Arguments

Provide the next semantic version (for example, `1.2.0`). If no version is provided, inspect the latest release tag and commits since that tag to recommend a version. Ask before choosing when the change set does not clearly indicate patch, minor, or major impact.

## Workflow

1. **Check repository state and release history.** Run `git status --short`, inspect the current branch, find the latest version tag with `git describe --tags --abbrev=0`, and review commits since that tag. If there is no tag, inspect `src/gex/__init__.py` (`__version__`) and recent history as context; do not invent a previous release boundary. Read commit subjects, bodies, changed paths, and relevant diffs. Record dates, authors, and issue or PR references when available. Preserve all pre-existing worktree changes.

2. **Inventory the documentation.** Find tracked Markdown files with `rg --files -g '*.md'`, excluding generated/build output. Review relevant content in `README.md`, `ROADMAP.md`, `AGENTS.md`, and any other docs affected by the changes. This repository maintains a durable release history in `CHANGELOG.md`; create or update it when preparing a release.

3. **Choose and apply version metadata.** The system version is declared in `src/gex/__init__.py` as `__version__ = "X.Y.Z"`. Use semantic versioning:
   - **Patch** (`1.1.X`): Backward-compatible bug fixes, minor performance refactors, or formatting adjustments.
   - **Minor** (`1.X.0`): New quantitative indicators (e.g. Vanna/Charm, IV Rank), new screening filters, additional CLI subcommands, or new strategy phases.
   - **Major** (`X.0.0`): Breaking architectural shifts, database schema redesigns requiring manual migrations, or major strategy engine overhauls.
   Keep the declared package version consistent with the release tag and release notes.

4. **Write release notes.** Add a dated version section to `CHANGELOG.md`. Summarize user-visible additions, changes, quant improvements, fixes, removals, and performance/security work in concise, grouped bullets. Include verified issue/PR links using the actual repository URL; do not guess issue numbers, ownership, or links.

5. **Update system documentation.** Update `README.md` for meaningful user-facing changes, and update `ROADMAP.md` or `AGENTS.md` only when their claims, workflows, or instructions changed. Keep documentation specific to implemented behavior; do not document roadmap proposals as shipped features.

6. **Reconcile the roadmap and GitHub issues.** Review completed roadmap items against code and the release changes. Query issues with `gh issue list --state all --limit 1000 --json number,title,state,url,labels,updatedAt` when GitHub CLI access is available. Reflect verified issue state and add links using the repository's actual URL. Do not close, reopen, edit, or create GitHub issues unless explicitly requested. Update roadmap counts, milestones, and release history accurately; label unavailable or incomplete data rather than guessing.

7. **Review agent and developer guidance.** Check `AGENTS.md`, `GEMINI.md`, `.agents/`, and `.github/` instructions for architecture or workflow notes that the release changes make inaccurate. If prompt or agent manifests changed, run `python3 scripts/sync_harnesses.py --sync` to maintain 100% parity across harnesses.

8. **Run project quality gates.** Run the mandatory test and performance checks:
   ```bash
   # 1. Syntax check all modified Python modules
   python3 -m py_compile src/gex_engine.py src/gex/**/*.py

   # 2. Comprehensive unit test discovery
   python3 -m unittest discover -s tests -p "test_*.py"

   # 3. Performance benchmarks
   python3 tests/test_performance.py

   # 4. Multi-harness synchronization check
   python3 scripts/sync_harnesses.py --check

   # 5. CLI sanity check
   python3 src/gex_engine.py --help
   ```

9. **Ask before committing and creating a release tag.** After release preparation and quality checks are complete, summarize the changes and ask the user via `ask_question` whether they want to commit the release changes and create a `v<major.minor.patch>` git tag.
   Do not stage, commit, push, or tag until the user explicitly approves.

   If approved:
   - Recheck the branch, worktree, remote, and whether the target tag already exists. Confirm the semantic version in `src/gex/__init__.py` matches the tag.
   - Stage only the changes prepared for this release. Exclude pre-existing or unrelated user changes unless the user explicitly includes them.
   - Commit the release changes to the branch first.
   - Create the version tag only after the release commit is made.
   - If instructed by the user, push the branch and tag to the remote repository.

   If declined, leave the changes uncommitted and untagged. Do not mutate GitHub issues or publish a GitHub Release unless explicitly requested.

## Completion Report

Summarize the version decision, documentation and roadmap changes, issue state checked, quality gates and benchmarks run, the user's commit/tag decision, and any release actions not completed.
