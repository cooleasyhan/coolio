from asyncio import events, base_futures, futures, coroutine,ensure_future
import traceback
import sys
import weakref

import threading
import heapq
import logging
import os
import selectors
import inspect

import collections
import time
import types
_COROUTINE_TYPES = (types.GeneratorType)
try:
    _types_coroutine = types.coroutine
    _types_CoroutineType = types.CoroutineType
except AttributeError:
    # Python 3.4
    _types_coroutine = None
    _types_CoroutineType = None



# A marker for iscoroutinefunction.
_is_coroutine = object()
# if _CoroutineABC is not None:
#     _COROUTINE_TYPES += (_CoroutineABC,)
# if _types_CoroutineType is not None:
#     # Prioritize native coroutine check to speed-up
#     # asyncio.iscoroutine.
#     _COROUTINE_TYPES = (_types_CoroutineType,) + _COROUTINE_TYPES


def iscoroutine(obj):
    """Return True if obj is a coroutine object."""
    return isinstance(obj, _COROUTINE_TYPES)

_inspect_iscoroutinefunction = inspect.iscoroutinefunction

CancelledError = base_futures.CancelledError
InvalidStateError = base_futures.InvalidStateError
TimeoutError = base_futures.TimeoutError
isfuture = base_futures.isfuture
TracebackLogger = futures._TracebackLogger
_PENDING = 'PENDING'
_CANCELLED = 'CANCELLED'
_FINISHED = 'FINISHED'


logger = logging.getLogger(__name__)


class Handle:
    """Object returned by callback registration methods."""

    __slots__ = ('_callback', '_args', '_cancelled', '_loop',
                 '_source_traceback', '_repr', '__weakref__')

    def __init__(self, callback, args, loop):
        self._loop = loop
        self._callback = callback
        self._args = args
        self._cancelled = False
        self._repr = None
        self._source_traceback = None

    # def _repr_info(self):
    #     info = [self.__class__.__name__]
    #     if self._cancelled:
    #         info.append('cancelled')
    #     if self._callback is not None:
    #         info.append(_format_callback_source(self._callback, self._args))
    #     if self._source_traceback:
    #         frame = self._source_traceback[-1]
    #         info.append('created at %s:%s' % (frame[0], frame[1]))
    #     return info

    # def __repr__(self):
    #     if self._repr is not None:
    #         return self._repr
    #     info = self._repr_info()
    #     return '<%s>' % ' '.join(info)

    def cancel(self):
        if not self._cancelled:
            self._cancelled = True

            self._callback = None
            self._args = None

    def _run(self):
        try:
            self._callback(*self._args)
        except Exception as exc:
            # cb = _format_callback_source(self._callback, self._args)
            # msg = 'Exception in callback {}'.format(cb)
            # context = {
            #     'message': msg,
            #     'exception': exc,
            #     'handle': self,
            # }
            # if self._source_traceback:
            #     context['source_traceback'] = self._source_traceback
            # self._loop.call_exception_handler(context)
            logger.exception('Handler _run')
        self = None  # Needed to break cycles when an exception occurs.


