"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import cherrypy
from cocktail.translations import translations, set_language
from cocktail import schema
from cocktail.urls import URL
from cocktail.persistence import transaction
from cocktail.controllers import (
    Controller,
    request_property,
    get_parameter,
    json_out
)
from woost import app
from woost.models import (
    Item,
    Document,
    LocaleMember,
    changeset_context
)
from woost.controllers.cmscontroller import CMSController
from woost.admin.dataexport import Export as DataExport

from woost.extensions.staticpub.destination import Destination
from woost.extensions.staticpub.export import Export
from woost.extensions.staticpub.exportpermission import ExportPermission
from .utils import iter_exportable_languages, iter_all_exportable_items

translations.load_bundle("woost.extensions.staticpub.publicationcontroller")


class ExportStateController(Controller):

    @json_out
    def __call__(self, export_id, lang, **kwargs):

        set_language(lang)

        try:
            export_id = int(export_id)
        except ValueError:
            raise cherrypy.HTTPError(400)

        export = Export.get_instance(export_id)
        if export is None:
            raise cherrypy.NotFound()

        destination = export.destination

        app.user.require_permission(
            ExportPermission,
            destination=destination
        )

        export_object = DataExport(include_paths=True).export_object
        tasks = []
        data = {
            "state": export.state,
            "tasks": tasks
        }

        for task in export.tasks.values():
            item = task["item"]
            lang = task["language"]
            source_url = item.get_uri(language=lang)
            task_data = task.copy()
            task_data["source_url"] = source_url
            task_data["export_url"] = destination.get_export_url(source_url)
            task_data["item"] = export_object(item)
            tasks.append(task_data)

        return data


class PublicationController(Controller):

    state = ExportStateController

    @json_out
    def __call__(self, lang, **kwargs):

        set_language(lang)

        if cherrypy.request.method == "GET":
            return self.preview()
        elif cherrypy.request.method == "POST":
            export = self.begin()
            return {"export_id": export.id}

    def preview(self):

        records = []
        current_publishable = None
        current_record = None
        destination = self.destination
        dest_url = (
            URL(destination.url)
            if destination and destination.url
            else None
        )

        def finish_record():
            if current_record:
                current_record["language_count"] = translations(
                    "woost.extensions.staticpub.publicationcontroller."
                    "PublicationController.language_count",
                    count=len(current_record["languages"])
                )

        task_count = 0
        export_object = DataExport(include_paths=True).export_object

        for action, publishable, language in self.iter_tasks():
            task_count += 1

            if publishable is not current_publishable:
                finish_record()
                current_publishable = publishable
                current_record = {
                    "publishable": export_object(publishable, ref=True),
                    "parents": [
                        export_object(parent, ref=True)
                        for parent in publishable.ascend_tree()
                    ],
                    "languages": {}
                }
                records.append(current_record)

            source_url = publishable.get_uri(language=language)
            export_url = destination.get_export_url(source_url)

            current_record["languages"][language or ""] = {
                "action": action,
                "status": "pending",
                "source_url": source_url,
                "export_url": export_url
            }

        finish_record()

        return {
            "summary": translations(
                "woost.extensions.staticpub.publicationcontroller."
                "PublicationController.task_count",
                count=task_count,
                pending_only=self.pending_only
            ),
            "tasks": records
        }

    def begin(self):

        def create_export():
            with changeset_context(app.user):
                export = Export.new()
                export.destination = self.destination
                export.user = app.user
                for action, publishable, language in self.iter_tasks():
                    export.add_task(action, publishable, language)
            return export

        export = transaction(create_export)
        export.execute_in_subprocess()
        return export

    def iter_tasks(self):

        destination = self.destination

        app.user.require_permission(ExportPermission, destination=destination)

        selection = self.selection or iter_all_exportable_items()
        pending_only = self.pending_only
        include_descendants = self.include_descendants
        language_mode = self.language_mode
        language_subset = self.language_subset
        include_neutral_language = self.include_neutral_language

        visited = set()

        def traverse(publishable_list):

            for publishable in publishable_list:

                if publishable in visited:
                    continue
                else:
                    visited.add(publishable)

                for lang in iter_exportable_languages(publishable):

                    if lang is None:
                        if not include_neutral_language:
                            continue
                    elif language_mode == "include":
                        if lang not in language_subset:
                            continue
                    elif language_mode == "exclude":
                        if lang in language_subset:
                            continue

                    if (
                        pending_only
                        and not destination.get_pending_task(publishable, lang)
                    ):
                        continue

                    yield "post", publishable, lang

                if include_descendants and isinstance(publishable, Document):
                    for item in traverse(publishable.children):
                        yield item

        return traverse(selection)

    @request_property
    def destination(self):
        return get_parameter(
            schema.Reference(
                "destination",
                type=Destination,
                required=True
            ),
            errors="raise"
        )

    @request_property
    def selection(self):
        return get_parameter(
            schema.Collection(
                "selection",
                items=schema.Reference(type=Item)
            ),
            errors="raise"
        )

    @request_property
    def pending_only(self):
        return get_parameter(
            schema.Boolean(
                "pending_only",
                required=True,
                default=False
            ),
            implicit_booleans=False,
            errors="raise"
        )

    @request_property
    def include_descendants(self):
        return get_parameter(
            schema.Boolean(
                "include_descendants",
                required=True,
                default=False
            ),
            implicit_booleans=False,
            errors="raise"
        )

    @request_property
    def language_mode(self):
        return get_parameter(
            schema.String(
                "language_mode",
                required=True,
                enumeration=["all", "include", "exclude"],
                default="all"
            ),
            errors="raise"
        )

    @request_property
    def language_subset(self):
        return get_parameter(
            schema.Collection(
                "language_subset",
                items=LocaleMember()
            ),
            errors="raise"
        )

    @request_property
    def include_neutral_language(self):
        return get_parameter(
            schema.Boolean(
                "include_neutral_language",
                required=True,
                default=True
            ),
            implicit_booleans=False,
            errors="raise"
        )


CMSController.x_staticpub_publication = PublicationController

