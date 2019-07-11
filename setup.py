"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from setuptools import setup

setup(
    name = "woost.extensions.staticpub",
    version = "0.0b1",
    description = "staticpub extension for the Woost CMS.",
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: ZODB",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
        "Topic :: Internet :: WWW/HTTP :: Site Management"
    ],
    install_requires = [
        "woost==3.0.*",
        "requests"
    ],
    packages = [
        "woost.extensions.staticpub"
    ],
    include_package_data = True,
    zip_safe = False
)

