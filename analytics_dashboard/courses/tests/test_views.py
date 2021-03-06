import json

from waffle import Switch
from django.core.cache import cache
import mock
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

import analyticsclient
import analyticsclient.constants.activity_type as AT
from analyticsclient.exceptions import NotFoundError

from courses.views import CourseValidMixin
from analytics_dashboard.tests.test_views import RedirectTestCaseMixin, UserTestCaseMixin
from courses.exceptions import PermissionsRetrievalFailedError
from courses.permissions import set_user_course_permissions, revoke_user_course_permissions
from courses.tests.test_middleware import MiddlewareAssertionMixin
from courses.tests.utils import get_mock_enrollment_data, get_mock_api_enrollment_geography_data, \
    get_mock_presenter_enrollment_geography_data, convert_list_of_dicts_to_csv, set_empty_permissions, \
    mock_engagement_activity_summary_and_trend_data, mock_course_activity, \
    get_mock_enrollment_summary_and_trend


class PermissionsTestMixin(object):
    def tearDown(self):
        super(PermissionsTestMixin, self).tearDown()
        cache.clear()

    def grant_permission(self, user, *courses):
        set_user_course_permissions(user, courses)

    def revoke_permissions(self, user):
        revoke_user_course_permissions(user)


class AuthenticationMixin(RedirectTestCaseMixin, UserTestCaseMixin):
    def test_authentication(self):
        """
        Users must be logged in to view the page.
        """

        # Authenticated users should go to the course page
        self.login()
        response = self.client.get(self.path, follow=True)
        self.assertEqual(response.status_code, 200)

        # Unauthenticated users should be redirected to the login page
        self.client.logout()
        response = self.client.get(self.path)
        self.assertRedirectsNoFollow(response, settings.LOGIN_URL, next=self.path)


class CourseViewTestMixin(PermissionsTestMixin, AuthenticationMixin):
    viewname = None

    def setUp(self):
        super(CourseViewTestMixin, self).setUp()
        self.course_id = 'edX/DemoX/Demo_Course'
        self.path = reverse(self.viewname, kwargs={'course_id': self.course_id})
        self.grant_permission(self.user, self.course_id)
        self.login()

    def assertResponseContentType(self, response, content_type):
        self.assertEqual(response['Content-Type'], content_type)

    def assertResponseFilename(self, response, filename):
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="{0}"'.format(filename))

    def assertPrimaryNav(self, nav):
        raise NotImplementedError

    def assertSecondaryNavs(self, nav):
        raise NotImplementedError

    @mock.patch('courses.permissions.refresh_user_course_permissions', mock.Mock(side_effect=set_empty_permissions))
    def test_authorization(self):
        """
        Users must be authorized to view a course in order to view the course pages.
        """

        # Authorized users should be able to view the page
        self.grant_permission(self.user, self.course_id)
        response = self.client.get(self.path, follow=True)
        self.assertEqual(response.status_code, 200)

        # Unauthorized users should be redirected to the 403 page
        self.revoke_permissions(self.user)
        response = self.client.get(self.path, follow=True)
        self.assertEqual(response.status_code, 403)

    @mock.patch('courses.views.CourseValidMixin.is_valid_course', mock.Mock(return_value=False))
    def test_invalid_course(self):
        course_id = 'fakeOrg/soFake/Fake_Course'
        self.grant_permission(self.user, course_id)
        path = reverse(self.viewname, kwargs={'course_id': course_id})

        response = self.client.get(path, follow=True)
        self.assertEqual(response.status_code, 404)


class CourseValidMixinTests(TestCase):
    def setUp(self):
        self.mixin = CourseValidMixin()
        self.mixin.course_id = 'edX/DemoX/Demo_Course'

    @override_settings(LMS_COURSE_VALIDATION_BASE_URL=None)
    def test_no_validation_url(self):
        self.assertTrue(self.mixin.is_valid_course())

    @override_settings(LMS_COURSE_VALIDATION_BASE_URL='a/url')
    @mock.patch('courses.views.requests.get')
    def test_valid_url(self, mock_lms_request):
        mock_lms_request.return_value.status_code = 404
        self.assertFalse(self.mixin.is_valid_course())

        mock_lms_request.return_value.status_code = 200
        self.assertTrue(self.mixin.is_valid_course())


