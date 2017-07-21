import selectors
import socket
import select
sel = selectors.DefaultSelector()


def add_status(resp, status='200', status_text='OK'):
    resp.insert(0, f'HTTP/1.1 {status} {status_text}')


def add_header(resp, name, value):
    resp.insert(1, f'{name}: {value}')


def add_body(resp, body):
    resp.append('')
    resp.append(body)
    add_header(resp, 'Content-length', len(body.encode('utf-8')))


def get_resp(resp):
    return '\r\n'.join(resp).encode('utf-8')


def handler(fileobj, mask, data):
    if mask == selectors.EVENT_READ:
        if fileobj == sock:
            conn, addr = fileobj.accept()
            print('accepted', conn, 'from', addr)
            conn.setblocking(False)
            sel.register(conn, selectors.EVENT_READ)
        else:
            conn = fileobj
            data = conn.recv(100000).decode('utf-8')
            if data:
                resp = []
                add_status(resp)

                resp_header = list(resp)


                add_body(resp, '''<html>
<header>
</header>
<body>
Request Data:
<pre>
{request_content}
Response Header:
{response_header}
</pre>
</body>
</html>'''.format(request_content=data, response_header='\r\n'.join(resp_header)))

                sel.modify(conn, selectors.EVENT_WRITE, get_resp(resp))

            else:
                print('closing', conn)
                sel.unregister(conn)
                conn.close()
    else:
        conn = fileobj
        fileobj.send(data)
        sel.modify(conn, selectors.EVENT_READ)


sock = socket.socket()
sock.bind(('localhost', 9002))
sock.listen(1)
sock.setblocking(False)
sel.register(sock, selectors.EVENT_READ | selectors.EVENT_WRITE)

while True:
    events = sel.select()
    for key, mask in events:
        handler(key.fileobj, mask, key.data)
