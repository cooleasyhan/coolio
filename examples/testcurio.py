from curio import run, run_in_thread
import time
def echo(var):
    time.sleep(1)
    print('echo',var)


# run(echo, 'Yi')

g = run_in_thread(echo, 'Yi')


run(g)