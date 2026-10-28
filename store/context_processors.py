from .models import Category

def store_context(request):
    try:
        categories = Category.objects.all().order_by('name')
    except Exception:
        categories = []

    cart = request.session.get('cart', {})
    cart_count = 0
    if isinstance(cart, dict):
        cart_count = sum(cart.values()) if cart else 0
    elif isinstance(cart, (list, tuple)):
        cart_count = len(cart)

    return {
        'all_categories': categories,
        'cart_count': cart_count,
    }
