import functools as _functools
import logging as _logging
import types as _types

import six as _six

from .counter import Counter
from .iterables import recursive_flatten

logger = _logging.getLogger(__name__)


class PipelineStep(object):

    # noinspection PyMethodMayBeStatic
    def process(self, iterator):
        return iterator

    def __call__(self, iterator):
        return self.process(iterator)


def identity_step(iterator):
    """A pipeline-step which does nothing."""
    return iterator


def entry_counter(iterator):
    counter = Counter(show_every=1)
    counter.init("products")
    for entry in iterator:
        counter.count("products")
        yield entry
    counter.show()


def defer_call(step_function):
    """Proxy argument passing of iterators.

    This decorator passes the argument signature on down the
    iterator pipeline, and the result back up.

    """
    def wraps(callable_thing):
        if isinstance(callable_thing, _types.FunctionType):
            return _functools.wraps(callable_thing)
        else:
            assert _six.callable(callable_thing)
            return identity_step

    @wraps(step_function)
    def wrapper(iterator_factory):
        @wraps(iterator_factory)
        def wrap(*args, **kw):
            return step_function(iterator_factory(*args, **kw))
        return wrap
    return wrapper


def combine_pipeline(source, pipeline, debugger=None):
    """Build the "pipeline" generator.

    Optionally a debugging object may be passed in.

    >>> def step(iterator):
    ...     for entry in iterator:
    ...         yield entry

    >>> def remover(iterator):
    ...     for count, entry in enumerate(iterator):
    ...         if count % 2 == 0:
    ...             yield entry

    >>> class Identity(PipelineStep):
    ...     def process(self, iterator):
    ...         for entry in iterator:
    ...             yield entry
    >>> assert hasattr(Identity, '__call__')

    It's possible for iterator-factories to return lists of iterators. These
    will then be flattened into the pipeline in the order of occurrence.

    >>> pipeline = [step, [remover, Identity()], step]

    Example: We construct 1000 elements and pass it through our pipeline. As
    the remover removes every second element we can expect to have only half
    as many elements out than we sent in.

    >>> gen = combine_pipeline(range(1000), pipeline)
    >>> assert len(list(gen)) == 500

    The `source` can also be a callable. If it is, `combine_pipeline` will also
    return a callable, which - when called - will pass the supplied arguments
    on to the source callable.

    >>> gen = combine_pipeline(range, pipeline)
    >>> assert len(list(gen(1000))) == 500

    """
    def identity(x):
        return x

    if debugger is not None:
        head = debugger.head
        tail = debugger.tail
        track = debugger.track
        report = debugger.report
    else:
        head = tail = track = report = identity

    gen = source
    if _six.callable(gen):
        # Source is (hopefully) an iterator-factory, so we need
        # to convert all our steps into iterator-factories
        # as well, to enable passing on the arguments passed
        # to our collapsed pipeline.
        defer = defer_call
    else:
        defer = identity

    track = defer(track)
    head = defer(head)
    tail = defer(tail)
    report = defer(report)

    gen = head(gen)

    for step in recursive_flatten(pipeline):
        gen = defer(step)(track(gen))

    return report(tail(track(gen)))