class CourseCSVTestMixin(object):
    client = None
    column_headings = None
    base_file_name = None

    def test_response_no_data(self, mock_call):
        # Create an "empty" CSV that only has headers
        data = convert_list_of_dicts_to_csv([], self.column_headings)
        mock_call.return_value = data

        self.client.login(username=self.user.username, password=self.PASSWORD)
        response = self.client.get(self.path)

        # Check content type
        self.assertResponseContentType(response, 'text/csv')

        # Check filename
        filename = '{0}_{1}.csv'.format(self.course_id, self.base_file_name)
        self.assertResponseFilename(response, filename)

        # Check data
        self.assertEqual(response.content, data)

    def test_response(self, mock_call):
        data = convert_list_of_dicts_to_csv(mock_call(self.course_id))
        mock_call.return_value = data

        response = self.client.get(self.path)

        # Check content type
        self.assertResponseContentType(response, 'text/csv')

        # Check filename
        filename = '{0}_{1}.csv'.format(self.course_id, self.base_file_name)
        self.assertResponseFilename(response, filename)

        # Check data
        self.assertEqual(response.content, data)

    def test_404(self):
        course_id = 'fakeOrg/soFake/Fake_Course'
        self.grant_permission(self.user, course_id)
        path = reverse(self.viewname, kwargs={'course_id': course_id})
        response = self.client.get(path, follow=True)
        self.assertEqual(response.status_code, 404)


class CourseEnrollmentViewTestMixin(CourseViewTestMixin):
    active_secondary_nav_label = None

    def assertPrimaryNav(self, nav):
        expected = {
            'icon': 'fa-child',
            'href': reverse('courses:enrollment_activity', kwargs={'course_id': self.course_id}),
            'label': _('Enrollment'),
            'name': 'enrollment'
        }
        self.assertDictEqual(nav, expected)

    def assertSecondaryNavs(self, nav):
        reverse_kwargs = {'course_id': self.course_id}
        expected = [
            {'name': 'activity', 'label': _('Activity'),
             'href': reverse('courses:enrollment_activity', kwargs=reverse_kwargs)},
            {'name': 'geography', 'label': _('Geography'),
             'href': reverse('courses:enrollment_geography', kwargs=reverse_kwargs)}
        ]

        for item in expected:
            if item['label'] == self.active_secondary_nav_label:
                item['active'] = True
                item['href'] = '#'
            else:
                item['active'] = False

        self.assertListEqual(nav, expected)

    def get_mock_enrollment_data(self):
        return get_mock_enrollment_data(self.course_id)

    def test_authentication(self):
        with mock.patch.object(analyticsclient.course.Course, 'enrollment',
                               return_value=self.get_mock_enrollment_data()):
            super(CourseEnrollmentViewTestMixin, self).test_authentication()

    def test_authorization(self):
        with mock.patch.object(analyticsclient.course.Course, 'enrollment',
                               return_value=self.get_mock_enrollment_data()):
            super(CourseEnrollmentViewTestMixin, self).test_authorization()


class CourseEngagementViewTestMixin(CourseViewTestMixin):

    def assertPrimaryNav(self, nav):
        expected = {
            'icon': 'fa-bar-chart',
            'href': reverse('courses:engagement_content', kwargs={'course_id': self.course_id}),
            'label': _('Engagement'),
            'name': 'engagement'
        }
        self.assertDictEqual(nav, expected)

    def assertSecondaryNavs(self, nav):
        expected = [{'active': True, 'name': 'content', 'label': _('Content'), 'href': '#'}]
        self.assertListEqual(nav, expected)

    def test_authentication(self):
        with mock.patch.object(analyticsclient.course.Course, 'activity', return_value=mock_course_activity()):
            super(CourseEngagementViewTestMixin, self).test_authentication()

    def test_authorization(self):
        with mock.patch.object(analyticsclient.course.Course, 'activity', return_value=mock_course_activity()):
            super(CourseEngagementViewTestMixin, self).test_authorization()


