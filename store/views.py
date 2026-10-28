from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.utils.text import slugify
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

import razorpay

from .models import Category, Order, OrderItem, Product, EmailOTP
from .utils import admin_required, send_otp_email, mask_email
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q



# ==================================================
# HOME
# ==================================================

def home(request):

    products = Product.objects.filter(
        is_available=True
    ).order_by('-created_at')

    return render(request, 'home.html', {
        'products': products
    })


# ==================================================
# PRODUCTS
# ==================================================

def products(request):

    products = Product.objects.filter(
        is_available=True
    ).order_by('-created_at')

    categories = Category.objects.all().order_by('name')

    search = request.GET.get('q', '').strip()

    category_slug = request.GET.get(
        'category',
        ''
    ).strip()

    if search:

        products = products.filter(
            name__icontains=search
        )

    if category_slug:

        products = products.filter(
            category__slug=category_slug
        )

    return render(
        request,
        'products.html',
        {
            'products': products,
            'categories': categories
        }
    )


# ==================================================
# CATEGORIES
# ==================================================

def categories(request):

    categories = Category.objects.all().order_by('name')

    return render(request, 'categories.html', {
        'categories': categories
    })


# ==================================================
# PRODUCT DETAIL
# ==================================================

def product_detail(request, slug):

    product = Product.objects.filter(
        slug=slug,
        is_available=True
    ).first()

    if product is None:
        return redirect('products')

    return render(request, 'product_detail.html', {
        'product': product
    })


# ==================================================
# ADD CATEGORY
# ==================================================

def add_category(request):

    if request.method == 'POST':

        name = request.POST.get('name')
        slug = request.POST.get('slug')

        if name and slug:

            Category.objects.create(
                name=name,
                slug=slug
            )

        return redirect('dashboard_categories')

    return render(request, 'add_category.html')


# ==================================================
# CART
# ==================================================

def cart(request):

    cart_data = request.session.get('cart', {})

    cart_items = []
    total = 0

    for product_id, quantity in cart_data.items():

        product = Product.objects.filter(
            id=product_id,
            is_available=True
        ).first()

        if product:

            subtotal = product.price * quantity

            total += subtotal

            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total
    })


def add_to_cart(request, id):

    product = Product.objects.filter(
        id=id,
        is_available=True
    ).first()

    if product is None:
        return redirect('products')

    cart = request.session.get('cart', {})

    product_id = str(id)

    if product_id in cart:

        cart[product_id] += 1

    else:

        cart[product_id] = 1

    request.session['cart'] = cart

    request.session.modified = True

    return redirect('cart')


def increase_cart(request, id):

    cart = request.session.get('cart', {})

    product_id = str(id)

    if product_id in cart:
        cart[product_id] += 1
    else:
        cart[product_id] = 1

    request.session['cart'] = cart
    request.session.modified = True

    return redirect('cart')


def decrease_cart(request, id):

    cart = request.session.get('cart', {})

    product_id = str(id)

    if product_id in cart:

        if cart[product_id] > 1:
            cart[product_id] -= 1
        else:
            del cart[product_id]

    request.session['cart'] = cart
    request.session.modified = True

    return redirect('cart')


def remove_from_cart(request, id):

    cart = request.session.get('cart', {})

    product_id = str(id)

    if product_id in cart:
        del cart[product_id]

    request.session['cart'] = cart
    request.session.modified = True

    return redirect('cart')


# ==================================================
# LOGIN
# ==================================================

