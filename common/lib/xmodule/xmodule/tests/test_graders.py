"""
Grading tests
"""


import unittest
from datetime import datetime, timedelta

import ddt
from pytz import UTC
import six
from six import text_type
from xmodule import graders
from xmodule.graders import AggregatedScore, ProblemScore, ShowCorrectness, aggregate_scores


class GradesheetTest(unittest.TestCase):
    """
    Tests the aggregate_scores method
    """

    def test_weighted_grading(self):
        scores = []
        agg_fields = dict(first_attempted=None)
        prob_fields = dict(raw_earned=0, raw_possible=0, weight=0, first_attempted=None)

        # No scores
        all_total, graded_total = aggregate_scores(scores)
        self.assertEqual(
            all_total,
            AggregatedScore(tw_earned=0, tw_possible=0, graded=False, **agg_fields),
        )
        self.assertEqual(
            graded_total,
            AggregatedScore(tw_earned=0, tw_possible=0, graded=True, **agg_fields),
        )

        # (0/5 non-graded)
        scores.append(ProblemScore(weighted_earned=0, weighted_possible=5, graded=False, **prob_fields))
        all_total, graded_total = aggregate_scores(scores)
        self.assertEqual(
            all_total,
            AggregatedScore(tw_earned=0, tw_possible=5, graded=False, **agg_fields),
        )
        self.assertEqual(
            graded_total,
            AggregatedScore(tw_earned=0, tw_possible=0, graded=True, **agg_fields),
        )

        # (0/5 non-graded) + (3/5 graded) = 3/10 total, 3/5 graded
        now = datetime.now()
        prob_fields['first_attempted'] = now
        agg_fields['first_attempted'] = now
        scores.append(ProblemScore(weighted_earned=3, weighted_possible=5, graded=True, **prob_fields))
        all_total, graded_total = aggregate_scores(scores)
        self.assertAlmostEqual(
            all_total,
            AggregatedScore(tw_earned=3, tw_possible=10, graded=False, **agg_fields),
        )
        self.assertAlmostEqual(
            graded_total,
            AggregatedScore(tw_earned=3, tw_possible=5, graded=True, **agg_fields),
        )

        # (0/5 non-graded) + (3/5 graded) + (2/5 graded) = 5/15 total, 5/10 graded
        scores.append(ProblemScore(weighted_earned=2, weighted_possible=5, graded=True, **prob_fields))
        all_total, graded_total = aggregate_scores(scores)
        self.assertAlmostEqual(
            all_total,
            AggregatedScore(tw_earned=5, tw_possible=15, graded=False, **agg_fields),
        )
        self.assertAlmostEqual(
            graded_total,
            AggregatedScore(tw_earned=5, tw_possible=10, graded=True, **agg_fields),
        )


