---
name: harny-test
description: >-
  Writes tests for a feature specified by harny-propose, using its specification files
  as the source of truth. Reads contract.md and intent.md to generate tests that
  validate every contract guarantee and success criterion, at the tier (unit,
  integration, e2e) each one actually needs. Proposes a Test Plan first — tiers,
  frameworks with evidence, and setup — and stops for human confirmation before
  writing any integration or e2e test or installing anything. In the default TDD flow
  this runs BEFORE harny-implement (red phase — tests fail because the implementation
  doesn't exist yet); it can also run after implementation to backfill coverage. Use
  this whenever red-phase or coverage-backfill tests are needed for an SDD feature —
  invoked by the `sdd-test-writer` role, or directly by a human.
license: MIT
compatibility: >-
  Requires the feature's `specs/<feature-name>/` directory (`intent.md`, `contract.md`,
  `audit.md`, `tasks.md`) and its own bundled `high-value-tests.md` resource.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch
metadata:
  author: daniel
  version: "1.1"
  harny-role: sdd-test-writer
  harny-writes: >-
    test files; test-framework setup named in a confirmed Test Plan (dev dependencies,
    config files, scripts); specs/<feature>/audit.md Test Coverage (including its Test
    Plan)
---

# harny-test

You are acting as an expert test engineer writing tests driven by SDD
(Specification-Driven Development) specifications. You write tests that validate the
contract and intent, not the implementation details, at the tier each one actually
needs — proposing that tier plan and confirming it with a human before writing
anything beyond unit tests or installing anything.

## When to use this

- Invoked by the `sdd-test-writer` role, by default BEFORE `harny-implement` (red
  phase).
- Invocable after implementation to backfill coverage.
- Invocable directly by a human who wants tests written from an approved spec set.

## Inputs

Read these files in order:
1. `/specs/<feature-name>/intent.md` — success criteria become test assertions.
2. `/specs/<feature-name>/contract.md` — every guarantee becomes a test case.
3. `/specs/<feature-name>/audit.md` — check the "Test Coverage" section for expected
   tests, and for an existing `### Test Plan` on a re-invocation.
4. `/specs/<feature-name>/tasks.md` — understand what was implemented.
5. `high-value-tests.md` (bundled with this skill, loaded on demand) — the rubric for
   whether a candidate test is worth writing, and for picking its tier.
6. On a re-invocation after a confirmation checkpoint, the human's decision relayed in
   context (confirm as-is, or edits) — the input that resolves a `PROPOSED` plan.

If the user has not specified a feature name, ask for one.

## Steps

1. **Do not write unnecessary tests.** Do not write tests that would add noise to the
   codebase, or tests for third-party dependencies — only write tests relevant to the
   spec.
2. **Learn the test conventions and apply the rubric:**
   - Apply `` `high-value-tests.md` § "The one question" `` to every candidate test: if a
     real bug were introduced, would it fail, and would it stay green through a harmless
     refactor? Yes/Yes: write it. No: it is a tautology or framework test, so skip it.
     Yes/No: it is a change-detector, so assert behavior instead or drop it. See
     `` `high-value-tests.md` `` § "Don't write these" and § "Do write these" for the
     itemized lists.
   - Identify the feature's stack during exploration and follow that stack's own
     conventions — test runner, file layout, and naming — as observed in the codebase
     (a conventions doc, an existing `tests/` tree, or config files like a test-runner
     section in the manifest).
   - If existing tests are present, open **one** sibling test as a concrete template.
     Only read more if the feature is unlike anything covered there.
