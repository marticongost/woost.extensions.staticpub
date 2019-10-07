"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from typing import Dict, Iterable, Sequence, Tuple
import re
import weakref
from itertools import zip_longest

import requests
from bs4 import BeautifulSoup, Tag
from cocktail.events import Event
from cocktail.translations import language_context
from cocktail.urls import URL
from cocktail.persistence import datastore, transaction
from woost import app
from woost.urls import URLResolution
from woost.models import Configuration, File, PublishableObject

from .exporter import Exporter
from .utils import EXPORT_HEADER, USER_AGENT

ResourceWithinDocument = Tuple[Tag, str, URL, str]


class ExportJob:

    export = None
    exporter = None
    dependencies = None
    reset = False
    errors = "resume" # "resume" or "raise"
    encoding = "utf-8"

    selecting_export_urls = Event()
    export_starting = Event()
    export_failed = Event()
    export_completed = Event()
    export_ended = Event()
    task_starting = Event()
    task_executed = Event()
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
        self.exporter = self.create_exporter()
        self.document_urls = set()
        self.dependencies = set()
        self.pending_dependencies = set()
        self.__url_resolutions = {}

    def create_exporter(self, **kwargs) -> Exporter:
        return self.export.destination.create_exporter(**kwargs)

    def get_export_urls(
            self,
            item: PublishableObject,
            language: str) -> Sequence[URL]:

        e = self.selecting_export_urls(
            item=item,
            language=language,
            urls=[item.get_uri(host="!", language=language)]
        )
        return e.urls

    def get_source_url(
            self,
            item: PublishableObject,
            language: str,
            path: Sequence[str] = None,
            parameters: Dict[str, str] = None) -> URL:

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

    def execute_task(self, task: dict):

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
                        content_type=resource.content_type
                    )

                elif action == "delete":
                    export_path = \
                        self.export.destination.get_export_path(source_url)
                    self.exporter.remove_file(export_path)

            self.task_executed(task=task)

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

    def get_request_parameters(
            self,
            resource: 'ExportedResource') -> Dict[str, str]:

        headers = {
            "User-agent": USER_AGENT,
            EXPORT_HEADER: str(self.export.id),
        }

        if self.export.auth_token:
            headers[app.authentication.AUTH_TOKEN_HEADER] = \
                self.export.auth_token

        return {"headers": headers}

    def process_resource(self, resource: 'ExportedResource'):

        if resource.content_type == "text/html":
            document = BeautifulSoup(resource.content, features="lxml")
            self.process_html(document, resource)
            resource.content = str(document)

        elif resource.content_type == "text/css":
            css = resource.content.decode(self.encoding)
            css = self.process_css(css, resource)
            resource.content = css.encode(self.encoding)

    def process_html(
            self,
            document: BeautifulSoup,
            resource: 'ExportedResource'):

        # Process embedded styles
        for element in document.find_all("style"):
            content_type = element.get("type")
            if (
                (not content_type or content_type == "text/css")
                and element.string
            ):
                element.string = self.process_css(element.string, resource)

        # Process embdded scripts
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
        for element, attr, url, content_type \
        in self.iter_urls_in_html(document, resource):
            self.process_html_url(
                element,
                attr,
                url,
                content_type,
                resource
            )

    def iter_urls_in_html(
            self,
            document: BeautifulSoup,
            resource: 'ExportedResource') -> Iterable[ResourceWithinDocument]:

        for link in document.find_all("link"):
            href = link.get("href")
            if href:
                ctype = link.get("type")
                if not ctype:
                    rel = link.get("rel")
                    if rel and str(rel).lower() == "stylesheet":
                        ctype = "text/css"
                yield link, "href", URL(href), ctype

        for script in document.find_all("script"):
            src = script.get("src")
            if src:
                yield (
                    script,
                    "src",
                    URL(src),
                    script.get("type") or "application/javascript"
                )

        for img in document.find_all("img"):
            src = img.get("src")
            if src:
                yield img, "src", URL(src), None

        for video in document.find_all("video"):
            src = video.get("src")
            if src:
                yield video, "src", URL(src), video.get("type")

        for audio in document.find_all("audio"):
            src = audio.get("src")
            if src:
                yield audio, "src", URL(src), audio.get("type")

        for source in document.find_all("source"):
            src = source.get("src")
            if src:
                yield source, "src", URL(src), source.get("type")

        for a in document.find_all("a"):
            href = a.get("href")
            if href and not href.startswith("#"):
                yield a, "href", URL(href), a.get("type")

        for iframe in document.find_all("iframe"):
            src = iframe.get("src")
            if src:
                yield iframe, "src", URL(src), None

    def process_html_url(
            self,
            element: Tag,
            attr: str,
            url: URL,
            content_type: str,
            resource: 'ExportedResource'):

        if url.scheme in ("javascript", "mailto"):
            return url

        url = self.normalize_href(url, resource)

        # Collect dependencies
        self.add_dependency(url, content_type=content_type)

        # Transform the resource URL into a relative path
        url = self.transform_href(url, resource, content_type=content_type)
        element[attr] = url

    def process_css(
            self,
            content: str,
            resource: 'ExportedResource') -> str:

        def replace_url(match):

            value = match.group(1).strip("'").strip('"')

            if value.startswith("javascript:"):
                return value

            url = URL(value)
            url = self.normalize_href(url, resource)
            self.add_dependency(url, content_type="text/css")
            url = self.transform_href(url, resource, content_type="text/css")
            return f"url('{url}')"

        return self.css_url_regexp.sub(replace_url, content)

    def process_embedded_javascript(
            self,
            content: str,
            resource: 'ExportedResource') -> str:

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
            self.add_dependency(url, content_type="application/javascript")
            url = self.transform_href(
                url,
                resource,
                content_type="application/javascript"
            )
            return match.group("head") + url + match.group("tail")

        return self.js_string_regexp.sub(process_strings, content)

    def get_base_url(self, url: URL) -> URL:
        if len(url.path) > 1:
            return url.copy(path=url.path.pop(-1))
        else:
            return url

    def normalize_href(self, url: URL, resource: 'ExportedResource') -> URL:

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
            resolution = self.resolve_url(url)
            if resolution and resolution.publishable:
                url = app.url_mapping.get_canonical_url(
                    url,
                    language=resource.language,
                    preserve_extra_path=True
                )

        return url

    def transform_href(
            self,
            url: URL,
            resource: "ExportedResource",
            content_type: str = None) -> URL:

        if self.url_is_external(url):
            return url
        else:
            if self.should_make_url_absolute(url, resource):
                return self.export.destination.get_export_url(
                    url,
                    content_type=content_type
                )
            else:
                return self.get_relative_url(
                    url,
                    resource,
                    content_type=content_type
                )

    def should_make_url_absolute(
            self,
            url: URL,
            resource: 'ExportedResource') -> bool:

        return False

    def get_relative_url(
            self,
            url: URL,
            resource: "ExportedResource",
            content_type: str = None) -> URL:

        # Express URLs as paths relative to the exported document
        url_export_path = self.export.destination.get_export_path(
            url,
            content_type=content_type
        )

        i = 0
        for a, b in zip_longest(resource.export_folder, url_export_path):
            if a != b:
                break
            i += 1

        url_export_path = url_export_path[i:]

        for n in range(len(resource.export_folder) - i):
            url_export_path.insert(0, u"..")

        return URL(
            path=url_export_path,
            query=url.query,
            fragment=url.fragment
        )

    def url_is_external(self, url: URL) -> bool:

        if not url.hostname:
            return False

        config = Configuration.instance
        return config.get_website_by_host(url.hostname) is None

    def url_is_exportable_dependency(
            self,
            url: URL,
            content_type: str = None) -> bool:

        # Ignore external URLs
        if self.url_is_external(url):
            return False

        # Ignore publishable elements
        resolution = self.resolve_url(url)
        return (
            not resolution
            or not resolution.publishable
            or (
                content_type
                or resolution.publishable.mime_type
            ) != "text/html"
        )

    def resolve_url(self, url: URL) -> URLResolution:
        try:
            return self.__url_resolutions[url]
        except KeyError:
            resolution = app.url_mapping.resolve(url)
            self.__url_resolutions[url] = resolution
            return resolution

    def add_dependency(
            self,
            url: URL,
            content_type: str = None):

        if url not in self.dependencies and url not in self.document_urls:
            if self.url_is_exportable_dependency(url, content_type):
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