def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('dashboard')
        return redirect('home')

    next_url = request.POST.get('next') or request.GET.get('next', '')

    if request.method == 'POST':
        login_input = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        if not login_input or not password:
            return render(request, 'login.html', {
                'error': 'Please enter your email/username and password.',
                'email': login_input,
                'next': next_url
            })

        # Find user by email OR username (case-insensitive)
        user_obj = User.objects.filter(
            Q(email__iexact=login_input) | Q(username__iexact=login_input)
        ).first()

        if user_obj is None:
            return render(request, 'login.html', {
                'error': 'Invalid email/username or password.',
                'email': login_input,
                'next': next_url
            })

        user = authenticate(
            request,
            username=user_obj.username,
            password=password
        )

        if user is None:
            return render(request, 'login.html', {
                'error': 'Invalid email/username or password.',
                'email': login_input,
                'next': next_url
            })

        if not user.is_active:
            return render(request, 'login.html', {
                'error': 'Your account has been deactivated. Please contact support.',
                'email': login_input,
                'next': next_url
            })

        # ==================================================
        # ADMIN LOGIN: DIRECT LOGIN (NO EMAIL VERIFY / NO OTP)
        # Admin can login with ANY email or username directly
        # ==================================================
        if user.is_staff or user.is_superuser:
            login(request, user)
            messages.success(request, f"Welcome Administrator, {user.username}!")
            if next_url and next_url.startswith('/dashboard'):
                return redirect(next_url)
            return redirect('dashboard')

        # ==================================================
        # CUSTOMER LOGIN: REAL EMAIL + OTP VERIFICATION
        # ==================================================
        try:
            validate_email(user.email)
        except ValidationError:
            return render(request, 'login.html', {
                'error': 'Please enter a valid real email address.',
                'email': login_input,
                'next': next_url
            })

        # Generate and Send OTP to real customer email
        otp_obj = EmailOTP.generate_otp(email=user.email, purpose='login')
        email_sent, err_msg = send_otp_email(user.email, otp_obj.otp, purpose='login')

        request.session['otp_user_id'] = user.id
        request.session['otp_email'] = user.email
        request.session['otp_purpose'] = 'login'
        request.session['otp_next'] = next_url

        if not email_sent and settings.DEBUG:
            messages.info(request, f"Development Notice: Live email send failed ({err_msg}). Testing OTP: {otp_obj.otp}")

        return redirect('verify_otp')

    return render(request, 'login.html', {'next': next_url})


# ==================================================
# SIGNUP
# ==================================================

def signup(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not username or not email or not password:
            return render(request, 'signup.html', {
                'error': 'All fields are required.',
                'username': username,
                'email': email
            })

        try:
            validate_email(email)
        except ValidationError:
            return render(request, 'signup.html', {
                'error': 'Please enter a valid real email address.',
                'username': username,
                'email': email
            })

        if password != confirm_password:
            return render(request, 'signup.html', {
                'error': 'Passwords do not match.',
                'username': username,
                'email': email
            })

        if len(password) < 6:
            return render(request, 'signup.html', {
                'error': 'Password must be at least 6 characters long.',
                'username': username,
                'email': email
            })

        if User.objects.filter(username__iexact=username).exists():
            return render(request, 'signup.html', {
                'error': 'Username is already taken. Please choose another username.',
                'username': username,
                'email': email
            })

        if User.objects.filter(email__iexact=email).exists():
            return render(request, 'signup.html', {
                'error': 'An account with this email already exists. Please log in.',
                'username': username,
                'email': email
            })

        # Generate and Send OTP for registration verification
        otp_obj = EmailOTP.generate_otp(email=email, purpose='signup')
        email_sent, err_msg = send_otp_email(email, otp_obj.otp, purpose='signup')

        request.session['signup_username'] = username
        request.session['signup_email'] = email
        request.session['signup_password'] = password
        request.session['otp_email'] = email
        request.session['otp_purpose'] = 'signup'

        if not email_sent and settings.DEBUG:
            messages.info(request, f"Development Notice: Live email send failed ({err_msg}). Testing OTP: {otp_obj.otp}")

        return redirect('verify_otp')

    return render(request, 'signup.html')


# ==================================================
# VERIFY OTP
# ==================================================

def verify_otp(request):
    if request.user.is_authenticated:
        return redirect('home')

    otp_email = request.session.get('otp_email')
    otp_purpose = request.session.get('otp_purpose', 'login')

    if not otp_email:
        messages.warning(request, "Verification session expired. Please log in or sign up again.")
        return redirect('login')

    masked = mask_email(otp_email)

    def render_verify(extra_ctx=None):
        ctx = {
            'email': otp_email,
            'masked_email': masked,
            'purpose': otp_purpose
        }
        if extra_ctx:
            ctx.update(extra_ctx)
        return render(request, 'verify_otp.html', ctx)

    if request.method == 'POST':
        otp_entered = request.POST.get('otp', '').strip()
        if not otp_entered:
            digits = [request.POST.get(f'digit{i}', '') for i in range(1, 7)]
            otp_entered = ''.join(digits).strip()

        if not otp_entered or len(otp_entered) != 6 or not otp_entered.isdigit():
            return render_verify({'error': 'Please enter a valid 6-digit OTP verification code.'})

        otp_record = EmailOTP.objects.filter(
            email__iexact=otp_email,
            purpose=otp_purpose,
            is_verified=False
        ).order_by('-created_at').first()

        if not otp_record:
            return render_verify({'error': 'No active OTP verification code found. Please click "Resend OTP".'})

        if otp_record.is_expired:
            return render_verify({'error': 'This OTP has expired. Please click "Resend OTP" to get a fresh code.'})

        if otp_record.attempts >= 5:
            return render_verify({'error': 'Maximum attempts exceeded for this OTP. Please click "Resend OTP".'})

        if otp_record.otp != otp_entered:
            otp_record.attempts += 1
            otp_record.save()
            remaining = 5 - otp_record.attempts
            return render_verify({'error': f'Incorrect OTP. {remaining} attempt(s) remaining.'})

        # Mark OTP as successfully verified
        otp_record.is_verified = True
        otp_record.save()

        if otp_purpose == 'login':
            user_id = request.session.get('otp_user_id')
            next_url = request.session.get('otp_next', '')

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                messages.error(request, "Account not found.")
                return redirect('login')

            login(request, user)

            request.session.pop('otp_user_id', None)
            request.session.pop('otp_email', None)
            request.session.pop('otp_purpose', None)
            request.session.pop('otp_next', None)

            # ADMIN vs CUSTOMER ROUTING
            if user.is_staff or user.is_superuser:
                messages.success(request, f"Welcome back, Administrator {user.username}!")
                if next_url and next_url.startswith('/dashboard'):
                    return redirect(next_url)
                return redirect('dashboard')
            else:
                messages.success(request, f"Welcome back, {user.username}!")
                if next_url and not next_url.startswith('/dashboard'):
                    return redirect(next_url)
                return redirect('home')

        elif otp_purpose == 'signup':
            username = request.session.get('signup_username')
            email = request.session.get('signup_email')
            password = request.session.get('signup_password')

            if not username or not email or not password:
                messages.error(request, "Registration details were lost. Please sign up again.")
                return redirect('signup')

            # Create regular customer (is_staff=False, is_superuser=False)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=False,
                is_superuser=False
            )

            request.session.pop('signup_username', None)
            request.session.pop('signup_email', None)
            request.session.pop('signup_password', None)
            request.session.pop('otp_email', None)
            request.session.pop('otp_purpose', None)

            login(request, user)
            messages.success(request, "Your email has been verified successfully! Welcome to RishiCart.")
            return redirect('home')

    return render_verify()


