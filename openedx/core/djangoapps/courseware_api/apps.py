"""
Courseware API Application Configuration

Signal handlers are connected here.
"""


from django.apps import AppConfig

from openedx.core.djangoapps.plugins.constants import PluginURLs, ProjectType


class CoursewareAPIConfig(AppConfig):
    """
    AppConfig for courseware API app
    """
    name = 'openedx.core.djangoapps.courseware_api'
    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: 'courseware_api',
                PluginURLs.REGEX: 'api/courseware/',
                PluginURLs.RELATIVE_PATH: 'urls',
            }
        },
    }
