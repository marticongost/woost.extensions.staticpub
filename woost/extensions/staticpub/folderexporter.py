"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import os

from .exporter import Exporter


class FolderExporter(Exporter):

    root_folder = None
    encoding = "utf-8"

    def __init__(self, root_folder):
        self.root_folder = root_folder

    def write_file(self, path, content, content_type=None):

        folder = os.path.join(self.root_folder, *path[:-1])
        if not os.path.exists(folder):
            os.makedirs(folder)
        file_path = os.path.join(self.root_folder, *path)

        if isinstance(content, unicode):
            content = content.encode(self.encoding)

        with open(file_path, "w") as file:
            file.write(content)

    def remove_file(self, path):
        file_path = os.path.join(self.root_folder, *path)
        try:
            os.remove(file_path)
        except OSError:
            if os.path.exists(file_path):
                raise

