import selectors
import socket
import select
sel = selectors.DefaultSelector()


def handler(fileobj, mask, data):
    if mask == selectors.EVENT_READ:
        if fileobj == sock:
            conn, addr = fileobj.accept()
            print('accepted', conn, 'from', addr)
            conn.setblocking(False)
            sel.register(conn, selectors.EVENT_READ)
        else:
            conn = fileobj
            data = conn.recv(100000)
            if data:
                print('recving data', data, 'from ', conn)
                resp = data
                sel.modify(conn, selectors.EVENT_WRITE, resp)

            else:
                print('closing', conn)
                sel.unregister(conn)
                conn.close()
    else:
        conn = fileobj
        fileobj.send(data)
        sel.modify(conn, selectors.EVENT_READ)


sock = socket.socket()
sock.bind(('localhost', 12345))
sock.listen(100)
sock.setblocking(False)
sel.register(sock, selectors.EVENT_READ | selectors.EVENT_WRITE)

while True:
    events = sel.select()
    for key, mask in events:
        handler(key.fileobj, mask, key.data)
