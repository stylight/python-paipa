#!/usr/bin/env python
# encoding: utf-8
"""
Pipeline processing
"""
from .iterables import consume
from .coroutines import combine_pipeline, identity_step
from .threaded import AbstractStep, Pipeline, SkipEntry, iterstep, funcstep

__all__ = ["AbstractStep", "Pipeline", "SkipEntry", "iterstep", "funcstep",
           "combine_pipeline", "identity_step", "consume"]

__version__ = "0.3.0"
