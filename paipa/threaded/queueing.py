"""
Everything related to managing/handling the queues between the thread-steps.
"""
import collections as _collections
import threading as _threading

import enum as _enum

Types = _enum.IntEnum('Types', ['sentry', 'exception', 'regular', 'meta'])
Entry = _collections.namedtuple("Entry", ["type", "payload", "retries"])


class QueueWrapper(object):
    """
    Queue object wrapper adding a "closed" attribute

    :IVariables:
      `_queue` : any
        The wrapped queue

      `_closed` : ``bool``
        The closed attribute, accessed through the closed property
    """

    def __new__(cls, queue):
        """
        Construction

        If the queue is already wrapped, don't wrap it again

        :Parameters:
          `queue` : any
            The queue object to wrap
        """
        try:
            if issubclass(queue, cls):
                raise AssertionError("Trying to rewrap queue, bad idea.")
        except TypeError:
            pass
        return super(QueueWrapper, cls).__new__(cls)

    def __init__(self, queue):
        """
        Initialization

        :Parameters:
          `queue` : any
            The queue object to wrap
        """
        self._queue = queue
        self._closed = False
        self._mutex = _threading.Lock()

    def __getattr__(self, name):
        """ Get everything unknown from the queue object """
        return getattr(self._queue, name)

    @property
    def closed(self):
        """Is the queue closed?"""
        self._mutex.acquire()
        try:
            return self._closed
        finally:
            self._mutex.release()

    @closed.setter
    def closed(self, value):
        """Set the closed status of the queue."""
        self._mutex.acquire()
        try:
            self._closed = bool(value)
        finally:
            self._mutex.release()