# ==================================================
# RESEND OTP
# ==================================================

def resend_otp(request):
    otp_email = request.session.get('otp_email')
    otp_purpose = request.session.get('otp_purpose', 'login')

    if not otp_email:
        messages.error(request, "No pending verification session. Please log in or sign up.")
        return redirect('login')

    otp_obj = EmailOTP.generate_otp(email=otp_email, purpose=otp_purpose)
    email_sent, err_msg = send_otp_email(otp_email, otp_obj.otp, purpose=otp_purpose)

    if email_sent:
        messages.success(request, f"A fresh verification code has been sent to {mask_email(otp_email)}.")
    else:
        if settings.DEBUG:
            messages.info(request, f"Development Notice: Live email could not be sent ({err_msg}). Testing OTP: {otp_obj.otp}")
        else:
            messages.warning(request, "Could not send verification email. Please check your email configuration.")

    return redirect('verify_otp')


# ==================================================
# PROFILE
# ==================================================

@login_required(login_url='login')
def profile(request):

    return render(request, 'profile.html')


# ==================================================
# LOGOUT
# ==================================================

@login_required(login_url='login')
def logout_view(request):

    logout(request)

    return redirect('home')


# ==================================================
# EDIT PROFILE
# ==================================================

@login_required(login_url='login')
def edit_profile(request):

    if request.method == 'POST':

        user = request.user

        user.username = request.POST.get(
            'username'
        )

        user.email = request.POST.get(
            'email'
        )

        user.save()

        return redirect('profile')

    return render(request, 'edit_profile.html')


# ==================================================
# MY ORDERS
# ==================================================

@login_required(login_url='login')
def my_orders(request):
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related('items__product')
        .order_by('-created_at')
    )

    return render(
        request,
        'my_orders.html',
        {'orders': orders}
    )
    
    
