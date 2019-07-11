"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from woost.app import ContextualProperty


class XStaticpubExportingProperty(ContextualProperty):
    """Indicates whether the current context is responding to a request by the
    static publisher.

    Checking the value of this makes it possible for views and controllers to
    behave differently when generating static content.
    """

