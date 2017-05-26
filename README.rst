paipa - the threaded pipelining framework
=========================================

Python pipeline library developed by `STYLIGHT <http://www.stylight.de/>`_.

.. image:: https://travis-ci.org/stylight/python-paipa.svg?branch=master
    :target: https://travis-ci.org/stylight/python-paipa


Installation
------------

    pip install paipa

Overview
--------

What it does:

 - process stuff one step at a time
 - allows class based and function based steps
 - can scale steps independent of each other (manually)
 - don't ever do deadlocks
 - never expose the developer to the concept of a thread
   (if she doesn't like to)
 - run in finite batches where all threads are terminated at the end
 - run in continuous mode while being fed through a queue
 - automatically rate limit each step to minimize memory usage
 - terminate the pipeline in case of an Exception and propagate the error
   to the developer

What it explicitly doesn't do (if it doesn't, it's not a bug!):

 - pipelines with multiple different parents. Multiple parents of
   the same type are handled automatically though.
 - auto-scale threads
 - bake bread

What it shouldn't do (if it does, it's a bug!):

 - confuse the user/developer
 - hang on termination
 - hog resources


Features
--------

The lib allows for threaded pipelines as well as so-called co-routine
pipelines. The main use-case is limiting peak memory usage when doing complex
operations on large-ish data-sets.

    >>> pipeline = paipa.Pipeline(
    ...     (DownloadImage, 4),
    ...     (StoreDatabase, 1),
    ... )
    >>> pipeline.run()

This example will create 5 threads, 4 for downloading images, one for storing
stuff to the database. The ouputs of all `DownloadImage` steps will be forwared
to the one `StoreDatabase` thread via a `Queue`.

Thread startup and tear-down is handled by the library and doesn't concern the
programmer at all. All (known) failure cases lead to either a re-spawning of the
failed thread or a controlled shutdown of the system. In no case the system
should block and do nothing, if it does then it's definitely a bug and needs
to be reported.

Pipeline ingestion can be done via a separate thread or by consuming an
iterable. In the case of using an iterable, an ingestion thread is created
which consumes the iterable in a controled manner.

The whole pipeline can also be run in the background like this:

    >>> pl = pipeline.run_forever(background=True)
    >>> # do some other stuff
    >>> pl.stop()  # this waits for the system to complete and do a shutdown


Co-Routine Pipelines
--------------------

    >>> def remove_odd(iterable):
    ...     for entry in iterable:
    ...         if entry % 2 == 0:
    ...             yield entry
    >>> steps = [remove_odd] # Arbitrary many steps supported
    >>> gen = combine_pipeline(range(100), steps)
    >>> print(sum(gen))
    2450

This will create nested generators which do the relevant processing. The
individual steps only need to support the iterator protocol and don't
necessarily need to be generators. Memory usage may make using generators
appealing though.
