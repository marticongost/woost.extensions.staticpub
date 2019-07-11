"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail import schema

from .destination import Destination
from .folderexporter import FolderExporter


class FolderDestination(Destination):

    members_order = [
        "root_folder"
    ]

    root_folder = schema.String(
        required=True,
        after_member="title"
    )

    def create_exporter(self):
        return FolderExporter(self.root_folder)

