"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.events import when
from cocktail.caching import whole_cache
from woost.models import Item, User, Publishable

from .destination import Destination
from .utils import iter_exportable_languages

members_affecting_publication_state = {
    Publishable.enabled,
    Publishable.enabled_translations,
    Publishable.per_language_publication,
    Publishable.access_level,
    Publishable.x_staticpub_exportable
}


@when(Publishable.changing)
def _track_publication_state(e):
    if (
        e.source.is_inserted
        and e.member in members_affecting_publication_state
    ):
        e.static_pub_published_languages = \
            set(iter_exportable_languages(e.source))


@when(Publishable.changed)
def _schedule_publication_state_updates(e):
    if (
        e.source.is_inserted
        and e.member in members_affecting_publication_state
    ):
        prev_languages = getattr(e, "static_pub_published_languages", None)

        if prev_languages is not None:
            current_languages = set(iter_exportable_languages(e.source))
            additions = current_languages - prev_languages
            deletions = prev_languages - current_languages

            for destination in Destination.select():

                for lang in additions:
                    destination.set_pending_task(e.source, lang, "add")

                for lang in deletions:
                    destination.set_pending_task(e.source, lang, "del")


@when(Item.inserted)
def _invalidation_after_object_inserted(e):
    for destination in Destination.select():
        destination.invalidate_exported_content(e.source)


@when(Item.changed)
def _invalidate_modified_objects(e):
    if (
        e.source.is_inserted
        and e.member.invalidates_cache
    ):
        for destination in Destination.select():
            destination.invalidate_exported_content(
                e.source,
                language=e.language,
                cache_part=e.member.cache_part
            )


@when(Item.deleted)
def _invalidate_deleted_objects(e):
    for destination in Destination.select():
        destination.invalidate_exported_content(e.source)


@when(Item.removing_translation)
def _invalidation_after_translation_removed(e):
    if e.source.is_inserted:
        for destination in Destination.select():
            destination.invalidate_exported_content(
                e.source,
                language=e.language
            )


@when(Destination.inserted)
def _invalidate_everything(e):
    e.source._invalidate_exported_scope(whole_cache, "add")

