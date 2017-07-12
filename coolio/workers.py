'''
coolio/workers.py

Functions for performing work outside of curio.  This includes
running functions in threads, processes, and executors from the
concurrent.futures module.

'''

__all__ = ['run_in_executor', 'run_in_thread', 'run_in_process', 'block_in_thread']

# -- Standard Library

import multiprocessing
import threading
import traceback
import signal
from collections import Counter, defaultdict

# -- Coolio
from .errors import CancelledError
from .traps import _future_wait, _get_kernel


import curio
