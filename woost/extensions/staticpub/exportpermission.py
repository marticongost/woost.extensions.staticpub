"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail import schema
from woost.models.permission import Permission, permission_doesnt_match_style
from .destination import Destination


class ExportPermission(Permission):

    members_order = [
        "destinations"
    ]

    destinations = schema.Collection(
        items=schema.Reference(
            type=Destination
        ),
        related_end=schema.Collection()
    )

    def match(self, user, destination, verbose=False):

        if self.destinations and destination not in self.destinations:
            if verbose:
                print(
                    permission_doesnt_match_style("destination doesn't match")
                )
            return False

        return True

