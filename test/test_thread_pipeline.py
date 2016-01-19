#!/usr/bin/env python
# coding: utf-8
"""
Tests for threaded pipeline
"""

import itertools as _itertools
import logging as _logging
import unittest as _unittest
import signal as _signal
import sys as _sys

from paipa import threaded as _threaded
from paipa import iterables as _iterables

_logging.basicConfig(format='%(asctime)-15s %(message)s')
logger = _logging.getLogger()

# pylint: disable = C0111, R0904
if _sys.version_info > (3,):
    long = int


class SigAlarmTimeout(object):
    """
    Sets an alarm timeout.
    If no handler is given, signal.SIG_DFL is used, which kills the process.
    """
    def __init__(self, duration, handler=None):
        self.duration = duration
        self.handler = handler or _signal.SIG_DFL
        self._old_alarm_handler = None

    def __enter__(self):
        self._old_alarm_handler = _signal.getsignal(_signal.SIGALRM)
        _signal.signal(_signal.SIGALRM, self.handler)
        _signal.alarm(self.duration)

    def __exit__(self, tpe, value, traceback):
        _signal.alarm(0)
        if self._old_alarm_handler:
            _signal.signal(_signal.SIGALRM, self._old_alarm_handler)
        else:
            _signal.signal(_signal.SIGALRM, _signal.SIG_IGN)


class FooException(Exception):
    pass


class Timeout(Exception):
    pass


def _crasher(iterator):
    for i in iterator:
        if i > 500:
            raise Exception


class TestThreadPipeline(_unittest.TestCase):
    # pylint: disable=invalid-name
    def setUp(self):
        logger.setLevel(_logging.INFO)

    def test_pipline_application(self):
        try:
            import tornado
            import tornado.web
        except ImportError:
            raise _unittest.SkipTest("Tornado test skipped, as not installed.")

        # pylint: disable=import-error,no-init,too-few-public-methods
        from paipa import glue as _glue

        class MainHandler(tornado.web.RequestHandler):
            def get(self):
                pass

        app = _glue.PipelineApplication(
            dogkey='test',
            queue_path='/tmp',
            pipeline=[
                (_threaded.iterstep(_crasher), 1)
            ],
            routes=[
                ('/', MainHandler),
            ]
        )

        import threading
        import time

        class Delay(threading.Thread):
            def run(self):
                # pylint: disable=protected-access
                time.sleep(2)
                app._ioloop.stop()

        stopper = Delay()
        stopper.daemon = True
        stopper.start()

        self.assertRaises(SystemExit, app.start, port=18080)

    def test_iterstep_failing_with_iterable_sourcestep(self):
        ppln = _threaded.Pipeline([(_threaded.iterstep(_crasher), 1)])
        ppln.put_iterable(_itertools.count())
        self.assertRaises(Exception, ppln.run)

    def test_iterstep_failing(self):
        # This test is dangerous, as it can stall the whole test-suite.
        # The whole sigalarm setting is to protect against that, somehow.
        def raise_alarm(*_):
            raise Timeout()

        def failing_iterator(iterator):
            for count, entry in enumerate(iterator):
                if count > 1000:
                    raise FooException
                yield entry

        pipeline = _threaded.Pipeline([
            (_threaded.iterstep(failing_iterator), 1),
        ], max_retries=1)
        pipeline.put_iterable(range(1000000))

        try:
            with SigAlarmTimeout(30, handler=raise_alarm):
                self.assertRaises(FooException, pipeline.run)
        except Timeout:
            try:
                pipeline.stop()
            finally:
                raise AssertionError("Timeout exceeded")

    def test_pipeline_crash(self):
        class Crasher(_threaded.AbstractStep):
            def process(self, entry):
                raise ValueError("What are you looking at!?")

        pipeline = _threaded.Pipeline([
            (Crasher, 1)
        ], max_retries=0)
        pipeline.put("Hey you!")
        pipeline.finish()
        import pytest
        with pytest.raises(ValueError):
            pipeline.run()

    def test_pipeline(self):
        class Download(_threaded.AbstractStep):
            def process(self, entry):
                return entry

        def process(response):
            if response == 17:
                raise FooException(response)
            return response

        class Upload(_threaded.AbstractStep):
            def process(self, entry):
                logger.debug("Upload %s", entry)
                return entry

        pipeline = _threaded.Pipeline([
            (Download, 10),
            (_threaded.funcstep(process), 1),
            (_threaded.iterstep(_iterables.chunk(10)), 2),
            (_threaded.iterstep(_iterables.flatten), 1),
            (Upload, 40),
        ], max_retries=1)

        pipeline.put_iterable(range(1000))
        # with self.assertRaises(FooException):
        pipeline.run()
        self.assertEquals(pipeline.count, 999, pipeline.count)

        pipeline = _threaded.Pipeline(
            [
                (Download, 10),
                (_threaded.funcstep(process), 1),
                (Upload, 40),
            ],
            max_retries=1,
            no_log_exceptions=(FooException,)
        )

        pipeline.put_all(range(1000))
        pipeline.finish()
        pipeline.run()

        self.assertEquals(pipeline.count, 999, pipeline.count)

    def test_meta_processing(self):
        class MetaIsDaHotShit(_threaded.AbstractStep):
            def process(self, entry):
                assert isinstance(entry, str)
                return entry

            def process_meta(self, entry):
                assert isinstance(entry, (int, long))
                return entry

        pipeline = _threaded.Pipeline([
            (MetaIsDaHotShit, 3),
        ], max_retries=0)

        pipeline.put("str")
        pipeline.put_meta(123)
        pipeline.put_meta(243)
        pipeline.put("str")
        pipeline.put_meta(325)
        pipeline.put("str")

        pipeline.finish()
        pipeline.run()
        self.assertEquals(pipeline.count, 6, pipeline.count)


if __name__ == '__main__':
    import nose
    nose.runmodule(argv=['-vv', '--with-doctest', '-a now'])
