#!/usr/bin/env python
# encoding: utf-8
"""
threaded pipelining framework

What it does:

 - process stuff one step at a time
 - allows class based and function based steps
 - can scale steps independent of each other (manually)

What it explicitly doesn't do:

 - diamond-structured pipelines
 - auto-scale threads
"""

import abc as _abc
import collections as _collections
import logging as _logging
import sys as _sys
import threading as _threading
import time as _time

# pylint: disable=import-error
if _sys.version_info > (3,):
    import queue as _queue
else:
    import Queue as _queue
# pylint: enable=import-error

import enum as _enum
import six as _six

from .counter import Counter


logger = _logging.getLogger(__name__)


class SkipEntry(Exception):
    """Exception to notify pipeline system to skip a particular entry."""
    pass


if 1:  # this is to restrict pylint's scope.
    # pylint: disable = invalid-name
    Types = _enum.IntEnum('Types', ['sentry', 'exception', 'regular', 'meta'])
    Entry = _collections.namedtuple("Entry", ["type", "payload", "retries"])
    SiblingInfo = _collections.namedtuple("SiblingInfo", [
        "index", "storage", "threads"
    ])


class AbstractStep(_threading.Thread):
    """
    Abstract threaded pipeline step.

    Subclass this class to create your own threaded pipeline step.

    How to use it
    -------------

    A concrete step has to inherit from this AbstractStep. The pipeline gets a
    list of step classes (or factories) with concurrency and option info as
    input, instantiates them and connects them using queues.

    Your step MUST provide a `process` method, which gets fed a single item
    from the input queue and is expected to return a resulting item, which
    then is put into the output queue.

    Override the following hook methods for customization:

    ``step_initialize``
        Called once per step, after the first step-thread instance has been
        created.

    ``initialize``
        Called once per thread, after the thread instance has been created.
        Called after ``step_initialize``.

    ``thread_initialize``
        Called once per thread, after the threat has begun running.

    ``thread_shutdown``
        Called once per thread after a step-thread has been finished
        processing right before it's shut down

    ``step_shutdown``
        Called once per step after the last step-thread has been finished
        processing, right before it's shut down. Called after thread_shutdown

    ``in_queue_empty``
        Called every time when we want an item from the in-queue and it's
        empty

    ``_pass_on``
        Only override when needed. The method is responsible for passing stuff
        down to the output queue.

    ``_loop``
        Only override when needed. This is the main thread loop. This one
        actually gets an item from the in-queue passes it to process() and
        puts the result into the out-queue.


    :IVariables:
      `_counter` : counter
        Counter object

      `threshold` : ``int``
        Max queue size for the output queue. The step is stalled until the
        output queue less entries or is closed.

      `_in_queue` : `_QueueWrapper`
        input queue

      `_out_queue` : `_QueueWrapper`
        output queue

      `sibling` : `SiblingInfo`
        Sibling info, containing the sibling index of this step (starting with
        0), the cross-sibling storage and references to all sibling threads.

      `_max_retries` : ``int``
        Maximum number of retries.

      `done` : ``bool``
        True, if the step is finished and shutdown

      `options` : ``dict``
        The optioal step options
    """
    __metaclass__ = _abc.ABCMeta

    def __init__(self, in_queue, out_queue, sibling, counter, max_retries=10,
                 threshold=64, no_log_exceptions=(), **kw):
        """
        Initialization

        :Parameters:
          `in_queue` : `_QueueWrapper`
            Input queue for this step

          `out_queue` : `_QueueWrapper`
            Output queue for this step

          `sibling` : `SiblingInfo`
            Sibling info

          `counter` : counter
            Counter object

          `max_retries` : ``int``
            Maximum number of retries before the processing of one item is
            recognized as failed

          `no_log_exceptions` : iterable
            Exception classes which are not logged (raised by process())

          `kw` : ``dict``
            extra options for this step
        """
        super(AbstractStep, self).__init__()
        self._threshold = threshold
        self._counter = counter
        self._in_queue = in_queue
        self._out_queue = out_queue
        self.sibling = sibling

        # Error handling
        self._max_retries = max_retries

        # Used for shutdown purposes.
        self.done = False

        # Subclasses can use this dictionary to access non-standard keyword
        # parameters.
        self.options = kw

        self._timeout = None
        self._size = None
        self._chunk = None
        self._last_sent = None

    def step_initialize(self):
        """ Only called on one instance of a Step. """
        pass

    def initialize(self):
        """ Called on each instance. """
        pass

    def thread_initialize(self):
        """ Called in the threads context once when it starts """
        pass

    def thread_shutdown(self):
        """ Called in the threads context when it shuts down """
        pass

    def step_shutdown(self):
        """ Called when the last thread of a step is shutting down """
        pass

    def _shutdown_step(self):
        """
        Signal the shutdown of siblings and subsequent steps.

        First it is checked that all siblings are shut down, after that the
        shutdown request is passed on the subsequent step.
        """
        self.done = True
        logger.debug("Thread %r: Shutdown requested", self)

        # If all siblings are done, leave a shutdown message for the next step
        # otherwise leave it for the siblings
        sentry = Entry(Types.sentry, None, None)
        all_done = all(sibling.done for sibling in self.sibling.threads)
        if all_done:
            logger.debug("Thread %r: All done, passing on to next step", self)
            self._pass_on(sentry)
        else:
            logger.debug("Thread %r: Passing on to sibling", self)
            self._in_queue.put(sentry)

        self.thread_shutdown()
        if all_done:
            self.step_shutdown()

    def _pass_on(self, result):
        """
        Enqueue the result as a work-item for the next step

        To reduce memory consumption we wait for the subsequent steps to
        finish the processing of their input queue, before putting new
        stuff in. This way we reduce the number of objects in the queues
        at any one time. In observation this has the effect of a rate-
        limit on the earlier steps so the later ones can keep up with the
        amount of work.
        """
        counter = self._counter
        out_queue = self._out_queue
        while True:
            if out_queue.closed:
                # There's no point in trying to continue at this point. The
                # subsequent thread must have died, so we don't try to write
                # any more.
                break
            elif out_queue.qsize() < self._threshold:
                counter.gauge(self.__class__.__name__ + " in",
                              self._in_queue.qsize())
                counter.count(self.__class__.__name__)
                out_queue.put(result)
                break
            else:
                _time.sleep(.01)

    def in_queue_empty(self):
        """ Will be run when the in_queue of this step is empty. """
        pass

    def run(self):
        """ Thread API - main entry point """
        self.thread_initialize()
        self._loop()

    def reenqueue(self, entry):
        """
        Re-enqueue an item

        :Parameters:
          `entry` : any
            Entry to re-enqueue
        """
        self._in_queue.put(Entry(Types.regular, entry, 0))

    def _retry(self, entry):
        """
        Re-enqueue an entry up to self._max_retries times

        :Parameters:
          `entry` : `Entry`
            Entry to possibly retry

        :Return: Have we enqueued a retry?
        :Rtype: ``bool``
        """
        if self._max_retries and entry.retries <= self._max_retries:
            self._in_queue.put(Entry(entry[0], entry[1], entry[2] + 1))
            return True
        return False

    def _loop(self):
        """ Main run loop """
        # pylint: disable = too-many-branches, too-many-statements

        # local store, otherwise it will be gone during interpreter shutdown
        empty = _queue.Empty
        in_queue, out_queue = self._in_queue, self._out_queue
        while True:
            if out_queue.closed:
                # Something bad happened to one of the subsequent steps, as
                # it closed it's in_queue. We now have to signal all the
                # precursor steps to shut down as well, because they would
                # just starve and do nothing because of the rate limiting.
                # To do this, we close our in_queue (their out_queue) so the
                # other steps will also hit this code and propagate it upwards.
                logger.debug("Thread %r: closing in_queue", self)
                in_queue.closed = True
                self._shutdown_step()
                break

            try:
                entry = in_queue.get(timeout=0.5)
            except empty:
                self.in_queue_empty()
                continue

            if entry.type == Types.sentry:
                self._shutdown_step()
                break
            elif entry.type == Types.exception:
                self._pass_on(entry)
                continue
            elif entry.type == Types.meta:
                try:
                    result = self.process_meta(entry.payload)
                    self._pass_on(Entry(Types.meta, result, None))
                    continue
                except SkipEntry:
                    continue
                except Exception:  # pylint: disable=broad-except
                    self._pass_fail()
                    continue

            # pylint: disable = broad-except
            try:
                result = self.process(entry.payload)
            except SkipEntry:
                continue
            except Exception:
                if self._max_retries:
                    retried = self._retry(entry)
                    if retried:
                        logger.error(
                        "Error in Step.process (retrying...)", exc_info=True
                        )
                    else:
                        logger.error("Error in Step.process", exc_info=True)
                        # TODO: close inqueue? Pass exception?
                        # self._pass_fail()
                    continue
                else:
                    self._pass_fail()


            else:
                self._pass_on(Entry(Types.regular, result, 0))

    def _pass_fail(self):
        """ Pass the current exception down the pipeline """
        exc_info = _sys.exc_info()
        logger.debug("Thread %r: passing on %r", self, exc_info[:2])
        self._pass_on(Entry(Types.exception, exc_info, None))

    def process_meta(self, entry):  # pylint: disable=no-self-use
        """ Called with meta entries, subclasses can implement this """
        return entry

    @_abc.abstractmethod
    def process(self, entry):
        """ Main step function, subclasses must implement this """
        raise NotImplementedError


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


