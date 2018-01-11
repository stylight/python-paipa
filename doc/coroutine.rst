paipa - How to write a co-routine pipeline
==========================================

Index
-----

 - Threaded Pipeline
     - `Introduction <./introduction.rst>`__
     - `More ways to use pipelines <./ingestion.rst>`__
     - `How to write steps <./steps.rst>`__
 - Coroutine Pipeline
     - How to write a co-routine pipeline

What is it?
-----------

A co-routine pipeline is simply a bunch of nested generator calls like this.


.. code:: python

    def a(iterator):
        for entry in iterator:
            yield 'Hel' + entry

    def b(iterator):
        for entry in iterator:
            yield 'lo ' + entry

    print list(a(b(['World!'])))[0]  # Prints "Hello World!"


For single threaded code with maximum runtime efficiency while still being
able to shift around pipeline steps easily, ``generator pipelines`` can be
used. Because these components can be written easily without much boilerplate
code they are convenient in a lot of ETL or data processing tasks.

They work a bit differently like the threaded pipelines but adapter steps to
and from each system are provided.

Simple example
--------------

.. code:: python

    def remove_odd(iterable):
        for entry in iterable:
            if entry % 2 == 0:
                yield entry

    # Arbitrary many steps supported
    steps = [
        remove_odd,
    ]
    gen = combine_pipeline(range(100), steps)
    print(sum(gen))  # will print 2450

This will create nested generators which do the relevant processing. The
individual steps only need to support the iterator protocol and don't
necessarily need to be generators. Memory usage may make using generators
appealing though.

More involved example
---------------------

The following example loads all products from a database table, filters them
for availability (for illustration purposes), then grouped in batches of 2048
entries which are then sent away over the network. The nice thing about this
method is that everything in ``itertools`` can be used easily. Grouping,
filtering, etc. is very natural that way.


.. code:: python

    def only_available(products):
        for product in products:
            if not product['available']:
                continue
            yield product

    def send_in_batch(chunks):
        url = get_config()['url']  # some hypothetical config
        for chunk in chunks:
            send_chunk(url, chunk)  # To some microservice perhaps? We're hip!
            yield chunk


    def get_products():
        return db.query("select * from products")

    steps = [
        only_available,
        paipa.chunk(2048),
        store_in_batch,
        flatten,  # flatten it out again for subsequent steps perhaps.
    ]

    pipeline = paipa.combine_pipeline(get_products(), steps)
    paipa.consume(pipeline)

Debugging pipelines
-------------------

This library also comes with a helpful debugging system for co-routine based
pipelines. You can use it like this:

.. code:: python

    import logging
    import time

    import paipa

    logging.basicConfig()

    def cast(_type):
        def caster(iterator):
            for entry in iterator:
                yield _type(entry)
        return caster

    def flip(iterator):
        for entry in iterator:
            yield entry[::-1]

    def flap(iterator):
        for entry in iterator:
            time.sleep(0.001)
            yield [entry]

    def flatten(iterator):
        for entry in iterator:
            yield entry[0]

    steps = [cast(str), flip, flap, flatten]

    pipeline = paipa.combine_pipeline(xrange(10000, 19999), steps,
                                      debugger=paipa.PipelineRuntimeDebugger())
    paipa.consume(pipeline)


This will yield the following log-output. It tracks runtime, throughput, cpu
usage and memory growth for each of the stacked co-routines. It will log to
stderr every few seconds and once at the end.

.. code::

    INFO:paipa.debugger:--------------------
    INFO:paipa.debugger:> list   : count: 3647 runtime: 0.05 78335.37/s utime: 0.02 stime: 0.00 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> caster : count: 3647 runtime: 0.06 58242.02/s utime: 0.05 stime: 0.00 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flip   : count: 3647 runtime: 0.06 61024.43/s utime: 0.14 stime: 0.00 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flap   : count: 3647 runtime: 4.10   889.67/s utime: 0.24 stime: 0.05 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flatten: count: 3647 runtime: 0.08 45269.69/s utime: 0.06 stime: 0.01 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:--------------------
    INFO:paipa.debugger:> list   : count: 7201 runtime: 0.10 74465.44/s utime: 0.10 stime: 0.01 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> caster : count: 7201 runtime: 0.13 55556.71/s utime: 0.08 stime: 0.03 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flip   : count: 7201 runtime: 0.12 58428.67/s utime: 0.27 stime: 0.00 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flap   : count: 7201 runtime: 8.13   885.65/s utime: 0.50 stime: 0.09 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flatten: count: 7201 runtime: 0.17 42884.64/s utime: 0.17 stime: 0.01 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:--------------------
    INFO:paipa.debugger:> list   : count: 10000 runtime:  0.13 75599.61/s utime: 0.11 stime: 0.01 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> caster : count: 10000 runtime:  0.18 56526.86/s utime: 0.11 stime: 0.04 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flip   : count: 10000 runtime:  0.17 59096.59/s utime: 0.32 stime: 0.01 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flap   : count: 10000 runtime: 11.29   885.92/s utime: 0.74 stime: 0.11 q: 0 q/e: 0.00 rss: 0.00
    INFO:paipa.debugger:> flatten: count: 10000 runtime:  0.23 43503.96/s utime: 0.22 stime: 0.03 q: 0 q/e: 0.00 rss: 0.00


The most interesting number in this example is of course the one counting the
throughput in entries/second. The ``time.sleep`` call in ``flap`` is easily
visible in the stats.

The ``PipelineRuntimeDebugger`` instance can also receive so called
"Reporters" which will take the stats from the debugger and either print them
or send it off to some reporting solution. A console-logging Reporter is
included with this library, but something like for example a DataDog reporter
can be written in about 10 lines of code.