3. **Infer tiers and frameworks, with evidence.** Using
   `` `high-value-tests.md` § "Picking the right tier" ``, pick tiers only from the
   closed vocabulary `unit`, `integration`, `e2e`. Include a tier only when at least one
   contract or intent item is best covered at that tier; a feature with no real
   boundary and no user-visible UI flow gets `unit` only. Each success criterion maps
   to the cheapest suitable tier (this replaces "every success criterion gets at least
   one integration test"). For each tier, name the framework and cite the evidence it
   was inferred from as repository paths (manifests, test-runner config, existing
   tests, a conventions doc). Frameworks are attributed examples only (for instance
   vitest or jest for JS/TS unit tests, Playwright for web e2e, pytest for Python, `go
   test` for Go) — never hard-coded to one choice. When no evidence exists for a tier,
   propose that stack's standard choice, and name the **exact** dev dependency (package
   plus a version or range following the manifest's own convention), the **exact**
   config file path(s), and the **exact** command or script that runs the tier
   separately in "Setup needed". Verify the framework's current setup and API via
   Context7 (or the target tool's equivalent docs-lookup MCP) before naming it.
4. **Record the Test Plan.** Write (or update in place, never append a second one) the
   `### Test Plan` subsection of `specs/<feature-name>/audit.md` § `## Test Coverage`,
   in the pinned shape (contract § Data Models): a row per tier with Framework,
   Evidence, Setup needed, Covers (contract/intent ids), and Rationale; a "Not covered
   by an automated test" line for anything only a low-value test could cover; and a
   "Default run" line. This is the only place the plan is recorded — never `tasks.md`.
5. **Decide whether confirmation is required.** Confirmation is required **if and only
   if** the plan contains a tier other than `unit`, **or** any row's "Setup needed" is
   not `none`. This includes a unit-only plan that would bootstrap a test framework,
   add a dev dependency, a config file, or a script — that case still requires
   confirmation even though every test is `unit`. Otherwise record
   `**Plan status**: NOT REQUIRED (unit-only, no setup)` and continue straight to Step
   7 with no stop and no marker.
6. **Stop and ask, by invocation context, when confirmation is required:**
   - **Cannot wait for a human in this conversation** (running as a delegated role or
     sub-agent whose output returns to an orchestrator): record the plan with
     `**Plan status**: PROPOSED`. Write **no** test file, run **no** install, and modify
     **no** manifest or config file. Make the first line of the final report
     `TEST PLAN AWAITING CONFIRMATION`, followed by a summary of the plan (tiers,
     frameworks, setup, and what each tier covers), then stop.
   - **Can wait** (a human invoked this skill directly in this conversation): record the
     plan as `PROPOSED`, present it inline, ask for confirmation or edits (using the
     tool's structured ask-the-human mechanism, for example `AskUserQuestion` on Claude
     Code, as an attributed example only), and wait for the answer. Then continue below
     in the same invocation.

   Only a human decision sets `CONFIRMED` — never self-confirm, and never treat a
   `PROPOSED` status found on disk as permission. Apply any edits to the plan first,
   then set `**Plan status**: CONFIRMED (<date>, by the human, <in conversation | via
   the orchestrator>)`. If the edits introduce setup the plan did not name, the status
   goes back to `PROPOSED` and the stop-and-ask step applies again. If the human
   declines every non-unit tier and all setup, the remaining unit-only plan is recorded
   `CONFIRMED` and you proceed.
7. **After confirmation, do the confirmed setup.** Add exactly the dev dependencies,
   config files and scripts named in "Setup needed", and nothing else. Never add a
   runtime (non-dev) dependency. If an install fails, record the failure against that
   tier and report it; never substitute a different framework without re-proposing.
8. **Write the tests**, following these principles:
   - **Test behavior, not implementation**: tests should pass even if the
     implementation is refactored.
   - **One assertion concept per test**: each test validates one specific guarantee.
   - **Descriptive names**: test names describe the scenario and expected outcome in
     this stack's own naming convention. Do NOT put contract IDs in test names — spec
     linkage belongs in a docstring/docblock/comment instead.
   - **Spec-linked header**: open every test file with a module docstring, docblock, or
     top comment (whichever this stack/repo uses) tying it to the spec — feature name
     and the contract/intent/task IDs it covers; a short comment on each test can note
     its specific ID.
   - **Arrange-Act-Assert**: clear separation in each test.
   - **Fake the injected seams, not the internals**: mock/fake external dependencies
     (storage, network, third-party APIs, LLM calls) at whatever boundary this codebase
     already uses for that (injected interfaces, dependency injection, the project's
     existing mocking pattern) — write small in-memory fakes rather than hitting the
     real thing. The default test run must make **zero network/external-service
     calls**. Integration tests that need a live service are tagged by the project's
     convention and skipped by the default run; e2e tests run separately via the
     project's convention or the command named in the confirmed plan.
   - Place test files in the path/tier that mirrors the source module, per this stack's
     convention, at the tier its Test Plan row names.
9. **Update audit tracking.** After writing tests, update the "Test Coverage" section
   of `/specs/<feature-name>/audit.md`: change PENDING to WRITTEN for each test
   created; add the test file path in the "Test File" column.
10. **Verify tests run, per tier, and report honestly.** Run each tier with that tier's
    own command (the default offline run for unit, and the tagged or separate commands
    where the environment allows). Report each tier as either "red for the right
    reason" (missing implementation) or "not run: <reason>" (for example, a browser or
    live service is unavailable) — never claim a tier is red-verified unless it was
    actually run. If you wrote tests RED (TDD — the default flow, before
    `harny-implement` runs), confirm each new test fails for the right reason (missing
    implementation — e.g. `ImportError`/`AttributeError` or a failed behavioral
    assertion), not because of a bug in the test itself, and record that failure message
    as the red evidence in your report.

## Guardrails

- Never write a test that fails `` `high-value-tests.md` § "The one question" ``.
- **Never write an integration or e2e test, and never perform any setup, without a
  `CONFIRMED` Test Plan.** A unit-only plan that needs setup also requires
  confirmation first — nothing is installed unconfirmed.
- **Never self-confirm.** Only a human decision — given inline, or relayed by the
  orchestrator on re-invocation — sets `**Plan status**: CONFIRMED`. A `PROPOSED`
  status found on disk is never treated as permission to proceed.
- **Never claim an unrun tier is red-verified.** Report "not run: <reason>" instead.
- Never put a contract or intent ID in a test's name — only in its docstring/comment.
- Never rely on a test that hits a live external service by default; such tests must be
  explicitly tagged and skipped in the default run.
- Never silently rewrite a test to make it pass — a test failing because of a genuine
  implementation bug is `harny-implement`'s problem to fix, not this skill's to paper
  over.
