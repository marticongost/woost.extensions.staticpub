"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from collections import Iterable

from BTrees.IOBTree import IOBTree
from BTrees.OOBTree import OOBTree, OOTreeSet, OOBucket
from cocktail.events import Event
from cocktail.caching import whole_cache, normalize_scope
from cocktail.urls import URL
from cocktail import schema
from woost import app
from woost.models import Item, Website

from .exportjob import ExportJob
from .utils import iter_all_exportable_content


class Destination(Item):

    type_group = "staticpub"
    export_file_extension = ".html"
    export_job_class = ExportJob
    instantiable = False

    resolving_export_path = Event()

    members_order = [
        "title",
        "url",
        "website_prefixes",
        "exports"
    ]

    title = schema.String(
        required=True,
        unique=True,
        indexed=True,
        translated=True,
        descriptive=True
    )

    url = schema.URL()

    website_prefixes = schema.Mapping(
        keys=schema.Reference(
            type=Website,
            ui_form_control="cocktail.ui.DropdownSelector"
        ),
        values=schema.String()
    )

    exports = schema.Collection(
        items="woost.extensions.staticpub.export.Export",
        bidirectional=True,
        integral=True,
        editable=schema.NOT_EDITABLE
    )

    def __init__(self, *args, **kwargs):
        Item.__init__(self, *args, **kwargs)
        self._pending_tasks = IOBTree()
        self._entries_by_tag = OOBTree()
        self._entry_tags = OOBTree()

    def create_exporter(self):
        raise ValueError("Not implemented")

    def get_export_url(self, url, resolution=None):
        root_url = URL(self.url)
        return root_url.copy(
            path=root_url.path.append(self.get_export_path(url, resolution))
        )

    def get_export_path(self, url, resolution=None):

        url = URL(url)

        if resolution is None:
            resolution = app.url_mapping.resolve(url)

        export_path = []

        # Add per-website prefixes
        if self.website_prefixes:
            website = (
                resolution
                and resolution.publishable
                and resolution.publishable.websites
                and len(resolution.publishable.websites) == 1
                and iter(resolution.publishable.websites).next()
            )
            if website:
                prefix = self.website_prefixes.get(website)
                if prefix:
                    export_path.extend(prefix.split("/"))

        # Path
        export_path.extend(url.path.segments)

        # Query string
        if url.query:
            export_path.append(url.query.replace("=", "-").replace("&", "."))

        # File extension
        if (
            self.export_file_extension
            and url.path.segments
            and "." not in url.path.segments[-1]
        ):
            export_path[-1] += self.export_file_extension

        # Customization
        e = self.resolving_export_path(
            url=url,
            resolution=resolution,
            export_path=export_path
        )

        return e.export_path

    def iter_pending_tasks(self, publishable=None, languages=None):
        if publishable:
            pub_tasks = self._pending_tasks.get(publishable.id)
            if pub_tasks:
                for lang, action in pub_tasks.iteritems():
                    if languages is None or lang in languages:
                        yield action, publishable.id, lang
        else:
            for pub_id, pub_tasks in self._pending_tasks.iteritems():
                for lang, action in pub_tasks.iteritems():
                    if languages is None or lang in languages:
                        yield action, pub_id, lang

    def has_pending_tasks(self, publishable=None, languages=None):
        for task in self.iter_pending_tasks(publishable, languages):
            return True
        else:
            return False

    def clear_pending_tasks(self, publishable=None, languages=None):
        if publishable:
            if languages:
                pub_tasks = self._pending_tasks.get(publishable.id)
                for lang in languages:
                    try:
                        del pub_tasks[language]
                    except KeyError:
                        pass
                if not pub_tasks:
                    del self._pending_tasks[publishable.id]
            else:
                del self._pending_tasks[publishable.id]
        else:
            for pub_id, pub_tasks in list(self._pending_tasks.iteritems()):
                if languages:
                    pub_tasks = self._pending_tasks.get(pub_id)
                    for lang in languages:
                        try:
                            del pub_tasks[language]
                        except KeyError:
                            pass
                    if not pub_tasks:
                        del self._pending_tasks[pub_id]
                else:
                    del self._pending_tasks[pub_id]

    def get_pending_task(self, publishable, language):
        pub_tasks = self._pending_tasks.get(publishable.id)
        if pub_tasks is not None:
            return pub_tasks.get(language)
        return None

    def set_pending_task(self, publishable, language, task):
        if task is None:
            pub_tasks = self._pending_tasks.get(publishable.id)
            if pub_tasks is not None:
                try:
                    del pub_tasks[language]
                except KeyError:
                    pass
                else:
                    if not pub_tasks:
                        del self._pending_tasks[publishable.id]
        else:
            pub_tasks = self._require_pub_tasks(publishable.id)
            pub_tasks[language] = task

    def _require_pub_tasks(self, publishable_id):
        pub_tasks = self._pending_tasks.get(publishable_id)
        if pub_tasks is None:
            pub_tasks = OOBucket()
            self._pending_tasks[publishable_id] = pub_tasks
        return pub_tasks

    def set_exported_content_tags(self, item, language, tags):

        entry = (item.id, language)
        prev_tags = self._entry_tags.get(entry)
        self._entry_tags[entry] = tags

        if prev_tags:
            for tag in prev_tags:
                tag_entries = self._entries_by_tag.get(tag)
                if tag_entries:
                    tag_entries.remove(entry)

        for tag in tags:
            tag_entries = self._entries_by_tag.get(tag)
            if tag_entries is None:
                tag_entries = OOTreeSet()
                self._entries_by_tag[tag] = tag_entries
            tag_entries.insert(entry)

    def invalidate_exported_content(
        self,
        item,
        language = None,
        cache_part = None
    ):
        scope = normalize_scope(
            item.get_cache_invalidation_scope(
                language=language,
                cache_part=cache_part
            )
        )
        self._invalidate_exported_scope(scope)

    def _invalidate_exported_scope(self, scope, task="mod"):

        # Invalidate everything
        if scope is whole_cache:
            for publishable, language in iter_all_exportable_content():
                pub_tasks = self._require_pub_tasks(publishable.id)
                pub_tasks.setdefault(language, task)

        # Invalidate a single tag
        elif isinstance(scope, basestring):
            for publishable_id, language in self._entries_by_tag.get(scope, ()):
                pub_tasks = self._require_pub_tasks(publishable_id)
                pub_tasks.setdefault(language, task)

        # Invalidate an intersection of tags
        elif isinstance(scope, tuple):

            matching_entries = None

            for tag in scope:
                tagged_entries = self._entries_by_tag.get(tag, ())

                if matching_entries is None:
                    matching_entries = set(tagged_entries)
                else:
                    matching_entries.intersection_update(tagged_entries)

                if not matching_entries:
                    break

            for publishable_id, language in matching_entries:
                pub_tasks = self._require_pub_tasks(publishable_id)
                pub_tasks.setdefault(language, task)

        # Invalidate a collection of scopes
        elif isinstance(scope, Iterable):
            for subscope in scope:
                self._invalidate_exported_scope(subscope)

        # Invalid scope
        else:
            raise TypeError(
               f"Invalid scope ({scope}). "
                "Expected whole_cache, a string, a tuple of strings or a "
                "collection of any of those elements."
            )

