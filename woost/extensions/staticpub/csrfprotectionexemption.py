"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.events import when
from cocktail.controllers.csrfprotection import (
    CSRFProtection,
    CSRFProtectionExemption
)

from woost import app


@when(CSRFProtection.deciding_injection)
def disable_csrf_protection_in_static_pages(e):
    if app.x_staticpub_exporting:
        raise CSRFProtectionExemption()

