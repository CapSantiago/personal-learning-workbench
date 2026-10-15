"""The same nonblocking file lock contract on Windows and Linux."""
import os

if os.name == 'nt':
    import msvcrt
else:
    import fcntl


def acquire(handle):
    handle.seek(0, 2)
    if not handle.tell():
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    if os.name == 'nt':
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def release(handle):
    handle.seek(0)
    if os.name == 'nt':
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
