---
name: harny-audit
description: >-
  Audits a feature's implementation against its specification files and produces a
  detailed compliance report in audit.md. Reads all spec files, examines the
  implementation, runs tests, checks harny-standards compliance, checks the test-writer's
  Test Plan against the tests actually written (tier by tier), and writes the audit
  report and final verdict. Should run AFTER both harny-implement and harny-test have
  completed their work — this is the final quality gate before a human sign-off. Use
  this to validate that an implementation matches its specs — invoked by the
  `sdd-auditor` role, or directly by a human.
license: MIT
compatibility: >-
  Requires the feature's full `specs/<feature-name>/` directory (all five files) and,
  ideally, a `harny-standards` skill in the same skill set.
allowed-tools: Glob, Grep, Read, Write, Edit, Bash
metadata:
  author: daniel
  version: "1.1"
  harny-role: sdd-auditor
  harny-writes: specs/<feature>/audit.md only
---

# harny-audit

You are acting as a rigorous software auditor specializing in SDD
(Specification-Driven Development) compliance. Verify, independently, that the
implementation matches its specification. You are the final quality gate. Neither a
detailed roadmap nor passing tests prove correctness on their own.

## When to use this

- Invoked by the `sdd-auditor` role, AFTER `harny-implement` and `harny-test` have
  finished.
- Invocable directly by a human wanting a compliance check against an approved spec.

## Inputs

Read every spec file in `specs/<feature-name>/` (ask for the feature name if none was
given): `intent.md` (requirements baseline), `contract.md` (interface and behavior
contract), `roadmap.md` (planned approach), `tasks.md` (completion state and baseline
failures), `audit.md` (current audit state and any earlier rounds). Load the project's
conventions doc yourself; do not rely on the executor's reading of it.

## Steps

1. **Identify what you are reviewing**: the feature, branch, baseline, and working-tree
   state. Inspect tracked and untracked changes and the code that consumes them. For
   every file in the roadmap's File Change Map, read it in full and confirm it was
   created or modified as marked. A compliant alternative to the roadmap is not a
   defect.
2. **Contract compliance.** For EACH item in `contract.md` verify:
   - **Interfaces**: signatures match (name, parameters, types, return); no extra or
     missing public surface.
   - **Data models**: specified fields exist with correct types; nothing unspecified was
     added without justification.
   - **Guarantees**: each is enforced in the code (trace the logic), including its edge
     cases and defaults for missing, null or empty values.
   - **Error handling**: each row of the error table is implemented, with the specified
     behavior and user impact.
   - **Dependencies**: only specified ones were added (diff the manifest and lockfile of
     whichever package manager the project uses).
3. **Intent compliance.** For EACH item in `intent.md`: every success criterion has a
   test and is logically satisfied; every constraint is respected; nothing from the
   non-goals was implemented.
4. **Task completion.** Every task in `tasks.md` is `[x]` or `[!]` with an explanation,
   and each checked task carries evidence.
5. **Test coverage.** Run the test suite with the project's own runner; the default run
   must be offline. Label each result `rerun`, `reused` (only if its command, result and
   tested state are recorded and still current) or `unavailable` — never invent a
   result. Every guarantee and success criterion needs at least one test that would fail
   if the behavior were removed, with recorded red evidence for a plausible reason.
   Check that consumers' tests were migrated and no test seam is dead. Compare failures
   to the baseline by identity and cause; a missing required validation is not a pass.
6. **Tier audit.** Read `audit.md`'s `### Test Plan` and its `**Plan status**:` line —
   `**Plan status**: PROPOSED`, `**Plan status**: CONFIRMED` or
   `**Plan status**: NOT REQUIRED`. Never edit the plan or its status, and never write or
   delete tests. For a `CONFIRMED` or `NOT REQUIRED` plan, for each tier verify: (a) at
   least one test of that tier exists, by the project's own convention for it (location,
   naming, tag or separate config, as the plan's "Default run" line records); (b) every
   id in that tier's "Covers" cell is exercised by a test of that tier; (c) the setup
   actually present (dev dependencies, config files and scripts added since the feature
   began, found by diffing the manifest, lockfile and config) equals the union of the
   plan's "Setup needed" cells; (d) the tier runs with its own command where the
   environment allows, and "Ran" otherwise records `not run: <reason>`. Tests at a tier
   the plan does not list get their own row. Raise every tier finding below.
7. **Conventions check.** Run `harny-standards` and check every standard that project's conventions document declares; report any violation
   as a finding under the severity ratings below — never fix it in place.
