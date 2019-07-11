"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
import cherrypy
from cocktail.translations import get_language
from woost import app
from woost.controllers.publishablecontroller import PublishableController

# Make PublishableController export an X-Woost-Tags header during static
# exports

PublishableController.cached_headers += ("X-Woost-Cache-Tags",)

base_produce_content = PublishableController._produce_content

def _produce_content(self, **kwargs):

    content = base_produce_content(self, **kwargs)

    if app.x_staticpub_exporting and self.view:
        tags = app.publishable.get_cache_tags(language=get_language())
        if self.view:
            tags.update(self.view.cache_tags)
        cherrypy.response.headers["X-Woost-Cache-Tags"] = " ".join(tags)

    return content

PublishableController._produce_content = _produce_content

