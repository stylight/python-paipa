Coroutine pipelines (aka generator pipelines)
=============================================

What is it?
-----------

A coroutine pipeline is simply a bunch of nested generator calls like this.


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
