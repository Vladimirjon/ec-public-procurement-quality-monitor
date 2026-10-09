# Glossary

This glossary fixes the meaning of the domain terms used in code, tests,
specs, and documentation. One term has one meaning; if a document needs a
different meaning, it must use a different word.

Each term has a definition, its invariants (what must always be true), and a
synthetic example. Examples are invented and never copy real SERCOP records.

## Procurement process (proceso de contratación)

### Definition

A single public purchasing procedure carried out by one buyer, from its
announcement to its award, identified in the source by its OCDS contracting
process identifier (`ocid`). It is what the system tracks, normalizes, and
evaluates. Each time the system reads it from the source, it may see
different values for the same process.

### Invariants

- It has exactly one `ocid`, and that `ocid` never changes. Two records with
  the same `ocid` describe the same process.
- It belongs to exactly one buyer.
- Every normalized version of it points to the raw evidence it came from.
- Absent optional data (for example `suppliers` or `budget` being `null`)
  does not make the process invalid. Absence is something quality rules
  report; it is not a reason to discard the process.

### Synthetic example

```text
ocid:      ocds-synthetic-0001
buyer:     SYNTHETIC BUYER S.A.
title:     Purchase of synthetic distribution transformers
amount:    1000.00
suppliers: null
budget:    null
```

On a first read the process has `amount` `1000.00`. A later read of the same
`ocid` returns `1200.00`. It is still the same process (same `ocid`), now
observed twice, and each observation points to its own raw evidence.

## Raw evidence (evidencia cruda)

### Definition

The exact, unmodified response the system received from the source in one
request, preserved before any transformation. In data-lifecycle terms, it is
the output of the ingestion stage stored as-is, so every later result
(normalized record, quality finding) can be traced back to it and
reproduced.

### Invariants

- It is immutable and append-only: once stored, its content is never
  overwritten or edited. A different response from the source is new
  evidence, never a replacement for the old one
  ([ADR 0002](adr/0002-immutable-raw-storage.md)).
- It is byte-faithful: it is stored before normalization, and nothing is
  cleaned, retyped, or reformatted.
- It is integrity-checkable: it carries a hash of its content, so anyone can
  verify later that it has not changed.
- It is traceable to its origin: it is always associated with the source
  request that produced it, the ingestion execution that obtained it, and
  the time it was captured.

### Synthetic example

```text
evidence:     sha256:0000...0001 (synthetic hash)
source:       synthetic search endpoint, query year=2025&page=1
execution:    synthetic-exec-001
captured_at:  2026-10-09T10:15:00-05:00
content:      {"total": 1, "page": 1,
               "data": [{"ocid": "ocds-synthetic-0001",
                         "amount": "1000.000000"}]}
```

Normalization later stores `amount` as `1000.00`, but the evidence still
says `"1000.000000"`. If the next day the source returns `1200.000000` for
the same `ocid`, that is a second piece of evidence; the first one stays
untouched.

## Ingestion execution (ejecución de ingesta)

### Definition

One bounded batch run of ingestion: it takes a request with an explicit
scope (source, buyer, year, pages), retrieves the responses from the source,
preserves each one as raw evidence, and ends with a recorded outcome. It is
the unit of audit: it tells you when, why, and how each piece of evidence
was obtained, and it is what lets a run be repeated or resumed safely.

### Invariants

- It is bounded: its scope is fixed when it starts. It never ingests
  everything, only what its request named.
- It is uniquely identified and timestamped: it has its own identity and
  start time, and that identity is never reused by another execution.
- It always ends with a recorded outcome: it finishes as success or failure,
  or, if interrupted, it leaves enough recorded progress to resume. It never
  disappears silently. The exact set of states is decided in the features
  that implement persistence and ingestion.
- It is idempotent in effect: repeating the same scope creates a new
  execution, but does not duplicate evidence or normalized records already
  obtained.
- It is resumable: after an interruption, a later execution continues from
  the recorded progress without redoing finished work.
- It is traceable: every response it obtains is recorded as obtained by it,
  even when that content was already stored by an earlier execution.

### Synthetic example

```text
execution:    synthetic-exec-001
scope:        synthetic source, buyer SYNTHETIC BUYER S.A.,
              year 2025, pages 1-2
started_at:   2026-10-09T10:15:00-05:00
finished_at:  2026-10-09T10:15:42-05:00
outcome:      succeeded
obtained:     2 responses (page 1, page 2)
```

`synthetic-exec-002` has the same scope and is interrupted after page 1; its
progress records page 1 as done. A later execution continues at page 2 and
does not fetch page 1 again. `synthetic-exec-003` repeats the full scope: the
two responses have the same content as before, so no new evidence is stored,
but both are recorded as obtained by `synthetic-exec-003`.

## Quality rule (regla de calidad)

### Definition

An explicit, named, and versioned expectation about the data, defined on a
stated target (for example a field of a procurement process). When the data
violates the expectation, the rule produces quality findings. Quality is how
well the data conforms to what is expected, so the expectation must be
written down and executable. The rule is the expectation itself, not the bad
data it detects.

### Invariants

- It has a stable identity and an explicit version. Changing its logic
  creates a new version; a published version is never edited, so findings
  from old versions stay reproducible.
- It belongs to exactly one quality dimension: completeness, validity,
  consistency, or uniqueness.
- It declares its target: which entity and field it evaluates, so it is
  clear what a finding is about.
- It is deterministic: the same data evaluated with the same rule version
  always yields the same findings. It does not depend on the current time,
  the network, or any state outside the data.
- It is read-only: it only reports. It never modifies, fixes, or discards
  the data it evaluates.

### Synthetic example

```text
rule:       synthetic-rule-completeness-suppliers
version:    1
dimension:  completeness
target:     procurement process, field `suppliers`
expects:    `suppliers` is not null
```

Applied to `ocds-synthetic-0001` (with `suppliers: null`), version 1
produces one finding. Later the team decides that a process that is not yet
awarded may legitimately have no suppliers. That is version 2 of the rule.
Version 1 is left as it was, and the findings it already produced stay
linked to version 1.

## Quality finding (hallazgo de calidad)

### Definition

A recorded statement that specific data, obtained from specific raw
evidence, did not meet the expectation of a specific version of a quality
rule. It is the end of the lineage chain: source response, raw evidence,
normalized data, rule, finding. Anyone can follow a finding back to the
exact evidence that produced it.

### Invariants

- It exists only on violation: it is created only when the rule's
  expectation was not met.
- It points to exactly one rule and one rule version, never just "the
  rule".
- It points to its subject and to the raw evidence it came from: which
  procurement process and field, and the evidence that contained that data.
  A finding without evidence is invalid.
- It records what was observed and when it was detected: the observed value
  and the detection time.
- It is not edited after being recorded: it is a historical statement. If
  the data is corrected later, a new evaluation produces its own findings
  (or none); the old one is not changed or deleted.
- It is not duplicated: evaluating the same evidence with the same rule
  version again does not produce a second finding.

### Synthetic example

```text
rule:         synthetic-rule-completeness-suppliers, version 1
subject:      procurement process ocds-synthetic-0001, field `suppliers`
evidence:     sha256:0000...0001 (synthetic hash)
observed:     null
detected_at:  2026-10-09T10:20:00-05:00
```

Evaluating the same evidence again with version 1 adds nothing. Evaluating
it with version 2 (processes not yet awarded may lack suppliers) yields no
finding, and the version 1 finding stays as it was. If the source later
returns new evidence with `suppliers` still `null`, that produces a new
finding that points to the new evidence.
