from django.conf import settings
from django.test import TestCase, RequestFactory
from django.utils.translation import activate
from analytics_dashboard.context_processors import locale


class ContextProcessorTests(TestCase):
    def test_locale(self):
        request = RequestFactory().get('/')

        # Test default language
        self.assertDictEqual(locale(request), {'LANGUAGE': settings.LANGUAGE_CODE})

        # Test overridden language
        language = 'fr-fr'
        activate(language)
        self.assertDictEqual(locale(request), {'LANGUAGE': language})
