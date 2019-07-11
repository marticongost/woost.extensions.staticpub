"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.translations import translations
from cocktail import schema
from woost.models import add_setting, Configuration

from .destination import Destination

translations.load_bundle("woost.extensions.staticpub.settings")

add_setting(
    schema.Reference(
        "x_staticpub_default_dest",
        type=Destination
    ),
    scopes=(Configuration,)
)

