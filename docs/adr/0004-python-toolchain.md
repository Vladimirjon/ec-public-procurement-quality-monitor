# ADR 0004: Python toolchain

- Status: Accepted
- Date: 2026-10-04

## Context

The project needs a Python toolchain that installs the same dependency
versions on every machine and in CI. Because code is written by both a person
and AI agents, style, type, and test checks must run automatically, locally
and in CI. It is an academic and portfolio project and is not published as a
package for other users, so it does not need to support older Python
versions.

## Decision

Require Python 3.13 or newer (`requires-python = ">=3.13"`) and run CI on
Python 3.13. Use `uv` to manage the virtual environment and install
dependencies, and commit `uv.lock` so every install resolves to the same exact
versions. Use `ruff` for linting and formatting and `mypy` for type checking,
with strict mode in the `domain` layer. Use `pytest` to run unit tests now and
integration tests against PostgreSQL later.

## Alternatives considered

Supporting Python 3.11 or newer was rejected because it would require testing
several Python versions in CI, and no other users need the compatibility.
Plain `pip` with `requirements.txt` was rejected because it has no real
lockfile, so transitive dependency versions can change between installs. It
would have avoided installing one more tool, which is what is lost. Poetry
was rejected because its main strength is building and publishing packages,
which this project does not do. What is lost is that packaging workflow. The
`flake8`, `black`, and `isort` combination was rejected because it needs three
tools and three configurations, and harny already provides a `ruff` profile.
What is lost is familiarity and the wider `flake8` plugin ecosystem. `unittest`
was rejected because it needs more boilerplate and gives less readable failure
messages. What is lost is having zero dependencies. Strict `mypy` on every
layer was rejected because it creates friction with external libraries, mostly
in `infrastructure`, while `domain` is where type errors cost the most. What
is lost is equally strict checking elsewhere; strictness can be extended layer
by layer later.

## Consequences

Installs are reproducible, and the same style, type, and test checks run
locally and in CI. The cost is that `uv` must be installed and learned, and
anyone on a Python version older than 3.13 cannot install or run the project
without upgrading. The main risk is drift: if a dependency is added without
updating `uv.lock`, or someone installs without following the `uv` workflow,
installs stop being reproducible.

This decision should be revisited if the project is published as a package for
other users, which would affect the Python version floor and the packaging
tool, or if strict `mypy` is extended to more layers.
