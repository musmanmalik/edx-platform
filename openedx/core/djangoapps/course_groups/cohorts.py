"""
This file contains the logic for cohorts, as exposed internally to the
forums, and to the cohort admin views.
"""


import logging
import random

import six
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.http import Http404
from django.utils.translation import ugettext as _
from edx_django_utils.cache import RequestCache
from eventtracking import tracker

from lms.djangoapps.courseware import courses
from openedx.core.lib.cache_utils import request_cached
from student.models import get_user_by_username_or_email, CourseAccessRole

from .models import (
    CohortMembership,
    CourseCohort,
    CourseCohortsSettings,
    CourseUserGroup,
    CourseUserGroupPartitionGroup,
    UnregisteredLearnerCohortAssignments
)
from .signals.signals import COHORT_MEMBERSHIP_UPDATED


class AlreadyAddedToCohortException(ValueError):
    """
    Raised when an attempt is made to add user to a cohort he's already added to
    """
    pass


log = logging.getLogger(__name__)


@receiver(post_save, sender=CourseUserGroup)
def _cohort_added(sender, **kwargs):
    """Emits a tracking log event each time a cohort is created"""
    instance = kwargs["instance"]
    if kwargs["created"] and instance.group_type == CourseUserGroup.COHORT:
        tracker.emit(
            "edx.cohort.created",
            {"cohort_id": instance.id, "cohort_name": instance.name}
        )


@receiver(m2m_changed, sender=CourseUserGroup.users.through)
def _cohort_membership_changed(sender, **kwargs):
    """Emits a tracking log event each time cohort membership is modified"""
    def get_event_iter(user_id_iter, cohort_iter):
        """
        Returns a dictionary containing a mashup of cohort and user information for the given lists
        """
        return (
            {"cohort_id": cohort.id, "cohort_name": cohort.name, "user_id": user_id}
            for user_id in user_id_iter
            for cohort in cohort_iter
        )

    action = kwargs["action"]
    instance = kwargs["instance"]
    pk_set = kwargs["pk_set"]
    reverse = kwargs["reverse"]

    if action == "post_add":
        event_name = "edx.cohort.user_added"
    elif action in ["post_remove", "pre_clear"]:
        event_name = "edx.cohort.user_removed"
    else:
        return

    if reverse:
        user_id_iter = [instance.id]
        if action == "pre_clear":
            cohort_iter = instance.course_groups.filter(group_type=CourseUserGroup.COHORT)
        else:
            cohort_iter = CourseUserGroup.objects.filter(pk__in=pk_set, group_type=CourseUserGroup.COHORT)
    else:
        cohort_iter = [instance] if instance.group_type == CourseUserGroup.COHORT else []
        if action == "pre_clear":
            user_id_iter = (user.id for user in instance.users.all())
        else:
            user_id_iter = pk_set

    for event in get_event_iter(user_id_iter, cohort_iter):
        tracker.emit(event_name, event)


# A 'default cohort' is an auto-cohort that is automatically created for a course if no cohort with automatic
# assignment have been specified. It is intended to be used in a cohorted course for users who have yet to be assigned
# to a cohort, if the course staff have not explicitly created a cohort of type "RANDOM".
# Note that course staff have the ability to change the name of this cohort after creation via the cohort
# management UI in the instructor dashboard.
DEFAULT_COHORT_NAME = _("Default Group")


# tl;dr: global state is bad.  capa reseeds random every time a problem is loaded.  Even
# if and when that's fixed, it's a good idea to have a local generator to avoid any other
# code that messes with the global random module.
_local_random = None


def local_random():
    """
    Get the local random number generator.  In a function so that we don't run
    random.Random() at import time.
    """
    # ironic, isn't it?
    global _local_random

    if _local_random is None:
        _local_random = random.Random()

    return _local_random


def is_course_cohorted(course_key):
    """
    Given a course key, return a boolean for whether or not the course is
    cohorted.

    Raises:
       Http404 if the course doesn't exist.
    """
    return _get_course_cohort_settings(course_key).is_cohorted


def get_course_cohort_id(course_key):
    """
    Given a course key, return the int id for the cohort settings.

    Raises:
        Http404 if the course doesn't exist.
    """
    return _get_course_cohort_settings(course_key).id


