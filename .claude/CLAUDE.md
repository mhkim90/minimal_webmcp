# CLAUDE.md

## Purpose

This repository is a minimal MCP (Model Context Protocol) server for browser automation via embedded WebView (pywebview/Qt). It exposes 10 browser tools over JSON-RPC 2.0 on stdio, with a zero-dependency stdlib mock mode and an optional headless/no-GPU mode for containers. Use these instructions for all code work in this repo.

## General Rules

- Prefer small, surgical changes.
- Keep code simple and avoid speculative abstractions.
- Use the existing repository structure and conventions.
- When multiple independent reads are needed, use parallel tool calls.
- Before editing, inspect the relevant files first.
- After edits, run the smallest useful validation for the touched area.

## Build, Test, and Validation

- Prefer the repository's existing build or test entrypoints when they exist.
- If a change affects notebooks or generated outputs, validate the smallest reproducible path instead of rerunning everything.
- If a dependency or library change is involved, confirm whether it is required before adding it.
- Do not introduce new tooling unless it is clearly needed.

## Library and Dependency Rules

- Prefer the libraries already used in the repository.
- Avoid adding a new dependency unless it materially improves correctness or maintainability.
- If a new library is necessary, keep the scope narrow and document why it is needed.
- Keep imports minimal and remove unused dependencies when possible.

## Coding Standards

Always load these skills at the start of relevant tasks:

- **karpathy**: When building/writing code — Karpathy's LLM coding best practices (simplicity, surgical changes, goal-driven execution)
- **grilled-me**: When planning or reviewing plans — adversarial self-review to stress-test a plan before presenting
- **handoff**: When ending a session or switching context — write a HANDOFF.md so the next agent can continue seamlessly
- **caveman**: When token efficiency is needed — ultra-compressed output (~75% fewer tokens) while keeping full technical accuracy; trigger with `/caveman` or "talk like caveman"
- Language-aware caveman default: use `full` for English responses and `korean-full` for Korean responses unless the user explicitly requests another level.

See [skills/karpathy-best-practices/SKILL.md](skills/karpathy-best-practices/SKILL.md), [skills/grilled-me/SKILL.md](skills/grilled-me/SKILL.md), [skills/handoff/SKILL.md](skills/handoff/SKILL.md), and [skills/caveman/SKILL.md](skills/caveman/SKILL.md).

### Quick Reminders

- State assumptions explicitly; surface ambiguity before writing code.
- Write the minimum code that solves the problem — no speculative abstractions.
- Touch only the files and lines required; match existing style.
- Define success criteria before editing; verify with the smallest useful check.
- Before acting on a plan, ask: am I solving more than asked? What is the most likely failure?
