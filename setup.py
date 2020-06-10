#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

setup(name='ISPProgrammer',
      version='1.0.3',
      description='NXP ISP Cortex-M programming tool',
      long_description=LONG_DESCRIPTION,
      long_description_content_type="text/markdown",
      url='https://github.com/snhobbs/NXPISP',
      author='Simon Hobbs',
      author_email='simon.hobbs@electrooptical.net',
      license='MIT',
      packages=find_packages(),
      classifiers=[
          "Programming Language :: Python :: 3",
          "License :: OSI Approved :: MIT License",
          "Operating System :: OS Independent",
      ],
      python_requires='>=3.6',
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
      zip_safe=True)
