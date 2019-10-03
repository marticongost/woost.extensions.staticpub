"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import sys
import subprocess
from datetime import timedelta

from BTrees.OOBTree import OOBTree
from cocktail import schema
from cocktail.javascriptserializer import JS
from cocktail.events import event_handler
from cocktail.persistence import PersistentMapping
from woost import app
from woost.models import Item, User, Publishable, LocaleMember

export_task_schema = schema.Schema(
    "woost.extensions.staticpub.export.export_task_schema",
    members = [
        schema.Reference(
            "item",
            type=Publishable,
            required=True
        ),
        LocaleMember(
            "language"
        ),
        schema.String(
            "action",
            required=True,
            enumeration=["post", "delete"]
        ),
        schema.String(
            "state",
            required=True,
            enumeration=["pending", "failed", "success"]
        ),
        schema.String(
            "error_message"
        )
    ]
)


class Export(Item):

    type_group = "staticpub"
    instantiable = False

    members_order = [
        "user",
        "destination",
        "state",
        "tasks"
    ]

    user = schema.Reference(
        editable=schema.READ_ONLY,
        type=User,
        related_end=schema.Collection()
    )

    destination = schema.Reference(
        editable=schema.READ_ONLY,
        type="woost.extensions.staticpub.destination.Destination",
        bidirectional=True,
        required=True
    )

    state = schema.String(
        editable=schema.READ_ONLY,
        default="idle",
        enumeration=[
            "idle",
            "running",
            "completed"
        ],
        indexed=True,
        ui_read_only_form_control=JS("""
            (binding) => binding.object.destination._class.state_ui_component
        """)
    )

    tasks = schema.Mapping(
        editable=schema.NOT_EDITABLE,
        searchable=False,
        type=OOBTree,
        keys=schema.Tuple(
            items=(schema.Integer(), LocaleMember())
        ),
        values=export_task_schema
    )

    auth_token = None

    def renew_auth_token(self):
        if self.user:
            self.auth_token = app.authentication.create_auth_token(
                self.user,
                expiration=timedelta(hours=2)
            )
        return self.auth_token

    def add_task(self, action, item, language):

        valid_actions = ("post", "delete")
        if action not in valid_actions:
            raise ValueError(
                f"Invalid export action ({action}); "
                f"should be one of {valid_actions}"
            )

        if not isinstance(item, Publishable):
            raise ValueError(
                f"Can't export ({item:r}); expected an instance of "
                "woost.models.Publishable"
            )

        key = (item.id, language)
        task = self.tasks.get(key)
        if task is None:
            task = PersistentMapping({
                "item": item,
                "language": language
            })
            self.tasks[key] = task

        task["action"] = action
        task["state"] = "pending"
        task["error_message"] = None
        return task

    @property
    def progress(self):

        total = 0
        completed = 0

        for task in self.tasks.itervalues():
            total += 1
            if task["state"] != "pending":
                completed += 1

        if not total:
            return 0.0

        return float(completed) / total

    def create_export_job(self):
        return self.destination.export_job_class(self)

    def execute_in_subprocess(self):
        script = app.path("scripts", "staticpub.py")
        return subprocess.Popen([
            sys.executable,
            script,
            "export",
            f"export:{self.id}"
        ])

    @event_handler
    def handle_changed(e):
        if e.member is Export.state:
            if e.value == "running":
                if e.source.user and not e.source.auth_token:
                    e.source.renew_auth_token()
            elif e.value == "completed":
                if e.source.auth_token:
                    app.authentication.revoke_auth_token(e.source.auth_token)
                    e.source.auth_token = None