class Futhure:
    _state = _PENDING
    _result = None
    _exception = None
    _loop = None
    _source_traceback = None

    _asyncio_future_blocking = False
    _log_traceback = False
    _tb_logger = None

    def __init__(self, *, loop=None):
        if loop is None:
            self._loop = get_event_loop()
        else:
            self._loop = loop

        self._callbacks = []

    _repr_info = base_futures._future_repr_info

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, ' '.join(self._repr_info()))

    def cancel(self):
        if self._state != _PENDING:
            return False
        self._state = _CANCELLED
        self._schedule_callbacks()
        return True

    def _schedule_callbacks(self):
        callbacks = self._callbacks[:]
        if len(callbacks) == 0:
            return
        self._callbacks = []
        for callback in callbacks:
            self._loop.call_soon(callback, self)

    def cancelled(self):
        return self._state == _CANCELLED

    def done(self):
        return self._state != _PENDING

    def result(self):
        if self._state == _CANCELLED:
            raise CancelledError
        if self._state != _FINISHED:
            raise InvalidStateError('Result is not ready.')
        self._log_traceback = False
        if self._tb_logger is not None:
            self._tb_logger.clear()
            self._tb_logger = None
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self):
        if self._state == _CANCELLED:
            raise CancelledError
        if self._state != _FINISHED:
            raise InvalidStateError('Exception is not set.')
        self._log_traceback = False
        if self._tb_logger is not None:
            self._tb_logger.clear()
            self._tb_logger = None
        return self._exception

    def add_done_callback(self, fn):
        if self._state == _PENDING:
            self._loop.call_soon(fn, self)
        else:
            self._callbacks.append(fn)

    def remove_done_callback(self, fn):
        """Remove all instances of a callback from the "call when done" list.

        Returns the number of callbacks removed.
        """
        filtered_callbacks = [f for f in self._callbacks if f != fn]
        removed_count = len(self._callbacks) - len(filtered_callbacks)
        if removed_count:
            self._callbacks[:] = filtered_callbacks
        return removed_count

    def set_result(self, result):
        if self._state != _PENDING:
            raise InvalidStateError('{}: {!r}'.format(self._state, self))
        self._result = result
        self._state = _FINISHED
        self._schedule_callbacks()

    def set_exception(self, exception):
        if self._state != _PENDING:
            raise InvalidStateError('{}: {!r}'.format(self._state, self))
        if isinstance(exception, type):
            exception = exception()
        if type(exception) is StopIteration:
            raise TypeError("StopIteration interacts badly with generators "
                            "and cannot be raised into a Future")
        self._exception = exception
        self._state = _FINISHED
        self._schedule_callbacks()

    def __iter__(self):
        if not self.done():
            self._asyncio_future_blocking = True
            yield self  # This tells Task to wait for completion.
        assert self.done(), "yield from wasn't used with future"
        return self.result()  # May raise too.

    __await__ = __iter__


class Task(Futhure):
    _all_tasks = weakref.WeakSet()
    _current_tasks = {}

    @classmethod
    def current_task(cls, loop=None):
        """Return the currently running task in an event loop or None.

        By default the current task for the current event loop is returned.

        None is returned when called not in the context of a Task.
        """
        if loop is None:
            loop = get_event_loop()
        return cls._current_tasks.get(loop)

    @classmethod
    def all_tasks(cls, loop=None):
        """Return a set of all tasks for an event loop.

        By default all tasks for the current event loop are returned.
        """
        if loop is None:
            loop = get_event_loop()
        return {t for t in cls._all_tasks if t._loop is loop}

    def __init__(self, coro, *, loop=None):
        # assert coroutines.iscoroutine(coro), repr(coro)
        super().__init__(loop=loop)
        if self._source_traceback:
            del self._source_traceback[-1]
        self._coro = coro
        self._fut_waiter = None
        self._must_cancel = False
        self._loop.call_soon(self._step)
        self.__class__._all_tasks.add(self)

    def cancel(self):
        if self.done():
            return False
        if self._fut_waiter is not None:
            if self._fut_waiter.cancel():
                # Leave self._fut_waiter; it may be a Task that
                # catches and ignores the cancellation so we may have
                # to cancel it again later.
                return True
        # It must be the case that self._step is already scheduled.
        self._must_cancel = True
        return True

    def _step(self, exc=None):
        assert not self.done(), \
            '_step(): already done: {!r}, {!r}'.format(self, exc)
        if self._must_cancel:
            if not isinstance(exc, futures.CancelledError):
                exc = futures.CancelledError()
            self._must_cancel = False
        coro = self._coro
        self._fut_waiter = None

        self.__class__._current_tasks[self._loop] = self
        # Call either coro.throw(exc) or coro.send(None).
        try:
            if exc is None:
                # We use the `send` method directly, because coroutines
                # don't have `__iter__` and `__next__` methods.
                result = coro.send(None)
            else:
                result = coro.throw(exc)
        except StopIteration as exc:
            self.set_result(exc.value)
        except futures.CancelledError:
            super().cancel()  # I.e., Future.cancel(self).
        except Exception as exc:
            self.set_exception(exc)
        except BaseException as exc:
            self.set_exception(exc)
            raise
        else:
            blocking = getattr(result, '_asyncio_future_blocking', None)
            if blocking is not None:
                # Yielded Future must come from Future.__iter__().
                if result._loop is not self._loop:
                    self._loop.call_soon(
                        self._step,
                        RuntimeError(
                            'Task {!r} got Future {!r} attached to a '
                            'different loop'.format(self, result)))
                elif blocking:
                    if result is self:
                        self._loop.call_soon(
                            self._step,
                            RuntimeError(
                                'Task cannot await on itself: {!r}'.format(
                                    self)))
                    else:
                        result._asyncio_future_blocking = False
                        result.add_done_callback(self._wakeup)
                        self._fut_waiter = result
                        if self._must_cancel:
                            if self._fut_waiter.cancel():
                                self._must_cancel = False
                else:
                    self._loop.call_soon(
                        self._step,
                        RuntimeError(
                            'yield was used instead of yield from '
                            'in task {!r} with {!r}'.format(self, result)))
            elif result is None:
                # Bare yield relinquishes control for one event loop iteration.
                self._loop.call_soon(self._step)
            elif inspect.isgenerator(result):
                # Yielding a generator is just wrong.
                self._loop.call_soon(
                    self._step,
                    RuntimeError(
                        'yield was used instead of yield from for '
                        'generator in task {!r} with {}'.format(
                            self, result)))
            else:
                # Yielding something else is an error.
                self._loop.call_soon(
                    self._step,
                    RuntimeError(
                        'Task got bad yield: {!r}'.format(result)))
        finally:
            self.__class__._current_tasks.pop(self._loop)
            self = None  # Needed to break cycles when an exception occurs.

    def _wakeup(self, future):
        try:
            future.result()
        except Exception as exc:
            # This may also be a cancellation.
            self._step(exc)
        else:
            # Don't pass the value of `future.result()` explicitly,
            # as `Future.__iter__` and `Future.__await__` don't need it.
            # If we call `_step(value, None)` instead of `_step()`,
            # Python eval loop would use `.send(value)` method call,
            # instead of `__next__()`, which is slower for futures
            # that return non-generator iterators from their `__iter__`.
            self._step()
        self = None  # Needed to break cycles when an exception occurs.


