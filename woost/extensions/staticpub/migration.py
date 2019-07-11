"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.persistence import migration_step, datastore

@migration_step
def preserve_woost2_info(e):

    from woost.models import Configuration, Publishable

    # Rename the staticpub_default_dest member
    config = Configuration.instance
    try:
        default_dest = config._staticpub_default_dest
    except AttributeError:
        pass
    else:
        del config._staticpub_default_dest
        del default_dest._Configuration_staticpub_default_dest
        config.x_staticpub_default_dest = default_dest

    # Rename the 'included_in_static_publication' member
    datastore.root.pop(
        "woost.models.item.Item.included_in_static_publication",
        None
    )

    for pub in Publishable.select():
        value = pub._included_in_static_publication
        try:
            del pub._included_in_static_publication
        except AttributeError:
            pass
        else:
            pub.x_staticpub_exportable = value

