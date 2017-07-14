import time
from collections import Counter, OrderedDict

d = OrderedDict()

d['upstream1'] = {'weight': 2, 'failed': 10}
d['upstream2'] = {'weight': 4, 'failed': 10}
d['upstream3'] = {'weight': 6, 'failed': 10}


def fetch_next():
    c = Counter()
    f = Counter()

    for upstream, conf in d.items():
        c[upstream] = conf['weight']
        f[upstream] = conf['failed']

    while True:
        for upstream, conf in d.items():

            if c[upstream] > 0 and f[upstream] > 0:
                c[upstream] -= 1
                rst = yield upstream
                print('get rst from ', upstream, rst)
                if rst != 'ok':
                    f[upstream] -= 1

        if sum([c[upstream] for upstream in d.keys() if f[upstream] > 0]) == 0:
            for upstream, conf in d.items():
                c[upstream] = conf['weight']

        if sum([c[upstream] for upstream in d.keys() if f[upstream] > 0]) == 0:
            raise StopIteration('No valid upstream')


g = fetch_next()
upstream = g.send(None)
while True:
    print(upstream)
    time.sleep(1)
    print('do something in', upstream)
    upstream = g.send('False')