class CourseEngagementContentViewTests(CourseEngagementViewTestMixin, TestCase):
    viewname = 'courses:engagement_content'

    def setUp(self):
        super(CourseEngagementContentViewTests, self).setUp()
        Switch.objects.create(name='navbar_display_engagement', active=True)
        Switch.objects.create(name='navbar_display_engagement_content', active=True)

    @mock.patch('courses.presenters.CourseEngagementPresenter.get_summary_and_trend_data',
                mock.Mock(return_value=mock_engagement_activity_summary_and_trend_data()))
    def test_engagement_page_success(self):
        response = self.client.get(self.path)

        # make sure that we get a 200
        self.assertEqual(response.status_code, 200)

        # check page title
        self.assertEqual(response.context['page_title'], 'Engagement Content')

        # make sure the summary numbers are correct
        self.assertEqual(response.context['summary'][AT.ANY], 100)
        self.assertEqual(response.context['summary'][AT.ATTEMPTED_PROBLEM], 301)
        self.assertEqual(response.context['summary'][AT.PLAYED_VIDEO], 1000)
        self.assertEqual(response.context['summary'][AT.POSTED_FORUM], 0)

        # check to make sure the activity trends are correct
        trends = response.context['js_data']['course']['engagementTrends']
        self.assertEqual(len(trends), 2)
        expected = {
            'weekEnding': '2013-01-08',
            AT.ANY: 100,
            AT.ATTEMPTED_PROBLEM: 301,
            AT.PLAYED_VIDEO: 1000,
            AT.POSTED_FORUM: 0
        }
        self.assertDictEqual(trends[0], expected)

        expected = {
            'weekEnding': '2013-01-01',
            AT.ANY: 1000,
            AT.ATTEMPTED_PROBLEM: 0,
            AT.PLAYED_VIDEO: 10000,
            AT.POSTED_FORUM: 45
        }
        self.assertDictEqual(trends[1], expected)

        self.assertPrimaryNav(response.context['primary_nav_item'])
        self.assertSecondaryNavs(response.context['secondary_nav_items'])

    @mock.patch('courses.presenters.CourseEngagementPresenter.get_summary_and_trend_data')
    def test_missing_data(self, get_summary_and_trend_data):
        get_summary_and_trend_data.side_effect = NotFoundError

        response = self.client.get(self.path)
        context = response.context

        # summary and engagementTrends should evaluate to falsy values, which the
        # template evaluates to render error messages
        self.assertIsNone(context['summary'])
        self.assertIsNone(context['js_data']['course']['engagementTrends'])


class CourseEnrollmentActivityViewTests(CourseEnrollmentViewTestMixin, TestCase):
    viewname = 'courses:enrollment_activity'
    active_secondary_nav_label = 'Activity'

    @mock.patch('courses.presenters.CourseEnrollmentPresenter.get_summary_and_trend_data')
    def test_valid_course(self, get_summary_and_trend_data):
        summary, enrollment_data = get_mock_enrollment_summary_and_trend(self.course_id)
        get_summary_and_trend_data.return_value = (summary, enrollment_data)

        response = self.client.get(self.path)
        context = response.context

        # Ensure we get a valid HTTP status
        self.assertEqual(response.status_code, 200)

        # check page title
        self.assertEqual(context['page_title'], 'Enrollment Activity')

        # make sure the summary numbers are correct
        self.assertDictEqual(context['summary'], summary)

        # make sure the trend is correct
        page_data = json.loads(context['page_data'])
        trend_data = page_data['course']['enrollmentTrends']
        expected = enrollment_data
        self.assertListEqual(trend_data, expected)

        self.assertPrimaryNav(context['primary_nav_item'])
        self.assertSecondaryNavs(context['secondary_nav_items'])

    @mock.patch('courses.presenters.CourseEnrollmentPresenter.get_summary_and_trend_data')
    def test_missing_data(self, get_summary_and_trend):
        get_summary_and_trend.side_effect = NotFoundError

        response = self.client.get(self.path)
        context = response.context

        # summary and enrollmentTrends should evaluate to falsy values, which the
        # template evaluates to render error messages
        self.assertIsNone(context['summary'])
        self.assertIsNone(context['js_data']['course']['enrollmentTrends'])


class CourseEnrollmentGeographyViewTests(CourseEnrollmentViewTestMixin, TestCase):
    viewname = 'courses:enrollment_geography'
    active_secondary_nav_label = 'Geography'

    def get_mock_enrollment_data(self):
        return get_mock_api_enrollment_geography_data(self.course_id)

    @mock.patch('courses.presenters.CourseEnrollmentPresenter.get_geography_data')
    def test_valid_course(self, get_geography_data):
        get_geography_data.side_effect = get_mock_presenter_enrollment_geography_data

        response = self.client.get(self.path)
        context = response.context

        # make sure that we get a 200
        self.assertEqual(response.status_code, 200)

        # check page title
        self.assertEqual(context['page_title'], 'Enrollment Geography')

        page_data = json.loads(context['page_data'])
        _summary, expected_data = get_mock_presenter_enrollment_geography_data()
        self.assertEqual(page_data['course']['enrollmentByCountry'], expected_data)

    @mock.patch('courses.presenters.CourseEnrollmentPresenter.get_geography_data')
    def test_missing_data(self, get_geography_data):
        get_geography_data.side_effect = NotFoundError

        response = self.client.get(self.path)
        context = response.context

        self.assertIsNone(context['update_message'])
        self.assertIsNone(context['js_data']['course']['enrollmentByCountry'])


