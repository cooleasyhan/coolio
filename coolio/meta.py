# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die. No seriously.
#
import inspect
from functools import partial, wraps

try:
    _isasyncgenfunction = inspect.isasyncgenfunction
except AttributeError:
    def _isasyncgenfunction(func): return False


def iscoroutinefunction(func):
    if isinstance(func, partial):
        return iscoroutinefunction(func.func)
    if hasattr(func, '__func__'):
        return iscoroutinefunction(func.__func__)

    return inspect.iscoroutinefunction(func) or hasattr(func, '_awaitable') or _isasyncgenfunction(func)


def instantiate_coroutine(corofunc, *args, **kwargs):
    '''
    Try to instantiate a coroutine. If corofunc is already a coroutine,
    we're done.  If it's a coroutine function, we call it inside an
    async context with the given arguments to create a coroutine.  If
    it's not a coroutine, we call corofunc(*args, **kwargs) and hope
    for the best.
    '''
    if inspect.iscoroutine(corofunc) or inspect.isgenerator(corofunc):
        return corofunc

    if not iscoroutinefunction(corofunc):
        coro = corofunc(*args, **kwargs)
        if not inspect.iscoroutine(coro):
            raise TypeError('Cound not create coroutine form %s' %corofunc)
        return coro
