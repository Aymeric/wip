#!/usr/bin/env python3
"""
Multi-Harness Synchronization Utility for GEX Options Trading System.

Synchronizes agent manifests and prompt files between different harness environments:
1. Canonical Agent Harness (.agents/) - Antigravity / Universal Agent Schema
2. GitHub Copilot Harness (.github/) - VS Code Copilot Agent Schema

Usage:
    python3 scripts/sync_harnesses.py --sync    # Synchronize .github from .agents
    python3 scripts/sync_harnesses.py --check   # Check parity and exit with error if out of sync
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".agents"
GITHUB_DIR = REPO_ROOT / ".github"

TOOL_MAPPING_TO_GITHUB = {
    "run_command": "execute",
    "view_file": "read",
    "replace_file_content": "edit",
    "ask_question": "vscode",
    "search_web": "search",
}


def translate_tools_for_copilot(tools_raw: str) -> str:
    """Translates tool list from Antigravity schema to GitHub Copilot schema."""
    # Pattern to match tool tokens inside brackets
    tokens = [t.strip().strip("'\"") for t in tools_raw.strip("[]").split(",") if t.strip()]
    copilot_tools = []
    seen = set()

    for token in tokens:
        mapped = TOOL_MAPPING_TO_GITHUB.get(token, token)
        if mapped not in seen:
            seen.add(mapped)
            # Retain quote if it was an MCP tool (e.g. 'robinhood-trading/*')
            if "/*" in mapped or "-" in mapped:
                copilot_tools.append(f"'{mapped}'")
            else:
                copilot_tools.append(mapped)

    if "todo" not in seen:
        copilot_tools.append("todo")

    return "[" + ", ".join(copilot_tools) + "]"


def adapt_agent_for_copilot(content: str) -> str:
    """Adapts an agent manifest from .agents to .github Copilot format."""
    # Check frontmatter
    if not content.startswith("---"):
        return content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content

    frontmatter = parts[1]
    body = parts[2]

    # Adapt tools line in frontmatter
    def replace_tools(match):
        tools_str = match.group(1)
        new_tools = translate_tools_for_copilot(tools_str)
        return f"tools: {new_tools}"

    frontmatter = re.sub(r"tools:\s*(\[[^\]]*\])", replace_tools, frontmatter)

    # Adapt tool mentions in body
    adapted_body = body.replace("ask_question", "vscode_askQuestions")

    return f"---{frontmatter}---{adapted_body}"


def adapt_prompt_for_copilot(content: str) -> str:
    """Adapts a prompt manifest from .agents to .github Copilot format."""
    # Replace references to .agents/agents with .github/agents
    content = content.replace(".agents/agents/", ".github/agents/")
    content = content.replace(".agents/prompts/", ".github/prompts/")
    return content


def get_sync_pairs() -> List[Tuple[Path, Path, str]]:
    """Returns pairs of (source_path, target_path, kind)."""
    pairs = []

    # Agent manifests
    agents_src = AGENTS_DIR / "agents"
    agents_dst = GITHUB_DIR / "agents"
    if agents_src.exists():
        for f in sorted(agents_src.glob("*.agent.md")):
            pairs.append((f, agents_dst / f.name, "agent"))

    # Prompt manifests
    prompts_src = AGENTS_DIR / "prompts"
    prompts_dst = GITHUB_DIR / "prompts"
    if prompts_src.exists():
        for f in sorted(prompts_src.glob("*.prompt.md")):
            pairs.append((f, prompts_dst / f.name, "prompt"))

    return pairs


def run_check() -> int:
    """Checks whether .github is in sync with .agents. Returns 0 if in sync, 1 if drift exists."""
    pairs = get_sync_pairs()
    drifts = []

    for src, dst, kind in pairs:
        if not dst.exists():
            drifts.append(f"Missing target file: {dst.relative_to(REPO_ROOT)}")
            continue

        src_content = src.read_text(encoding="utf-8")
        expected_dst_content = adapt_agent_for_copilot(src_content) if kind == "agent" else adapt_prompt_for_copilot(src_content)
        actual_dst_content = dst.read_text(encoding="utf-8")

        if expected_dst_content != actual_dst_content:
            drifts.append(f"Content divergence: {dst.relative_to(REPO_ROOT)} differs from {src.relative_to(REPO_ROOT)}")

    if drifts:
        print("❌ Multi-Harness Sync Check FAILED. The following divergences were detected:")
        for d in drifts:
            print(f"  - {d}")
        print("\nRun `python3 scripts/sync_harnesses.py --sync` to synchronize harnesses.")
        return 1

    print("✅ Multi-Harness Sync Check PASSED. All agent manifests and prompts are synchronized.")
    return 0


def run_sync() -> int:
    """Synchronizes .github manifests from .agents manifests."""
    pairs = get_sync_pairs()
    updated_count = 0

    for src, dst, kind in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src_content = src.read_text(encoding="utf-8")
        expected_content = adapt_agent_for_copilot(src_content) if kind == "agent" else adapt_prompt_for_copilot(src_content)

        if not dst.exists() or dst.read_text(encoding="utf-8") != expected_content:
            dst.write_text(expected_content, encoding="utf-8")
            updated_count += 1
            print(f"  Synchronized: {dst.relative_to(REPO_ROOT)}")

    print(f"✅ Multi-Harness Sync Complete. {updated_count} file(s) updated across harnesses.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Harness Synchronization Utility")
    parser.add_argument("--sync", action="store_true", help="Synchronize .github from .agents")
    parser.add_argument("--check", action="store_true", help="Check parity between harnesses without modifying files")

    args = parser.parse_args()

    if args.check:
        return run_check()
    elif args.sync:
        return run_sync()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
