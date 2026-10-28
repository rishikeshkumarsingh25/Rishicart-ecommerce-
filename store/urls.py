from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('products/', views.products, name='products'),
    path('categories/', views.categories, name='categories'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),

    path('login/', views.login_view, name='login'),
    path('signup/', views.signup, name='signup'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('edit-profile/', views.edit_profile, name='edit_profile'),

    path('cart/', views.cart, name='cart'),
    path('add-to-cart/<int:id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/increase/<int:id>/',views.increase_cart,name='increase_cart'),
    path('cart/decrease/<int:id>/',views.decrease_cart,name='decrease_cart'),
    path('cart/remove/<int:id>/', views.remove_from_cart, name='remove_from_cart'),

    path('checkout/', views.checkout, name='checkout'),
    path('place-order/', views.place_order, name='place_order'),

    path('orders/', views.my_orders, name='my_orders'),
    path('orders/cancel/<int:order_id>/', views.cancel_order, name='cancel_order'),
    path('orders/return/<int:order_id>/', views.return_order, name='return_order'),
    path('orders/replace/<int:order_id>/', views.replace_order, name='replace_order'),

    path('dashboard/', views.dashboard, name='dashboard'),

    path('dashboard/products/', views.dashboard_products, name='dashboard_products'),
    path('dashboard/products/add/', views.dashboard_add_product, name='dashboard_add_product'),
    path('dashboard/products/edit/<int:id>/', views.edit_product, name='edit_product'),
    path('dashboard/products/delete/<int:id>/', views.delete_product, name='delete_product'),

    path('dashboard/categories/', views.dashboard_categories, name='dashboard_categories'),
    path('dashboard/categories/add/', views.dashboard_add_category, name='dashboard_add_category'),
    path('dashboard/categories/edit/<int:id>/',views.edit_category,name='edit_category'),
    path('dashboard/categories/delete/<int:id>/', views.delete_category, name='delete_category'),
    path('dashboard/orders/', views.dashboard_orders,name='dashboard_orders'),
    path('dashboard/orders/update/<int:order_id>/', views.update_order_status, name='update_order_status'),
    path('dashboard/users/', views.dashboard_users, name='dashboard_users'),
    path('payment-success/',views.payment_success, name='payment_success'),
    path('order/<int:order_id>/invoice/', views.download_invoice, name='download_invoice'),
]