# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'async_context', 'async_iter', 'AsyncThread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine

from . import sync
from .task import spawn, disable_cancellation
from .traps import _future_wait
from . import errors