class _RunningLoop(threading.local):
    _loop = None
    _pid = None


_running_loop = _RunningLoop()


def get_event_loop():
    current_loop = None
    if _running_loop._pid == os.getpid():
        current_loop = _running_loop._loop
    if current_loop is not None:
        return current_loop
    else:
        return Myloop()

def _set_running_loop(loop):
    """Set the running event loop.

    This is a low-level function intended to be used by event loops.
    This function is thread-specific.
    """
    _running_loop._pid = os.getpid()
    _running_loop._loop = loop


class Myloop(events.AbstractEventLoop):
    def __init__(self,selector=None):
        self._timer_cancelled_count = 0
        self._closed = False
        self._stopping = False
        self._ready = collections.deque()
        self._scheduled = []
        self._default_executor = None
        self._internal_fds = 0
        # Identifier of the thread running the event loop, or None if the
        # event loop is not running
        self._thread_id = None
        self._clock_resolution = time.get_clock_info('monotonic').resolution
        self._exception_handler = None

        # In debug mode, if the execution of a callback or a step of a task
        # exceed this duration in seconds, the slow callback/task is logged.
        self.slow_callback_duration = 0.1
        self._current_handle = None
        self._task_factory = None
        self._coroutine_wrapper_set = False

        if hasattr(sys, 'get_asyncgen_hooks'):
            # Python >= 3.6
            # A weak set of all asynchronous generators that are
            # being iterated by the loop.
            self._asyncgens = weakref.WeakSet()
        else:
            self._asyncgens = None

        # Set to True when `loop.shutdown_asyncgens` is called.
        self._asyncgens_shutdown_called = False
        self._debug = False
        if selector is None:
            selector = selectors.DefaultSelector()
        logger.debug('Using selector: %s', selector.__class__.__name__)
        self._selector = selector
        # self._make_self_pipe()
        self._transports = weakref.WeakValueDictionary()
    def _make_self_pipe(self):
        # A self-socket, really. :-)
        self._ssock, self._csock = self._socketpair()
        self._ssock.setblocking(False)
        self._csock.setblocking(False)
        self._internal_fds += 1
        self._add_reader(self._ssock.fileno(), self._read_from_self)

    def _process_self_data(self, data):
        pass

    def time(self):
        """Return the time according to the event loop's clock.

        This is a float expressed in seconds since an epoch, but the
        epoch, precision, accuracy and drift are unspecified and may
        differ per event loop.
        """
        return time.monotonic()

    def _read_from_self(self):
        while True:
            try:
                data = self._ssock.recv(4096)
                if not data:
                    break
                self._process_self_data(data)
            except InterruptedError:
                continue
            except BlockingIOError:
                break
    
    def _write_to_self(self):
        # This may be called from a different thread, possibly after
        # _close_self_pipe() has been called or even while it is
        # running.  Guard for self._csock being None or closed.  When
        # a socket is closed, send() raises OSError (with errno set to
        # EBADF, but let's not rely on the exact error code).
        csock = self._csock
        if csock is not None:
            try:
                csock.send(b'\0')
            except OSError:
                if self._debug:
                    logger.debug("Fail to write a null byte into the "
                                 "self-pipe socket",
                                 exc_info=True)



    def run_forever(self):

        self._thread_id = threading.get_ident()
        try:
            _set_running_loop(self)
            while True:
                self._run_once()
                if self._stopping:
                    break
        finally:
            self._stopping = False
            self._thread_id = None
            _set_running_loop(None)
            self._set_coroutine_wrapper(False)

    def _set_coroutine_wrapper(self, enabled):
        pass

    def _check_closed(self):
        if self._closed:
            raise RuntimeError('Event loop is closed')

    def run_until_complete(self, future):
        """Run until the Future is done.

        If the argument is a coroutine, it is wrapped in a Task.

        WARNING: It would be disastrous to call run_until_complete()
        with the same coroutine twice -- it would wrap it in two
        different Tasks and that can't be good.

        Return the Future's result, or raise its exception.
        """
        self._check_closed()

        # new_task = not futures.isfuture(future)
        # future = tasks.ensure_future(future, loop=self)
        # if new_task:
        #     # An exception is raised if the future didn't complete, so there
        #     # is no need to log the "destroy pending task" message
        #     future._log_destroy_pending = False

        future.add_done_callback(_run_until_complete_cb)
        try:
            self.run_forever()
        except:
            if future.done() and not future.cancelled():
                # The coroutine raised a BaseException. Consume the exception
                # to not log a warning, the caller doesn't have access to the
                # local task.
                future.exception()
            raise
        future.remove_done_callback(_run_until_complete_cb)
        if not future.done():
            raise RuntimeError('Event loop stopped before Future completed.')

        return future.result()

    def stop(self):
        """Stop running the event loop.

        Every callback already scheduled will still run.  This simply informs
        run_forever to stop looping after a complete iteration.
        """
        self._stopping = True

    def _call_soon(self, callback, args):
        handle = Handle(callback, args, self)
        self._ready.append(handle)
        return handle

    def call_soon(self, callback, *args):
        """Arrange for a callback to be called as soon as possible.

        This operates as a FIFO queue: callbacks are called in the
        order in which they are registered.  Each callback will be
        called exactly once.

        Any positional arguments after the callback will be passed to
        the callback when it is called.
        """
        self._check_closed()
        if self._debug:
            self._check_thread()
            self._check_callback(callback, 'call_soon')
        handle = self._call_soon(callback, args)
        if handle._source_traceback:
            del handle._source_traceback[-1]
        return handle

    def _process_events(self, event_list):
        for key, mask in event_list:
            fileobj, (reader, writer) = key.fileobj, key.data
            if mask & selectors.EVENT_READ and reader is not None:
                if reader._cancelled:
                    self._remove_reader(fileobj)
                else:
                    self._add_callback(reader)
            if mask & selectors.EVENT_WRITE and writer is not None:
                if writer._cancelled:
                    self._remove_writer(fileobj)
                else:
                    self._add_callback(writer)

    def _add_reader(self, fd, callback, *args):
        self._check_closed()
        handle = events.Handle(callback, args, self)
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            self._selector.register(fd, selectors.EVENT_READ,
                                    (handle, None))
        else:
            mask, (reader, writer) = key.events, key.data
            self._selector.modify(fd, mask | selectors.EVENT_READ,
                                  (handle, writer))
            if reader is not None:
                reader.cancel()

    def _remove_reader(self, fd):
        if self.is_closed():
            return False
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            return False
        else:
            mask, (reader, writer) = key.events, key.data
            mask &= ~selectors.EVENT_READ
            if not mask:
                self._selector.unregister(fd)
            else:
                self._selector.modify(fd, mask, (None, writer))

            if reader is not None:
                reader.cancel()
                return True
            else:
                return False

    def _add_writer(self, fd, callback, *args):
        self._check_closed()
        handle = events.Handle(callback, args, self)
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            self._selector.register(fd, selectors.EVENT_WRITE,
                                    (None, handle))
        else:
            mask, (reader, writer) = key.events, key.data
            self._selector.modify(fd, mask | selectors.EVENT_WRITE,
                                  (reader, handle))
            if writer is not None:
                writer.cancel()

    def _remove_writer(self, fd):
        """Remove a writer callback."""
        if self.is_closed():
            return False
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            return False
        else:
            mask, (reader, writer) = key.events, key.data
            # Remove both writer and connector.
            mask &= ~selectors.EVENT_WRITE
            if not mask:
                self._selector.unregister(fd)
            else:
                self._selector.modify(fd, mask, (reader, None))

            if writer is not None:
                writer.cancel()
                return True
            else:
                return False

    def add_reader(self, fd, callback, *args):
        """Add a reader callback."""
        self._ensure_fd_no_transport(fd)
        return self._add_reader(fd, callback, *args)

    def remove_reader(self, fd):
        """Remove a reader callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_reader(fd)

    def add_writer(self, fd, callback, *args):
        """Add a writer callback.."""
        self._ensure_fd_no_transport(fd)
        return self._add_writer(fd, callback, *args)

    def remove_writer(self, fd):
        """Remove a writer callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_writer(fd)

    def _run_once(self):
        # print('_run_once')
        """Run one full iteration of the event loop.

        This calls all currently ready callbacks, polls for I/O,
        schedules the resulting callbacks, and finally schedules
        'call_later' callbacks.
        """

        sched_count = len(self._scheduled)

        # Remove delayed calls that were cancelled from head of queue.
        while self._scheduled and self._scheduled[0]._cancelled:
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False

        timeout = None
        if self._ready or self._stopping:
            timeout = 0
        elif self._scheduled:
            # Compute the desired timeout.
            when = self._scheduled[0]._when
            timeout = max(0, when - self.time())

        if self._debug and timeout != 0:
            t0 = self.time()
            event_list = self._selector.select(timeout)
            dt = self.time() - t0
            if dt >= 1.0:
                level = logging.INFO
            else:
                level = logging.DEBUG
            nevent = len(event_list)
            if timeout is None:
                logger.log(level, 'poll took %.3f ms: %s events',
                           dt * 1e3, nevent)
            elif nevent:
                logger.log(level,
                           'poll %.3f ms took %.3f ms: %s events',
                           timeout * 1e3, dt * 1e3, nevent)
            elif dt >= 1.0:
                logger.log(level,
                           'poll %.3f ms took %.3f ms: timeout',
                           timeout * 1e3, dt * 1e3)
        else:
            event_list = self._selector.select(timeout)
        self._process_events(event_list)

        # Handle 'later' callbacks that are ready.
        end_time = self.time() + self._clock_resolution
        while self._scheduled:
            handle = self._scheduled[0]
            if handle._when >= end_time:
                break
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False
            self._ready.append(handle)

        # This is the only place where callbacks are actually *called*.
        # All other places just add them to ready.
        # Note: We run all currently scheduled callbacks, but not any
        # callbacks scheduled by callbacks run this time around --
        # they will be run the next time (after another I/O poll).
        # Use an idiom that is thread-safe without using locks.
        ntodo = len(self._ready)
        for i in range(ntodo):
            handle = self._ready.popleft()
            if handle._cancelled:
                continue
            if self._debug:
                try:
                    self._current_handle = handle
                    t0 = self.time()
                    handle._run()
                    dt = self.time() - t0
                    # if dt >= self.slow_callback_duration:
                    #     logger.warning('Executing %s took %.3f seconds',
                    #                    _format_handle(handle), dt)
                finally:
                    self._current_handle = None
            else:
                handle._run()
        handle = None  # Needed to break cycles when an exception occurs.