@login_required(login_url='login')
def download_invoice(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product'),
        id=order_id,
        user=request.user
    )

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="RishiCart_Invoice_{order.id}.pdf"'
    )

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    # Invoice heading
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(50, height - 60, "RishiCart")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, height - 95, "ORDER INVOICE")

    # Order details
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, height - 125, f"Invoice No: RC-{order.id}")
    order_date = order.created_at.strftime('%d-%m-%Y %H:%M') if hasattr(order.created_at, 'strftime') else str(order.created_at)
    pdf.drawString(50, height - 142, f"Order Date: {order_date}")

    customer_name = order.full_name or request.user.get_full_name() or request.user.username
    pdf.drawString(50, height - 159, f"Customer: {customer_name}")
    if order.phone:
        pdf.drawString(50, height - 176, f"Phone: {order.phone}")

    # Delivery Address
    if order.address:
        address_text = f"Address: {order.address}, {order.city}, {order.state} - {order.pincode}"
        pdf.drawString(50, height - 193, address_text[:75])

    # Table Header
    y = height - 225
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Item")
    pdf.drawString(290, y, "Qty")
    pdf.drawString(360, y, "Price")
    pdf.drawString(460, y, "Subtotal")

    y -= 8
    pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
    pdf.line(50, y, 545, y)
    y -= 18

    pdf.setFont("Helvetica", 10)
    items = list(order.items.all())
    if items:
        for item in items:
            name = item.product_name or (item.product.name if item.product else 'Product')
            pdf.drawString(50, y, str(name)[:35])
            pdf.drawString(290, y, str(item.quantity))
            pdf.drawString(360, y, f"Rs. {float(item.price):.2f}")
            pdf.drawString(460, y, f"Rs. {float(item.subtotal):.2f}")
            y -= 18
            if y < 100:
                pdf.showPage()
                y = height - 60
    else:
        pdf.drawString(50, y, "Order Total")
        pdf.drawString(460, y, f"Rs. {float(order.total_amount):.2f}")
        y -= 18

    y -= 5
    pdf.line(50, y, 545, y)
    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(360, y, "Total Amount:")
    pdf.drawString(460, y, f"Rs. {float(order.total_amount):.2f}")

    y -= 35
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Payment Method: {order.payment_method}  |  Payment Status: {order.payment_status}  |  Order Status: {order.status}")
    y -= 20
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(50, y, "Thank you for shopping with RishiCart!")

    pdf.save()
    return response


@admin_required
def dashboard_orders(request):

    orders = (
        Order.objects
        .prefetch_related('items__product')
        .all()
        .order_by('-created_at')
    )

    return render(
        request,
        'dashboard_orders.html',
        {
            'orders': orders
        }
    )


@login_required(login_url='login')
def cancel_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.can_cancel:
            reason = request.POST.get('reason', '').strip()
            comment = request.POST.get('comment', '').strip()
            full_reason = f"{reason} - {comment}".strip(' -') if comment else reason
            order.status = 'Cancelled'
            order.action_reason = full_reason or 'Cancelled by customer'
            order.save()
            messages.success(request, f"Order #{order.id} has been cancelled successfully.")
        else:
            messages.error(request, "This order cannot be cancelled at this stage.")
    return redirect('my_orders')


@login_required(login_url='login')
def return_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.can_return:
            reason = request.POST.get('reason', '').strip()
            comment = request.POST.get('comment', '').strip()
            full_reason = f"{reason} - {comment}".strip(' -') if comment else reason
            order.status = 'Return Requested'
            order.action_reason = full_reason or 'Return requested by customer'
            order.save()
            messages.success(request, f"Return request for Order #{order.id} submitted. Our courier partner will contact you for pickup.")
        else:
            messages.error(request, "Return is only eligible for delivered items.")
    return redirect('my_orders')


@login_required(login_url='login')
def replace_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.can_replace:
            reason = request.POST.get('reason', '').strip()
            comment = request.POST.get('comment', '').strip()
            full_reason = f"{reason} - {comment}".strip(' -') if comment else reason
            order.status = 'Replacement Requested'
            order.action_reason = full_reason or 'Replacement requested by customer'
            order.save()
            messages.success(request, f"Replacement request for Order #{order.id} submitted. A replacement item will be arranged for dispatch.")
        else:
            messages.error(request, "Replacement is only eligible for delivered items.")
    return redirect('my_orders')


