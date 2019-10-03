"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail.stringutils import normalize_indentation
from woost import app
from woost.models import (
    Configuration,
    Website,
    Role,
    Publishable,
    get_publishable_models
)

from .exportpermission import ExportPermission


EXPORT_SCRIPT_TEMPLATE = normalize_indentation(
    """
    #!/usr/bin/env python
    import %(package)s.scripts.shell
    from woost.extensions.staticpub.cli import CLI

    if __name__ == "__main__":
        CLI().main()
    """
).lstrip()


def install():
    """Creates the assets required by the staticpub extension."""
    create_export_script()
    create_default_permissions()
    set_exportable_flag()


def create_export_script():
    script_path = app.path("scripts", "staticpub.py")
    with open(script_path, "w") as script_file:
        script_file.write(
            EXPORT_SCRIPT_TEMPLATE
            % {"package": app.package}
        )


def create_default_permissions():
    admins = Role.require_instance(qname="woost.administrators")
    for permission in admins.permissions:
        if isinstance(permission, ExportPermission):
            break
    else:
        permission = ExportPermission.new()
        admins.permissions.append(permission)


def set_exportable_flag():

    for item in [Configuration.instance] + list(Website.select()):
        for key in (
            "login_page",
            "maintenance_page",
            "generic_error_page",
            "not_found_error_page",
            "forbidden_error_page"
        ):
            page = getattr(item, key, None)
            if page:
                page.x_staticpub_exportable = False

        for qname in (
            "woost.password_change_page",
            "woost.password_change_confirmation_page"
        ):
            page = Publishable.get_instance(qname=qname)
            if page:
                page.included_in_static_publication = False

    for cls in get_publishable_models():
        member = cls.get_member("x_staticpub_exportable")
        if member and member.indexed:
            member.rebuild_index()

