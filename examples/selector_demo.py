import selectors
import socket
import select
sel = selectors.DefaultSelector()
sel.register


def accept(sock, mask):
    print('accept mask', mask)
    if mask == selectors.EVENT_READ:
        conn, addr = sock.accept()
        print('accepted', conn, 'from', addr)
        conn.setblocking(False)
        sel.register(conn, selectors.EVENT_READ, read)
    else:
        sel.modify(sock, selectors.EVENT_WRITE, write)

def write(conn, mask):
    conn.send(b'Hello\n')
    sel.modify(conn, selectors.EVENT_READ, read)

def read(conn, mask):
    data = conn.recv(1000)
    if data:
        print('echoing', repr(data), 'to', conn)
        sel.modify(conn, selectors.EVENT_WRITE, write)
        #conn.send(data)
        
    else:
        print('closing', conn)
        sel.unregister(conn)
        conn.close()


sock = socket.socket()
sock.bind(('localhost', 1234))
sock.listen(100)
sock.setblocking(False)
sel.register(sock, selectors.EVENT_READ | selectors.EVENT_WRITE, accept)

while True:
    events = sel.select()
    for key, mask in events:
        callback = key.data
        callback(key.fileobj, mask)
