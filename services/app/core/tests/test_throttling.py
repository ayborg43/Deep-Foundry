from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import UserRateThrottle

from core.views import LoginView


class TwoPerMinuteThrottle(UserRateThrottle):
    rate = "2/min"


class ApiThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.original_throttles = LoginView.throttle_classes
        LoginView.throttle_classes = [TwoPerMinuteThrottle]

    def tearDown(self):
        LoginView.throttle_classes = self.original_throttles
        cache.clear()

    def test_anonymous_auth_requests_are_rate_limited_by_source(self):
        url = reverse("auth-login")
        body = {"email": "nobody@example.com", "password": "wrong-password"}
        self.assertNotEqual(self.client.post(url, body, format="json").status_code, 429)
        self.assertNotEqual(self.client.post(url, body, format="json").status_code, 429)
        response = self.client.post(url, body, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