class TimedChunk(AbstractStep):
    """
    Intermediate step which chunks incoming entries and flushes them out
    after a threshold or timeout.

    >>> import time
    >>> result = []
    >>> def append_result(xxx):
    ...    result.append(xxx)
    >>> def crash_when_17(iterator):
    ...     for chunk in iterator:
    ...         if chunk == [17]:
    ...            raise RuntimeError("Argh!")
    ...         yield chunk
    >>> steps = [(TimedChunk, 1, dict(timeout=0.5, size=5)),
    ...          (iterstep(crash_when_17), 1),
    ...          (funcstep(append_result), 1)]

    >>> pipeline = Pipeline(steps)
    >>> for ixx in range(10):
    ...    pipeline.put(ixx)
    >>> pipeline.finish()
    >>> pipeline.run()
    >>> result
    [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]

    >>> result = []
    >>> pipeline = Pipeline(steps)
    >>> pipeline.run_forever(background=True)
    >>> pipeline.put(1)
    >>> time.sleep(2)
    >>> pipeline.put(2)
    >>> assert pipeline.alive
    >>> time.sleep(2)

    >>> pipeline.put(17)
    >>> time.sleep(2)

    At this point the pipeline is no longer usable, because at least one
    iterstep irrecoverable crashed.

    >>> assert not pipeline.alive

    >>> pipeline.finish()
    >>> time.sleep(1)
    >>> result
    [[1], [2]]
    """

    def initialize(self, timeout=5, size=64):
        # pylint: disable=arguments-differ
        self._timeout = timeout
        self._size = size
        self._chunk = []
        self._last_sent = _time.time()

    def process(self, entry):
        return entry

    def _pass_on(self, entry):
        pass_on = super(TimedChunk, self)._pass_on

        def pass_chunk():
            """ Pass current chunk """
            if self._chunk:
                chunk, self._chunk = self._chunk, []
                pass_on(Entry(Types.regular, chunk, 0))
                self._last_sent = _time.time()

        if entry.type in (Types.sentry, Types.meta):
            pass_chunk()
            pass_on(entry)
        elif entry.type == Types.exception:
            pass_on(entry)
        else:
            self._chunk.append(entry.payload)
            if len(self._chunk) >= self._size:
                pass_chunk()

    def in_queue_empty(self):
        if self._chunk and (_time.time() - self._last_sent) > self._timeout:
            logger.debug("Passed %d seconds timeout. Flushing chunker %s.",
                         self._timeout, self.__class__.__name__)
            chunk, self._chunk = self._chunk, []
            super(TimedChunk, self)._pass_on(Entry(Types.regular, chunk, 0))
            self._last_sent = _time.time()