class CourseEnrollmentByCountryCSVViewTests(CourseCSVTestMixin, CourseEnrollmentViewTestMixin, TestCase):
    viewname = 'courses:csv_enrollment_by_country'
    column_headings = ['count', 'country', 'course_id', 'date']
    base_file_name = 'enrollment_by_country'

    @mock.patch('analyticsclient.course.Course.enrollment')
    def test_response(self, mock_enrollment):
        super(CourseEnrollmentByCountryCSVViewTests, self).test_response(mock_enrollment)

    @mock.patch('analyticsclient.course.Course.enrollment')
    def test_response_no_data(self, mock_call):
        super(CourseEnrollmentByCountryCSVViewTests, self).test_response_no_data(mock_call)

    @mock.patch('analyticsclient.course.Course.enrollment', mock.Mock(side_effect=NotFoundError))
    def test_404(self):
        super(CourseEnrollmentByCountryCSVViewTests, self).test_404()


class CourseEnrollmentCSVViewTests(CourseCSVTestMixin, CourseEnrollmentViewTestMixin, TestCase):
    viewname = 'courses:csv_enrollment'
    column_headings = ['count', 'course_id', 'date']
    base_file_name = 'enrollment'

    @mock.patch('analyticsclient.course.Course.enrollment')
    def test_response(self, mock_enrollment):
        super(CourseEnrollmentCSVViewTests, self).test_response(mock_enrollment)

    @mock.patch('analyticsclient.course.Course.enrollment')
    def test_response_no_data(self, mock_call):
        super(CourseEnrollmentCSVViewTests, self).test_response_no_data(mock_call)

    @mock.patch('analyticsclient.course.Course.enrollment', mock.Mock(side_effect=NotFoundError))
    def test_404(self):
        super(CourseEnrollmentCSVViewTests, self).test_404()


class CourseEngagementActivityTrendCSVViewTests(CourseCSVTestMixin, CourseEngagementViewTestMixin, TestCase):
    viewname = 'courses:csv_engagement_activity_trend'
    column_headings = ['any', 'attempted_problem', 'course_id', 'interval_end', 'interval_start',
                       'played_video', 'posted_forum']
    base_file_name = 'engagement_activity_trend'

    @mock.patch('analyticsclient.course.Course.activity')
    def test_response(self, mock_engagement_activity):
        super(CourseEngagementActivityTrendCSVViewTests, self).test_response(mock_engagement_activity)

    @mock.patch('analyticsclient.course.Course.activity')
    def test_response_no_data(self, mock_call):
        super(CourseEngagementActivityTrendCSVViewTests, self).test_response_no_data(mock_call)

    @mock.patch('analyticsclient.course.Course.activity', mock.Mock(side_effect=NotFoundError))
    def test_404(self):
        super(CourseEngagementActivityTrendCSVViewTests, self).test_404()


class CourseHomeViewTests(CourseEnrollmentViewTestMixin, TestCase):
    """
    Course homepage

    We do not actually have a course homepage, so redirect to the enrollment activity page.
    """
    viewname = 'courses:home'

    def test_redirect(self):
        response = self.client.get(self.path)

        expected_url = reverse('courses:enrollment_activity', kwargs={'course_id': self.course_id})
        self.assertRedirectsNoFollow(response, expected_url)


class CourseIndexViewTests(MiddlewareAssertionMixin, PermissionsTestMixin, AuthenticationMixin, TestCase):
    def setUp(self):
        super(CourseIndexViewTests, self).setUp()
        self.path = reverse('courses:index')
        self.course_id = 'edX/DemoX/Demo_Course'
        self.login()

    def test_authentication(self):
        self.grant_permission(self.user, self.course_id)
        super(CourseIndexViewTests, self).test_authentication()

    def test_get(self):
        # If no course permissions, raise an error.
        self.grant_permission(self.user)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 403)

        # With permissions, the course list should include the accessible course(s)
        self.grant_permission(self.user, self.course_id)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(response.context['courses'], [self.course_id])

    @mock.patch('courses.permissions.get_user_course_permissions',
                mock.Mock(side_effect=PermissionsRetrievalFailedError))
    def test_get_with_permissions_error(self):
        response = self.client.get(self.path)
        self.assertIsPermissionsRetrievalFailedResponse(response)