def _run_until_complete_cb(fut):
    exc = fut._exception
    if (isinstance(exc, BaseException)
            and not isinstance(exc, Exception)):
        # Issue #22429: run_forever() already finished, no need to
        # stop it.
        return
    fut._loop.stop()


def test():
    print(1)
    yield time.sleep(1)
    print(2)


def coroutine1(func):
    """Decorator to mark coroutines.

    If the coroutine is not yielded from before it is destroyed,
    an error message is logged.
    """
    if _inspect_iscoroutinefunction(func):
        # In Python 3.5 that's all we need to do for coroutines
        # defiend with "async def".
        # Wrapping in CoroWrapper will happen via
        # 'sys.set_coroutine_wrapper' function.
        return func

    if inspect.isgeneratorfunction(func):
        coro = func
    else:
        @functools.wraps(func)
        def coro(*args, **kw):
            res = func(*args, **kw)
            if (base_futures.isfuture(res) or inspect.isgenerator(res) or
                isinstance(res, CoroWrapper)):
                res = yield from res
            elif _AwaitableABC is not None:
                # If 'func' returns an Awaitable (new in 3.5) we
                # want to run it.
                try:
                    await_meth = res.__await__
                except AttributeError:
                    pass
                else:
                    if isinstance(res, _AwaitableABC):
                        res = yield from await_meth()
            return res
    _DEBUG = False
    if not _DEBUG:
        if _types_coroutine is None:
            wrapper = coro
        else:
            wrapper = _types_coroutine(coro)
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwds):
            w = CoroWrapper(coro(*args, **kwds), func=func)
            if w._source_traceback:
                del w._source_traceback[-1]
            # Python < 3.5 does not implement __qualname__
            # on generator objects, so we set it manually.
            # We use getattr as some callables (such as
            # functools.partial may lack __qualname__).
            w.__name__ = getattr(func, '__name__', None)
            w.__qualname__ = getattr(func, '__qualname__', None)
            return w

    wrapper._is_coroutine = _is_coroutine  # For iscoroutinefunction().
    return wrapper

