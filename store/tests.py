from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from store.models import EmailOTP, Category, Product


class DashboardAccessRestrictionTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Normal customer
        self.customer = User.objects.create_user(
            username='testcustomer',
            email='customer@example.com',
            password='Password123!',
            is_staff=False,
            is_superuser=False
        )
        # Admin user
        self.admin = User.objects.create_user(
            username='testadmin',
            email='admin@example.com',
            password='AdminPassword123!',
            is_staff=True,
            is_superuser=True
        )

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated user accessing /dashboard/ should be redirected to login."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_regular_customer_blocked_from_dashboard(self):
        """A normal customer cannot access dashboard and is redirected to home with error."""
        self.client.force_login(self.customer)
        response = self.client.get(reverse('dashboard'), follow=True)
        # Should be redirected to home
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('home'))
        messages = list(response.context['messages'])
        self.assertTrue(any('Access Denied' in str(m) for m in messages))

    def test_regular_customer_blocked_from_all_dashboard_suburls(self):
        """Customer cannot access any dashboard URLs (products, categories, users, orders)."""
        self.client.force_login(self.customer)
        dashboard_urls = [
            reverse('dashboard_products'),
            reverse('dashboard_categories'),
            reverse('dashboard_orders'),
            reverse('dashboard_users'),
            reverse('dashboard_add_product'),
            reverse('dashboard_add_category'),
        ]
        for url in dashboard_urls:
            response = self.client.get(url, follow=True)
            self.assertRedirects(response, reverse('home'))

    def test_admin_can_access_dashboard(self):
        """Admin (is_staff=True) can access the dashboard."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')


class EmailOTPAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user(
            username='rajesh',
            email='rajesh@gmail.com',
            password='UserPass123!',
            is_staff=False,
            is_superuser=False
        )
        self.admin = User.objects.create_user(
            username='adminraj',
            email='adminraj@anyemail.xyz',
            password='AdminPass123!',
            is_staff=True,
            is_superuser=True
        )

    def test_admin_logs_in_directly_without_otp_using_email(self):
        """Admin can log in directly using email without needing email verification/OTP."""
        response = self.client.post(reverse('login'), {
            'email': 'adminraj@anyemail.xyz',
            'password': 'AdminPass123!'
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertTrue(response.context['user'].is_staff)

        # Ensure NO OTP record was generated for admin
        otp_exists = EmailOTP.objects.filter(email='adminraj@anyemail.xyz').exists()
        self.assertFalse(otp_exists)

    def test_admin_logs_in_directly_without_otp_using_username(self):
        """Admin can also log in directly using username without OTP."""
        response = self.client.post(reverse('login'), {
            'email': 'adminraj',
            'password': 'AdminPass123!'
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.context['user'].is_authenticated)

    def test_customer_login_triggers_otp_and_redirects_to_verify(self):
        """Customer entering credentials generates an OTP and redirects to /verify-otp/."""
        response = self.client.post(reverse('login'), {
            'email': 'rajesh@gmail.com',
            'password': 'UserPass123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))

        # Check OTP created in database for customer
        otp_record = EmailOTP.objects.filter(email='rajesh@gmail.com', purpose='login').first()
        self.assertIsNotNone(otp_record)
        self.assertEqual(len(otp_record.otp), 6)
        self.assertFalse(otp_record.is_verified)

    def test_verify_otp_customer_logs_in_to_home(self):
        """Customer entering correct OTP is logged in and redirected to home."""
        # 1. Login step
        self.client.post(reverse('login'), {
            'email': 'rajesh@gmail.com',
            'password': 'UserPass123!'
        })
        otp_record = EmailOTP.objects.filter(email='rajesh@gmail.com', purpose='login').first()

        # 2. Verify OTP step
        response = self.client.post(reverse('verify_otp'), {
            'otp': otp_record.otp
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('home'))
        # User is authenticated
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'rajesh')

    def test_invalid_otp_rejected(self):
        """Entering incorrect OTP shows error and fails."""
        self.client.post(reverse('login'), {
            'email': 'rajesh@gmail.com',
            'password': 'UserPass123!'
        })

        response = self.client.post(reverse('verify_otp'), {
            'otp': '000000'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect OTP')

    def test_signup_with_real_email_and_otp_verification(self):
        """Signup requires real email, sends OTP, and verifies before creating regular customer."""
        # Step 1: Signup post
        response = self.client.post(reverse('signup'), {
            'username': 'newuser123',
            'email': 'newuser@example.com',
            'password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))

        # User is not created yet before verification
        self.assertFalse(User.objects.filter(username='newuser123').exists())

        # Step 2: Verify OTP
        otp_record = EmailOTP.objects.filter(email='newuser@example.com', purpose='signup').first()
        self.assertIsNotNone(otp_record)

        verify_response = self.client.post(reverse('verify_otp'), {
            'otp': otp_record.otp
        }, follow=True)

        self.assertEqual(verify_response.status_code, 200)
        self.assertRedirects(verify_response, reverse('home'))

        # User is now created and is a customer (not admin)
        created_user = User.objects.get(username='newuser123')
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)
        self.assertEqual(created_user.email, 'newuser@example.com')