@ddt.ddt
class GraderTest(unittest.TestCase):
    """
    Tests grader implementations
    """

    empty_gradesheet = {
    }

    incomplete_gradesheet = {
        'Homework': {},
        'Lab': {},
        'Midterm': {},
    }

    class MockGrade(object):
        """
        Mock class for SubsectionGrade object.
        """
        def __init__(self, graded_total, display_name):
            self.graded_total = graded_total
            self.display_name = display_name

    common_fields = dict(graded=True, first_attempted=datetime.now())
    test_gradesheet = {
        'Homework': {
            'hw1': MockGrade(AggregatedScore(tw_earned=2, tw_possible=20.0, **common_fields), display_name='hw1'),
            'hw2': MockGrade(AggregatedScore(tw_earned=16, tw_possible=16.0, **common_fields), display_name='hw2'),
        },

        # The dropped scores should be from the assignments that don't exist yet
        'Lab': {
            # Dropped
            'lab1': MockGrade(AggregatedScore(tw_earned=1, tw_possible=2.0, **common_fields), display_name='lab1'),
            'lab2': MockGrade(AggregatedScore(tw_earned=1, tw_possible=1.0, **common_fields), display_name='lab2'),
            'lab3': MockGrade(AggregatedScore(tw_earned=1, tw_possible=1.0, **common_fields), display_name='lab3'),
            # Dropped
            'lab4': MockGrade(AggregatedScore(tw_earned=5, tw_possible=25.0, **common_fields), display_name='lab4'),
            # Dropped
            'lab5': MockGrade(AggregatedScore(tw_earned=3, tw_possible=4.0, **common_fields), display_name='lab5'),
            'lab6': MockGrade(AggregatedScore(tw_earned=6, tw_possible=7.0, **common_fields), display_name='lab6'),
            'lab7': MockGrade(AggregatedScore(tw_earned=5, tw_possible=6.0, **common_fields), display_name='lab7'),
        },

        'Midterm': {
            'midterm': MockGrade(
                AggregatedScore(tw_earned=50.5, tw_possible=100, **common_fields),
                display_name="Midterm Exam",
            ),
        },
    }

    def test_assignment_format_grader(self):
        homework_grader = graders.AssignmentFormatGrader("Homework", 12, 2)
        no_drop_grader = graders.AssignmentFormatGrader("Homework", 12, 0)
        # Even though the minimum number is 3, this should grade correctly when 7 assignments are found
        overflow_grader = graders.AssignmentFormatGrader("Lab", 3, 2)
        lab_grader = graders.AssignmentFormatGrader("Lab", 7, 3)

        # Test the grading of an empty gradesheet
        for graded in [
                homework_grader.grade(self.empty_gradesheet),
                no_drop_grader.grade(self.empty_gradesheet),
                homework_grader.grade(self.incomplete_gradesheet),
                no_drop_grader.grade(self.incomplete_gradesheet),
        ]:
            self.assertAlmostEqual(graded['percent'], 0.0)
            # Make sure the breakdown includes 12 sections, plus one summary
            self.assertEqual(len(graded['section_breakdown']), 12 + 1)

        graded = homework_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.11)  # 100% + 10% / 10 assignments
        self.assertEqual(len(graded['section_breakdown']), 12 + 1)

        graded = no_drop_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.0916666666666666)  # 100% + 10% / 12 assignments
        self.assertEqual(len(graded['section_breakdown']), 12 + 1)

        graded = overflow_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.8880952380952382)  # 100% + 10% / 5 assignments
        self.assertEqual(len(graded['section_breakdown']), 7 + 1)

        graded = lab_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.9226190476190477)
        self.assertEqual(len(graded['section_breakdown']), 7 + 1)

    def test_assignment_format_grader_on_single_section_entry(self):
        midterm_grader = graders.AssignmentFormatGrader("Midterm", 1, 0)
        # Test the grading on a section with one item:
        for graded in [
                midterm_grader.grade(self.empty_gradesheet),
                midterm_grader.grade(self.incomplete_gradesheet),
        ]:
            self.assertAlmostEqual(graded['percent'], 0.0)
            # Make sure the breakdown includes just the one summary
            self.assertEqual(len(graded['section_breakdown']), 0 + 1)
            self.assertEqual(graded['section_breakdown'][0]['label'], 'Midterm')

        graded = midterm_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.505)
        self.assertEqual(len(graded['section_breakdown']), 0 + 1)

    def test_weighted_subsections_grader(self):
        # First, a few sub graders
        homework_grader = graders.AssignmentFormatGrader("Homework", 12, 2)
        lab_grader = graders.AssignmentFormatGrader("Lab", 7, 3)
        midterm_grader = graders.AssignmentFormatGrader("Midterm", 1, 0)

        weighted_grader = graders.WeightedSubsectionsGrader([
            (homework_grader, homework_grader.category, 0.25),
            (lab_grader, lab_grader.category, 0.25),
            (midterm_grader, midterm_grader.category, 0.5),
        ])

        over_one_weights_grader = graders.WeightedSubsectionsGrader([
            (homework_grader, homework_grader.category, 0.5),
            (lab_grader, lab_grader.category, 0.5),
            (midterm_grader, midterm_grader.category, 0.5),
        ])

        # The midterm should have all weight on this one
        zero_weights_grader = graders.WeightedSubsectionsGrader([
            (homework_grader, homework_grader.category, 0.0),
            (lab_grader, lab_grader.category, 0.0),
            (midterm_grader, midterm_grader.category, 0.5),
        ])

        # This should always have a final percent of zero
        all_zero_weights_grader = graders.WeightedSubsectionsGrader([
            (homework_grader, homework_grader.category, 0.0),
            (lab_grader, lab_grader.category, 0.0),
            (midterm_grader, midterm_grader.category, 0.0),
        ])

        empty_grader = graders.WeightedSubsectionsGrader([])

        graded = weighted_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.5106547619047619)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

        graded = over_one_weights_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.7688095238095238)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

        graded = zero_weights_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.2525)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

        graded = all_zero_weights_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.0)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

        for graded in [
                weighted_grader.grade(self.empty_gradesheet),
                weighted_grader.grade(self.incomplete_gradesheet),
                zero_weights_grader.grade(self.empty_gradesheet),
                all_zero_weights_grader.grade(self.empty_gradesheet),
        ]:
            self.assertAlmostEqual(graded['percent'], 0.0)
            self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
            self.assertEqual(len(graded['grade_breakdown']), 3)

        graded = empty_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.0)
        self.assertEqual(len(graded['section_breakdown']), 0)
        self.assertEqual(len(graded['grade_breakdown']), 0)

    def test_grade_with_string_min_count(self):
        """
        Test that the grading succeeds in case the min_count is set to a string
        """
        weighted_grader = graders.grader_from_conf([
            {
                'type': "Homework",
                'min_count': '12',
                'drop_count': 2,
                'short_label': "HW",
                'weight': 0.25,
            },
            {
                'type': "Lab",
                'min_count': '7',
                'drop_count': 3,
                'category': "Labs",
                'weight': 0.25
            },
            {
                'type': "Midterm",
                'min_count': '0',
                'drop_count': 0,
                'name': "Midterm Exam",
                'short_label': "Midterm",
                'weight': 0.5,
            },
        ])

        graded = weighted_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.5106547619047619)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

    def test_grader_from_conf(self):

        # Confs always produce a graders.WeightedSubsectionsGrader, so we test this by repeating the test
        # in test_graders.WeightedSubsectionsGrader, but generate the graders with confs.

        weighted_grader = graders.grader_from_conf([
            {
                'type': "Homework",
                'min_count': 12,
                'drop_count': 2,
                'short_label': "HW",
                'weight': 0.25,
            },
            {
                'type': "Lab",
                'min_count': 7,
                'drop_count': 3,
                'category': "Labs",
                'weight': 0.25
            },
            {
                'type': "Midterm",
                'min_count': 0,
                'drop_count': 0,
                'name': "Midterm Exam",
                'short_label': "Midterm",
                'weight': 0.5,
            },
        ])

        empty_grader = graders.grader_from_conf([])

        graded = weighted_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.5106547619047619)
        self.assertEqual(len(graded['section_breakdown']), (12 + 1) + (7 + 1) + 1)
        self.assertEqual(len(graded['grade_breakdown']), 3)

        graded = empty_grader.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.0)
        self.assertEqual(len(graded['section_breakdown']), 0)
        self.assertEqual(len(graded['grade_breakdown']), 0)

        # Test that graders can also be used instead of lists of dictionaries
        homework_grader = graders.AssignmentFormatGrader("Homework", 12, 2)
        homework_grader2 = graders.grader_from_conf(homework_grader)

        graded = homework_grader2.grade(self.test_gradesheet)
        self.assertAlmostEqual(graded['percent'], 0.11)
        self.assertEqual(len(graded['section_breakdown']), 12 + 1)

    @ddt.data(
        (
            # empty
            {},
            u"Configuration has no appropriate grader class."
        ),
        (
            # no min_count
            {'type': "Homework", 'drop_count': 0},
            u"Configuration has no appropriate grader class."
        ),
        (
            # no drop_count
            {'type': "Homework", 'min_count': 0},
            # pylint: disable=line-too-long
            u"__init__() takes at least 4 arguments (3 given)" if six.PY2 else u"__init__() missing 1 required positional argument: 'drop_count'"
        ),
    )
    @ddt.unpack
    def test_grader_with_invalid_conf(self, invalid_conf, expected_error_message):
        with self.assertRaises(ValueError) as error:
            graders.grader_from_conf([invalid_conf])
        self.assertIn(expected_error_message, text_type(error.exception))


