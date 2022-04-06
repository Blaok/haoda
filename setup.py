"""Hardware-Aware Optimization and Design Automation.

Reusable Python utilities for hardware-aware optimization and design automation.

See:
https://github.com/Blaok/haoda
"""

from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
  long_description = f.read()

setup(
    name='haoda',
    version='0.0.20220405.dev1',
    description='Hardware-aware optimization and design automation',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Blaok/haoda',
    author='Blaok Chi',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: System :: Hardware',
    ],
    packages=find_packages(exclude=(
        'tests.*',
        'tests',
    )),
    python_requires='>=3.6',
    install_requires=[
        'absl-py',
        'cached_property',
    ],
)
