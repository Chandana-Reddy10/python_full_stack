from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from .models import Product, Order, OrderItem


def home(request):
    products = Product.objects.all()

    search = request.GET.get('search', '')
    category = request.GET.get('category', '')

    if search:
        products = products.filter(name__icontains=search)

    if category:
        products = products.filter(category__iexact=category)

    categories = Product.objects.values_list(
        'category', flat=True
    ).distinct()

    return render(request, 'home.html', {
        'products': products,
        'categories': categories,
        'search': search,
        'selected_category': category,
    })


def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)

        if product.stock <= 0:
            messages.error(request, 'Product is out of stock.')
            return redirect('home')

        cart = request.session.get('cart', {})
        product_id = str(product.id)

        quantity = int(cart.get(product_id, 0))

        if quantity >= product.stock:
            messages.error(request, 'Maximum available stock reached.')
        else:
            cart[product_id] = quantity + 1
            request.session['cart'] = cart
            messages.success(request, 'Product added to cart!')

    return redirect('home')


def cart(request):
    cart_data = request.session.get('cart', {})
    cart_items = []
    total = Decimal('0.00')

    for product_id, quantity in cart_data.items():
        product = Product.objects.filter(id=product_id).first()

        if product:
            subtotal = product.price * quantity

            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal,
            })

            total += subtotal

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total,
    })


def update_cart(request, product_id):
    if request.method == 'POST':
        cart_data = request.session.get('cart', {})
        product = get_object_or_404(Product, id=product_id)

        quantity = request.POST.get('quantity', '1')

        try:
            quantity = int(quantity)

            if quantity <= 0:
                cart_data.pop(str(product_id), None)

            elif quantity <= product.stock:
                cart_data[str(product_id)] = quantity

            else:
                messages.error(request, 'Requested quantity is unavailable.')

        except ValueError:
            messages.error(request, 'Invalid quantity.')

        request.session['cart'] = cart_data

    return redirect('cart')


def remove_from_cart(request, product_id):
    if request.method == 'POST':
        cart_data = request.session.get('cart', {})
        cart_data.pop(str(product_id), None)

        request.session['cart'] = cart_data

        messages.success(request, 'Product removed from cart.')

    return redirect('cart')


def checkout(request):
    cart_data = request.session.get('cart', {})

    if not cart_data:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    cart_items = []
    total = Decimal('0.00')

    for product_id, quantity in cart_data.items():
        product = Product.objects.filter(id=product_id).first()

        if not product:
            continue

        subtotal = product.price * quantity

        cart_items.append({
            'product': product,
            'quantity': quantity,
            'subtotal': subtotal,
        })

        total += subtotal

    if not cart_items:
        request.session['cart'] = {}
        return redirect('cart')

    if request.method == 'POST':

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()

        if not all([name, email, phone, address]):
            messages.error(request, 'Please fill in all fields.')

        else:
            try:
                with transaction.atomic():

                    # Lock products and verify stock
                    order_products = []

                    for item in cart_items:
                        product = Product.objects.select_for_update().get(
                            id=item['product'].id
                        )

                        if product.stock < item['quantity']:
                            raise ValueError(
                                f'Insufficient stock for {product.name}.'
                            )

                        order_products.append((product, item['quantity']))

                    order = Order.objects.create(
                        customer_name=name,
                        email=email,
                        phone=phone,
                        address=address,
                        total_amount=total
                    )

                    for product, quantity in order_products:

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            quantity=quantity,
                            price=product.price
                        )

                        product.stock -= quantity
                        product.save(update_fields=['stock'])

                request.session['cart'] = {}

                return render(request, 'checkout.html', {
                    'success': True,
                    'order': order,
                })

            except ValueError as error:
                messages.error(request, str(error))
                return redirect('cart')

    return render(request, 'checkout.html', {
        'cart_items': cart_items,
        'total': total,
        'success': False,
    })