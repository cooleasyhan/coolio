from curio import run, run_in_thread
import time
import asyncio
def echo(var):
    time.sleep(1)
    print('echo',var)


# run(echo, 'Yi')

g = run_in_thread(echo, 'Yi')


run(g)

asyncio.open_connection(host, 80)

loop = asyncio.events.get_event_loop()


loop.create_connection()