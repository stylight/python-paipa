paipa - the threaded pipelining framework
=========================================

.. image:: https://travis-ci.org/stylight/python-paipa.svg?branch=master
    :target: https://travis-ci.org/stylight/python-paipa

Overview
--------

What it does:

 - process stuff one step at a time
 - allows class based and function based steps
 - can scale steps independent of each other (manually)
 - don't do deadlocks
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
