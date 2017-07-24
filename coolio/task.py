# coolio/task.py
from concurrent.futures import Future as f
_PENDING = 'PENDING'
_CANCELLED = 'CANCELLED'
_FINISHED = 'FINISHED'

def get_event_loop():
    pass

class Futhure(object):
    def __init__(self, *, loop=None):
        self._state = _PENDING
        if loop is None:
            self._loop = ''
        else:
            self._loop = get_event_loop()
        self._call_backs = []
        self._result = None
        self._exception = None
    
    def set_result(self, result):
        pass

    def set_exception(self, result):
        pass

    def result(self):
        pass

    def add_done_callback(self):
        pass

    def remove_done_callback(self):
        pass
    
    def cancel(self):
        pass
    
    def exception(self):
        pass

    def _