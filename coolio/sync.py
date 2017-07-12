from . import thread
from .sched import SchedFIFO
from .traps import _scheduler_wait, _scheduler_wake


class _LockBase(object):

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self):
        return thread.AWAIT(self.__aexit__())


class Semaphore(_LockBase):

    __slots__ = ('_value', '_waiting')

    def __init__(self, value=1):
        self._value = value
        self._waiting = SchedFIFO()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},value:{},waiters:{}]>'.format(
            res[1:-1], extra, self._value, len(self._waiting))

    async def acquire(self):
        if self._value <= 0:
            await _scheduler_wait(self._waiting, 'SEMA_ACQUIRE')
        else:
            self._value -= 1
        return True

    async def release(self):
        if self._waiting:
            await _scheduler_wake(self._waiting, n=1)
        else:
            self._value += 1

    def locked(self):
        return self._value == 0
