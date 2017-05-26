"""
Reporter classes for various purposes.

They can be used to report pipeline stats to the console or to datadog.
"""
import abc
import re

import six


class DebugReporter(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def show(self, info):
        raise NotImplementedError


class LoggingReporter(DebugReporter):

    def __init__(self, _logger):
        self._logger = _logger
        pattern = (
            "> %-s: count: %d runtime: %.2f %.2f/s "
            "utime: %.2f stime: %.2f q: %d q/e: %.2f "
            "rss: %.2f"
        )
        self._aligned_log = AlignedLog(self._logger, pattern)

    def show(self, info):
        self._logger.info("-" * 20)
        for step_name, resources in info:
            if not resources:
                continue

            self._aligned_log.info(
                step_name,
                int(resources['count']),
                resources['runtime'],
                resources['throughput'],
                resources['utime'],
                resources['stime'],
                int(resources['queries']),
                resources['qpe'],
                resources['rss']
            )
        self._aligned_log.flush()


def align_pattern(pattern, args_list):
    """
    >>> align_pattern("%s %s", [(object(), object()), (object(), object())])
    '%s %s'

    >>> align_pattern("%s %s", [('foo', 'bar'), ('f', '1234')])
    '%3s %4s'

    >>> align_pattern("%s %s", [('foo', 'bar baz barf'), ('foo', 'bar')])
    '%3s %12s'

    >>> align_pattern("%-s %s", [('foo', 'bar baz barf'), ('foo', 'bar')])
    '%-3s %12s'

    >>> align_pattern("%.2f %-.2f", [(1.22222, 1), (1.1, 12)])
    '%4.2f %-2.2f'

    >>> pattern = (
    ...     "> %-s: count: %d runtime: %.2f %.2f/s "
    ...     "utime: %-.2f stime: %-.2f q: %-d q/e: %.2f "
    ...     "rss: %.2f"
    ... )
    >>> align_pattern(pattern, [('foo', 1, 1.2, 11, 1.2, 1.2, 11, 1.2, 1.2)])
    '> %-3s: count: %1d runtime: %4.2f %2.2f/s utime: %-4.2f stime: %-4.2f\
 q: %-2d q/e: %4.2f rss: %4.2f'

    :param pattern:
    :param args_list:
    :return:
    """
    sub_re = re.compile("%(-?)")
    max_lens = [0] * max(len(arg) for arg in args_list)
    for args in args_list:
        assert len(args) == len(max_lens)
        for pos, arg in enumerate(args):
            if isinstance(arg, six.string_types):
                max_lens[pos] = max(max_lens[pos], len(arg.strip()))
            elif isinstance(arg, float):
                max_lens[pos] = max(max_lens[pos], len("%.2f" % arg))
            elif isinstance(arg, six.integer_types):
                max_lens[pos] = max(max_lens[pos], len(str(int(arg))))

    pre = sub_re.sub('%%\\1%s', pattern)
    return pre % tuple([str(l) if l else '' for l in max_lens])


class AlignedLog(object):
    def __init__(self, logger_, pattern):
        self._logger = logger_
        self._pattern = pattern
        self._logs = []

    def info(self, *args):
        self._logs.append(("info", args))

    def debug(self, *args):
        self._logs.append(("debug", args))

    def warn(self, *args):
        self._logs.append(("warn", args))

    def flush(self):
        pattern = align_pattern(self._pattern, [arg for _, arg in self._logs])
        for level, args in self._logs:
            getattr(self._logger, level)(pattern, *args)
        self._logs[:] = []
