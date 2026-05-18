# CLAUDE.md

This file defines how Claude or any AI coding agent should work in this repository.

The goal is not to write a lot of code.
The goal is to make the smallest correct change, verify it, and leave the codebase better than before.

This project follows a practical agentic engineering workflow:
think before coding, keep changes simple, edit surgically, and verify against clear success criteria.

---

# 1. Core Principles

Before writing code, understand the task.

Do not assume silently.
Do not hide confusion.
Do not pick an interpretation without saying why.
Do not create speculative features.
Do not refactor unrelated code.
Do not optimize for looking clever.

Prefer:
- clear assumptions
- small plans
- minimal code
- focused diffs
- existing patterns
- verified behavior
- honest uncertainty

Every changed line should trace back to the user's request.

---

# 2. Think Before Coding

Before implementing, state what you believe the task means.

If anything is unclear, say so.

Explicitly state:
- assumptions
- unclear requirements
- possible interpretations
- tradeoffs
- simpler alternatives
- risks

Do not pretend to understand something you do not understand.

If multiple interpretations exist, present them.

Example:

```text
I see two possible interpretations:

1. Add client-side validation only.
2. Add both client-side and server-side validation.

The safer implementation is option 2, but the smaller requested change is option 1.
I will implement option 1 unless you want full server-side enforcement.
```

If the task is blocked by missing information, stop and ask.

Do not build a random version just to keep moving.

---

# 3. Push Back When Needed

Push back when the requested solution is likely wrong, too complex, unsafe, or unnecessary.

Good pushback is direct and useful.

Examples:
- "This can be done with a smaller change."
- "Adding a new dependency is unnecessary here."
- "This refactor is unrelated to the bug."
- "This feature needs a product decision before implementation."
- "The simpler approach is enough for the stated goal."

Do not be passive.
A coding agent should help protect the project from bad complexity.

---

# 4. Simplicity First

Write the minimum code that solves the problem.

Do not add:
- features not requested
- abstractions for single-use code
- configuration that was not requested
- extension points for hypothetical future needs
- error handling for impossible scenarios
- new libraries without a strong reason
- architectural changes for small tasks

If 50 lines solve the problem, do not write 200.

Ask:

```text
Would a senior engineer say this is overcomplicated?
```

If yes, simplify before finishing.

---

# 5. No Speculative Engineering

Do not build for imagined future requirements.

Avoid phrases in your reasoning like:
- "This might be useful later"
- "For flexibility"
- "To make it extensible"
- "In case we need it someday"

Those are not valid reasons by themselves.

Build what is needed now.

Add flexibility only when the current requirement demands it.

---

# 6. Surgical Changes

Touch only what you must.

When editing existing code:
- do not improve unrelated code
- do not reformat unrelated sections
- do not rename unrelated variables
- do not refactor things that are not broken
- do not update comments unrelated to the task
- do not move files unless necessary
- do not change public APIs unless required

Match the existing style, even if you would normally write it differently.

The test:

```text
Can every changed line be explained by the user's request?
```

If not, remove it.

---

# 7. Clean Up Only Your Own Mess

If your change creates unused imports, variables, functions, files, or tests, remove them.

Do not remove pre-existing dead code unless explicitly asked.

If you notice unrelated dead code, mention it in the final report instead of deleting it.

Good:

```text
I noticed an unrelated unused helper in auth.ts, but did not remove it because it is outside this task.
```

Bad:

```text
Removed unrelated unused code while I was there.
```

Do not do drive-by cleanup.

---

# 8. Goal-Driven Execution

Convert the request into verifiable goals.

Weak goal:

```text
Make validation better.
```

Strong goal:

```text
Invalid email input shows an error, prevents submission, and has a regression test.
```

Before implementation, define success criteria.

Examples:

```text
Task: Add validation.
Success:
- invalid input is rejected
- valid input still works
- tests cover both cases
```

```text
Task: Fix bug.
Success:
- write or identify a failing test that reproduces the bug
- implement the smallest fix
- verify the test passes
```

```text
Task: Refactor component.
Success:
- behavior remains unchanged
- existing tests pass before and after
- code is easier to read
```

Strong success criteria let the agent work independently.

Weak success criteria require clarification.

---

# 9. Plan For Multi-Step Tasks

For non-trivial tasks, write a brief plan before editing.

Use this format:

```text
Plan:
1. Inspect relevant files → verify: identify current behavior.
2. Add/adjust implementation → verify: targeted test or manual check.
3. Run validation → verify: tests/typecheck/lint pass.
```

Keep the plan short.

Do not over-plan simple one-line fixes.

Do not use the plan as theater.
Use it to guide execution.

---

# 10. Implementation Loop

Follow this loop:

1. Understand the task
2. State assumptions
3. Define success criteria
4. Inspect relevant code
5. Make the smallest change
6. Remove only new unused code
7. Run targeted verification
8. Run broader checks when appropriate
9. Report what changed and what remains uncertain

Do not skip verification unless impossible.

If verification is impossible, explain why.

---

# 11. Tests First When Useful

For bug fixes, prefer a failing test first.

Bug fix workflow:

1. Find or write a test that reproduces the bug
2. Confirm it fails for the expected reason
3. Implement the smallest fix
4. Confirm the test passes
5. Run nearby related tests

If writing a test is impractical, explain why and perform the best available verification.

Do not claim a bug is fixed without verification.

---

# 12. Verification Rules

After code changes, run the smallest relevant check first.

Look for project commands in:
- `package.json`
- `pyproject.toml`
- `Cargo.toml`
- `go.mod`
- `Makefile`
- CI config

Common commands:

```bash
npm test
npm run test
npm run lint
npm run typecheck
npm run build
pytest
cargo test
go test ./...
```

