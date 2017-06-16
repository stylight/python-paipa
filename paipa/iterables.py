import collections as _collections
import itertools as _itertools

import six as _six


def flatten(gen):
    """Flatten an iterable.

    >>> flat = flatten([(1, 2, 3), [4, 5, 6], range(7, 10)])
    >>> list(flat)
    [1, 2, 3, 4, 5, 6, 7, 8, 9]

    """
    return _itertools.chain.from_iterable(gen)


def recursive_flatten(elements):
    """Flatten an iterable.

    This implementation is slower than `flatten` but works recursively.

    >>> gen = recursive_flatten([1, [2, [3, [lambda blah: blah]]]])
    >>> l = list(gen)
    >>> l[:3]
    [1, 2, 3]
    >>> import types
    >>> assert type(l[-1]) == types.FunctionType

    """
    gen = iter(elements)
    for element in gen:
        if is_iterable(element) and not isinstance(element, _six.string_types):
            for element in recursive_flatten(element):
                yield element
        else:
            yield element


def is_iterable(testee):
    """Check if a value is iterable.

    This does no type comparisons. Note that strings are iterables too!

    >>> is_iterable([])
    True

    >>> is_iterable("Hello World!")
    True

    >>> is_iterable(False)
    False

    """
    try:
        iter(testee)
        return True
    except TypeError:
        return False


def chunk(chunk_size=32):
    """Chunk `chunk_size` elements of an iterable.

    Every yielded chunk will be a list. The last chunk may contain less
    elements than `chunk_size`.

    >>> chunker = chunk(32)
    >>> gen = chunker(range(64))
    >>> assert len(list(gen)) == 2

    >>> chunker = chunk(3)
    >>> list(chunker([1,2,3,4,5,6,7,8]))
    [[1, 2, 3], [4, 5, 6], [7, 8]]

    """
    if chunk_size < 1:
        raise ValueError("chunk_size can not be less than 1, got %d" %
                         chunk_size)
    key = lambda x, s=chunk_size: x[0] // s

    def chunker(gen):
        """ Actual chunker """
        for _, grouped_chunk in _itertools.groupby(enumerate(gen), key=key):
            yield [entry[1] for entry in grouped_chunk]

    return chunker


def consume(iterator, n=None):
    """Advance the iterator n-steps ahead. If n is none, consume entirely.

    :param iterator:
        Some iterable.

    :param n:
        Optionally, how many entries to consume from the iterator.

    """
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        _collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(_itertools.islice(iterator, n, n), None)