def set_course_cohorted(course_key, cohorted):
    """
    Given a course course and a boolean, sets whether or not the course is cohorted.

    Raises:
        Value error if `cohorted` is not a boolean
    """
    if not isinstance(cohorted, bool):
        raise ValueError("Cohorted must be a boolean")
    course_cohort_settings = _get_course_cohort_settings(course_key)
    course_cohort_settings.is_cohorted = cohorted
    course_cohort_settings.save()


def get_cohort_id(user, course_key, use_cached=False):
    """
    Given a course key and a user, return the id of the cohort that user is
    assigned to in that course.  If they don't have a cohort, return None.
    """
    cohort = get_cohort(user, course_key, use_cached=use_cached)
    return None if cohort is None else cohort.id


COHORT_CACHE_NAMESPACE = u"cohorts.get_cohort"


def _cohort_cache_key(user_id, course_key):
    """
    Returns the cache key for the given user_id and course_key.
    """
    return u"{}.{}".format(user_id, course_key)


def bulk_cache_cohorts(course_key, users):
    """
    Pre-fetches and caches the cohort assignments for the
    given users, for later fast retrieval by get_cohort.
    """
    # before populating the cache with another bulk set of data,
    # remove previously cached entries to keep memory usage low.
    RequestCache(COHORT_CACHE_NAMESPACE).clear()
    cache = RequestCache(COHORT_CACHE_NAMESPACE).data

    if is_course_cohorted(course_key):
        cohorts_by_user = {
            membership.user: membership
            for membership in
            CohortMembership.objects.filter(user__in=users, course_id=course_key).select_related('user')
        }
        for user, membership in six.iteritems(cohorts_by_user):
            cache[_cohort_cache_key(user.id, course_key)] = membership.course_user_group
        uncohorted_users = [u for u in users if u not in cohorts_by_user]
    else:
        uncohorted_users = users

    for user in uncohorted_users:
        cache[_cohort_cache_key(user.id, course_key)] = None


def get_cohort(user, course_key, assign=True, use_cached=False):
    """
    Returns the user's cohort for the specified course.

    The cohort for the user is cached for the duration of a request. Pass
    use_cached=True to use the cached value instead of fetching from the
    database.

    Arguments:
        user: a Django User object.
        course_key: CourseKey
        assign (bool): if False then we don't assign a group to user
        use_cached (bool): Whether to use the cached value or fetch from database.

    Returns:
        A CourseUserGroup object if the course is cohorted and the User has a
        cohort, else None.

    Raises:
       ValueError if the CourseKey doesn't exist.
    """
    if user is None or user.is_anonymous:
        return None
    cache = RequestCache(COHORT_CACHE_NAMESPACE).data
    cache_key = _cohort_cache_key(user.id, course_key)

    if use_cached and cache_key in cache:
        return cache[cache_key]

    cache.pop(cache_key, None)

    # First check whether the course is cohorted (users shouldn't be in a cohort
    # in non-cohorted courses, but settings can change after course starts)
    if not is_course_cohorted(course_key):
        return cache.setdefault(cache_key, None)

    # If course is cohorted, check if the user already has a cohort.
    try:
        membership = CohortMembership.objects.get(
            course_id=course_key,
            user_id=user.id,
        )
        return cache.setdefault(cache_key, membership.course_user_group)
    except CohortMembership.DoesNotExist:
        # Didn't find the group. If we do not want to assign, return here.
        if not assign:
            # Do not cache the cohort here, because in the next call assign
            # may be True, and we will have to assign the user a cohort.
            return None

    # Otherwise assign the user a cohort.
    try:
        # If learner has been pre-registered in a cohort, get that cohort. Otherwise assign to a random cohort.
        course_user_group = None
        for assignment in UnregisteredLearnerCohortAssignments.objects.filter(email=user.email, course_id=course_key):
            course_user_group = assignment.course_user_group
            assignment.delete()
            break
        else:
            is_user_staff = CourseAccessRole.objects.filter(user=user, course_id=course_key, role='staff').exists()
            course_user_group = get_default_cohort(course_key) if is_user_staff else get_random_cohort(course_key)
        add_user_to_cohort(course_user_group, user)
        return course_user_group
    except ValueError:
        # user already in cohort
        return course_user_group
    except IntegrityError as integrity_error:
        # An IntegrityError is raised when multiple workers attempt to
        # create the same row in one of the cohort model entries:
        # CourseCohort, CohortMembership.
        log.info(
            u"HANDLING_INTEGRITY_ERROR: IntegrityError encountered for course '%s' and user '%s': %s",
            course_key, user.id, six.text_type(integrity_error)
        )
        return get_cohort(user, course_key, assign, use_cached)


