"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import os
import zipfile

from .exporter import Exporter


class ZIPExporter(Exporter):

    filename: str = None
    zip_options: dict = {}
    _file = None

    def __init__(self, filename: str = None):
        self.filename = filename
        self.zip_options = self.zip_options.copy()

    def open(self):

        folder = os.path.dirname(self.filename)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        self._file = zipfile.ZipFile(
            self.filename,
            mode="w",
            **self.zip_options
        )

    def close(self):
        self._file.close()

    def get_zip_options_for_path(
            self,
            path: str,
            content: bytes,
            content_type: str = None) -> dict:

        return {}

    def write_file(self, path, content, content_type=None):
        self._file.writestr(
            "/".join(path),
            content,
            **self.get_zip_options_for_path(path, content, content_type)
        )

