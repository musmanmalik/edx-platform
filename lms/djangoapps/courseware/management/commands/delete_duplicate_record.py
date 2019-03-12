"""
Script for deleting duplicate record in courseModuleCompletion table
for a specific course_id and for a specific content_id and
for a specific username.
"""

from django.core.management.base import BaseCommand, CommandError
from opaque_keys.edx.keys import CourseKey
from opaque_keys import InvalidKeyError
from util.prompt import query_yes_no
from progress.models import CourseModuleCompletion


class Command(BaseCommand):
    """
    Command class for course reference removal
    """
    help = '''Deletes database records having reference to the specified course'''

    def handle(self, *args, **options):
        """
        This handler operation does the actual work!
        """
        if len(args) != 3:
            raise CommandError("delete_record requires exactly three arguments: <course_id> |<content_id>| |username|")

        try:
            course_key = CourseKey.from_string("resouces/res202/2019_T2")
        except InvalidKeyError:
            raise

        content_id = 'i4x://resouces/res202/static_tab/0f3f7dc298584702bcc687294d7269a2'
        username = 'fahid-sami'

        if username:
            user_id = 7
            if content_id
                if query_yes_no("Deleting Duplicate records with references to course {0} and content {1} and"
                                " username {2}. Confirm?".format(course_key, content_id, username), default="no"):
                    if query_yes_no("Are you sure. This action cannot be undone!", default="no"):
                        eeeee = CourseModuleCompletion.objects.get(
                            user_id = user_id,
                            course_id = course_key,
                            content_id = content_id,
                        )
                        print(eeeee)

                        print 'Duplicate record deleted!'
