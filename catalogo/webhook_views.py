# catalogo/webhook_views.py
"""Endpoint de webhook para recibir eventos de Stripe — W15/W16.

Verificación de seguridad:
    Stripe firma cada evento con STRIPE_WEBHOOK_SECRET.
    stripe.Webhook.construct_event() verifica la firma.
    Si la firma es inválida → 400 (Stripe no reintenta).
    Si la firma es válida → procesar el evento → 200.

Eventos manejados:
    payment_intent.succeeded      → Pedido.estado = 'pagado'
                                     Descontar stock de productos
                                     W16: encolar correo de confirmación
    payment_intent.payment_failed → Pedido.estado = 'cancelado'
"""
import logging

import stripe
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from productos.models import Producto
from ventas.models import Pedido
from ventas.tasks import enviar_confirmacion_pedido   # W16

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request) -> HttpResponse:
    """Recibe y procesa eventos de Stripe.

    Returns:
        HttpResponse: 200 si el evento fue procesado correctamente,
                      400 si la firma es inválida o el payload es inválido.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    # ── 1. Verificar firma ─────────────────────────────────────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        logger.warning('Webhook: payload inválido recibido.')
        return HttpResponse('Payload inválido.', status=400)
    # CAMBIO: en stripe-python reciente la excepción está en el paquete raíz
    except stripe.SignatureVerificationError:
        logger.warning('Webhook: firma inválida — posible ataque o secreto incorrecto.')
        return HttpResponse('Firma inválida.', status=400)

    # stripe >= 15 devuelve StripeObject, que ya NO es un dict
    if hasattr(event, 'to_dict'):
        event = event.to_dict()

    # ── 2. Despachar por tipo de evento ────────────────────────────────────
    tipo = event['type']
    logger.info('Webhook recibido: %s', tipo)

    if tipo == 'payment_intent.succeeded':
        _manejar_pago_exitoso(event['data']['object'])

    elif tipo == 'payment_intent.payment_failed':
        _manejar_pago_fallido(event['data']['object'])

    else:
        logger.debug('Evento ignorado: %s', tipo)

    # Siempre 200 para eventos que no necesitamos (Stripe reintenta con 4xx/5xx)
    return HttpResponse(status=200)


# ── HANDLERS INTERNOS ──────────────────────────────────────────────────────

def _manejar_pago_exitoso(payment_intent: dict) -> None:
    """Actualiza el Pedido a 'pagado', descuenta stock y encola el correo."""
    pedido_id = _extraer_pedido_id(payment_intent)
    if pedido_id is None:
        return

    try:
        pedido = Pedido.objects.get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error('Webhook: Pedido %s no encontrado en BD.', pedido_id)
        return

    if pedido.estado == 'pagado':
        logger.info('Pedido %s ya estaba pagado — idempotente.', pedido.numero_pedido)
        return

    pedido.estado = 'pagado'
    pedido.save(update_fields=['estado'])
    logger.info('Pedido %s actualizado a "pagado".', pedido.numero_pedido)

    _descontar_stock(pedido)

    # El webhook es el ÚNICO punto que dispara el correo (una vez por pedido).
    try:
        enviar_confirmacion_pedido.delay(pedido.pk)
    except Exception:
        logger.exception(
            'Webhook: no se pudo encolar la confirmación del pedido %s '
            '(¿Redis disponible?).', pedido.numero_pedido,
        )


def _manejar_pago_fallido(payment_intent: dict) -> None:
    """Actualiza el Pedido a 'cancelado' si sigue pendiente."""
    pedido_id = _extraer_pedido_id(payment_intent)
    if pedido_id is None:
        return

    try:
        pedido = Pedido.objects.get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error('Webhook: Pedido %s no encontrado.', pedido_id)
        return

    if pedido.estado == 'pendiente':
        pedido.estado = 'cancelado'
        pedido.save(update_fields=['estado'])
        logger.info('Pedido %s cancelado por pago fallido.', pedido.numero_pedido)


def _extraer_pedido_id(payment_intent: dict) -> int | None:
    """Extrae el pedido_id del metadata del PaymentIntent."""
    if hasattr(payment_intent, 'to_dict'):
        payment_intent = payment_intent.to_dict()

    metadata = payment_intent.get('metadata') or {}
    pedido_id = metadata.get('pedido_id')

    if not pedido_id:
        logger.warning(
            'Webhook: PaymentIntent sin pedido_id en metadata. ID: %s',
            payment_intent.get('id'),
        )
        return None

    try:
        return int(pedido_id)
    except (ValueError, TypeError):
        logger.error('Webhook: pedido_id inválido: %r', pedido_id)
        return None


def _descontar_stock(pedido: Pedido) -> None:
    """Descuenta el stock de los productos del pedido de forma atómica."""
    for item in pedido.items_snapshot or []:
        producto_id = item.get('producto_id')
        cantidad = int(item.get('cantidad', 0))

        if not producto_id or cantidad <= 0:
            continue

        filas = Producto.objects.filter(
            pk=producto_id,
            stock__gte=cantidad,
        ).update(stock=F('stock') - cantidad)

        if filas:
            logger.info('Stock decrementado: Producto %s - %s unidades.', producto_id, cantidad)
        else:
            logger.warning(
                'Producto %s: stock insuficiente para decrementar %s unidades.',
                producto_id, cantidad,
            )