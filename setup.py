from setuptools import setup

setup(
    name='paipa',
    version='0.0.2',
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
)
