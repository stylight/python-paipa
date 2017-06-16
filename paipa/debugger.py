"""
Pipeline debugging helpers. This one analyses the amount and speed of data
flowing in and out of every step through the pipeline. Awesome!
"""
import abc
import collections
import logging
import os
import resource
import time

from .debug_reporter import LoggingReporter

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Debugger(object):
    __metaclass__ = abc.ABCMeta

    """Base class for the pipeline debuggers."""

    @abc.abstractmethod
    def head(self, iterator):
        """This wraps the source of the pipeline."""
        raise NotImplementedError

    @abc.abstractmethod
    def tail(self, iterator):
        """This wraps the combined pipeline."""
        raise NotImplementedError

    @abc.abstractmethod
    def do_track(self, iterator):
        """This wraps every individual step of the pipeline."""
        raise NotImplementedError

    @abc.abstractmethod
    def report(self, iterator):
        """This wraps the pipeline again. There for convenience reasons."""
        raise NotImplementedError

    def track(self, iterator):
        """This wraps every individual step of the pipeline.

        WARNING: Do not override.
        """
        if _object_name(iterator) == 'do_track':
            return iterator
        else:
            return self.do_track(iterator)


def _dict_sub(left, right):
    """

    >>> _dict_sub({'a': 21}, {'a': 7})
    {'a': 14}

    :param left:
    :param right:
    :return:
    """
    new = left.copy()
    for key, value in right.items():
        new[key] -= value
    return new

CPU_TIME_KEYS = (
    'utime',   # user time
    'stime',   # system time
    'ctime',   # children's user time
    'cstime',  # children's system time
    'rtime'    # elapsed real time since a fixed point in the past
    # we don't need this as we can't measure this accurately
    # without fiddling with offsets, etc. so we skip this.
)


def _get_times(cpu_keys=CPU_TIME_KEYS):
    # Python 3's zip type is a generator and thus not subscriptable
    return dict(list(zip(cpu_keys, os.times()))[:4])


def _get_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


class PipelineRuntimeDebugger(Debugger):
    """Track the run-times of individual generators.

    We keep a stack of coroutines (obtained by wrapping all of them) and then

    """

    def __init__(self, reporters=None, call_counter=None):
        # NOTE
        # call_counter is a bit specific to our own purposes, this could be
        # made more generic by passing in a dict of functions which return
        # the count. Sadly then the dependency on the reporters would require
        # us to make these functions typed (i.e. pass a type) so that
        # reporters could distinguish between gauges and increments.
        self._call_counter = call_counter
        self._reporters = reporters or [LoggingReporter(logger)]
        self._stack = []
        self._start = None
        self._rss = None
        self._cpu_times = None
        self._resources = collections.defaultdict(
            lambda: collections.defaultdict(float)
        )
        self._tracked_steps = []
        self._last_shown = time.time()

    def register(self, who):
        who = _object_name(who)
        id_ = object()
        self._tracked_steps.insert(0, (who, id_))
        return id_

    def push(self, id_):
        self._start = time.time()
        self._cpu_times = _get_times()
        self._rss = _get_rss()
        self._stack.append(id_)

    def pop(self, count=1):
        assert self._stack, "Popped too often!"
        id_ = self._stack.pop()
        call_count = self._call_counter.pop() if self._call_counter else 0
        _resource = self._resources[id_]

        _resource['queries'] += call_count
        _resource['count'] += count
        _resource['runtime'] += time.time() - self._start

        queries = _resource['queries']
        count_ = _resource['count']
        runtime = _resource['runtime']

        _resource['queries_per_entry'] = (
            (queries / count_) if count_ else 0)
        _resource['runtime_per_entry'] = (
            (runtime / count_) if count_ else 0)
        _resource['throughput'] = (
            (count_ / runtime) if runtime else 0)

        _resource['rss'] += _get_rss() - self._rss
        delta = _dict_sub(
            _get_times(),
            self._cpu_times
        )
        for key, value in delta.items():
            _resource[key] += value

        self._start = time.time()
        self._cpu_times = _get_times()
        self._rss = _get_rss()

    def show(self, force=False):
        do_show = force or (time.time() - self._last_shown) > 5
        if not do_show:
            return

        for reporter in self._reporters:
            info = [(step_name, self._resources[id_])
                    for step_name, id_ in self._tracked_steps]
            reporter.show(info)

        self._last_shown = time.time()

    def do_track(self, iterator):
        myself = self.register(iterator)
        self.push(myself)
        for entry in iterator:
            count = len(entry) if isinstance(entry, list) else 1
            self.pop(count=count)
            self.show()
            yield entry
            self.push(myself)
        self.pop()

    def head(self, iterator):
        return iterator

    def report(self, iterator):
        for entry in iterator:
            yield entry
        self.show(force=True)

    def tail(self, iterator):
        for entry in iterator:
            yield entry


def _object_name(thing):
    if hasattr(thing, '__name__'):
        return thing.__name__
    elif hasattr(thing, '__class__'):
        return thing.__class__.__name__
    else:
        return repr(thing)
