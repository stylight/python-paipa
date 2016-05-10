from setuptools import setup

setup(
    name='paipa',
    version='0.1.0',
    description='Python pipeline library. Maori: (noun) pipe.',
    packages=['paipa'],
    author="Bizdev Engineers",
    author_email="busdev_engineers@stylight.com",
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
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