def funcstep(func, base=AbstractStep):
    """
    Transform a filtering function to a pipeline step

    This function dynamically creates a new step class, iniheriting from base.
    `func` will become the step's process method.

    :Parameters:
      `func` : callable
        The filter function

    :Return: New step type
    :Rtype: ``type``
    """
    try:
        name = func.__name__
    except AttributeError:
        name = type(func).__name__
    return type(name, (base,), dict(process=staticmethod(func)))


class AbstractIterStep(AbstractStep):
    """
    Step type converting an iterator function into a pipeline step

    The iterator function gets an iterator, which pulls items from the
    in-queue. The items of the output iterator are pushed into the
    out-queue.
    """

    def _loop(self):
        def pull():
            """ Pull the queue """
            # local store, otherwise it will be gone during interpreter
            # shutdown
            empty = _queue.Empty

            while True:
                if self._out_queue.closed:
                    self._shutdown_step()
                    break

                try:
                    entry = self._in_queue.get(block=False)
                except empty:
                    _time.sleep(.1)
                    continue

                if entry.type == Types.sentry:
                    raise StopIteration
                elif entry.type == Types.exception:
                    logger.debug("Thread %r: passing on exception", self)
                    self._pass_on(entry)
                elif entry.type == Types.meta:
                    self._pass_on(entry)
                else:
                    yield entry.payload

        try:
            iterator = self.process(pull()) or []
            for value in iterator:
                self._pass_on(Entry(Types.regular, value, 0))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "Thread %r: self.process failed. Closing in_queue", self
            )
            logger.error(
                "Thread %r: %s", self, exc)
            self._in_queue.closed = True
            self._pass_fail()

        self._shutdown_step()