@admin_required
def update_order_status(request, order_id):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Unauthorized action.")
        return redirect('dashboard_orders')

    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status', '').strip()
        new_location = request.POST.get('current_location', '').strip()
        tracking_number = request.POST.get('tracking_number', '').strip()
        courier_partner = request.POST.get('courier_partner', '').strip()

        if new_status:
            order.status = new_status
        if new_location:
            order.current_location = new_location
        if tracking_number:
            order.tracking_number = tracking_number
        if courier_partner:
            order.courier_partner = courier_partner

        order.save()
        messages.success(request, f"Order #{order.id} status updated to '{order.status}'.")

    return redirect('dashboard_orders')


# ==================================================
# DASHBOARD
# ==================================================

@admin_required
def dashboard(request):

    context = {
        'total_users': User.objects.count(),
        'total_products': Product.objects.count(),
        'total_categories': Category.objects.count(),
        'total_orders': Order.objects.count(),
    }

    return render(
        request,
        'dashboard.html',
        context
    )


# ==================================================
# DASHBOARD PRODUCTS
# ==================================================

@admin_required
def dashboard_products(request):

    products = Product.objects.all().order_by(
        '-created_at'
    )

    return render(request, 'dashboard_products.html', {
        'products': products
    })


@admin_required
def dashboard_users(request):

    users = User.objects.all().order_by('-date_joined')

    return render(
        request,
        'dashboard_users.html',
        {
            'users': users
        }
    )

# ==================================================
# ADD PRODUCT
# ==================================================


@admin_required
def dashboard_add_product(request):

    categories = Category.objects.all()

    if request.method == 'POST':

        category_id = request.POST.get('category')
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        image = request.FILES.get('image')

        slug = slugify(name)

        original_slug = slug
        counter = 1

        while Product.objects.filter(slug=slug).exists():

            slug = f"{original_slug}-{counter}"

            counter += 1

        Product.objects.create(
            category_id=category_id,
            name=name,
            slug=slug,
            description=description,
            price=price,
            stock=stock,
            image=image
        )

        return redirect('dashboard_products')

    return render(
        request,
        'add_product.html',
        {
            'categories': categories
        }
    )


# ==================================================
# EDIT PRODUCT
# ==================================================

@admin_required
def edit_product(request, id):

    product = Product.objects.filter(
        id=id
    ).first()

    if product is None:
        return redirect('dashboard_products')

    categories = Category.objects.all().order_by(
        'name'
    )

    if request.method == 'POST':

        product.category_id = request.POST.get(
            'category'
        )

        product.name = request.POST.get(
            'name'
        )

        product.slug = request.POST.get(
            'slug'
        )

        product.description = request.POST.get(
            'description'
        )

        product.price = request.POST.get(
            'price'
        )

        product.stock = request.POST.get(
            'stock'
        )

        if request.FILES.get('image'):

            product.image = request.FILES.get(
                'image'
            )

        product.is_available = (
            request.POST.get('is_available')
            == 'on'
        )

        product.save()

        return redirect('dashboard_products')

    return render(request, 'product_edit.html', {
        'product': product,
        'categories': categories
    })


# ==================================================
# DELETE PRODUCT
# ==================================================

@admin_required
def delete_product(request, id):

    product = Product.objects.filter(
        id=id
    ).first()

    if product:

        product.delete()

    return redirect('dashboard_products')


# ==================================================
# DASHBOARD CATEGORIES
# ==================================================

@admin_required
def dashboard_categories(request):

    categories = Category.objects.all().order_by(
        'name'
    )

    return render(
        request,
        'dashboard_categories.html',
        {
            'categories': categories
        }
    )


# ==================================================
# ADD DASHBOARD CATEGORY
# ==================================================

@admin_required
def dashboard_add_category(request):

    if request.method == 'POST':

        name = request.POST.get('name', '').strip()

        if name:

            # Duplicate category check
            if not Category.objects.filter(
                name__iexact=name
            ).exists():

                # Slug automatically create hoga
                slug = slugify(name)

                original_slug = slug
                counter = 1

                # Slug unique rakho
                while Category.objects.filter(
                    slug=slug
                ).exists():

                    slug = f"{original_slug}-{counter}"
                    counter += 1

                Category.objects.create(
                    name=name,
                    slug=slug
                )

        return redirect('dashboard_categories')

    return render(
        request,
        'add_category.html'
    )


