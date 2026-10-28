from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random


# ==================================================
# CATEGORY MODEL
# ==================================================

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


# ==================================================
# PRODUCT MODEL
# ==================================================

class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='store'
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='store/')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def is_electronics(self):
        if not self.category:
            return False
        cat_name = (self.category.name or '').strip().lower()
        cat_slug = (self.category.slug or '').strip().lower()
        return 'electronic' in cat_name or 'electronic' in cat_slug

    @property
    def is_footwear(self):
        if self.is_electronics:
            return False

        cat_name = (self.category.name if self.category else '').strip().lower()
        cat_slug = (self.category.slug if self.category else '').strip().lower()
        prod_name = (self.name or '').strip().lower()
        prod_slug = (self.slug or '').strip().lower()

        footwear_terms = [
            'footwear', 'shoe', 'shoes', 'sneaker', 'sneakers', 'boot', 'boots',
            'sandal', 'sandals', 'slipper', 'slippers', 'heel', 'heels',
            'loafer', 'loafers', 'crocs', 'slides', 'chappal', 'flip flop',
            'flip-flop', 'flipflop', 'jutti', 'mojari'
        ]

        if any(term in cat_name or term in cat_slug for term in footwear_terms):
            return True

        import re
        for term in footwear_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', prod_name) or term in prod_slug:
                return True

        return False

    @property
    def is_kids_wear(self):
        if not self.category or self.is_electronics or self.is_footwear:
            return False
        cat_name = (self.category.name or '').strip().lower()
        cat_slug = (self.category.slug or '').strip().lower()
        return 'kid' in cat_name or 'kid' in cat_slug

    @property
    def is_clothing(self):
        if not self.category or self.is_electronics or self.is_footwear:
            return False
        cat_name = (self.category.name or '').strip().lower()
        cat_slug = (self.category.slug or '').strip().lower()
        clothing_terms = ['wear', 'cloth', 'shirt', 'pant', 'jean', 'dress', 'men', 'women', 'kid', 'apparel', 'fashion']
        return any(term in cat_name or term in cat_slug for term in clothing_terms)


# ==================================================
# ORDER MODEL
# ==================================================

class Order(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Delivery Address
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    # Order Status
    status = models.CharField(
        max_length=30,
        default='Pending'
    )

    # Payment Details
    payment_method = models.CharField(
        max_length=30,
        default='COD'
    )

    payment_status = models.CharField(
        max_length=30,
        default='Pending'
    )

    razorpay_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    # Tracking & Logistics Details
    current_location = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    courier_partner = models.CharField(
        max_length=100,
        blank=True,
        default='BlueDart Express'
    )

    action_reason = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"

    @property
    def tracking_id(self):
        if self.tracking_number:
            return self.tracking_number
        pin = self.pincode or '800001'
        return f"RC-EXP-{self.id:04d}-{pin}"

    @property
    def courier_name(self):
        return self.courier_partner or 'BlueDart Express'

    @property
    def tracking_step(self):
        s = (self.status or '').strip().lower()
        if s in ['pending', 'confirmed', 'order placed']:
            return 1
        elif s == 'packed':
            return 2
        elif s == 'shipped':
            return 3
        elif s == 'out for delivery':
            return 4
        elif s == 'delivered':
            return 5
        elif s == 'cancelled':
            return -1
        elif 'return' in s:
            return -2
        elif 'replace' in s:
            return -3
        return 1

    @property
    def is_cancelled(self):
        return (self.status or '').strip().lower() == 'cancelled'

    @property
    def is_returned(self):
        return 'return' in (self.status or '').strip().lower()

    @property
    def is_replaced(self):
        return 'replace' in (self.status or '').strip().lower()

    @property
    def can_cancel(self):
        s = (self.status or '').strip().lower()
        return s in ['pending', 'confirmed', 'packed', 'shipped'] and not self.is_cancelled and not self.is_returned and not self.is_replaced

    @property
    def can_return(self):
        s = (self.status or '').strip().lower()
        return s == 'delivered' and not self.is_returned and not self.is_replaced

    @property
    def can_replace(self):
        s = (self.status or '').strip().lower()
        return s == 'delivered' and not self.is_returned and not self.is_replaced

    @property
    def estimated_delivery_date(self):
        from datetime import timedelta
        if self.created_at:
            eta = self.created_at + timedelta(days=4)
            return eta.strftime("%d %b, %Y")
        return "Within 3-4 Days"

    @property
    def display_location(self):
        if self.current_location:
            return self.current_location
        s = (self.status or '').strip().lower()
        destination = (self.city or 'Your City').strip().title()
        state = (self.state or 'State').strip().title()

        if s == 'packed':
            return "RishiCart Central Warehouse, Sector 18, Gurugram, Haryana (Packaging & Quality Inspection Complete)"
        elif s == 'shipped':
            return f"BlueDart Express Trans-Shipment Facility, Hub #{100 + (self.id % 20)} (In-Transit to {destination} Sorting Hub)"
        elif s == 'out for delivery':
            return f"Local Courier Delivery Center, {destination}, {state} - Delivery Executive Arun Kumar (+91 98765-43210) is out for delivery"
        elif s == 'delivered':
            addr = self.address or f"{destination}, {state}"
            return f"Delivered to customer address: {addr} (Signed by recipient)"
        elif s == 'cancelled':
            return "Order Cancelled - Shipment recalled to warehouse"
        elif 'return' in s:
            return f"Return Request Active - Pickup Agent assigned at {destination} hub"
        elif 'replace' in s:
            return "Replacement Processing - New replacement unit being prepared at fulfillment center"
        else:
            return "RishiCart Order Processing Facility, New Delhi (Order Verified, preparing for packing)"


# ==================================================
# ORDER ITEM MODEL
# ==================================================

class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    product_name = models.CharField(max_length=200)

    quantity = models.PositiveIntegerField(default=1)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity


# ==================================================
# EMAIL OTP VERIFICATION MODEL
# ==================================================

class EmailOTP(models.Model):
    PURPOSE_CHOICES = (
        ('login', 'Login'),
        ('signup', 'Signup'),
    )

    email = models.EmailField(db_index=True)
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='login')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} - {self.otp} ({self.purpose})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def generate_otp(cls, email, purpose='login', validity_minutes=10):
        # Invalidate previous unverified OTPs for this email and purpose
        cls.objects.filter(email__iexact=email, purpose=purpose, is_verified=False).delete()
        otp = f"{random.randint(100000, 999999)}"
        expires_at = timezone.now() + timedelta(minutes=validity_minutes)
        return cls.objects.create(
            email=email.strip().lower(),
            otp=otp,
            purpose=purpose,
            expires_at=expires_at
        )
