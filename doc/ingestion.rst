Paipa documentation - Ingestion
===============================

Items can be ingested into the pipeline in various ways and can be
grouped by use-case and data-size. For the examples we have a fictional case
of URLs we need to download and store. We'll use 128 threads for downloading
and 16 threads for saving it to disk. The pipeline looks like this:

**How it works in a nutshell**

    The output of the previous step is the input of the next step.


For detailed instructions on how to build steps `look here <./steps.rst>`__.

.. code:: python

    import paipa

    def download_url(url):
        resp = requests.get(url)
        return resp

    def save_to_disk(resp):
        filename = make_filename(resp)
        with open(filename, 'w') as f:
             f.write(resp.content)
        # We have no subsequent step, so we don't really need to return
        # anything, but returning the filename for some indexing step could
        # be interesting.
        return filename

    pipeline = paipa.Pipeline(
        (paipa.funcstep(download_url), 128),
        (paipa.funcstep(save_to_disk), 16),
    )

Repeat, this example spawns 128 download threads and 16 saving threads. All
urls fed to this system will first be downloaded and the response forwarded
to the saving threads.


Putting in everything at once
-----------------------------

The simplest way is just to put the items in at the beginning and then start
the pipeline - and thus the processing.

.. code:: python

    # put in single entry
    pipeline.put(url)
    # put in multiple entries
    pipeline.put_all(list_of_urls)
    # tell the pipeline that no further entries are to be expected.
    pipeline.finish()
    pipeline.run()  # will block until everything done

The memory usage of this will be determined on how many entries
have been put in. Everything will be in the input-queue and thus in RAM.
Be aware of that.

Streaming an iterable into the pipeline
---------------------------------------

To limit memory usage, iterators (e.g. generators) can be consumed in the
background on a pull basis. The pipeline will pull new entries if the
input-queue will run low. In this case a new thread is created - called
the "source step" - which will feed the pipeline in the background.

.. code:: python

    # a call to finish is not needed here. If the iterator runs out of
    # items, the pipeline will start to shutdown from the source step.
    pipeline.put_iterable(generator_of_urls)
    pipeline.run()  # will block until everything done


Streaming and running the pipeline in the background
----------------------------------------------------

The pipeline can be run in the background as well, either explicitly or by
using it as a context-manager.

.. code:: python

    # This will spawn a thread to run the whole thing in the background.
    pipeline.put_iterable(some_stuff)
    with pipeline:
         twiddle_thumbs()
         twiddle_thumbs_some_more()
    # If we end up here, we can be sure that everything in pipeline has
    # been processed without errors.
    send_email()

This is completely equivalent to:

.. code:: python

    pipeline.put_iterable(some_stuff)
    # This will spawn a thread to run the whole thing in the background.
    pipeline.run_forever(background=True)
    twiddle_thumbs()
    twiddle_thumbs_some_more()
    pipeline.stop()
    # If we end up here, we can be sure that everything in pipeline has
    # been processed without errors.
    send_email()

Checking in on the pipeline when run in the background
------------------------------------------------------

During the background run the health of the pipeline can be checked by
accessing the ``alive`` attribute on it.

.. code:: python

    pipeline.run_forever(background=True)
    time.sleep(100)
    if pipeline.alive:
         print("I feel fine!")


Using a specific queue
----------------------

Entries can also be ingested by passing a ``queue.Queue`` instance to the
``Pipeline`` constructor. The pipeline will then read from that queue for new
entries. Please be aware that in this case **the pipeline will never stop by
itself**, you'll have to stop it explicitly. This won't work with ``run``,
but you need to use ``run_forever(background=True)`` instead.

.. code:: python

    import paipa
    import queue
    my_queue = queue.Queue()

    pipeline = paipa.Pipeline(
        (PingHost, 128),
        my_queue,
    )
    # This one can be changed from another function, thread or scope.
    should_stop = [False]

    with pipeline:
        while not should_stop[0]:
            continue
        pipeline.stop()



Blocking or not blocking script exit
------------------------------------

If your script exits by hitting the last instruction in it, Python will wait
for all steps in the pipeline to be processed, thereby preventing any
information loss. This behaviour can be changed though.

If you don't care about the data in the pipeline and want to exit right away
you can use the ``daemon`` flag during pipeline instantiation.
Setting the ``daemon`` flag to ``True`` will allow the threads to be
discarded when the process exits. The ``daemon`` flag will be propagated to
every thread which will be created by the library.

.. code:: python

    pipeline = paipa.Pipeline(
        (PingHost, 128),
        daemon=True
    )
    pipeline.put_iterable(all_hosts)
    pipeline.run_forever(background=True)
    time.sleep(60)
    # EOF - end of file

Warning: You will lose data here. Only do this if you really need it!
