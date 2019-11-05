"""
Module for code that should run during Studio startup (deprecated)
"""

import django
#import logging
from django.conf import settings

# Force settings to run so that the python path is modified
settings.INSTALLED_APPS  # pylint: disable=pointless-statement

# TODO: Move this commented code in edx-notifications apps.py
# # edx notifications related imports
# from student.scope_resolver import CourseEnrollmentsScopeResolver, StudentEmailScopeResolver
# from openedx.core.djangoapps.course_groups.scope_resolver import CourseGroupScopeResolver
# from edx_solutions_projects.scope_resolver import GroupProjectParticipantsScopeResolver
# from edx_notifications.scopes import register_user_scope_resolver
# from edx_notifications.namespaces import register_namespace_resolver
# from util.namespace_resolver import CourseNamespaceResolver
# from edx_notifications import startup
#
# log = logging.getLogger(__name__)


def run():
    """
    Executed during django startup

    NOTE: DO **NOT** add additional code to this method or this file! The Platform Team
          is moving all startup code to more standard locations using Django best practices.
    """
    django.setup()

#     if settings.FEATURES.get('ENABLE_NOTIFICATIONS', False):
#         startup_notification_subsystem()
#
#     if settings.FEATURES.get('EDX_SOLUTIONS_API', False) and \
#             settings.FEATURES.get('DISABLE_SOLUTIONS_APPS_SIGNALS', False):
#         disable_solutions_apps_signals()
#
#
# def disable_solutions_apps_signals():
#     """
#     Disables signals receivers in solutions apps
#     """
#     from edx_solutions_api_integration.test_utils import SignalDisconnectTestMixin
#     SignalDisconnectTestMixin.disconnect_signals()
#
#
# def startup_notification_subsystem():
#     """
#     Initialize the Notification subsystem
#     """
#     try:
#         startup.initialize()
#
#         # register the scope resolvers that the runtime will be providing
#         # to edx-notifications
#         register_user_scope_resolver('course_enrollments', CourseEnrollmentsScopeResolver())
#         register_user_scope_resolver('course_group', CourseGroupScopeResolver())
#         register_user_scope_resolver('group_project_participants', GroupProjectParticipantsScopeResolver())
#         register_user_scope_resolver('group_project_workgroup', GroupProjectParticipantsScopeResolver())
#         register_user_scope_resolver('student_email_resolver', StudentEmailScopeResolver())
#
#         # register namespace resolver
#         register_namespace_resolver(CourseNamespaceResolver())
#     except Exception, ex:
#         # Note this will fail when we try to run migrations as manage.py will call startup.py
#         # and startup.initialze() will try to manipulate some database tables.
#         # We need to research how to identify when we are being started up as part of
#         # a migration script
#         log.error(
#             'There was a problem initializing notifications subsystem. '
#             'This could be because the database tables have not yet been created and '
#             './manage.py lms syncdb needs to run setup.py. Error was "{err_msg}". Continuing...'.format(err_msg=str(ex))
#         )
#