def iterstep(func):
    """
    Transform a iterator/generator filter to a pipeline step

    :Parameters:
      `func` : callable
        iterator

    :Return: New step class
    :Rtype: ``type``
    """
    # pylint: disable = W0223, R0912

    return funcstep(func, base=AbstractIterStep)


def _sourcestep(func):
    """
    Transform a iterator factory to a pipeline source

    :Warning: The step ignores its in_queue and only writes to the out_queue.

    :Parameters:
      `func` : callable
        iterator

    :Return: New step class
    :Rtype: ``type``
    """
    class SourceStep(AbstractStep):
        """
        Step implementation which emits values from an iterable

        The input queue is not checked at all.
        """
        # pylint: disable=abstract-method

        def _loop(self):
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

    return funcstep(func, base=SourceStep)


def is_step(step):
    """
    >>> is_step(AbstractStep)
    True

    >>> is_step(5)
    False

    >>> is_step(range(1))
    False

    >>> is_step([])
    False
    """
    try:
        return issubclass(step, AbstractStep)
    except TypeError:
        return False


class _QueueWrapper(object):
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
        return super(_QueueWrapper, cls).__new__(cls)

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


def _combine_thread_pipeline_steps(in_queue, need_converter, pipeline_steps,
                                   counter, options):
    """ Construct the steps and connect them via queues """
    threads = []
    assert hasattr(in_queue, 'closed'),\
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
        out_queue = _QueueWrapper(_queue.Queue())

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
                 quiet=False, fail_callback=lambda: None, **kw):
        self.ok = True  # pylint: disable=invalid-name
        self._daemon = daemon
        self.options = kw
        self.steps = steps
        if in_queue is None:
            self._need_converter = False
            in_queue = _queue.Queue()
        else:
            self._need_converter = True

        if not isinstance(in_queue, _QueueWrapper):
            in_queue = _QueueWrapper(in_queue)

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
        self.steps.insert(0, (_sourcestep(lambda _: iterable), 1, kw))

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
            try:
                # We provide this flag so that api consumers can use it to
                # determine if we exited in a planned or in an unplanned
                # manner and act accordingly.
                self.ok = False
                self._fail_callback()
            except:  # noqa pylint: disable=bare-except
                pass

            exc = exceptions[0]
            _six.reraise(*exc)

        self.counter.show()
