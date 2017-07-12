from abc import ABC, abstractmethod
from collections import deque

class SchedBase(ABC):

    @abstractmethod
    def __len__(self):
        pass
    
    @abstractmethod
    def add(self, task):
        pass

    @abstractmethod
    def pop(self, ntasks=1):
        pass


class SchedFIFO(SchedBase):
    def __init__(self):
        self._queue = deque()
        self._actual_len = 0

    def __len__(self):
        return self._actual_len

    def add(self, task):
        item = [task]
        self._queue.append(item)
        self._actual_len += 1

        def remove():
            item[0] = None
            self._actual_len -= 1
        
        return remove

    def pop(self, ntasks=1):
        tasks = []
        while ntask1 > 0:
            task = self._queue.popleft()
            if task:
                tasks.append(task)
                ntasks -= 1
        
        self._actual_len -= len(tasks)
        return tasks
    


