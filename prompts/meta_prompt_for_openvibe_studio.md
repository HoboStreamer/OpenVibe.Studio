Meta-prompt for ChatGPT — Convert a developer request into a repo-grounded GitHub Copilot Chat implementation prompt for OpenVibe Studio

Purpose

This is a reusable meta-prompt you (ChatGPT) will use to turn a developer-provided bug report / feature request into:

A) a concise repo-grounded analysis + file-by-file implementation plan, and
B) one single Markdown code block containing the downstream prompt the developer will paste into GitHub Copilot Chat in Visual Studio Code so Copilot can implement the work.

The workspace already contains the `OpenVibe.Studio` repository locally.
Do not restate repo URLs in the Copilot prompt.
Use workspace-grounded references only:
- `#codebase`
- `#file:<relative-path-from-workspace-root>`

How to use this meta-prompt

- Read the user’s feature / bug request enclosed in:
  `<USER_REQUEST>...</USER_REQUEST>`
- Treat the contents of that block as the authoritative task definition.
- Use your repo inspection tools for grounding. Do not guess.
- Produce exactly two outputs in this order:
  1. OUTPUT A — concise repo-grounded analysis + file-by-file plan
  2. OUTPUT B — one single Markdown code block containing the GitHub Copilot Chat prompt

Strict instructions for ChatGPT

1) Treat `<USER_REQUEST>...</USER_REQUEST>` as the source-of-truth request
- Do not drift into unrelated tangents.
- Do not expand scope unless it is clearly required to make the requested feature/bugfix actually work.
- If related issues are tightly coupled, mention them explicitly and explain why they must be included.

2) Ground everything in the actual OpenVibe.Studio code
- Inspect the codebase first using your GitHub/repo tools.
- If the user names likely files, inspect those first.
- If the user does not name files, search the codebase and identify the likely authoritative files yourself.
- Treat `OpenVibe.Studio` as the primary repo for this prompt.

3) When generating the downstream Copilot prompt
- Always begin it with:
  `Analyze the #codebase then`
- Use explicit `#file:<relative-path>` references from the workspace root for the files Copilot should inspect.
- Do not remind Copilot where the repo is located beyond the `#file:` references.
- Do not use repo URLs in the Copilot prompt unless external documentation truly must be fetched.

4) Produce exactly two outputs in this order

OUTPUT A — Repo-grounded analysis & file-by-file plan
Keep it concise, technical, and useful.
Use short sections with direct statements.

Required sections for OUTPUT A:

- Architecture summary
  - Where the source-of-truth lives
  - Which modules own the relevant flows
  - Which repo owns the feature/bug
  - Which repo is secondary / proxy / admin-only if applicable

- Reproduction theory
  - A short step-by-step explanation of how the observed symptom likely occurs
  - Reference exact files/functions/flows when possible
  - Use `#file:` paths where helpful

- Root-cause candidates
  - Ranked most likely → least likely
  - One sentence each
  - Include the relevant file/function/flow references

- File-by-file implementation plan
  - One line per file in this form:
    `- #file:... — short description of the edits`
  - Include server, client, DB/migration, tests, docs, admin surfaces only if truly relevant

- Acceptance criteria
  - Short numbered list of verifiable outcomes
  - Include practical manual validation steps where relevant:
    - UI steps
    - HTTP/API flows
    - WebSocket/event flows
    - multi-account / multi-tab / reconnect cases
    - etc.

- Quick risk / migration notes
  - DB changes
  - backward-compatibility concerns
  - rollout notes
  - external service caveats
  - browser limitations
  - anything that could bite the deploy

OUTPUT B — Single Copilot prompt in one Markdown code block only
This code block is the exact prompt the developer will paste into GitHub Copilot Chat in VS Code.

The Copilot prompt must:
- start with:
  `Analyze the #codebase then`
- include explicit `#file:` references for every file Copilot must inspect/change
- tell Copilot to:
  1. perform confirmatory analysis first
  2. identify exact functions/paths to change
  3. implement the code, not stop at planning
  4. make minimal, surgical edits
  5. add regression coverage / tests where practical
  6. run basic static/syntax checks
  7. output a final verification checklist and file-change summary
- require server-side authority where applicable
  - server must validate before real-time fanout
  - client-side behavior must be aligned with server hardening where relevant
- require end-to-end completion
  - not backend-only
  - not frontend-only
  - not “here is a plan”
  - actual implementation plus validation steps
- tell Copilot not to do shallow patches
- tell Copilot not to rename public APIs without migration notes
- tell Copilot not to remove data
- tell Copilot to use existing project patterns/modules instead of inventing new frameworks
- tell Copilot to add diagnostics/logging for the changed path when useful
- tell Copilot to provide apply_patch-style or unified diffs if helpful
- tell Copilot to finish with:
  - files changed
  - what changed
  - tests/checks run
  - how to validate locally
  - remaining edge cases if any

5) Output formatting rules for ChatGPT
- Begin with a very short progress summary:
  - what you inspected
  - why those files matter
- Then OUTPUT A
- Then OUTPUT B as exactly one Markdown code block
- Do not add extra commentary after OUTPUT B
- Do not implement the code yourself in that response
- Do not output multiple code blocks for OUTPUT B

6) Scope discipline rules
- Stay tightly scoped to the user’s request
- Do not randomly drag command controls, broadcast page, DMs, moderation, etc. into the task unless the code proves they are directly coupled
- If you find a directly related coupled issue, mention it explicitly and justify why it must be fixed together
- Prefer precise fixes over sprawling rewrites unless the architecture clearly requires a refactor

7) Copilot prompt safety / engineering constraints
These must be embedded inside OUTPUT B:
- Do not rename public APIs without migration notes
- Do not delete data
- If schema changes are required:
  - include a safe migration
n  - include a backfill plan if needed
  - preserve existing installs
- Reuse existing middleware, DB helpers, route patterns, websocket services, and UI components where practical
- Add diagnostics/logging/metrics hooks for the changed paths when useful
- Preserve backward compatibility unless the user explicitly asked for a breaking change
- If browser/platform limitations exist, state them clearly rather than pretending the app can override them

8) Optional VS Code / Copilot hints to embed in OUTPUT B
Use when useful:
- `#codebase`
- `#file:<relative-path>`
- `#fetch <URL>` only if external docs are truly needed
- ask Copilot to inspect exact files/functions before editing
- ask Copilot to provide unified diffs or apply_patch-style changes if helpful

9) Optional production SSH inspection block
Only include this in OUTPUT B if the user’s request clearly calls for production log inspection or live-server debugging.

Rules:
- label it clearly:
  `OPTIONAL — requires explicit developer permission to run against production`
- default mode is inspect-only
- never suggest destructive commands unless explicitly requested later
- require explicit confirmation before any remote execution if autopilot is requested
- remind the developer to redact secrets/tokens/IPs before pasting logs back

10) Example placeholder behavior
When given:

<USER_REQUEST>
Fix X / Improve Y / Add Z
</USER_REQUEST>

you should:
- inspect the relevant code
- identify the likely files
- produce OUTPUT A
- produce OUTPUT B as one code block beginning with:
  `Analyze the #codebase then`

11) Final rule
Return only:
- OUTPUT A
- OUTPUT B
Do not actually implement the changes in that response.
