# pylint: disable=missing-docstring,unused-argument,broad-except
"""" Common utilities for comment client wrapper """


import logging
from uuid import uuid4

import requests
import six
from django.utils.translation import get_language

from .settings import SERVICE_HOST as COMMENTS_SERVICE

log = logging.getLogger(__name__)


def strip_none(dic):
    return dict([(k, v) for k, v in six.iteritems(dic) if v is not None])


def strip_blank(dic):
    def _is_blank(v):
        return isinstance(v, str) and len(v.strip()) == 0
    return dict([(k, v) for k, v in six.iteritems(dic) if not _is_blank(v)])


def extract(dic, keys):
    if isinstance(keys, str):
        return strip_none({keys: dic.get(keys)})
    else:
        return strip_none({k: dic.get(k) for k in keys})


def perform_request(method, url, data_or_params=None, raw=False,
                    metric_action=None, metric_tags=None, paged_results=False):
    # To avoid dependency conflict
    from openedx.core.djangoapps.django_comment_common.models import ForumsConfig
    config = ForumsConfig.current()

    if not config.enabled:
        raise CommentClientMaintenanceError('service disabled')

    if metric_tags is None:
        metric_tags = []

    metric_tags.append(u'method:{}'.format(method))
    if metric_action:
        metric_tags.append(u'action:{}'.format(metric_action))

    if data_or_params is None:
        data_or_params = {}
    headers = {
        'X-Edx-Api-Key': config.api_key,
        'Accept-Language': get_language(),
    }
    request_id = uuid4()
    request_id_dict = {'request_id': request_id}

    if method in ['post', 'put', 'patch']:
        data = data_or_params
        params = request_id_dict
    else:
        data = None
        params = data_or_params.copy()
        params.update(request_id_dict)
    response = requests.request(
        method,
        url,
        data=data,
        params=params,
        headers=headers,
        timeout=config.connection_timeout
    )

    metric_tags.append(u'status_code:{}'.format(response.status_code))
    status_code = int(response.status_code)
    if status_code > 200:
        metric_tags.append(u'result:failure')
    else:
        metric_tags.append(u'result:success')

    if 200 < status_code < 500:
        log.error(u"Comment Client Request Error on url={url} with error message='{text}' and "
                  u"status_code={status_code}".format(url=url, status_code=response.status_code,
                                                      text=response.text))
        raise CommentClientRequestError(response.text, response.status_code)
    elif status_code in (502, 504):
        log.error(u"Comment Client Gateway Error on url={url} with error message='{text}' and "
                  u"status_code={status_code}".format(url=url, status_code=response.status_code,
                                                      text=response.text))
        raise CommentClientGatewayError(response.text, response.status_code)
    # Heroku returns a 503 when an application is in maintenance mode
    elif status_code == 503:
        log.error(u"Comment Client Maintenance Error on url={url} with error message='{text}' and "
                  u"status_code={status_code}".format(url=url, status_code=response.status_code,
                                                      text=response.text))
        raise CommentClientMaintenanceError(response.text, response.status_code)
    elif status_code == 500:
        log.error(
            u"Comment Client 500 Error on url={url} with error message='{text}' and "
            u"status_code={status_code}".format(
                url=url,
                status_code=response.status_code,
                text=response.text
            )
        )
        raise CommentClient500Error(u"Internal Server Error: {}".format(response.text),
                                    response.status_code)
    else:
        if raw:
            return response.text
        else:
            try:
                data = response.json()
            except ValueError:
                #This error message is modified only for debugging purpose and will be revert back in future.
                raise CommentClientError(
                    u"Invalid JSON response for request {request_id} with status code: {status_code}"
                    u" and response length: {length}; first 100 characters: '{content}'".format(
                        request_id=request_id,
                        content=response.text[:100],
                        length=len(response.text),
                        status_code=response.status_code
                    )
                )
            return data


class CommentClientError(Exception):
    pass


class CommentClientRequestError(CommentClientError):
    def __init__(self, msg, status_codes=400):
        super(CommentClientRequestError, self).__init__(msg)
        self.status_code = status_codes


class CommentClient500Error(CommentClientError):
    def __init__(self, msg, status_code=500):
        super(CommentClient500Error, self).__init__(msg)
        self.status_code = status_code


class CommentClientMaintenanceError(CommentClientError):
    def __init__(self, msg, status_code=503):
        super(CommentClientMaintenanceError, self).__init__(msg)
        self.status_code = status_code


class CommentClientGatewayError(CommentClientError):
    def __init__(self, msg, status_code=502):
        super(CommentClientGatewayError, self).__init__(msg)
        self.status_code = status_code


class CommentClientPaginatedResult(object):
    """ class for paginated results returned from comment services"""

    def __init__(self, collection, page, num_pages, thread_count=0, corrected_text=None):
        self.collection = collection
        self.page = page
        self.num_pages = num_pages
        self.thread_count = thread_count
        self.corrected_text = corrected_text


def check_forum_heartbeat():
    """
    Check the forum connection via its built-in heartbeat service and create an answer which can be used in the LMS
    heartbeat django application.
    This function can be connected to the LMS heartbeat checker through the HEARTBEAT_CHECKS variable.
    """
    # To avoid dependency conflict
    from openedx.core.djangoapps.django_comment_common.models import ForumsConfig
    config = ForumsConfig.current()

    if not config.enabled:
        # If this check is enabled but forums disabled, don't connect, just report no error
        return 'forum', True, 'OK'

    try:
        res = requests.get(
            '%s/heartbeat' % COMMENTS_SERVICE,
            timeout=config.connection_timeout
        ).json()
        if res['OK']:
            return 'forum', True, 'OK'
        else:
            return 'forum', False, res.get('check', 'Forum heartbeat failed')
    except Exception as fail:
        return 'forum', False, six.text_type(fail)
