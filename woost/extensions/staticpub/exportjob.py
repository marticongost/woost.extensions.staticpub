"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import re

import requests
from bs4 import BeautifulSoup
from cocktail.events import Event
from cocktail.translations import language_context
from cocktail.urls import URL
from cocktail.persistence import datastore, transaction
from woost import app
from woost.models import Configuration, File

from .utils import EXPORT_HEADER, USER_AGENT


class ExportJob:

    export = None
    exporter = None
    dependencies = None
    reset = False
    errors = "resume" # "resume" or "raise"

    selecting_export_urls = Event()
    export_starting = Event()
    export_failed = Event()
    export_completed = Event()
    export_ended = Event()
    task_starting = Event()
    task_successful = Event()
    task_failed = Event()
    dependency_transfers_starting = Event()
    dependency_transfer_starting = Event()
    dependency_transfer_successful = Event()
    dependency_transfer_failed = Event()

    css_url_regexp = re.compile(r"""url\(([^)]+)\)""")
    js_string_regexp = re.compile(
        r"""
        (?P<delim>['"])
        (?P<value>.*)
        \1              # Same string delimiter used in the opening
        (?!\\)          # Not preceded by a escape character
        """,
        re.VERBOSE
    )
    js_url_regexp = re.compile(
        r"""
        (?P<head>
            (\s+src\s*=|\s+href\s*=|\Wurl\()
            \s*
            \\?
            ['"]?
        )
        (?P<url>.*?)
        (?P<tail>['")\\])
        """,
        re.VERBOSE
    )

    def __init__(self, export):
        self.export = export
        self.exporter = export.destination.create_exporter()
        self.document_urls = set()
        self.dependencies = set()
        self.pending_dependencies = set()
        self.__url_resolutions = {}

    def get_export_urls(self, item, language):
        e = self.selecting_export_urls(
            item=item,
            language=language,
            urls=[item.get_uri(host="!", language=language)]
        )
        return e.urls

    def get_source_url(self, item, language, path=None, parameters=None):
        return item.get_uri(
            language=language,
            path=path,
            parameters=parameters,
            host="!"
        )

    def execute(self):

        @transaction
        def begin():
            self.export.state = "running"
            if self.reset:
                for task in self.export.tasks.itervalues():
                    task["state"] = "pending"

        with self.exporter:

            self.export_starting()

            try:
                for task in self.export.tasks.itervalues():

                    # Ignore completed / failed tasks
                    if task["state"] != "pending":
                        continue

                    # Give other scripts a chance to abort the export operation
                    datastore.sync()
                    if self.export.state != "running":
                        raise Halt()

                    self.execute_task(task)

                if self.dependencies:
                    self.export_dependencies()

            except Halt:
                pass
            except Exception as error:
                @transaction
                def complete():
                    self.export.state = "idle"
                self.export_failed(error=error)
                if self.errors == "raise":
                    raise
            else:
                @transaction
                def complete():
                    self.export.state = "completed"
                self.export_completed()
            finally:
                self.export_ended()
                self.exporter.close()

    def execute_task(self, task):

        self.task_starting(task=task)

        action = task["action"]
        item = task["item"]
        language = task["language"]

        try:
            tags = set()

            for source_url in self.get_export_urls(item, language):

                if action == "post":
                    resource = ExportedResource(self, source_url)
                    resource.language = language
                    resource.open(**self.get_request_parameters(resource))

                    url_tags = resource.headers.get("X-Woost-Cache-Tags")
                    if url_tags:
                        tags.update(url_tags.split())

                    self.process_resource(resource)

                    # Prevent documents from also being downloaded as
                    # dependencies
                    self.document_urls.add(resource.source_url)
                    self.dependencies.discard(resource.source_url)
                    self.pending_dependencies.discard(resource.source_url)

                    self.exporter.write_file(
                        resource.export_path,
                        resource.content,
                        content_type = resource.content_type
                    )

                elif action == "delete":
                    export_path = \
                        self.export.destination.get_export_path(source_url)
                    self.exporter.remove_file(export_path)

        except Exception as export_error:
            if self.errors == "raise":
                raise
        else:
            export_error = None

        @transaction
        def update_task():

            if export_error:
                task["state"] = "failed"
                task["error_message"] = repr(export_error)
            else:
                task["state"] = "success"
                publishable = task["item"]
                self.export.destination.set_pending_task(
                    publishable,
                    language,
                    None
                )
                self.export.destination.set_exported_content_tags(
                    publishable,
                    language,
                    tags
                )

        if export_error:
            self.task_failed(task=task, error=export_error)
        else:
            self.task_successful(task=task)

    def get_request_parameters(self, resource):
        return {
            "headers": {
                "User-agent": USER_AGENT,
                EXPORT_HEADER: str(self.export.id)
            }
        }

    def process_resource(self, resource):

        if resource.content_type == "text/html":
            document = BeautifulSoup(resource.content)
            self.process_html(document, resource)
            resource.content = unicode(document)

        elif resource.content_type == "text/css":
            resource.content = self.process_css(resource.content, resource)

    def process_html(self, document, resource):

        # Process embedded styles
        for element in document.find_all("style"):
            content_type = element.get("type")
            if (
                (not content_type or content_type == "text/css")
                and element.string
            ):
                element.string = self.process_css(element.string, resource)

        # Process client models
        for element in document.find_all("script"):
            content_type = element.get("type")
            if (
                (not content_type or content_type == "text/javascript")
                and element.string
            ):
                element.string = self.process_embedded_javascript(
                    element.string,
                    resource
                )

        # Transform URLs
        for element, attr, url in self.iter_urls_in_html(document, resource):
            self.process_html_url(
                element,
                attr,
                url,
                resource
            )

    def iter_urls_in_html(self, document, resource):

        for link in document.find_all("link"):
            href = link.get("href")
            if href:
                yield link, "href", URL(href)

        for script in document.find_all("script"):
            src = script.get("src")
            if src:
                yield script, "src", URL(src)

        for img in document.find_all("img"):
            src = img.get("src")
            if src:
                yield img, "src", URL(src)

        for a in document.find_all("a"):
            href = a.get("href")
            if href and not href.startswith("#"):
                yield a, "href", URL(href)

        for iframe in document.find_all("iframe"):
            src = iframe.get("src")
            if src:
                yield iframe, "src", URL(src)

    def process_html_url(self, element, attr, url, resource):

        if url.scheme in ("javascript", "mailto"):
            return url

        url = self.normalize_href(url, resource)

        # Collect dependencies
        self.add_dependency(url)

        # Transform the resource URL into a relative path
        url = self.transform_href(url, resource)
        element[attr] = url

    def process_css(self, content, resource):

        def replace_url(match):

            value = match.group(1).strip("'").strip('"')

            if value.startswith("javascript:"):
                return value

            url = URL(value)
            url = self.normalize_href(url, resource)
            self.add_dependency(url)
            url = self.transform_href(url, resource)
            return u"url('%s')" % url

        return self.css_url_regexp.sub(replace_url, content)

    def process_embedded_javascript(self, content, resource):

        def process_strings(match):
            c = match.group("delim")
            return (
                c
                + self.js_url_regexp.sub(replace_url, match.group("value"))
                + c
            )

        def replace_url(match):

            value = match.group("url")

            if value.startswith("javascript:"):
                return match.group(0)

            url = URL(value)
            url = self.normalize_href(url, resource)
            self.add_dependency(url)
            url = self.transform_href(url, resource)
            return match.group("head") + url + match.group("tail")

        return self.js_string_regexp.sub(process_strings, content)

    def get_base_url(self, url):
        if url.path and "." in url.path.segments[-1]:
            return url.copy(path=url.path.pop(-1))
        else:
            return url

    def normalize_href(self, url, resource):

        # Normalize relative URLs using the source URL for the processed
        # document
        if not url.hostname:
            url = resource.base_url.copy(
                path=resource.base_url.path.merge(url.path),
                query=url.query,
                fragment=url.fragment
            )

        # Normalize URLs to their canonical form
        if not self.url_is_external(url):
            url = app.url_mapping.get_canonical_url(
                url,
                language=resource.language
            )

        return url

    def transform_href(self, url, resource):
        if self.url_is_external(url):
            return url
        else:
            if self.should_make_url_absolute(url, resource):
                return self.export.destination.get_export_url(url)
            else:
                return self.get_relative_url(url, resource)

    def should_make_url_absolute(self, url, resource):
        return False

    def get_relative_url(self, url, resource):

        # Express URLs as paths relative to the exported document
        url_export_path = self.export.destination.get_export_path(url)

        i = 0
        while (
            i < len(resource.export_folder)
            and i < len(url_export_path)
            and resource.export_folder[i] == url_export_path[i]
        ):
            i += 1

        url_export_path = url_export_path[i:]

        for n in xrange(len(resource.export_folder) - i - 1):
            url_export_path.insert(0, u"..")

        return URL(
            path=url_export_path,
            query=url.query,
            fragment=url.fragment
        )

    def url_is_external(self, url):

        if not url.hostname:
            return False

        config = Configuration.instance
        return config.get_website_by_host(url.hostname) is None

    def url_is_exportable_dependency(self, url):

        # Ignore external URLs
        if self.url_is_external(url):
            return False

        # Ignore publishable elements
        resolution = self.resolve_url(url)
        return (
            not resolution
            or not resolution.publishable
            or resolution.publishable.mime_type != "text/html"
        )

    def resolve_url(self, url):
        try:
            return self.__url_resolutions[url]
        except KeyError:
            resolution = app.url_mapping.resolve(url)
            self.__url_resolutions[url] = resolution
            return resolution

    def add_dependency(self, url):
        if url not in self.dependencies and url not in self.document_urls:
            if self.url_is_exportable_dependency(url):
                self.dependencies.add(url)
                self.pending_dependencies.add(url)

    def export_dependencies(self):

        if self.dependencies:
            self.dependency_transfers_starting()

        while self.pending_dependencies:

            source_url = self.pending_dependencies.pop()
            resource = ExportedResource(self, source_url)
            self.dependency_transfer_starting(resource=resource)

            try:
                resource.open(**self.get_request_parameters(resource))
                self.process_resource(resource)
                self.exporter.write_file(
                    resource.export_path,
                    resource.content,
                    content_type=resource.content_type
                )
            except Exception as export_error:
                self.dependency_transfer_failed(
                    resource=resource,
                    error=export_error
                )
                if self.errors == "raise":
                    raise
            else:
                self.dependency_transfer_successful(resource=resource)


class Halt(Exception):
    pass


class ExportedResource(object):

    publishable = None
    language = None
    source_url = None
    export_path = None
    base_url = None
    export_folder = None
    headers = None
    content_type = None
    content = None

    def __init__(self, export_job, source_url):

        # Source URLs
        self.source_url = source_url
        self.base_url = export_job.get_base_url(source_url)

        # Destination paths
        get_export_path = export_job.export.destination.get_export_path
        self.export_folder = get_export_path(self.base_url)
        self.export_path = get_export_path(source_url)

    def open(self, **kwargs):

        response = requests.get(self.source_url, **kwargs)
        self.headers = response.headers
        self.content = response.content

        self.content_type = self.headers.get("Content-Type")
        if self.content_type:
            self.content_type = self.content_type.split(";", 1)[0]

