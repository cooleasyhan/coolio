'''
coolio/errors.py

Coolio specific exceptions

'''

class CoolioError(Exception):
    '''
    Base class for all coolio-related exceptions
    '''

class CancelledError(Exception):
    '''
    Base class for all task-cancellation related exceptions
    '''
