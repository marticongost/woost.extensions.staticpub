"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
from cocktail import schema
from .destination import Destination
from .amazons3exporter import AmazonS3Exporter


class AmazonS3Destination(Destination):

    exporter_class = AmazonS3Exporter

    members_order = [
        "aws_access_key",
        "aws_secret_key",
        "aws_profile",
        "bucket_name",
        "prefix"
    ]

    aws_access_key = schema.String(
        listed_by_default=False
    )

    aws_secret_key = schema.String(
        listed_by_default=False
    )

    aws_profile = schema.String(
        listed_by_default=False
    )

    bucket_name = schema.String(
        required=True,
        listed_by_default=False
    )

    prefix = schema.String(
        listed_by_default=False,
        before_member="website_prefixes"
    )

    def get_export_path(self, url, resolution = None):
        path = Destination.get_export_path(self, url, resolution)
        if self.prefix:
            path = self.prefix.strip("/").split("/") + path
        return path

    def create_exporter(self):

        session_parameters = {}

        if self.aws_access_key:
            session_parameters["aws_access_key_id"] = self.aws_access_key

        if self.aws_secret_key:
            session_parameters["aws_secret_access_key"] = self.aws_secret_key

        if self.aws_profile:
            session_parameters["profile_name"] = self.profile_name

        return self.exporter_class(self.bucket_name, session_parameters)

