# coolio
## learning from asyncio , curio

## asyncio 源码解析
### 小总结
1. 多并发有一个核心问题在于计算单元的分配， 而协程是非抢占，用于需要自己释放使用权， 本质上仍然是单线程的处理能力，但是切换成本却很低，造成其在IO场景下具有很大的优势。
2. 协程编程说到底仍然是异步编程，还是需要与callback和事件机制的结合使用。
3. 协程更多的让用户以一种同步的方式编写异步代码，利用带有中间状态的函数，python中主要是yield等。  yield前半部为正常处理，后半部为callback部分。

### 源码TODO
1.  futhures : _asyncio_future_blocking 使用， Task _wakeup使用
2. 原生yield yield from 实现Task
3. ensure_future， 多个输入类型之间的封装等细节
4. selector的使用，在socket， http等领域的实现


### 简单实例追踪
不涉及到selector内容，更多是一个callback调度器。
```python
import time
import asyncio
from asyncio import sleep, ensure_future, wait


async def long_time_work(x=1):
    print('long time work')
    await sleep(x)
    print('long time work End')


async def do_some_work(x):
    print('Waiting: ', x)
    await long_time_work(x)


def main():
    def now(): return time.time()

    start = now()
    coroutine1 = do_some_work(1)
    coroutine2 = do_some_work(2)
    coroutine3 = do_some_work(3)

    '''
    get_event_loop
    1. 利用threading local获取线程当前event_loop, 
    class _UnixSelectorEventLoop(selector_events.BaseSelectorEventLoop):
        ...
    class BaseSelectorEventLoop(base_events.BaseEventLoop):
        ...
    class BaseEventLoop(events.AbstractEventLoop):
        ...

    class _RunningLoop(threading.local):
        _loop = None
        _pid = None

    def get_event_loop():
        current_loop = None
        if _running_loop._pid == os.getpid():
            current_loop = _running_loop._loop
        if current_loop is not None:
            return current_loop
        else:
            return get_event_loop_policy().get_event_loop()
    
    2. 在这里主要关注BaseEventLoop，不会涉及到selector相关内容
    '''
    loop = asyncio.get_event_loop()

    '''
    1. run_until_complete(futhure)：
        1.1 确保参数futhure 为futhure[细节TODO， 这里可简单理解为将相应job转换成tasks.Task]
            future = tasks.ensure_future(future, loop=self)
        1.2 添加回调，用于在futhure执行完成后关闭loop
            future.add_done_callback(_run_until_complete_cb)
        1.3 运行loop
            self.run_forever()
    2. run_forever
        events._set_running_loop(self)
        while True:
            self._run_once()
            if self._stopping:
                break
    3. _run_once
        3.1 计算_scheduled
        3.2 利用selector获取事件并处理，这个例子并不会使用到
            event_list = self._selector.select(timeout)
            self._process_events(event_list)
        3.3 处理self._ready中的内容，这里是唯一一个真正执行callback的位置
            handle = self._ready.popleft()
            if handle._cancelled:
                continue
            handle._run()
        
    4. 重点来了，Task至怎么一步步执行的呢。 
        4.1 loop 中有一个核心方法： call_soon, 用于生成 events.Handle, Handler 会在_run_once中执行
            def _call_soon(self, callback, args):
                handle = events.Handle(callback, args, self)
                if handle._source_traceback:
                    del handle._source_traceback[-1]
                self._ready.append(handle)
                return handle
        4.2 tasks.Task 初始化时
            class Task(Future):
                def __init__(self, coro, *, loop=None):
                    ...
                    self._loop.call_soon(self._step)
                    self.__class__._all_tasks.add(self)
        4.3 重心来到Task._step, 核心语法是async， await 的调用， 但需要注意的是，不能直接使用yield, yield from
            def _step(self, exc=None):
                ...
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
                    ...
                    else:
                        # Yielding something else is an error.
                        self._loop.call_soon(
                            self._step,
                            RuntimeError(
                                'Task got bad yield: {!r}'.format(result)))
    '''
    loop.run_until_complete(wait([coroutine1, coroutine2, coroutine3]))

    print('TIME: ', now() - start)


if __name__ == '__main__':
    main()

```

