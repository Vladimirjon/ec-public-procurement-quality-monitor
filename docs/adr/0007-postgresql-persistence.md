# ADR 0007: PostgreSQL persistence, migrations and local environment

- Status: Accepted
- Date: 2026-10-13

## Context

[ADR 0003](0003-no-distributed-infrastructure-in-v1.md) fixed PostgreSQL as the
database of version 1 and announced Docker Compose to run it locally. It did
not decide how the application talks to the database, how the schema changes
over time, or how the local instance is defined. F3 (`postgres-persistence`)
needs all three before its specs can be written.

PostgreSQL holds normalized procurement data, audit records and quality
results. It does not change where raw evidence lives: the exact response bytes
stay in the local store of [ADR 0005](0005-raw-evidence-store-layout.md), which
keeps the append-only rule of [ADR 0002](0002-immutable-raw-storage.md).

The system is a bounded batch CLI, and the layer rules of
[ADR 0001](0001-modular-monolith.md) apply: `domain` and `application` must not
depend on a database driver. The project has one runtime dependency so far
(`httpx`, [ADR 0006](0006-http-client-for-source-access.md)).

## Decision

### Database access

Use `psycopg` 3 through its synchronous API, with explicit SQL and no ORM.

- **Placement.** Only `infrastructure` imports it. `application` defines the
  persistence ports; the PostgreSQL adapter implements them. No `psycopg` type
  or exception crosses into `domain` or `application`.
- **SQL.** Statements are written by hand and parameterized. Row-to-domain
  mapping lives in the adapter.
- **Dependency.** Added by the first task of F3, not by this ADR. The choice
  between the `binary` and source variants of the package is left to the F3
  spec.

### Migrations

Keep schema changes as numbered SQL files in `migrations/`, applied by a small
runner owned by the project.

- **Files.** One file per change, named so that lexical order is application
  order (`NNNN_description.sql`). Migrations are forward-only: an applied file
  is never edited, a new file corrects it.
- **Runner.** Lives in `infrastructure`, applies each pending file once and in
  order, and records what it applied in the database. Its exact contract
  (bookkeeping table, integrity check of applied files, locking and
  transaction scope) is decided in the F3 spec and covered by its tests.
- **Schema design.** Tables, keys and constraints, including the `UNIQUE`
  constraints that make ingestion idempotent, belong to the F3 spec.

### Local environment

Provide PostgreSQL for development with Docker Compose, defined in
`compose.yaml` at the repository root, with only that one service.

- **Image.** The official `postgres` image with the major version pinned to 18.
  Version 18.6 was observed on 2026-10-13.
- **Exposure.** The port is published on `127.0.0.1` only.
- **Data.** A named volume mounted at `/var/lib/postgresql`, the location the
  18 image expects. It survives `docker compose down`; `down -v` deletes it.
- **Credentials.** Read from `.env`, which git ignores. `.env.example` is
  versioned with fake values and lists the required variables. Compose fails
  if one is missing.
- **Scope.** A development and test tool, not a deployment definition. ADR 0003
  still excludes any other service.

## Alternatives considered

SQLAlchemy (Core or ORM) was rejected because it adds a mapping layer between
the domain and the schema that this project does not need and hides the SQL
the project wants to keep explicit. What is lost is a query builder and
database portability. `asyncpg` was rejected because the system has no
concurrency need, as in ADR 0006, and its API is specific to PostgreSQL. What
is lost is raw throughput. `psycopg2` was rejected because `psycopg` 3 is its
successor with a cleaner API and typed parameters. What is lost is familiarity.

Alembic was rejected because it needs SQLAlchemy and keeps migrations as Python
scripts, while the project wants plain SQL files that review as SQL. What is
lost is autogeneration, downgrade scaffolding and a widely tested runner. A
standalone migration tool such as Flyway or dbmate was rejected because it adds
a second runtime or binary to install on every developer machine and in CI.

A PostgreSQL installed directly on the machine was rejected because the
version and settings would differ between machines and CI. What is lost is not
needing Docker.

## Consequences

The project gains its second runtime dependency, `psycopg`, recorded in
`uv.lock` and watched by Dependabot. It also owns a migration runner: more code
to write, test and maintain, in exchange for no further dependency and
migrations that read as SQL.

Docker Desktop becomes a requirement for local work on persistence and for the
integration tests. CI integration tests must use a PostgreSQL service of the
same major version. The local volume lets developers keep data between runs;
nothing in it is evidence, since raw responses stay in the local raw store.

This decision should be revisited if the schema grows to need generated
migrations or downgrades, if a second database engine is required, or if the
workload needs concurrent writers.