@ddt.ddt
class ShowCorrectnessTest(unittest.TestCase):
    """
    Tests the correctness_available method
    """

    def setUp(self):
        super(ShowCorrectnessTest, self).setUp()

        now = datetime.now(UTC)
        day_delta = timedelta(days=1)
        self.yesterday = now - day_delta
        self.today = now
        self.tomorrow = now + day_delta

    def test_show_correctness_default(self):
        """
        Test that correctness is visible by default.
        """
        self.assertTrue(ShowCorrectness.correctness_available())

    @ddt.data(
        (ShowCorrectness.ALWAYS, True),
        (ShowCorrectness.ALWAYS, False),
        # Any non-constant values behave like "always"
        ('', True),
        ('', False),
        ('other-value', True),
        ('other-value', False),
    )
    @ddt.unpack
    def test_show_correctness_always(self, show_correctness, has_staff_access):
        """
        Test that correctness is visible when show_correctness is turned on.
        """
        self.assertTrue(ShowCorrectness.correctness_available(
            show_correctness=show_correctness,
            has_staff_access=has_staff_access
        ))

    @ddt.data(True, False)
    def test_show_correctness_never(self, has_staff_access):
        """
        Test that show_correctness="never" hides correctness from learners and course staff.
        """
        self.assertFalse(ShowCorrectness.correctness_available(
            show_correctness=ShowCorrectness.NEVER,
            has_staff_access=has_staff_access
        ))

    @ddt.data(
        # Correctness not visible to learners if due date in the future
        ('tomorrow', False, False),
        # Correctness is visible to learners if due date in the past
        ('yesterday', False, True),
        # Correctness is visible to learners if due date in the past (just)
        ('today', False, True),
        # Correctness is visible to learners if there is no due date
        (None, False, True),
        # Correctness is visible to staff if due date in the future
        ('tomorrow', True, True),
        # Correctness is visible to staff if due date in the past
        ('yesterday', True, True),
        # Correctness is visible to staff if there is no due date
        (None, True, True),
    )
    @ddt.unpack
    def test_show_correctness_past_due(self, due_date_str, has_staff_access, expected_result):
        """
        Test show_correctness="past_due" to ensure:
        * correctness is always visible to course staff
        * correctness is always visible to everyone if there is no due date
        * correctness is visible to learners after the due date, when there is a due date.
        """
        if due_date_str is None:
            due_date = None
        else:
            due_date = getattr(self, due_date_str)
        self.assertEqual(
            ShowCorrectness.correctness_available(ShowCorrectness.PAST_DUE, due_date, has_staff_access),
            expected_result
        )
