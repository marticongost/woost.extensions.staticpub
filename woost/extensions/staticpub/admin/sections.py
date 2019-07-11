"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.events import when
from cocktail.translations import translations
from woost.admin.sections import Folder, CRUD, Settings
from woost.admin.sections.publicationsection import PublicationSection

from woost.extensions.staticpub.destination import Destination
from woost.extensions.staticpub.export import Export

translations.load_bundle("woost.extensions.staticpub.admin.sections")


class StaticpubSettings(Settings):

    members = [
        "x_staticpub_default_dest"
    ]


class StaticpubSection(Folder):

    icon_uri = (
        "woost.extensions.staticpub.admin.ui://"
        "images/sections/staticpub.svg"
    )

    def _fill(self):
        self.append(StaticpubSettings("settings"))
        self.append(CRUD("destinations", model=Destination))
        self.append(CRUD("export", model=Export))


@when(PublicationSection.declared)
def _add_static_pub(e):
    e.source.append(StaticpubSection("x_staticpub"))