# ==================================================
# DELETE CATEGORY
# ==================================================

@admin_required
def delete_category(request, id):

    category = Category.objects.filter(
        id=id
    ).first()

    if category:

        category.delete()

    return redirect(
        'dashboard_categories'
    )


@admin_required
def edit_category(request, id):

    category = Category.objects.filter(id=id).first()

    if not category:
        return redirect('dashboard_categories')

    if request.method == 'POST':

        name = request.POST.get('name')

        if name:

            name = name.strip()

            if name:

                category.name = name

                slug = slugify(name)

                original_slug = slug
                counter = 1

                while Category.objects.filter(
                    slug=slug
                ).exclude(id=category.id).exists():

                    slug = f"{original_slug}-{counter}"
                    counter += 1

                category.slug = slug

                category.save()

        return redirect('dashboard_categories')

    return render(
        request,
        'edit_category.html',
        {
            'category': category
        }
    )



# ==================================================
# CHECKOUT
# ==================================================

@login_required(login_url='login')
def checkout(request):

    cart_data = request.session.get(
        'cart',
        {}
    )

    if not cart_data:

        return redirect('cart')

    cart_items = []

    total = 0

    for product_id, quantity in cart_data.items():

        product = Product.objects.filter(
            id=product_id,
            is_available=True
        ).first()

        if product:

            subtotal = (
                product.price * quantity
            )

            total += subtotal

            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })

    if not cart_items:

        return redirect('cart')

    return render(
        request,
        'checkout.html',
        {
            'cart_items': cart_items,
            'total': total
        }
    )



# ==================================================
# PLACE ORDER
# ==================================================

# ==================================================
# PLACE ORDER
# ==================================================

@login_required(login_url='login')
def place_order(request):

    if request.method != 'POST':
        return redirect('checkout')

    cart_data = request.session.get('cart', {})

    print("CART DATA:", cart_data)

    if not cart_data:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    # Calculate total
    total = Decimal('0.00')
    cart_products = []

    for product_id, quantity in cart_data.items():

        product = Product.objects.filter(
            id=product_id,
            is_available=True
        ).first()

        if not product:
            messages.error(
                request,
                'A product in your cart is no longer available.'
            )
            return redirect('cart')

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid product quantity.')
            return redirect('cart')

        if quantity <= 0:
            messages.error(request, 'Invalid product quantity.')
            return redirect('cart')

        cart_products.append((product, quantity))
        total += product.price * quantity

    print("TOTAL:", total)

    if total <= 0:
        messages.error(request, 'Invalid order total.')
        return redirect('cart')

    # ==================================================
    # DELIVERY ADDRESS
    # ==================================================

    full_name = request.POST.get('full_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    address = request.POST.get('address', '').strip()
    city = request.POST.get('city', '').strip()
    state = request.POST.get('state', '').strip()
    pincode = request.POST.get('pincode', '').strip()

    if not all([
        full_name,
        phone,
        address,
        city,
        state,
        pincode
    ]):
        messages.error(
            request,
            'Please fill in all delivery details.'
        )
        return redirect('checkout')

    if not phone.isdigit() or len(phone) != 10:
        messages.error(
            request,
            'Please enter a valid 10-digit phone number.'
        )
        return redirect('checkout')

    if not pincode.isdigit() or len(pincode) != 6:
        messages.error(
            request,
            'Please enter a valid 6-digit pincode.'
        )
        return redirect('checkout')

    # ==================================================
    # PAYMENT METHOD
    # ==================================================

    payment_method = request.POST.get(
        'payment_method', ''
    ).strip()

    print("PAYMENT METHOD:", payment_method)

    # ==================================================
    # COD PAYMENT
    # ==================================================

    if payment_method == 'COD':

        try:
            from django.db import transaction

            with transaction.atomic():

                order = Order.objects.create(
                    user=request.user,
                    total_amount=total,
                    full_name=full_name,
                    phone=phone,
                    address=address,
                    city=city,
                    state=state,
                    pincode=pincode,
                    status='Confirmed',
                    payment_method='COD',
                    payment_status='Pending'
                )

                for product, quantity in cart_products:

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=quantity,
                        price=product.price
                    )

            print("COD ORDER CREATED:", order.id)

            request.session['cart'] = {}
            request.session.modified = True

            messages.success(
                request,
                'Your order has been placed successfully.'
            )

            return redirect('my_orders')

        except Exception as e:
            print("COD ORDER ERROR:", str(e))
            messages.error(
                request,
                'Could not place your order. Please try again.'
            )
            return redirect('checkout')

    # ==================================================
    # RAZORPAY ONLINE PAYMENT
    # ==================================================

    elif payment_method == 'Online':

        try:
            import razorpay
            from django.db import transaction

            client = razorpay.Client(
                auth=(
                    settings.RAZORPAY_KEY_ID,
                    settings.RAZORPAY_KEY_SECRET
                )
            )

            amount = int(total * 100)

            # Create Razorpay order
            razorpay_order = client.order.create({
                'amount': amount,
                'currency': 'INR',
                'receipt': (
                    f'order_{request.user.id}_'
                    f'{request.session.session_key}'
                )
            })

            # Create Django order and its items
            with transaction.atomic():

                order = Order.objects.create(
                    user=request.user,
                    total_amount=total,
                    full_name=full_name,
                    phone=phone,
                    address=address,
                    city=city,
                    state=state,
                    pincode=pincode,
                    status='Pending',
                    payment_method='Online',
                    payment_status='Pending'
                )

                for product, quantity in cart_products:

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=quantity,
                        price=product.price
                    )

            print("DJANGO ORDER CREATED:", order.id)
            print("RAZORPAY ORDER ID:", razorpay_order['id'])

            # Save IDs in session for payment verification.
            # This avoids requiring an extra model field.
            request.session['pending_order_id'] = order.id
            request.session['pending_razorpay_order_id'] = (
                razorpay_order['id']
            )

            return render(
                request,
                'rozarpay_payment.html',
                {
                    'order': order,
                    'razorpay_order_id': razorpay_order['id'],
                    'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                    'amount': amount,
                    'total': total,
                    'user': request.user,
                }
            )

        except Exception as e:
            print("RAZORPAY ORDER ERROR:", str(e))
            messages.error(
                request,
                'Online payment could not be started. Please try again.'
            )
            return redirect('checkout')

    # ==================================================
    # INVALID PAYMENT METHOD
    # ==================================================

    else:
        messages.error(
            request,
            'Please select a valid payment method.'
        )
        return redirect('checkout')