Prefer targeted checks before full suites.

If a command fails, inspect the failure.

If the failure is unrelated to your change, report it clearly.

Never say tests passed if they were not run.

---

# 13. Do Not Hide Confusion

If you are confused, say exactly what is confusing.

Good:

```text
I cannot tell whether this validation should happen only in the UI or also in the API route.
The existing code validates similar fields only on the client.
I will follow that pattern unless told otherwise.
```

Bad:

```text
Implemented validation.
```

Hidden confusion creates bad software.

Surface confusion early.

---

# 14. Assumptions Format

When assumptions matter, use this format:

```text
Assumptions:
- The change should follow the existing pattern in `src/forms/`.
- No new dependency should be added.
- The public API should remain unchanged.
```

If an assumption is risky, ask before implementation.

If the assumption is low-risk, proceed and mention it in the final report.

---

# 15. Tradeoff Format

When tradeoffs exist, use this format:

```text
Tradeoff:
- Simpler option: local fix in one file.
- Broader option: shared helper used across all forms.
- Choice: local fix, because only one form currently needs this behavior.
```

Do not silently choose the complex option.

Prefer the simpler option unless evidence says otherwise.

---

# 16. Existing Patterns Win

Before creating new patterns, search for existing ones.

Check:
- nearby files
- similar components
- similar API routes
- existing tests
- existing utilities
- project docs

Use the established approach.

Do not introduce a new architecture because it looks cleaner in isolation.

Consistency beats personal taste.

---

# 17. Dependency Discipline

Do not add a dependency unless necessary.

Before adding one, ask:
- Can the standard library do this?
- Does the project already have a utility?
- Is this dependency already installed?
- Is the problem large enough to justify it?
- Will this increase bundle size or maintenance cost?

If a dependency is added, explain why.

Update the correct lockfile.

---

# 18. Error Handling Discipline

Handle realistic errors.

Do not add defensive code for impossible states unless the project convention requires it.

Good error handling:
- protects user data
- prevents crashes
- explains failures clearly
- matches existing patterns

Bad error handling:
- catches everything silently
- hides bugs
- creates fake fallback behavior
- adds complexity without real risk

Do not swallow errors without a reason.

---

# 19. Security Discipline

Never hardcode secrets.

Be careful with:
- API keys
- tokens
- credentials
- auth logic
- file paths
- user input
- SQL queries
- shell commands
- redirects
- external URLs

Avoid command injection.
Validate inputs at trust boundaries.
Do not log sensitive information.

Security changes require extra caution and verification.

---

# 20. Public API Discipline

Do not change public APIs casually.

If a public function, endpoint, component prop, schema, or config changes:
- update callers
- update tests
- update docs if relevant
- mention the breaking risk
- preserve backward compatibility when possible

If the task does not require an API change, avoid it.

---

# 21. UI Change Discipline

For UI tasks:
- match existing design patterns
- preserve accessibility
- handle loading states when relevant
- handle empty states when relevant
- handle error states when relevant
- avoid layout shifts
- avoid unnecessary animation
- do not add large UI libraries unless asked

For React:
- keep components focused
- avoid unnecessary state
- prefer derived values
- use hooks correctly
- avoid side effects during render

---

# 22. Refactoring Discipline

Refactor only when it directly supports the task.

Valid reasons:
- remove duplication required by the change
- isolate logic for a test
- make a bug fix safer
- simplify code touched by the task

Invalid reasons:
- personal preference
- style cleanup
- architecture improvement unrelated to the request
- rewriting working code because it looks old

Do not mix unrelated refactoring with feature work.

---

# 23. Comment Discipline

Comments should explain why, not what.

Good comments:
- explain a non-obvious constraint
- document a tradeoff
- clarify an external requirement

Bad comments:
- repeat the code
- explain obvious syntax
- become stale quickly

Prefer clear code over more comments.

---

# 24. Documentation Discipline

Update docs when behavior changes.

Useful documentation:
- setup steps
- usage examples
- environment variables
- changed commands
- known limitations
- troubleshooting notes

Do not write vague docs.

Keep docs practical.

---

# 25. File And Naming Discipline

Put new files where similar files already live.

Use existing naming conventions.

Avoid vague names:
- `data`
- `temp`
- `thing`
- `stuff`
- `helper`
- `utils2`
- `newFile`

Create new folders only when the project structure supports it.

---

# 26. Formatting Discipline

Use the project's formatter.

Do not reformat unrelated code.

Do not change indentation, quote style, import order, or semicolon style by hand unless required.

Keep diffs focused.

---

# 27. Git Discipline

Do not create commits unless asked.

Do not change git config.

Do not rewrite history.

Do not run destructive commands unless explicitly asked.

Safe commands:
- `git status`
- `git diff`
- `git log`
- `git branch`

Ask before:
- `git reset --hard`
- `git clean`
- `git rebase`
- `git push --force`

---

# 28. Final Report

At the end of a task, report concisely:

```md
## Completed

- ...

## Changed Files

- `path/to/file`

## Verification

- Ran: ...
- Result: ...

## Assumptions

- ...

## Notes

- Risks:
- Follow-up:
```

Do not paste huge diffs unless asked.

Do not claim verification that was not performed.

---

# 29. When Blocked

If blocked, report:

```md
## Blocked

Reason:
- ...

What I checked:
- ...

Most likely cause:
- ...

Next step:
- ...
```

Do not pretend to finish.

Do not hide missing information.

---

# 30. Final Rule

Think before coding.
Keep it simple.
Change only what matters.
Verify the result.
Report honestly.

The best code agent is not the one that writes the most code.
The best code agent is the one that solves the problem with the least unnecessary damage.
