"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import zipfile

from .exporter import Exporter


class ZipExporter(Exporter):

    filename: str = None
    zip_options: dict = {}
    _file = None

    def __init__(self, filename: str):
        self.filename = root_folder
        self.zip_options = self.zip_options.copy()

    def open(self):

        if os.path.exists(self.filename):
            mode = "a"
        else:
            mode = "w"

        self._file = zipfile.ZipFile(
            self.filename,
            mode=mode,
            **self.zip_options
        )

    def get_zip_options_for_path(
            self,
            path: str,
            content: bytes,
            content_type: str = None) -> dict:

        return {}

    def write_file(self, path, content, content_type=None):
        self._file.writestr(
            path,
            content,
            **self.get_zip_options_for_path(path, content, content_type)
        )

    def remove_file(self, path):
        pass

