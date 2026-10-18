"""Feature ingest-command (F4), outcome O2 (AC16, decision P-1): the hierarchy of
the persistence errors, with `MigrationLockError`.

`MigrationLockError` is imported inside each test, so the file collects while the
class does not exist yet and the red reason is the `ImportError` inside the test.
The existing `test_persistence_errors_are_direct_subclasses_of_persistence_error`
in `test_ingestion_audit.py` is not edited: it checks the four direct subclasses,
which stay the same. This file pins what that test cannot: the new class sits
under `MigrationError` and there are six errors in all. Names to focus on, by
`-k`: `hierarchy`. No database, no socket.
"""

from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)


def _family(root: type[BaseException]) -> set[type[BaseException]]:
    """`root` and its subclasses at any depth."""
    family = {root}
    pending = [root]
    while pending:
        for subclass in pending.pop().__subclasses__():
            if subclass not in family:
                family.add(subclass)
                pending.append(subclass)
    return family


def test_hierarchy_migration_lock_error_is_a_direct_subclass_of_migration_error_only() -> (
    None
):
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    assert MigrationLockError.__bases__ == (MigrationError,)
    assert issubclass(MigrationLockError, PersistenceError)
    assert MigrationError.__subclasses__() == [MigrationLockError]
    assert MigrationLockError.__subclasses__() == []


def test_hierarchy_has_exactly_six_errors_at_any_depth() -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    family = _family(PersistenceError)

    assert len(family) == 6
    assert family == {
        PersistenceError,
        PersistenceConnectionError,
        PersistenceIntegrityError,
        PersistenceNotFoundError,
        MigrationError,
        MigrationLockError,
    }


def test_hierarchy_persistence_error_keeps_its_four_direct_subclasses() -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    direct = PersistenceError.__subclasses__()

    assert len(direct) == 4
    assert set(direct) == {
        PersistenceConnectionError,
        PersistenceIntegrityError,
        PersistenceNotFoundError,
        MigrationError,
    }
    assert MigrationLockError not in direct
