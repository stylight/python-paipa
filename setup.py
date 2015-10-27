from setuptools import setup
from setuptools.command.test import test as TestCommand
import sys



class Tox(TestCommand):
    user_options = [('tox-args=', 'a', "Arguments to pass to tox")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.tox_args = None

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import tox
        import shlex
        args = self.tox_args
        if args:
            args = shlex.split(self.tox_args)
        errno = tox.cmdline(args=args)
        sys.exit(errno)


setup(
    name='paipa',
    version='0.0.1',
    description='Python pipeline library. Maori: (noun) pipe.',
    packages=['paipa'],
    tests_require=[
        'tox',
    ],
    install_requires=[
        'six',
        'enum34',
    ],
    extras_require={
        'glue': ['tornado'],
    },
    cmdclass={
        'test': Tox,
    }
)
