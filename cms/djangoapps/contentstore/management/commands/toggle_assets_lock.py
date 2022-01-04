"""
A Django command that toggles lock for assets of all/given courses.
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

from openedx.core.djangoapps.contentserver.caching import del_cached_content
from xmodule.contentstore.django import contentstore
from xmodule.modulestore.django import modulestore

logger = logging.getLogger(__name__)  # pylint: disable=locally-disabled, invalid-name


class Command(BaseCommand):
    """
    Toggle lock for assets of all/given courses.
    """
    def add_arguments(self, parser):
        parser.add_argument('--course-id', dest='course_id')
        lock_parser = parser.add_mutually_exclusive_group(required=False)
        lock_parser.add_argument('--lock', dest='locked', action='store_true')
        lock_parser.add_argument('--unlock', dest='locked', action='store_false')
        parser.set_defaults(locked=True)

    def handle(self, *args, **options):
        course_id = options.get('course_id', None)
        locked = options.get('locked', True)
        if course_id:
            try:
                course_key = CourseKey.from_string(course_id)
            except InvalidKeyError:
                raise CommandError("Invalid course_id: '%s'." % course_id)

            toggle_course_assets_lock(course_key, locked)
        else:
            courses = modulestore().get_courses()
            for course in courses:
                toggle_course_assets_lock(course.id, locked)


def toggle_course_assets_lock(course_key, locked):
    """Toggle course assets lock"""
    content_store = contentstore()
    assets, __ = content_store.get_all_content_for_course(course_key)

    for asset in assets:
        content_store.set_attr(asset['asset_key'], 'locked', locked)
        # Delete the asset from the cache so that asset is locked/unlocked the next time it is requested.
        del_cached_content(asset['asset_key'])

    logger.info('Assets for course: {} successfully {}'.format(course_key, 'locked' if locked else 'unlocked'))
