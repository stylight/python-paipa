"""

"""
import collections as _collections
import logging as _logging
import threading as _threading
import time as _time

import six as _six
from six.moves import queue as _queue

from ..counter import Counter

from .queueing import Types, Entry, QueueWrapper
from .adapters import is_step, funcstep
from .steps import AbstractStep

logger = _logging.getLogger(__name__)
SiblingInfo = _collections.namedtuple("SiblingInfo", [
    "index", "storage", "threads"
])


class Pipeline(object):
    """
    A queue based threaded pipeline.

    Can be used to parallelize IO heavy code without having to think about
    the intricacies of threads. Guaranteed deadlock free.

    The pipeline object also works as a context manager. This starts the
    pipeline as a background thread and stops it again on context exit.

    """
    # pylint: disable = R0902
    # (too many instance attributes)

    def __init__(self, steps, in_queue=None, daemon=False,
                 quiet=False, fail_callback=lambda: None,
                 **kw):
        """
        Params affecting the Pipeline itself:

        :param steps:
            A list of (AbstractStep subclass, int) tuples.

        :param in_queue:
            An optional in_queue. If omitted an internal one is created and
            the adding of data has to go through the API of `Pipeline` itself.
            It is not recommended that you use this, as the API of stuff which
            gets sent through the queues may change.

        :param daemon:
            Shall all created threads be daemon threads or not? For more
            information about what this means, see:
            https://docs.python.org/2/library/threading.html#thread-objects

        :param quiet:
            Do not print progress/throughput notices.

        Vars passed on the the actual steps:

        :param fail_callback:
            A callable which gets called when something goes wrong. It takes
            no parameters.

        :param tracker:
            An object with tracking methods as attributes. The possible
            attributes are:
                * before_process
                * after_process

        """
        self.ok = True  # pylint: disable=invalid-name
        self._daemon = daemon
        self.options = kw
        self.steps = steps
        if in_queue is None:
            self._need_converter = False
            in_queue = _queue.Queue()
        else:
            self._need_converter = True

        if not isinstance(in_queue, QueueWrapper):
            in_queue = QueueWrapper(in_queue)

        self._in_queue = in_queue
        self.counter = Counter(show_every=1, quiet=quiet)
        self.count = 0
        self._got_entries = False
        self._fail_callback = fail_callback
        self._background_thread = None

    def put(self, element):
        """
        Put in a single element

        :Parameters:
          `element` : any
            The element to pass through the pipeline
        """
        self._in_queue.put(Entry(Types.regular, element, 0))

    def put_all(self, iterable):
        """
        Iterate over elements and pass each item through the pipeline

        The iterable is looped over eagerly.

        :Parameters:
          `iterable` : iterable
            List of elements to put in.
        """
        for element in iterable:
            self.put(element)

    def put_iterable(self, iterable, **kw):
        """
        Pass elements of an iterable through the pipeline

        The iterable is looped over lazily.
        """
        iterable = iter(iterable)
        self._got_entries = True
        self.steps.insert(0, (_source_step(lambda _: iterable), 1, kw))

    def put_meta(self, element):
        """
        Put in a single meta element

        :Parameters:
          `element` : any
            The element to pass through the pipeline
        """
        self._in_queue.put(Entry(Types.meta, element, None))

    def finish(self):
        """
        Finish the pipeline

        This passes a sentry entry down the queue, which tells the
        steps to finish.
        """
        logger.debug("Finishing queue")
        self._got_entries = True
        self._in_queue.put(Entry(Types.sentry, None, None))

    def __enter__(self):
        self.run_forever(background=True)
        return self

    # noinspection PyUnusedLocal
    def __exit__(self, exc_type, exc_value, exc_traceback):
        return self.stop()

    def run_forever(self, background=False):
        """ Run the pipeline, optionally in a background thread. """
        self._got_entries = True
        if background:
            assert self._background_thread is None, "already running"

            # pylint: disable = W0108
            # The lambda seems to help avoiding spurious exceptions at
            # interpreter shutdown
            self._background_thread = thread = _threading.Thread(
                name="background_loop", target=lambda: self.run()
            )
            logger.debug("Thread %r: starting", thread)
            thread.daemon = self._daemon
            thread.start()
        else:
            self.run()

    def stop(self):
        """Stop the background thread."""
        if self._background_thread is None:
            raise ValueError("No background thread running.")
        self.finish()  # Make sure the threads get shut down
        self._background_thread.join()
        logger.debug("Thread %r: stopped", self._background_thread)
        self._background_thread = None

    @property
    def alive(self):
        """ Shows the health status of the pipeline. """
        return not self._in_queue.closed

    def run(self):
        """ Main loop. Tend to the threads and stuff. """
        # pylint: disable = too-many-branches

        # local store, otherwise it will be gone during interpreter shutdown
        empty = _queue.Empty

        if not self._got_entries:
            raise ValueError("Pipeline must be filled with entries.")

        out_queue, threads = _combine_thread_pipeline_steps(
            self._in_queue,
            self._need_converter,
            self.steps,
            self.counter,
            self.options,
        )

        for thread in threads:
            logger.debug("Thread %r: starting", thread)
            thread.daemon = self._daemon
            thread.start()

        exceptions = []

        while True:
            _time.sleep(0.01)
            someone_is_alive = False
            for thread in threads:
                if thread.isAlive():
                    someone_is_alive = True
                    break

            try:
                while True:  # this loop is stopped by exceptions only
                    out = out_queue.get(block=False)
                    if out.type == Types.exception:
                        exceptions.append(out.payload)
                    elif out.type != Types.sentry:
                        self.count += 1
            except empty:
                pass

            if not someone_is_alive:
                break

        for thread in threads:
            thread.join()

        if exceptions:
            # noinspection PyBroadException
            try:
                # We provide this flag so that api consumers can use it to
                # determine if we exited in a planned or in an unplanned
                # manner and act accordingly.
                self.ok = False
                self._fail_callback()
            except Exception:  # pylint: disable=broad-except
                pass

            exc = exceptions[0]
            _six.reraise(*exc)

        self.counter.show()