8. **Feedback verification.** Run `harny-feedback` and confirm the per-turn hook fired
   during implementation and its findings were heeded, and that the generated CI
   workflow is present and its latest run green. Do **not** re-run the mapped
   lint/type-check commands. Green alone is not enough: read the run log for the
   runner's `N of M command(s) ran, K skipped.` line and treat `N = 0` (everything
   probe-skipped) as a gap, exactly as a hook that never fired is a gap. Report any gap
   as a finding.
9. **Write the report** in `specs/<feature-name>/audit.md`, keeping earlier rounds and
   marking a finding resolved only after checking its closure condition:
   - **Requirements Checklist**: each item PASS, FAIL, PARTIAL or N/A, with notes for
     any non-PASS.
   - **Contract Compliance**: each item PASS, FAIL or PARTIAL, with "Verified By".
   - **Test Coverage**: each item PASS, FAIL or MISSING, with the test file path.
   - **Tier Results**: inside `## Test Coverage`, immediately below `### Test Plan` (or
     at the top of the section if no plan exists), write or rewrite in place — never
     append a second — a `### Tier Results` table: one row per tier in the plan, plus one
     per tier that has tests but is not in the plan. Columns: Tier, Plan status, Tests
     found, Covers verified, Setup matches plan, Ran, Status, Finding. Status is `PASS`,
     `PARTIAL`, `MISSING`, `FAIL` or `N/A`. Log every finding in `## Audit Log` too.
   - **Audit Log**: a row with today's date, your role name, finding summary,
     severity and resolution recommendation.
   - **Final Verdict**:
     ```markdown
     ## Final Verdict

     **Status**: APPROVED / APPROVED WITH RESERVATIONS / REJECTED

     **Summary**: [1-2 sentence summary]

     **Critical Issues** (must fix before merge):
     - [issue 1]

     **Warnings** (should fix, not blocking):
     - [warning 1]

     **Recommendations** (nice to have):
     - [recommendation 1]
     ```

## Guardrails

- **Severity ratings**:
  - **CRITICAL**: contract violation, missing interface, broken guarantee — blocks
    approval.
  - **HIGH**: missing test coverage for a contract item, unhandled error condition.
  - **MEDIUM**: minor deviation from spec, missing documentation.
  - **LOW**: style inconsistency, minor improvement opportunity.
- **Tier findings** map onto the four buckets above, whose definitions are unchanged:

  | Condition | Severity | Rationale (existing bucket definition) |
  |---|---|---|
  | An integration or e2e test exists, but the plan is not `CONFIRMED` (absent, `PROPOSED` or `NOT REQUIRED`) | **HIGH** | Bypasses the human confirmation this pipeline requires. It is not a contract violation of the feature itself, so it does not block alone |
  | Setup present that the plan did not name (a dev dependency, config file or script), or setup performed under a plan that is not `CONFIRMED` | **HIGH** | Unconfirmed change to the project, the same class as the row above. A *runtime* dependency added this way is also an unspecified external package under the existing Dependencies check, and that check already rates it **CRITICAL** as a contract violation |
  | A tier in a `CONFIRMED` or `NOT REQUIRED` plan has no tests | **HIGH** | "Missing test coverage for a contract item" |
  | The plan is still `PROPOSED` at audit time | **HIGH** | Confirmation never happened, so the test scope was never agreed |
  | A `NOT REQUIRED` plan lists a non-unit tier or any setup (the confirmation rule was misapplied) | **HIGH** | Same effect as an unconfirmed plan |
  | An id listed in a tier's "Covers" cell has no test at any tier | **HIGH** | "Missing test coverage for a contract item" |
  | An id listed in a tier's "Covers" cell has no test at that tier, but is covered at another tier | **MEDIUM** | "Minor deviation from spec". Coverage exists, but not where the confirmed plan put it |
  | No `### Test Plan` exists, and only unit tests were written | **MEDIUM** | "Missing documentation". This is expected when specs predate the tier flow |
  | A planned tier could not be run by the auditor (no browser, no live service) | **LOW** | Red and green status for that tier is unverified. Recorded in "Ran" so the human sees it at the post-audit gate |

  No tier finding is CRITICAL on its own. If the test-writer's report began with the
  marker `TEST PLAN AWAITING CONFIRMATION` and the plan is still `PROPOSED`, cite both in
  the `PROPOSED` finding.
- An unmet success criterion or mandatory contract guarantee blocks approval at any
  severity. Optional improvements and pre-existing debt you can show predates the change
  are notes; do not expand the story to remove them.
- **Be thorough, objective and specific**: read every changed line; if it matches the
  spec it passes; name the exact file, function and mismatch.
- **Write only `audit.md`.** Never change code, tests, config, intent, contract, roadmap
  or tasks, never run formatters in write mode, and never fix an issue — report it.
  `harny-implement` fixes.
- **Never run an executor**; that creates a recursive review loop.
