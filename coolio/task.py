# coolio/task.py

from . import meta
from .traps import *
async def spawn(corofunc, *args, daemon=False, allow_cancel=True):
    coro = meta.instantiate_coroutine(corofunc, *args)
    task = await _spawn(coro, daemon)
    task.allow_cancel = allow_cancel
    return task

async def current_task():
    '''
    Returns a reference to the current task
    '''
    return await _get_current()

class _CancellationManager(object):
    def __init__(self, allow_cancel):
        self.allow_cancel = allow_cancel
        self.cancel_pending = None
    
    async def __aenter__(self):
        self.task = await current_task()
        if self.task.allow_cancel and self.allow_cancel:
            raise RuntimeError('enable_cancellation() may not be used in a context where cancellation is already allowed')
        self._last_allow_cancel = self.task.allow_cancel
        self.task.allow_cancel = self.allow_cancel
        return self

    async def __aexit__(self, ty, val, tb):
        self.task.allow_cancel = self._last_allow_cancel

        # If a CancelledError is raised on exit from a block, the
        # following rules are in play:
        #
        # 1. If the block did not allow cancellation in the first place,
        #    a RuntimeError occurs.  It illegal for CancelledError to
        #    be raised in any form when cancellation is disabled.
        #
        # 2. If cancellation is not allowed in the outer block,
        #    the CancelledError is transformed back into a pending
        #    exception.  The outer block can certainly check for
        #    this if it wants, but it can also just defer the
        #    cancellation to a point where cancellation is allowed again.
        #
        if isinstance(val, CancelledError):
            if not self.allow_cancel:
                raise RuntimeError('%s must not be raised in a disable_cancellation block' %
                                   ty.__name__)
            if not self.task.allow_cancel:
                self.cancel_pending = self.task.cancel_pending = val
                return True
        else:
            self.cancel_pending = self.task.cancel_pending
            return False

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))



def disable_cancellation(coro=None, *args):
    if coro is None:
        return 