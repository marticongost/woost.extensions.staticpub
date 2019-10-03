"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import sys
from time import time
from collections import defaultdict
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
    RawTextHelpFormatter
)

from cocktail.styled import ProgressBar, styled
from cocktail.stringutils import normalize_indentation as ni
from cocktail.events import when
from cocktail.translations import (
    translations,
    translate_locale,
    set_language
)
from cocktail.persistence import transaction
from woost.models import Configuration, Publishable, Document, User

from .export import Export
from .destination import Destination
from .utils import (
    iter_exportable_languages,
    iter_all_exportable_content
)


class CLI(object):

    action = "export"
    export = None
    tasks = None
    languages = None
    reset = False
    errors = None
    verbose = False
    start = None
    end = None

    def __init__(self):
        self.start = time()
        self.parser = self.create_arg_parser()

    def create_arg_parser(self):

        parser = ArgumentParser(
            formatter_class=RawTextHelpFormatter
        )

        def content_parser(selector):

            if selector.startswith("branch:"):
                doc_id = selector.split(":", 1)[1]
                try:
                    document = Document.require_instance(int(doc_id))
                except:
                    raise ArgumentTypeError(
                        f"{doc_id} is not a valid branch ID"
                    )
                else:
                    return ("branch", ("post", document))

            elif selector.startswith("delbranch:"):
                doc_id = selector.split(":", 1)[1]
                try:
                    document = Document.require_instance(int(doc_id))
                except:
                    raise ArgumentTypeError(
                        f"{doc_id} is not a valid branch ID"
                    )
                else:
                    return ("branch", ("delete", document))

            elif selector.startswith("item:"):
                pub_id = selector.split(":", 1)[1]
                try:
                    publishable = Publishable.require_instance(int(pub_id))
                except:
                    raise ArgumentTypeError(
                        f"{pub_id} is not a valid branch ID"
                    )
                else:
                    return ("item", ("post", publishable))

            elif selector.startswith("delitem:"):
                pub_id = selector.split(":", 1)[1]
                try:
                    publishable = Publishable.require_instance(int(pub_id))
                except:
                    raise ArgumentTypeError(
                        f"{pub_id} is not a valid branch ID"
                    )
                else:
                    return ("item", ("delete", publishable))

            elif selector.startswith("export:"):
                export_id = selector.split(":", 1)[1]
                try:
                    export = Export.require_instance(int(export_id))
                except:
                    raise ArgumentTypeError(
                        f"{export_id} is not a valid export ID"
                    )
                else:
                    return ("export", export)

        def destination_parser(id):
            try:
                return Destination.require_instance(int(id))
            except:
                raise ArgumentTypeError(f"{id} is not a valid destination ID")

        def user_parser(value):

            try:
                try:
                    id = int(value)
                except ValueError:
                    return User.require_instance(email=value)
                else:
                    return User.require_instance(id)
            except:
                pass

            raise ArgumentTypeError(f"{id} is not a valid user ID or email")

        parser.add_argument(
            "action",
            choices=["export", "list"],
            help=ni("""
                The action to perform. Use 'list' to perform a dry run without
                actually commiting any change to the export target, or 'export'
                to go through with the export operation.
                """)
        )
        parser.add_argument(
            "content",
            nargs="*",
            type=content_parser,
            help=ni("""
                The subset to export; leave unspecified to export the whole
                site. Otherwise, can be specified using one or more of the
                following selectors:

                    branch:DOCUMENT_ID
                        Export all elements descending from the indicated
                        document.

                    delbranch:DOCUMENT_ID
                        Delete all elements descending from the indicated
                        document.

                    item:ITEM_ID
                        Export the indicated element.

                    delitem:ITEM_ID
                        Delete the indicated element.

                    export:EXPORT_ID
                        Don't create a new export operation, resume the given
                        one instead.
                """)
        )
        parser.add_argument(
            "-d", "--destination",
            type=destination_parser,
            help=ni("""
                The ID of the Destination object indicating the export target.
                """)
        )
        parser.add_argument(
            "-u", "--user",
            type=user_parser,
            help=ni("""
                The ID or email of the User that the export operation should be
                run as. The default is to run the export as an anonymous user;
                using a specific user might be necessary in order to reach
                restricted content.
                """)
        )
        parser.add_argument(
            "-p", "--pending",
            action="store_true",
            help=ni("""
                Limits the export operation to publishable items that have been
                modified since the last export.
                """)
        )
        parser.add_argument(
            "-l", "--languages",
            nargs="*",
            choices=["neutral"]
                      + list(Configuration.instance.get_enabled_languages()),
            metavar="LANGUAGE",
            help=ni("""
                Limits the export operation to the indicated set of locales.
                The special 'neutral' locale is also accepted, to include
                content that is not language specific (such as files).
                """)
        )
        parser.add_argument(
            "-r", "--reset",
            action="store_true",
            help=ni("""
                Resets the state of all the content in the selected export
                operation, essentially forcing the operation to start over.
                """)
        )
        parser.add_argument(
            "-e", "--errors",
            choices=["raise", "resume"],
            help="The behavior when an error occurs."
        )
        parser.add_argument(
            "-v", "--verbose",
            action="store_true",
            help=ni("""
                Enable to show progress information for the export operation.
                """)
        )

        return parser

    def apply_args(self, args):

        self.action = args.action
        self.reset = args.reset
        self.errors = args.errors
        self.verbose = args.verbose

        if args.languages:
            self.languages = [
                (None if lang == "neutral" else lang)
                for lang in args.languages
            ]

        if len(args.content) == 1 and args.content[0][0] == "export":
            self.export = args.content[0][1]

            if args.destination:
                sys.stderr.write(
                    "Can't specify --destination when executing an existing "
                    "export operation\n"
                )
                sys.exit(1)

            if self.languages:
                sys.stderr.write(
                    "Can't specify --languages when executing an existing "
                    "export operation\n"
                )
                sys.exit(1)

            if args.pending:
                sys.stderr.write(
                    "Can't specify --pending when executing an existing "
                    "export operation\n"
                )
                sys.exit(1)
        else:
            if args.destination is None:
                args.destination = Configuration.instance.x_staticpub_default_dest
                if args.destination is None:
                    args.destination = Destination.select()[0]
                    if args.destination is None:
                        sys.stderr.write("No destination available\n")
                        sys.exit(1)

            if self.action == "export":
                try:
                    self.export = transaction(
                        self._create_export_from_args,
                        action_args=(args,)
                    )
                except EmptyExport:
                    pass
            elif self.action == "list":
                self.tasks = self._get_tasks_from_args(args)

    def _create_export_from_args(self, args):

        tasks = self._get_tasks_from_args(args)

        if tasks:
            export = Export.new(destination=args.destination)
            export.user = args.user
            for task in tasks:
                export.add_task(*task)
            return export
        else:
            raise EmptyExport()

    def _get_tasks_from_args(self, args):

        user = args.user
        tasks = set()

        if args.content:
            for selector_type, selector_value in args.content:

                if selector_type == "export":
                    sys.stderr.write(
                        "Can't mix an export: selector with other content "
                        "selectors\n"
                    )
                    sys.exit(1)

                elif selector_type == "branch":
                    action, root = selector_value
                    for pub in root.descend_tree(include_self=True):
                        for lang in iter_exportable_languages(pub, user=user):
                            if not self.languages or lang in self.languages:
                                tasks.add((action, pub, lang))

                elif selector_type == "item":
                    action, pub = selector_value
                    for lang in iter_exportable_languages(pub, user=user):
                        if not self.languages or lang in self.languages:
                            tasks.add((action, pub, lang))
        else:
            for pub, lang in iter_all_exportable_content(user=user):
                if not self.languages or lang in self.languages:
                    tasks.add(("post", pub, lang))

        if args.pending:
            actions = {"add": "post", "mod": "post", "del": "delete"}
            tasks.intersection_update(
                (actions[action], pub, lang)
                for pub, lang, action
                in args.destination.iter_pending_tasks()
            )

        return tasks

    def main(self):
        args = self.parser.parse_args()
        self.apply_args(args)

        if self.action == "export":
            self.export_action()
        elif self.action == "list":
            self.list_action()

    def export_action(self):
        if self.export is None:
            if self.verbose:
                print("Nothing to export")
        else:
            job = self.export.create_export_job()
            job.errors = self.errors

            if self.verbose:
                self._track_job_progress(job)

            job.reset = self.reset
            job.execute()

    def _track_job_progress(self, job):

        tasks_count = sum(
            1
            for task in self.export.tasks.itervalues()
            if task["state"] == "pending"
        )

        progress_bar = ProgressBar(tasks_count)

        @when(job.export_ended)
        def show_execution_summary(e):
            progress_bar.finish()
            self.end = time()
            print(
                f"Processed {tasks_count} publications "
                f"and {len(job.dependencies)} dependencies "
                f"in {self.end - self.start:.2f}"
            )

        @when(job.task_starting)
        def task_starting(e):

            progress_bar.label = translations(
                e.task["item"],
                e.task["language"]
            )

            if e.task["language"]:
                progress_bar.label += (
                    " (%s)" % translate_locale(e.task["language"])
                )

            progress_bar.update()

        @when(job.task_successful)
        def task_successful(e):
            progress_bar.label += " => exported"
            progress_bar.update(1)

        @when(job.task_failed)
        def task_failed(e):
            progress_bar.label += " => failed (%s)" % e.task["error_message"]
            progress_bar.update(1)

        @when(job.dependency_transfers_starting)
        def resource_transfers_starting(e):
            progress_bar.total_cycles = len(job.dependencies)
            progress_bar.progress = 0
            progress_bar.label = "Transfering static resources"
            progress_bar.update()

        @when(job.dependency_transfer_starting)
        def resource_transfer_starting(e):
            progress_bar.label = e.resource.source_url

        @when(job.dependency_transfer_successful)
        def resource_transfer_successful(e):
            progress_bar.label += " => exported"
            progress_bar.update(1)

        @when(job.dependency_transfer_failed)
        def resource_transfer_failed(e):
            progress_bar.label += f" => failed ({e.error})"
            progress_bar.update(1)

    def list_action(self):

        tasks = list(self.tasks)
        tasks.sort()

        tasks = defaultdict(
            (lambda: defaultdict(
                (lambda: defaultdict(list))
            ))
        )

        for action, publishable, language in self.tasks:
            tasks[action][publishable.__class__][publishable].append(language)

        for action in sorted(tasks):
            print()
            print(
                styled(
                    action.upper().ljust(120),
                    "white",
                    "green" if action == "post" else "red",
                    "bold"
                )
            )

            for cls, cls_tasks in tasks[action].iteritems():
                cls_label = translations(cls)
                print()
                print(
                    styled(
                        cls_label.ljust(120),
                        "white",
                        "dark_gray",
                        "bold"
                    )
                )

                for publishable, languages in cls_tasks.iteritems():
                    print(str(publishable.id).ljust(10), end=" ")
                    print(
                        styled(
                            translations(
                                publishable,
                                discard_generic_translation=True,
                                language=languages[0]
                            )[:36].ljust(38),
                            "slate_blue"
                        ),
                        end=" "
                    )
                    if languages != [None]:
                        print(styled(", ".join(languages), "pink"))
                    else:
                        print()


class EmptyExport(Exception):
    pass