def get_default_cohort(course_key):
    try:
        cohort = get_cohort_by_name(course_key, CourseUserGroup.default_cohort_name)
    except CourseUserGroup.DoesNotExist:
        cohort = add_cohort(course_key, CourseUserGroup.default_cohort_name, CourseCohort.MANUAL)
    return cohort


def get_random_cohort(course_key):
    """
    Helper method to get a cohort for random assignment.

    If there are multiple cohorts of type RANDOM in the course, one of them will be randomly selected.
    If there are no existing cohorts of type RANDOM in the course, one will be created.
    """
    course = courses.get_course(course_key)
    cohorts = get_course_cohorts(course, assignment_type=CourseCohort.RANDOM)
    if cohorts:
        cohort = local_random().choice(cohorts)
    else:
        cohort = CourseCohort.create(
            cohort_name=DEFAULT_COHORT_NAME,
            course_id=course_key,
            assignment_type=CourseCohort.RANDOM
        ).course_user_group
    return cohort


def migrate_cohort_settings(course):
    """
    Migrate all the cohort settings associated with this course from modulestore to mysql.
    After that we will never touch modulestore for any cohort related settings.
    """
    cohort_settings, created = CourseCohortsSettings.objects.get_or_create(
        course_id=course.id,
        defaults=_get_cohort_settings_from_modulestore(course)
    )

    # Add the new and update the existing cohorts
    if created:
        # Update the manual cohorts already present in CourseUserGroup
        manual_cohorts = CourseUserGroup.objects.filter(
            course_id=course.id,
            group_type=CourseUserGroup.COHORT
        ).exclude(name__in=course.auto_cohort_groups)
        for cohort in manual_cohorts:
            CourseCohort.create(course_user_group=cohort)

        for group_name in course.auto_cohort_groups:
            CourseCohort.create(cohort_name=group_name, course_id=course.id, assignment_type=CourseCohort.RANDOM)

    return cohort_settings


def get_course_cohorts(course=None, course_id=None, assignment_type=None):
    """
    Get a list of all the cohorts in the given course. This will include auto cohorts,
    regardless of whether or not the auto cohorts include any users.

    Arguments:
        course: the course for which cohorts should be returned
        assignment_type: cohort assignment type

    Returns:
        A list of CourseUserGroup objects. Empty if there are no cohorts. Does
        not check whether the course is cohorted.
    """
    assert bool(course) ^ bool(course_id), "course or course_id required"
    # Migrate cohort settings for this course
    if course:
        migrate_cohort_settings(course)
        course_id = course.location.course_key

    query_set = CourseUserGroup.objects.filter(
        course_id=course_id,
        group_type=CourseUserGroup.COHORT
    )
    query_set = query_set.filter(cohort__assignment_type=assignment_type) if assignment_type else query_set
    return list(query_set)


def get_cohort_names(course):
    """Return a dict that maps cohort ids to names for the given course"""
    return {cohort.id: cohort.name for cohort in get_course_cohorts(course)}


# Helpers for cohort management views


def get_cohort_by_name(course_key, name):
    """
    Return the CourseUserGroup object for the given cohort.  Raises DoesNotExist
    it isn't present.
    """
    return CourseUserGroup.objects.get(
        course_id=course_key,
        group_type=CourseUserGroup.COHORT,
        name=name
    )


def get_cohort_by_id(course_key, cohort_id):
    """
    Return the CourseUserGroup object for the given cohort.  Raises DoesNotExist
    it isn't present.  Uses the course_key for extra validation.
    """
    return CourseUserGroup.objects.get(
        course_id=course_key,
        group_type=CourseUserGroup.COHORT,
        id=cohort_id
    )


def add_cohort(course_key, name, assignment_type):
    """
    Add a cohort to a course.  Raises ValueError if a cohort of the same name already
    exists.
    """
    log.debug(u"Adding cohort %s to %s", name, course_key)
    if is_cohort_exists(course_key, name):
        raise ValueError(_("You cannot create two cohorts with the same name"))

    try:
        course = courses.get_course_by_id(course_key)
    except Http404:
        raise ValueError("Invalid course_key")

    cohort = CourseCohort.create(
        cohort_name=name,
        course_id=course.id,
        assignment_type=assignment_type
    ).course_user_group

    tracker.emit(
        "edx.cohort.creation_requested",
        {"cohort_name": cohort.name, "cohort_id": cohort.id}
    )
    return cohort


