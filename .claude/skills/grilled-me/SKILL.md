---
name: grilled-me
description: When planning or reviewing plans — adversarial self-review to stress-test a plan before presenting
---

# Grilled-Me: Adversarial Plan Self-Review

A self-interrogation technique to stress-test a plan before presenting it to the user or delegating to agents.

**When to use:** After drafting a plan, before presenting it for user approval.

---

## How It Works

Play devil's advocate against your own plan. Ask hard questions as if a skeptical senior engineer is reviewing it.

---

## The Grilling Checklist

### 1. Assumption Check
- What am I assuming to be true that I haven't verified?
- What if those assumptions are wrong?
- Did I silently pick an interpretation without surfacing it?

### 2. Scope Creep Check
- Am I solving more than what was asked?
- Did I add "nice-to-haves" that weren't requested?
- Is every step in the plan traceable to the user's request?

### 3. Risk & Failure Check
- What is the most likely way this plan fails?
- What is the worst-case impact of each step?
- Are there irreversible actions in the plan? (If yes, flag them explicitly.)

### 4. Simplicity Check
- Is there a simpler plan that achieves the same goal?
- Am I over-engineering? Would 50% of this plan still solve the problem?
- Can any steps be merged or eliminated?

### 5. Blind Spot Check
- What am I NOT looking at that could be relevant?
- Are there side effects on other files, modules, or systems?
- Is there existing code that already does part of what I'm planning?

---

## Output Format

After grilling, revise the plan or explicitly document surviving risks:

```
[Grilled-Me Review]
Assumptions confirmed: ...
Risks identified: ...
Simplification applied: ...
Surviving concerns (flagged to user): ...
```

If the plan passes all checks with no changes, state: `[Grilled-Me: No issues found]`

---

## Anti-Patterns to Catch

- ❌ "I'll also refactor X while I'm at it..."
- ❌ Silently assuming a file exists / a function behaves a certain way
- ❌ A plan step that could delete or overwrite without a rollback
- ❌ Steps that are vague ("fix the issue") instead of concrete