# ==================================================
# PAYMENT SUCCESS / VERIFY PAYMENT
# ==================================================

@login_required(login_url='login')
def payment_success(request):

    if request.method != 'POST':
        messages.error(
            request,
            'Invalid payment verification request.'
        )
        return redirect('my_orders')

    payment_id = request.POST.get('razorpay_payment_id')
    razorpay_order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')

    if not all([
        payment_id,
        razorpay_order_id,
        signature
    ]):
        messages.error(
            request,
            'Payment details are incomplete.'
        )
        return redirect('my_orders')

    # Match the order created for this checkout session
    pending_order_id = request.session.get('pending_order_id')
    pending_razorpay_order_id = request.session.get(
        'pending_razorpay_order_id'
    )

    if (
        not pending_order_id
        or razorpay_order_id != pending_razorpay_order_id
    ):
        messages.error(
            request,
            'Order verification failed. Please contact support.'
        )
        return redirect('my_orders')

    try:
        import razorpay
        from django.db import transaction

        client = razorpay.Client(
            auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET
            )
        )

        # Verify Razorpay signature on the server
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
        })

        # Verify order ownership
        with transaction.atomic():

            order = Order.objects.select_for_update().get(
                id=pending_order_id,
                user=request.user
            )

            if order.payment_status != 'Paid':

                order.payment_status = 'Paid'
                order.status = 'Confirmed'
                order.save(
                    update_fields=[
                        'payment_status',
                        'status'
                    ]
                )

        # Clear cart only after successful verification
        request.session['cart'] = {}
        request.session.modified = True

        request.session.pop('pending_order_id', None)
        request.session.pop(
            'pending_razorpay_order_id',
            None
        )

        messages.success(
            request,
            'Payment verified successfully. Your order is confirmed.'
        )

        return render(
            request,
            'payment_success.html',
            {
                'order': order,
                'payment_id': payment_id,
                'razorpay_order_id': razorpay_order_id,
            }
        )

    except Exception as e:
        print("PAYMENT VERIFICATION ERROR:", str(e))

        messages.error(
            request,
            'Payment verification failed. Please contact support '
            'if money was deducted.'
        )

        return redirect('my_orders')
