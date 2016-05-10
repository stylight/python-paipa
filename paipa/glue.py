#!/usr/bin/env python
# encoding: utf-8
"""
Tornado pipeline application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

"""

import logging as _logging
import signal as _signal
import sys as _sys
if _sys.version_info > (3,):
    import queue as _queue
else:
    import Queue as _queue

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado as _tornado
del tornado

from . import threaded as _threaded


logger = _logging.getLogger(__name__)


_SIGNAL_NAMES = dict(
    (k, v) for v, k in vars(_signal).items() if v.startswith('SIG')
)


class PipelineApplication(_tornado.web.Application):

    def __init__(self, *args, **kw):
        _logging.basicConfig(level=_logging.INFO)
        _logging.getLogger("core").setLevel(_logging.INFO)

        self.in_queue = None

        self._pipeline = None
        self._pipeline_steps = kw.pop('pipeline')

        self._ioloop = None

        routes = (args[0]
                  if args else kw.pop('routes'))
        super(PipelineApplication, self).__init__(routes, *args, **kw)

    def alive(self):
        """Show the health status of the pipeline-application """
        return self._pipeline.alive

    def start(self, port):
        """Start the application on the specified port.

        We do a lot of seemingly scary stuff in here, but don't worry, it'll
        work out.
        """
        io_loop = _tornado.ioloop.IOLoop.instance()
        self._ioloop = io_loop
        server = _tornado.httpserver.HTTPServer(self)

        def shutdown_loop():
            """
            Tell tornado to shut itself down... asynchronously of course.
            """
            logger.info('Stopping http server (accepting no new connections)')
            server.stop()

            def stop_loop():
                """Stop the loop.
                """
                # pylint: disable=no-member,protected-access
                if io_loop._callbacks or io_loop._timeouts:
                    logger.debug("Work to do. Will try again.")
                    io_loop.add_callback(stop_loop)
                else:
                    logger.info('Stopping IOLoop')
                    io_loop.stop()

            stop_loop()

        def shutdown_sig_handler(sig, _):
            """Receive a signal and pass off the shutdown callback to tornado.
            """
            logger.warning(
                'Caught signal: %s (%s)', sig, _SIGNAL_NAMES.get(sig, sig)
            )
            loop = _tornado.ioloop.IOLoop.instance()
            loop.add_callback(shutdown_loop)

        _signal.signal(_signal.SIGTERM, shutdown_sig_handler)
        _signal.signal(_signal.SIGINT, shutdown_sig_handler)

        server.listen(port)
        logger.info("HTTP server listening on port %d", port)

        self.in_queue = in_queue = _queue.Queue()

        self._pipeline = _threaded.Pipeline(
            self._pipeline_steps,
            quiet=True,
            in_queue=in_queue,
            fail_callback=shutdown_loop,
        )
        self._pipeline.run_forever(background=True)
        logger.info("Pipeline started")

        io_loop.start()

        logger.info("Stopping pipeline")
        self._pipeline.stop()
        logger.info("Pipeline stopped")

        _signal.signal(_signal.SIGTERM, _signal.SIG_DFL)
        _signal.signal(_signal.SIGINT, _signal.SIG_DFL)

        _sys.exit(int(not self._pipeline.ok))
