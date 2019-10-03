"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import cherrypy
from cocktail.controllers import Controller, serve_file
from woost import app
from woost.controllers.cmscontroller import CMSController

from woost.extensions.staticpub.export import Export
from woost.extensions.staticpub.exportpermission import ExportPermission


class ZIPController(Controller):

    def __call__(self, export_id, **kwargs):

        try:
            export_id = int(export_id)
        except ValueError:
            raise cherrypy.HTTPError(400)

        export = Export.get_instance(export_id)
        if export is None:
            raise cherrypy.NotFound()

        app.user.require_permission(
            ExportPermission,
            destination=export.destination
        )

        return serve_file(
            export.zip_path,
            content_type="application/zip",
            disposition="attachment",
            name="project.zip"
        )


CMSController.x_staticpub_zip = ZIPController

