#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(name='ISPProgrammer',
    version='1.0.0',
    description='',
    url='',
    author='ElectroOptical Innovations, LLC.',
    author_email='simon.hobbs@electrooptical.net',
    license='BSD',
    packages=find_packages(),
    install_requires=[
        'click',
        'pyserial',
        'numpy',
        'intelhex',
        'timeout_decorator',
        #'zlib'
    ],
    test_suite='nose.collector',
    tests_require=['nose'],
    scripts=["bin/ISPProgrammer"],
    include_package_data=True,
    zip_safe=True
)
