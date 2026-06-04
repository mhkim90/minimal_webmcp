---
name: karpathy
description: When building/writing code — Karpathy's LLM coding best practices (simplicity, surgical changes, goal-driven execution)
---

# Karpathy's LLM Coding Best Practices

Behavioral guidelines to reduce common LLM coding mistakes. Derived from Andrej Karpathy's observations on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Examples
- ❌ "I'll add authentication." → ✅ "I see three ways to add auth: X, Y, Z. Which fits your needs?"
- ❌ Silently choosing a library. → ✅ "This needs a library. Options: A (simple), B (powerful), C (lightweight)?"

---

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Checklist
- [ ] Does every line of code serve the immediate goal?
- [ ] Are there any premature abstractions?
- [ ] Can I remove 30% of the code without breaking it?
- [ ] Would a junior engineer understand this in 2 minutes?

---

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

**The test:** Every changed line should trace directly to the user's request.

### Bad Patterns
- ❌ "While I'm here, let me refactor this function..."
- ❌ Changing formatting in unrelated sections
- ❌ Updating docstrings for code you didn't touch

---

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### Plan Template
```
Goal: [What the user asked for]
Success Criteria:
  - Test 1: [What should happen]
  - Test 2: [What should happen]
  - Test 3: [What should not happen]
Approach:
  1. Step A → verify: Test 1
  2. Step B → verify: Test 2
  3. Step C → verify: Test 3
```

---

## Summary: These guidelines work when:

- ✅ Fewer unnecessary changes in diffs
- ✅ Fewer rewrites due to overcomplication
- ✅ Clarifying questions come before implementation (not after mistakes)
- ✅ Code stays maintainable and readable
- ✅ Tasks complete predictably without scope creep
