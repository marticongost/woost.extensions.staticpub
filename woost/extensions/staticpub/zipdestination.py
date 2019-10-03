"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from .destination import Destination
from .zipexportjob import ZIPExportJob
from .zipexporter import ZIPExporter


class ZIPDestination(Destination):

    export_job_class = ZIPExportJob
    exporter_class = ZIPExporter
    state_ui_component = (
        "woost.extensions.staticpub.admin.ui."
        "ZIPPublicationState"
    )

