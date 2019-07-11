"""

.. moduleauthor:: Martí Congost <marti.congost@whads.com>
"""


class Exporter:

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def open(self):
        pass

    def close(self):
        pass

    def write_file(self, path, content, content_type=None):
        raise ValueError("Not implemented")

    def delete_file(self, path, content):
        raise ValueError("Not implemented")

