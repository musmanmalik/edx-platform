"""
Signal handlers supporting various gradebook use cases
"""
from django.dispatch import receiver

from xmodule.modulestore.django import SignalHandler
from student.models import CourseAccessRole


@receiver(SignalHandler.course_deleted)
def on_course_deleted(sender, **kwargs):  # pylint: disable=W0613
    """
    Listens for a 'course_deleted' signal and when observed
    removes model entries for the specified course
    """
    course_key = kwargs['course_key']
    CourseAccessRole.objects.filter(course_id=course_key).delete()