def is_cohort_exists(course_key, name):
    """
    Check if a cohort already exists.
    """
    return CourseUserGroup.objects.filter(course_id=course_key, group_type=CourseUserGroup.COHORT, name=name).exists()


def remove_user_from_cohort(cohort, username_or_email):
    """
    Look up the given user, and if successful, remove them from the specified cohort.

    Arguments:
        cohort: CourseUserGroup
        username_or_email: string.  Treated as email if has '@'

    Raises:
        User.DoesNotExist if can't find user.
        ValueError if user not already present in this cohort.
    """
    user = get_user_by_username_or_email(username_or_email)

    try:
        membership = CohortMembership.objects.get(course_user_group=cohort, user=user)
        course_key = membership.course_id
        membership.delete()
        COHORT_MEMBERSHIP_UPDATED.send(sender=None, user=user, course_key=course_key)
    except CohortMembership.DoesNotExist:
        raise ValueError(u"User {} was not present in cohort {}".format(username_or_email, cohort))


def add_user_to_cohort(cohort, username_or_email_or_user):
    """
    Look up the given user, and if successful, add them to the specified cohort.

    Arguments:
        cohort: CourseUserGroup
        username_or_email_or_user: user or string.  Treated as email if has '@'

    Returns:
        User object (or None if the email address is preassigned),
        string (or None) indicating previous cohort,
        and whether the user is a preassigned user or not

    Raises:
        User.DoesNotExist if can't find user. However, if a valid email is provided for the user, it is stored
        in a database so that the user can be added to the cohort if they eventually enroll in the course.
        ValueError if user already present in this cohort.
        ValidationError if an invalid email address is entered.
        User.DoesNotExist if a user could not be found.
    """
    try:
        if hasattr(username_or_email_or_user, 'email'):
            user = username_or_email_or_user
        else:
            user = get_user_by_username_or_email(username_or_email_or_user)

        membership, previous_cohort = CohortMembership.assign(cohort, user)
        tracker.emit(
            "edx.cohort.user_add_requested",
            {
                "user_id": user.id,
                "cohort_id": cohort.id,
                "cohort_name": cohort.name,
                "previous_cohort_id": getattr(previous_cohort, 'id', None),
                "previous_cohort_name": getattr(previous_cohort, 'name', None),
            }
        )
        cache = RequestCache(COHORT_CACHE_NAMESPACE).data
        cache_key = _cohort_cache_key(user.id, membership.course_id)
        cache[cache_key] = membership.course_user_group
        COHORT_MEMBERSHIP_UPDATED.send(sender=None, user=user, course_key=membership.course_id)
        return user, getattr(previous_cohort, 'name', None), False
    except User.DoesNotExist as ex:
        # If username_or_email is an email address, store in database.
        try:
            validate_email(username_or_email_or_user)

            try:
                assignment = UnregisteredLearnerCohortAssignments.objects.get(
                    email=username_or_email_or_user, course_id=cohort.course_id
                )
                assignment.course_user_group = cohort
                assignment.save()
            except UnregisteredLearnerCohortAssignments.DoesNotExist:
                assignment = UnregisteredLearnerCohortAssignments.objects.create(
                    course_user_group=cohort, email=username_or_email_or_user, course_id=cohort.course_id
                )

            tracker.emit(
                "edx.cohort.email_address_preassigned",
                {
                    "user_email": assignment.email,
                    "cohort_id": cohort.id,
                    "cohort_name": cohort.name,
                }
            )

            return (None, None, True)
        except ValidationError as invalid:
            if "@" in username_or_email_or_user:
                raise invalid
            else:
                raise ex


def is_user_in_cohort(cohort, user_id, group_type=CourseUserGroup.COHORT):
    """
    Returns True or False if a user is in a cohort
    """
    return CourseUserGroup.objects.filter(
        course_id=cohort.course_id,
        users__id=user_id,
        group_type=group_type).exists()


