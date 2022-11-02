#!/usr/bin/env python3

import os
import sys
from distutils.core import setup

from setuptools import find_packages

if sys.version_info.major <= 2:
    raise Exception("Only python 3+ is supported!")

requirements = [
    "pyyaml",
    "pyqt5",
]

__version__ = "1.0"
package_name = "host-monitor"

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

description = long_description.splitlines()[0].strip()

data_files = [f"{this_directory}/host_monitor/config_default.yaml"]

setup(
    name=package_name,
    version=__version__,
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Jan Cychnerski',
    url='https://github.com/cvlab-ai/host-monitor',
    packages=find_packages("."),
    package_data={"host_monitor": data_files},
    entry_points={'gui_scripts': ['host-monitor=host_monitor.main:main']},
    license="GPL-3.0+",
    python_requires='>=3.6',
    install_requires=requirements,
)
