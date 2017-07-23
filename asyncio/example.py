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

    loop = asyncio.get_event_loop()

    loop.run_until_complete(wait([coroutine1, coroutine2, coroutine3]))

    print('TIME: ', now() - start)

async def error_coro2():
    await sleep(2)

def error_coro():
    yield  error_coro2()

def error_coro2():
    yield error_coro()
    
def main2():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(error_coro())



if __name__ == '__main__':
    main2()
