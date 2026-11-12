# catalogo/views.py
"""Vistas del módulo de catálogo y carrito (W13).

El catálogo es público. El carrito vive en la sesión de Django con esta forma:

    request.session['carrito'] = {
        '1': {
            'nombre':   'Laptop HP',
            'precio':   '10000.00',   # str: Decimal no es serializable en JSON
            'cantidad': 2,
            'imagen':   'productos/laptop.jpg' o None,
        },
    }
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from productos.models import Producto
from ventas.models import Pedido

from .checkout_utils import (
    armar_items,
    calcular_totales,
    generar_numero_pedido,
    obtener_o_crear_cliente,
)
from .filters import ProductoFilter

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

# Ajusta este valor a uno de los estados que existen en tu modelo Pedido.
ESTADO_PENDIENTE = 'pendiente'
ESTADO_PAGADO = 'pagado'

CANTIDAD_MAXIMA = 99


# ── CATÁLOGO ──────────────────────────────────────────────────────────────

class CatalogoView(ListView):
    """Catálogo público de productos con filtros. No requiere login."""

    model = Producto
    template_name = 'catalogo/catalogo.html'
    context_object_name = 'productos'
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Producto.objects
            .select_related('categoria', 'proveedor')
            .filter(activo=True)
            .order_by('nombre')
        )
        self.filtro = ProductoFilter(self.request.GET, queryset=qs)
        return self.filtro.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtro'] = self.filtro
        ctx['categorias'] = self.filtro.form.fields['categoria'].queryset
        return ctx


# ── HELPERS DEL CARRITO ───────────────────────────────────────────────────

def _obtener_carrito(request):
    """Devuelve el carrito de la sesión (dict vacío si no existe)."""
    return request.session.get('carrito', {})


def _guardar_carrito(request, carrito):
    request.session['carrito'] = carrito
    request.session.modified = True


def _leer_cantidad(request, default=1):
    """Lee 'cantidad' del POST de forma segura, entre 1 y CANTIDAD_MAXIMA."""
    try:
        cantidad = int(request.POST.get('cantidad', default))
    except (TypeError, ValueError):
        cantidad = default
    return max(1, min(cantidad, CANTIDAD_MAXIMA))


def _redirigir_seguro(request, next_url):
    """Redirige solo a URLs del mismo sitio (evita open redirects)."""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('catalogo:catalogo')


# ── CARRITO ───────────────────────────────────────────────────────────────

def ver_carrito(request):
    """Muestra el carrito con subtotales y total calculados."""
    carrito = _obtener_carrito(request)
    items = []
    total = Decimal('0.00')

    for prod_id, datos in carrito.items():
        precio = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        subtotal = precio * cantidad
        total += subtotal
        items.append({
            'prod_id': prod_id,
            'nombre': datos['nombre'],
            'precio': precio,
            'cantidad': cantidad,
            'subtotal': subtotal,
            'imagen': datos.get('imagen'),
        })

    return render(request, 'catalogo/carrito.html', {
        'items': items,
        'total': total,
    })


@require_POST
def agregar_al_carrito(request, producto_id):
    """Agrega un producto o incrementa su cantidad. Solo POST."""
    producto = get_object_or_404(Producto, pk=producto_id, activo=True)
    carrito = _obtener_carrito(request)
    clave = str(producto_id)
    cantidad = _leer_cantidad(request)

    if clave in carrito:
        carrito[clave]['cantidad'] = min(
            carrito[clave]['cantidad'] + cantidad, CANTIDAD_MAXIMA
        )
    else:
        carrito[clave] = {
            'nombre': producto.nombre,
            'precio': str(producto.precio),
            'cantidad': cantidad,
            'imagen': producto.imagen.name if producto.imagen else None,
        }

    _guardar_carrito(request, carrito)
    messages.success(request, f'"{producto.nombre}" agregado al carrito.')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    return _redirigir_seguro(request, next_url)


@require_POST
def remover_del_carrito(request, producto_id):
    """Elimina un producto del carrito. Solo POST."""
    carrito = _obtener_carrito(request)
    clave = str(producto_id)
    nombre = carrito.pop(clave, {}).get('nombre', 'Producto')
    _guardar_carrito(request, carrito)

    messages.warning(request, f'"{nombre}" eliminado del carrito.')
    return redirect('catalogo:carrito')


@require_POST
def actualizar_cantidad(request, producto_id):
    """Cambia la cantidad de un producto. Si es 0 o menos, lo elimina."""
    carrito = _obtener_carrito(request)
    clave = str(producto_id)

    try:
        cantidad = int(request.POST.get('cantidad', 1))
    except (TypeError, ValueError):
        cantidad = 1

    if clave in carrito:
        if cantidad > 0:
            carrito[clave]['cantidad'] = min(cantidad, CANTIDAD_MAXIMA)
        else:
            carrito.pop(clave)

    _guardar_carrito(request, carrito)
    return redirect('catalogo:carrito')


@require_POST
def vaciar_carrito(request):
    """Vacía el carrito completo. Solo POST."""
    _guardar_carrito(request, {})
    messages.info(request, 'Carrito vaciado.')
    return redirect('catalogo:carrito')


# ── CHECKOUT ──────────────────────────────────────────────────────────────

@login_required
def checkout(request):
    """Resumen del carrito (GET) y creación del pago en Stripe (POST).

    GET:  muestra el resumen con IVA. No crea nada en Stripe.
    POST: crea Pedido + PaymentIntent y devuelve client_secret a Stripe.js.
    """
    carrito = _obtener_carrito(request)
    if not carrito:
        messages.warning(request, 'Tu carrito está vacío.')
        return redirect('catalogo:catalogo')

    totales = calcular_totales(carrito)
    items = armar_items(carrito)
    publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', '') or ''

    if request.method == 'POST':
        # Falla temprano y con mensaje claro si faltan las claves en Render
        if not publishable_key or not getattr(settings, 'STRIPE_SECRET_KEY', ''):
            logger.error('Faltan STRIPE_PUBLISHABLE_KEY / STRIPE_SECRET_KEY.')
            messages.error(
                request,
                'El pago no está configurado (faltan las claves de Stripe).'
            )
            return redirect('catalogo:pago_error')

        try:
            # atomic: si Stripe falla, el Pedido se revierte y no quedan
            # pedidos "pendiente" huérfanos.
            with transaction.atomic():
                cliente = obtener_o_crear_cliente(request.user)

                pedido = Pedido.objects.create(
                    numero_pedido=generar_numero_pedido(),
                    cliente=cliente,
                    estado=ESTADO_PENDIENTE,
                    total_pagado=totales['total'],
                    items_snapshot=[
                        {
                            'producto_id': int(prod_id),
                            'nombre': datos['nombre'],
                            'cantidad': int(datos['cantidad']),
                            'precio': datos['precio'],
                        }
                        for prod_id, datos in carrito.items()
                    ],
                )

                # Stripe pide enteros en centavos
                monto_centavos = int(
                    (totales['total'] * 100).quantize(Decimal('1'), ROUND_HALF_UP)
                )

                intent = stripe.PaymentIntent.create(
                    amount=monto_centavos,
                    currency='mxn',
                    automatic_payment_methods={
                        'enabled': True,
                        'allow_redirects': 'never',  # solo tarjeta, sin redirecciones
                    },
                    metadata={
                        'pedido_id': str(pedido.pk),
                        'pedido_num': pedido.numero_pedido,
                        'cliente': cliente.nombre,
                    },
                    idempotency_key=f'pedido-{pedido.pk}',
                )

            # Guardamos el último pedido e intent para validarlos al volver
            request.session['ultimo_pedido_id'] = pedido.pk
            request.session['ultimo_intent_id'] = intent.id
            request.session.modified = True

            return render(request, 'catalogo/checkout.html', {
                'carrito': carrito,
                'items': items,
                'totales': totales,
                'pedido': pedido,
                'client_secret': intent.client_secret,
                'publishable_key': publishable_key,
            })

        except stripe.StripeError as exc:
            logger.exception('Error de Stripe en checkout')
            messages.error(
                request,
                f'Error con Stripe: {exc.user_message or "intenta de nuevo."}'
            )
            return redirect('catalogo:pago_error')

        except Exception:
            logger.exception('Error inesperado en checkout')
            messages.error(
                request,
                'Ocurrió un error inesperado al preparar el pago.'
            )
            return redirect('catalogo:pago_error')

    return render(request, 'catalogo/checkout.html', {
        'carrito': carrito,
        'items': items,
        'totales': totales,
        'client_secret': None,
        'publishable_key': publishable_key,
    })


@login_required
def pago_exitoso(request, pedido_id):
    """Confirma el pago al volver de Stripe.

    No basta con que la URL exista: se verifica en Stripe que el
    PaymentIntent esté 'succeeded' y que pertenezca a este pedido.
    El estado del pedido y el stock los actualiza el webhook
    (única fuente de verdad), no esta vista.
    """
    if request.session.get('ultimo_pedido_id') != pedido_id:
        messages.error(request, 'No encontramos ese pedido en tu sesión.')
        return redirect('catalogo:catalogo')

    pedido = get_object_or_404(Pedido, pk=pedido_id)
    payment_intent_id = (
        request.GET.get('payment_intent')
        or request.session.get('ultimo_intent_id')
    )

    if not payment_intent_id:
        messages.error(request, 'Falta la confirmación del pago.')
        return redirect('catalogo:pago_error')

    try:
        # stripe-python >= 15: StripeObject no es dict, se convierte
        intent = stripe.PaymentIntent.retrieve(payment_intent_id).to_dict()
    except stripe.StripeError as exc:
        logger.exception('Error al verificar el PaymentIntent')
        messages.error(
            request,
            f'No pudimos verificar el pago: {exc.user_message or "intenta de nuevo."}'
        )
        return redirect('catalogo:pago_error')

    pedido_en_intent = (intent.get('metadata') or {}).get('pedido_id')
    if intent.get('status') != 'succeeded' or pedido_en_intent != str(pedido.pk):
        messages.error(request, 'El pago no está confirmado.')
        return redirect('catalogo:pago_error')

    _guardar_carrito(request, {})
    request.session.pop('ultimo_pedido_id', None)
    request.session.pop('ultimo_intent_id', None)

    messages.success(
        request,
        f'¡Pago exitoso! Tu pedido {pedido.numero_pedido} está confirmado. '
        f'Total: ${pedido.total_pagado}'
    )
    return render(request, 'catalogo/pago_exitoso.html', {'pedido': pedido})


def pago_error(request):
    """Muestra el error de pago y permite reintentar."""
    return render(request, 'catalogo/pago_error.html')