def _combine_thread_pipeline_steps(in_queue, need_converter, pipeline_steps,
                                   counter, options):
    """ Construct the steps and connect them via queues """
    threads = []
    assert hasattr(in_queue, 'closed'), \
        "The in-queue needs a 'closed' attribute!"

    out_queue = in_queue

    pipeline_steps = tuple(pipeline_steps)
    if need_converter:
        pipeline_steps = ((_ConverterStep, 1),) + pipeline_steps

    for step_def in pipeline_steps:
        if len(step_def) == 2:
            (step, concurrency), step_options = step_def, {}
        elif len(step_def) == 3:
            step, concurrency, step_options = step_def
        else:
            raise ValueError("Invalid step definition: %r" % step_def)

        if not is_step(step):
            raise ValueError("Unknown step %r" % step)

        in_queue = out_queue
        out_queue = QueueWrapper(_queue.Queue())

        counter.init(step.__name__)

        # We need to let the threads know about each other so when
        # it comes to shutting them down they can wait until all their
        # siblings are done before giving the shutdown command to the
        # next threads.
        sibling_threads = []

        # Every step get's its own dictionary for cross-thread storage.
        sibling_storage = {}

        for index in range(concurrency):
            thread = step(
                in_queue,
                out_queue,
                counter=counter,
                sibling=SiblingInfo(
                    index,
                    sibling_storage,
                    sibling_threads,
                ),
                **options
            )

            if index == 0:
                thread.step_initialize()

            thread.initialize(**step_options)

            # As lists are mutable and variables are referenced by
            # memory-location every thread has the complete list.
            sibling_threads.append(thread)
            threads.append(thread)

    return out_queue, threads


def _source_step(func):
    """
    Transform a iterator factory to a pipeline source

    :Warning: The step ignores its in_queue and only writes to the out_queue.

    :Parameters:
      `func` : callable
        iterator

    :Return: New step class
    :Rtype: ``type``
    """
    class _SourceStep(AbstractStep):
        """
        Step implementation which emits values from an iterable

        The input queue is not checked at all.
        """
        # pylint: disable=abstract-method

        def process(self, entry):
            raise NotImplementedError("Never called.")

        def _loop(self):
            # noinspection PyBroadException
            try:
                for value in self.process(None):
                    if self._out_queue.closed:
                        self._shutdown_step()
                        break
                    else:
                        self._pass_on(Entry(Types.regular, value, 0))
            except Exception:  # pylint: disable=broad-except
                self._pass_fail()

            self._shutdown_step()

    return funcstep(func, base=_SourceStep)


class _ConverterStep(AbstractStep):
    """ Step implementation which converts raw inputs to wrapped outputs """

    def process(self, entry):
        return entry

    def _loop(self):
        """ Main run loop """
        # local store, otherwise it will be gone during interpreter shutdown
        empty = _queue.Empty
        in_queue, out_queue = self._in_queue, self._out_queue
        while True:
            try:
                entry = in_queue.get(timeout=0.5)
            except empty:
                continue

            if not out_queue.closed:
                if not isinstance(entry, Entry):
                    entry = Entry(Types.regular, entry, 0)
                elif entry.type == Types.sentry:
                    self._shutdown_step()
                    break

                self._pass_on(entry)
