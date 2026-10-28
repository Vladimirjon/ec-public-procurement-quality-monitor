"""Writes to stdout and stderr that fail inside the attempt, not at exit.

Only the standard library is used by this module. In a real process stdout to a pipe
or a file is block-buffered: a ``print`` only fills Python's buffer, and a closed pipe
shows only when Python flushes at exit (``Exception ignored ... flushing sys.stdout``,
exit code 120). Every write of the command and of ``main`` goes through
``write_line`` or ``write_text``, which flush inside the same single attempt, so the
failure is raised there and the callers' rules handle it. A stream that failed is
then redirected to the null device, so Python's own exit-time flush cannot fail.

A missing stream (``None``, what Python leaves in ``sys.stdout`` or ``sys.stderr`` when
it started without that descriptor) is disabled output, not a failing stream: nothing is
written on it or in its place, nothing is flushed, and nothing is neutralized.
"""

import os
import weakref
from contextlib import suppress
from typing import TextIO

# The streams whose neutralizing was attempted, successful or not: at most one
# attempt per stream in the process, shared by the writes and the last flush.
_NEUTRALIZING_ATTEMPTED: weakref.WeakSet[TextIO] = weakref.WeakSet()


def neutralize(stream: TextIO | None) -> None:
    """Redirect the descriptor of a failed ``stream`` to the null device, once.

    A descriptor opened on ``os.devnull`` is copied onto the stream's own with
    ``os.dup2``. The stream object and its buffers stay, so what Python pushes into
    the descriptor later is discarded and cannot fail. A stream with no descriptor
    is not touched. The attempt is made at most once per stream, and every
    ``Exception`` it raises is absorbed: it writes nothing and replaces nothing. A
    ``KeyboardInterrupt`` and a ``SystemExit`` are not absorbed. A missing stream
    (``None``) is not touched and is not recorded.
    """
    if stream is None:
        return
    with suppress(Exception):
        if stream in _NEUTRALIZING_ATTEMPTED:
            return
        _NEUTRALIZING_ATTEMPTED.add(stream)
        descriptor = stream.fileno()
        null_device = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null_device, descriptor)
        finally:
            os.close(null_device)


def _written_and_flushed(stream: TextIO | None, text: str, *, line: bool) -> None:
    """One attempt: write ``text`` as ``print`` or ``write`` would, then flush.

    A missing stream writes nothing: ``print(file=None)`` would write on stdout.

    An ``Exception`` neutralizes the stream and is raised again, the same object. A
    ``KeyboardInterrupt`` or a ``SystemExit`` is raised unchanged: the stream may
    still work, and the last flush of ``main`` covers what stays buffered.
    """
    if stream is None:
        return
    try:
        if line:
            print(text, file=stream)
        else:
            stream.write(text)
        stream.flush()
    except Exception:
        neutralize(stream)
        raise


def write_line(stream: TextIO | None, text: str) -> None:
    """Write ``text`` and its line end to ``stream`` and flush it, in one attempt."""
    _written_and_flushed(stream, text, line=True)


def write_text(stream: TextIO | None, text: str) -> None:
    """Write ``text`` as it is to ``stream`` with one ``write`` and flush it."""
    _written_and_flushed(stream, text, line=False)


def _flushed_for_exit(stream: TextIO | None) -> KeyboardInterrupt | SystemExit | None:
    """Flush ``stream``; return the ``KeyboardInterrupt`` or ``SystemExit`` it ended in.

    A missing stream is skipped: nothing is flushed and nothing is returned.

    Any other exception neutralizes the stream and is dropped. A ``KeyboardInterrupt``
    neutralizes it too and is returned.
    """
    if stream is None:
        return None
    try:
        try:
            stream.flush()
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- see above.
            neutralize(stream)
            return error if isinstance(error, KeyboardInterrupt) else None
    except (KeyboardInterrupt, SystemExit) as raised:
        return raised
    return None


def flush_for_exit(*streams: TextIO | None) -> KeyboardInterrupt | SystemExit | None:
    """Flush each stream in its own guard; writes no text and retries no output.

    Return what must leave in the caller's exit: the first ``SystemExit`` if any
    stream ended in one, else a ``KeyboardInterrupt``, else ``None``. A missing
    stream is skipped.
    """
    ended = [_flushed_for_exit(stream) for stream in streams]
    exits = [error for error in ended if isinstance(error, SystemExit)]
    if exits:
        return exits[0]
    return next((error for error in ended if error is not None), None)
