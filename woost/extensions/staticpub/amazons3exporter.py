"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""
try:
    import boto3
except ImportError:
    boto3 = None

from .exporter import Exporter


class AmazonS3Exporter(Exporter):

    bucket_name = None
    session_parameters = None
    connection = None
    bucket = None

    def __init__(self, bucket_name, session_parameters = None):
        self.bucket_name = bucket_name
        self.session_parameters = session_parameters or {}

    def open(self):

        if boto3 is None:
            raise ImportError("The 'boto3' package is not available")

        self.session = boto3.Session(**self.session_parameters)
        self.s3 = self.session.resource("s3")

    def write_file(self, path, content, content_type = None):

        if isinstance(content, unicode):
            content = content.encode("utf-8")

        key = self.s3.Object(
            self.bucket_name,
            u"/".join(path)
        )

        kwargs = {"Body": content}
        if content_type:
            kwargs["ContentType"] = content_type

        key.put(**kwargs)

    def remove_file(self, path):
        key = self.s3.Object(
            self.bucket_name,
            u"/".join(path)
        )
        key.delete()