@coroutine
def _wrap_awaitable(awaitable):
    """Helper for asyncio.ensure_future().

    Wraps awaitable (an object with __await__) into a coroutine
    that will later be wrapped in a Task by ensure_future().
    """
    return (yield from awaitable.__await__())



def ensure_future(coro_or_future, *, loop=None):
    """Wrap a coroutine or an awaitable in a future.

    If the argument is a Future, it is returned directly.
    """
    if futures.isfuture(coro_or_future):
        if loop is not None and loop is not coro_or_future._loop:
            raise ValueError('loop argument must agree with Future')
        return coro_or_future
    elif iscoroutine(coro_or_future):
        if loop is None:
            loop = events.get_event_loop()
        task = loop.create_task(coro_or_future)
        if task._source_traceback:
            del task._source_traceback[-1]
        return task
    elif inspect.isawaitable(coro_or_future):
        return ensure_future(_wrap_awaitable(coro_or_future), loop=loop)
    else:
        raise TypeError('A Future, a coroutine or an awaitable is required')



def main():
    import time
    import asyncio
    
    now = lambda : time.time()
    @coroutine
    def do_some_work(x):
        print('aaaa')
        yield 'a'
        print('Waiting: ', x)
    
    start = now()
    
    c1 = do_some_work(2)
    c1 = ensure_future(c1)
    # t = Task(coroutine)
    
    loop = get_event_loop()
    loop.run_until_complete(c1)
    
    print('TIME: ', now() - start)

if __name__ == '__main__':
    main()