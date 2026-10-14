"""Persistence errors: failures reported by any persistence adapter.

Messages are fixed text naming the operation and, where useful, an identity
(an execution id, a sequence, a content hash, a migration file name). They never
carry a stored value, a credential or any text from a driver or a server.
"""


class PersistenceError(Exception):
    """Base class for persistence failures."""


class PersistenceConnectionError(PersistenceError):
    """The database could not be reached, or the connection was lost.

    After a loss during a commit, whether the transaction committed is unknown.
    """


class PersistenceIntegrityError(PersistenceError):
    """New data conflicts with stored data, or a stored row is invalid."""


class PersistenceNotFoundError(PersistenceError):
    """The requested run, observation or event list is not stored."""


class MigrationError(PersistenceError):
    """A migration file or the migration bookkeeping is not acceptable."""
