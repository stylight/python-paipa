Paipa documentation - writing steps
===================================

Steps can be written in various ways to allow for better code re-use. You can
mix and match any of them within one pipeline.


Using a step class explicitly
-----------------------------

Using a step class is rather bothersome but can be desirable in some cases.

.. code:: python

    from paipa import AbstractStep, SkipEntry
    class DownloadUrl(AbstractStep):
        def process(self, item):
            if not item:
                raise SkipEntry
            return requests.get(item)

    pipeline = Pipeline([
        (DownloadUrl, 16),
    ])
    pipeline.add_iterable(lots_of_urls)
    pipeline.run()


This will download the items in `lots_of_urls` in 16 threads concurrently,
though if no URL is passed due to data-error, the entry will be skipped.


Using a generator (factory) as a step
-------------------------------------

A generator factory can be used as a step with a wrapper with is provided by
the library. The advantage of using a generator over a simple function as
shown below is that one can keep internal state. In this example we print
after every 1000 entries, which can't be done by using a `funcstep`.

.. code:: python

    from paipa import iterstep

    def download_url(iterator):
         for count, item in enumerate(iterator):
             if not item:
                  continue  # do not raise SkipEntry!
             if count % 1000 == 0:
                  print "Downloaded 1000 urls."
             yield requests.get(item)

    pipeline = Pipeline([
        (iterstep(download_url), 16),
    ])
    pipeline.add_iterable(lots_of_urls)
    pipeline.run()

This is functionally equivalent to the explicit class, but uses a generator
instead. These can be tested quite easily with unit-tests. In these cases a
subclass of `AbstractStep` is created on the fly and used in the pipeline.
Skipping entries must use the `continue` keyword because throwing a
`SkipEntry` exception will *abort the pipeline!*


Using a simple function as a step
---------------------------------

Similar to the `iterstep` case, a wrapper for simple functions is also
provided. This is functionally completely equivalent to the other examples,
though no internal state can be tracked, but throwing a `SkipEntry` exception
will work like in the class based approach.


.. code:: python

    from paipa import funcstep, SkipEntry

    # decorator which skips empty entries
    def skip_empty(func):
        def skipper(item):
            if not item:
                raise SkipEntry
            return func(item)
        return skipper

    pipeline = Pipeline([
        (funcstep(skipper(requests.get)), 16),
    ])
    pipeline.add_iterable(lots_of_urls)
    pipeline.run()


Also in this case, a subclass of `AbstractStep` is created on the fly and
used in the pipeline.