def get_group_info_for_cohort(cohort, use_cached=False):
    """
    Get the ids of the group and partition to which this cohort has been linked
    as a tuple of (int, int).

    If the cohort has not been linked to any group/partition, both values in the
    tuple will be None.

    The partition group info is cached for the duration of a request. Pass
    use_cached=True to use the cached value instead of fetching from the
    database.
    """
    cache = RequestCache(u"cohorts.get_group_info_for_cohort").data
    cache_key = six.text_type(cohort.id)

    if use_cached and cache_key in cache:
        return cache[cache_key]

    cache.pop(cache_key, None)

    try:
        partition_group = CourseUserGroupPartitionGroup.objects.get(course_user_group=cohort)
        return cache.setdefault(cache_key, (partition_group.group_id, partition_group.partition_id))
    except CourseUserGroupPartitionGroup.DoesNotExist:
        pass

    return cache.setdefault(cache_key, (None, None))


def set_assignment_type(user_group, assignment_type):
    """
    Set assignment type for cohort.
    """
    course_cohort = user_group.cohort

    if is_last_random_cohort(user_group) and course_cohort.assignment_type != assignment_type:
        raise ValueError(_("There must be one cohort to which students can automatically be assigned."))

    course_cohort.assignment_type = assignment_type
    course_cohort.save()


def get_assignment_type(user_group):
    """
    Get assignment type for cohort.
    """
    course_cohort = user_group.cohort
    return course_cohort.assignment_type


def is_last_random_cohort(user_group):
    """
    Check if this cohort is the only random cohort in the course.
    """
    random_cohorts = CourseUserGroup.objects.filter(
        course_id=user_group.course_id,
        group_type=CourseUserGroup.COHORT,
        cohort__assignment_type=CourseCohort.RANDOM
    )

    return len(random_cohorts) == 1 and random_cohorts[0].name == user_group.name


@request_cached()
def _get_course_cohort_settings(course_key):
    """
    Return cohort settings for a course. NOTE that the only non-deprecated fields in
    CourseCohortSettings are `course_id` and  `is_cohorted`. Other fields should only be used for
    migration purposes.

    Arguments:
        course_key: CourseKey

    Returns:
        A CourseCohortSettings object. NOTE that the only non-deprecated field in
        CourseCohortSettings are `course_id` and  `is_cohorted`. Other fields should only be used
        for migration purposes.

    Raises:
        Http404 if course_key is invalid.
    """
    try:
        course_cohort_settings = CourseCohortsSettings.objects.get(course_id=course_key)
    except CourseCohortsSettings.DoesNotExist:
        course = courses.get_course_by_id(course_key)
        course_cohort_settings = migrate_cohort_settings(course)
    return course_cohort_settings


class CohortConflict(Exception):
    """
    Raised when user to be added is already in another cohort in same course.
    """
    pass


def get_course_cohort_names(course_key):
    """
    Return a list of the cohort names in a course.
    """
    course = courses.get_course_by_id(course_key)
    return [c.name for c in get_course_cohorts(course)]


def delete_empty_cohort(course_key, name):
    """
    Remove an empty cohort.  Raise ValueError if cohort is not empty.
    """
    cohort = get_cohort_by_name(course_key, name)
    if cohort.users.exists():
        raise ValueError(
            "Can't delete non-empty cohort {0} in course {1}".format(
                name, course_key))

    cohort.delete()


def get_legacy_discussion_settings(course_key):

    try:
        course_cohort_settings = CourseCohortsSettings.objects.get(course_id=course_key)
        return {
            'is_cohorted': course_cohort_settings.is_cohorted,
            'cohorted_discussions': course_cohort_settings.cohorted_discussions,
            'always_cohort_inline_discussions': course_cohort_settings.always_cohort_inline_discussions
        }
    except CourseCohortsSettings.DoesNotExist:
        course = courses.get_course_by_id(course_key)
        return _get_cohort_settings_from_modulestore(course)


def _get_cohort_settings_from_modulestore(course):
    return {
        'is_cohorted': course.is_cohorted,
        'cohorted_discussions': list(course.cohorted_discussions),
        'always_cohort_inline_discussions': course.always_cohort_inline_discussions
    }


def get_cohort_user_ids(user_id, course_key, **kwargs):
    """
    Get cohort from course identified by `course_key` in which member `user_id` is present
    and return list of all its members' ids.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None

    cohort = get_cohort(user, course_key, **kwargs)
    try:
        return cohort.users.values_list('id', flat=True)
    except AttributeError:
        return None
