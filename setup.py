from setuptools import setup

try:
    from os.path import abspath, dirname, join
    _desc = join(dirname(abspath(__file__)), 'README.rst')
    long_description = open(_desc, 'r').read()
except IOError:
    long_description = "python-paipa"

setup(
    name='paipa',
    version='0.1.0',
    description='Python pipeline library. Maori: (noun) pipe.',
    packages=['paipa'],
    tests_require=[
        'tox',
    ],
    long_description=long_description,
    author='python-paipa contributors',
    author_email='python-tribe@stylight.com',
    url='http://github.com/stylight/python-paipa',
    license='Apache Software License 2.0',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=[
        'six',
        'enum34',
    ],
    extras_require={
        'glue': ['tornado'],
    },
)
