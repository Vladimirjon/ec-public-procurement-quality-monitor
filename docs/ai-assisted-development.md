# AI-assisted development

AI assistance is subject to the repository architecture, human review, and
the project's data-handling responsibilities. It does not replace design
ownership or verification.

## Required workflow

Use this sequence for substantive work:

1. **Analysis:** inspect the repository, constraints, and relevant decisions.
2. **Plan:** identify exact files, behavior, risks, and verification steps.
3. **Approval:** obtain approval when the task changes scope, dependencies,
   infrastructure, or an architectural decision.
4. **Implementation:** make only the approved changes.
5. **Tests:** run relevant automated and focused checks.
6. **Human review:** inspect the diff, results, and remaining assumptions
   before accepting the change.

## Task formulation

A useful task states the desired outcome, in-scope files, explicit
constraints, acceptance criteria, and required verification. Acceptance
criteria should be observable, for example: repeated ingestion does not
duplicate results, a failed batch can resume, raw evidence is preserved, and
audit records identify the execution and outcome.

## Reviewing changes

Review `git diff --stat`, the complete diff, and `git diff --check`. Confirm
that every changed file is necessary, that layer boundaries remain intact,
that no source contract was invented, and that documentation does not claim
unimplemented functionality. Check error paths and data-handling behavior,
not only the expected path.

Before merging, the developer must understand the changed design, its
assumptions, its failure modes, its tests, and any unresolved questions. A
passing check is not a substitute for understanding the diff.

## Responsible data use

Use minimal fixtures rather than submitting or storing complete downloaded
datasets. Fixtures should be synthetic, sanitized, or limited to the fields
needed by the test. Keep public source descriptions separate from responsible
handling of downloaded content: public availability does not remove the need
to minimize exposure, avoid secrets, and prevent raw responses from entering
prompts, logs, commits, or documentation.