class ExportedResource:

    __export_job = None
    __export_path = None
    __export_folder = None

    publishable: PublishableObject = None
    language: str = None
    source_url: URL = None
    base_url: URL = None
    headers: Dict[str, str] = None
    content_type: str = None
    content: bytes = None

    def __init__(self, export_job: ExportJob, source_url: URL):

        # Source URLs
        self.source_url = source_url
        self.base_url = export_job.get_base_url(source_url)
        self.__export_job = weakref.ref(export_job)

    def open(self, **kwargs):

        response = requests.get(self.source_url, **kwargs)
        self.headers = response.headers
        self.content = response.content

        self.content_type = self.headers.get("Content-Type")
        if self.content_type:
            self.content_type = self.content_type.split(";", 1)[0]

    @property
    def export_folder(self) -> Sequence[str]:

        if self.__export_folder is None:
            job = self.__export_job()
            get_export_path = job.export.destination.get_export_path
            self.__export_folder = get_export_path(
                self.base_url,
                add_file_extension=False
            )

        return self.__export_folder

    @property
    def export_path(self) -> Sequence[str]:

        if self.__export_path is None:
            job = self.__export_job()
            get_export_path = job.export.destination.get_export_path
            self.__export_path = get_export_path(
                self.source_url,
                content_type=self.content_type
            )

        return self.__export_path

