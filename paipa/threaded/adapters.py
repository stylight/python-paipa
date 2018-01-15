"""
These can be used to plug in normal functions or iterators into the threaded
pipeline without having to do any code modifications.
"""
from .steps import AbstractStep, AbstractIterStep


def funcstep(func, base=AbstractStep):
    """
    Transform a filtering function to a pipeline step

    This function dynamically creates a new step class, inheriting from base.
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


def iterstep(func, base=AbstractIterStep):
    """
    Transform a iterator/generator filter to a pipeline step

    :Parameters:
      `func` : callable
        iterator

    :Return: New step class
    :Rtype: ``type``
    """
    # pylint: disable = W0223, R0912

    return funcstep(func, base=base)


def is_step(step):
    """Check if it's a step.

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
