"""Bounded startup receipt for our own update job; no game or network checks."""
import hmac
import os
from pathlib import Path
import re
import stat
import time

from .updates import atomic_json, read_json

JOB_ENV = 'LUPIN_UPDATE_JOB'
TOKEN_ENV = 'LUPIN_UPDATE_TOKEN'


def bounded_json(path, limit):
    # Receipts live in the invoking user's private job folder. Refuse pipes,
    # devices and final symlinks, particularly when read by the root helper.
    if stat.S_ISLNK(os.lstat(path).st_mode):
        raise ValueError('Invalid startup document')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Invalid startup document')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Startup document too large')
    return read_json(raw)


class StartupReceipt:
    def __init__(self, job, token, version):
        self.job = Path(job)
        self.token = token
        self.version = version
        self.sent = False

    @classmethod
    def take_environment(cls, root, cache, version, environ=None):
        env = os.environ if environ is None else environ
        folder, token = env.pop(JOB_ENV, ''), env.pop(TOKEN_ENV, '')
        if not isinstance(folder, str) or not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}', token):
            return None
        try:
            job = Path(folder).resolve()
            if (job.parent != Path(cache).resolve()
                    or not re.fullmatch(r'job-[a-zA-Z0-9_-]{6,64}', job.name)):
                return None
            if hasattr(os, 'getuid') and job.stat().st_uid != os.getuid():
                return None
            plan = bounded_json(job / 'request.json', 524288)
            if (not isinstance(plan, dict) or Path(plan.get('root', '')).resolve() != Path(root).resolve()
                    or plan.get('offer', {}).get('manifest', {}).get('version') != version
                    or not hmac.compare_digest(str(plan.get('startup_token', '')), token)):
                return None
            return cls(job, token, version)
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def report(self, ready, error=''):
        if self.sent:
            return
        # Fixed error codes only: drafts, captured text and raw exception details
        # never enter update diagnostics.
        document = dict(ready=bool(ready), version=self.version, pid=os.getpid(), token=self.token)
        if not ready:
            document['error'] = error if error in (
                'already-running', 'app-startup-failed', 'overlay-unavailable', 'startup-timeout',
            ) else 'app-startup-failed'
        atomic_json(self.job / 'started.json', document)
        self.sent = True


def wait_for_startup(job, token, version, child, *, timeout=20, clock=time.monotonic, sleep=time.sleep):
    """Used only by our installer helper for the child it just launched."""
    deadline = clock() + timeout
    while clock() < deadline:
        if child.poll() is not None:
            return False
        try:
            data = bounded_json(Path(job) / 'started.json', 8192)
            if (isinstance(data, dict) and data.get('version') == version
                    and type(data.get('pid')) is int and data['pid'] == child.pid
                    and isinstance(data.get('token'), str) and hmac.compare_digest(data['token'], token)):
                return data.get('ready') is True and clock() < deadline and child.poll() is None
        except (OSError, ValueError, TypeError):
            pass
        sleep(.1)
    return False
