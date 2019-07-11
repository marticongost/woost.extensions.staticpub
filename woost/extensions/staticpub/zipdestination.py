"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail import schema

from .destination import Destination
from .zipexporter import ZIPExporter


class ZIPDestination(Destination):

    def create_exporter(self):
        return ZIPExporter()

