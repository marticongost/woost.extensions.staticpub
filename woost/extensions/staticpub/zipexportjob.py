"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import os
from woost import app

from .exportjob import ExportJob
from .exporter import Exporter


class ZIPExportJob(ExportJob):

    zip_folder = None

    def create_exporter(self) -> Exporter:
        folder = self.zip_folder or app.path("x-staticpub-zip-files")
        os.makedirs(folder, exist_ok=True)
        filename = os.path.join(folder, f"{self.export.id}.zip")
        self.export.zip_path = filename
        return super().create_exporter(filename=filename)

