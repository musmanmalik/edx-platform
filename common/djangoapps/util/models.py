"""Models for the util app. """

import base64
import gzip
import logging
from io import BytesIO

import six
from config_models.models import ConfigurationModel
from django.db import models
from django.utils.text import compress_string

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class RateLimitConfiguration(ConfigurationModel):
    """
    Configuration flag to enable/disable rate limiting.

    Applies to Django Rest Framework views.

    This is useful for disabling rate limiting for performance tests.
    When enabled, it will disable rate limiting on any view decorated
    with the `can_disable_rate_limit` class decorator.

    .. no_pii:
    """
    class Meta(ConfigurationModel.Meta):
        app_label = "util"


def decompress_string(value):
    """
    Helper function to reverse CompressedTextField.get_prep_value.
    """

    try:
        val = base64.b64decode(value.encode('utf8'))
        zbuf = BytesIO(val)
        zfile = gzip.GzipFile(fileobj=zbuf)
        ret = zfile.read().decode('utf8')
        zfile.close()
    except Exception as e:
        logger.error('String decompression failed. There may be corrupted data in the database: %s', e)
        ret = value
    return ret


class CompressedTextField(models.TextField):
    """
    TextField that transparently compresses data when saving to the database, and decompresses the data
    when retrieving it from the database.
    """

    def get_prep_value(self, value):
        """
        Compress the text data.
        """
        if value is not None:
            if isinstance(value, six.text_type):
                value = value.encode('utf8')
            value = compress_string(value)
            value = base64.b64encode(value).decode('utf8')
        return value

    def to_python(self, value):
        """
        Decompresses the value from the database.
        """
        if isinstance(value, six.text_type):
            value = decompress_string(value)

        return value

    def from_db_value(self, value, expression, connection):  # pylint: disable=unused-argument
        return self.to_python(value)
