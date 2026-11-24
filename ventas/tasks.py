# ventas/tasks.py
"""Tareas asíncronas de la app ventas — W17/W18.

Idempotencia:
    Pedido.correo_enviado=True previene envíos duplicados si la tarea
    se llama más de una vez para el mismo pedido.

Uso:
    enviar_confirmacion_pedido.delay(pedido_id)
"""
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _url_absoluta(nombre_url: str) -> str:
    """Construye una URL absoluta sin request (las tareas no tienen request)."""
    return f'{settings.SITE_URL}{reverse(nombre_url)}'


def _items_con_subtotal(items_snapshot: list) -> list:
    """Agrega 'subtotal' (precio × cantidad, Decimal) a cada item del snapshot."""
    items = []
    for item in items_snapshot or []:
        try:
            precio = Decimal(str(item.get('precio', '0')))
            cantidad = int(item.get('cantidad', 0))
        except (InvalidOperation, TypeError, ValueError):
            precio, cantidad = Decimal('0.00'), 0
        items.append({
            **item,
            'precio': precio.quantize(Decimal('0.01')),
            'cantidad': cantidad,
            'subtotal': (precio * cantidad).quantize(Decimal('0.01')),
        })
    return items


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='ventas.enviar_confirmacion_pedido',
)
def enviar_confirmacion_pedido(self, pedido_id: int) -> dict:
    """Envía el correo de confirmación de pedido al cliente."""
    from configuracion.models import ConfiguracionERP
    from ventas.models import Pedido

    try:
        pedido = Pedido.objects.select_related('cliente').get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error('[correo_confirmacion] Pedido %s no existe.', pedido_id)
        return {'estado': 'error', 'pedido_id': pedido_id, 'razon': 'Pedido no encontrado'}

    if pedido.correo_enviado:
        logger.info('[correo_confirmacion] Pedido %s: correo ya enviado — skip.',
                    pedido.numero_pedido)
        return {'estado': 'skip', 'pedido_id': pedido_id, 'razon': 'correo ya enviado'}

    correo_destino = (pedido.cliente.correo or '').strip()
    if not correo_destino:
        logger.warning(
            '[correo_confirmacion] Pedido %s: el cliente no tiene correo registrado.',
            pedido.numero_pedido,
        )
        return {'estado': 'skip', 'pedido_id': pedido_id, 'razon': 'cliente sin correo'}

    config = ConfiguracionERP.get_instance()

    contexto = {
        'pedido': pedido,
        'config': config,
        'items': _items_con_subtotal(pedido.items_snapshot),
        'url_tienda': _url_absoluta('catalogo:catalogo'),
    }

    asunto = f'Confirmación de pedido {pedido.numero_pedido} — {config.nombre_empresa}'
    texto_plano = render_to_string('emails/confirmacion_pedido.txt', contexto)
    html_body = render_to_string('emails/confirmacion_pedido.html', contexto)

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[correo_destino],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
    except Exception as exc:
        logger.error('[correo_confirmacion] Error al enviar para pedido %s: %s',
                     pedido.numero_pedido, exc)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

    Pedido.objects.filter(pk=pedido.pk).update(correo_enviado=True)
    logger.info('[correo_confirmacion] Correo enviado a %s para pedido %s.',
                correo_destino, pedido.numero_pedido)
    return {'estado': 'ok', 'pedido_id': pedido_id, 'correo': correo_destino}


@shared_task(name='ventas.verificar_stock_bajo')
def verificar_stock_bajo(umbral: int = 5) -> dict:
    """Verifica productos con stock bajo y envía alerta al admin."""
    from productos.models import Producto

    productos_bajos = list(
        Producto.objects
        .filter(activo=True, stock__lt=umbral)
        .values('pk', 'nombre', 'stock', 'categoria__nombre')
        .order_by('stock')
    )

    if not productos_bajos:
        logger.info('[stock_bajo] Todos los productos tienen stock >= %s.', umbral)
        return {'umbral': umbral, 'total': 0, 'productos_bajos': [], 'alerta_enviada': False}

    logger.warning('[stock_bajo] %s producto(s) con stock < %s.',
                   len(productos_bajos), umbral)

    alerta_enviada = False
    if settings.ADMINS:
        alerta_enviada = _enviar_alerta_stock(productos_bajos, umbral)

    return {
        'umbral': umbral,
        'total': len(productos_bajos),
        'productos_bajos': productos_bajos,
        'alerta_enviada': alerta_enviada,
    }


def _enviar_alerta_stock(productos_bajos: list, umbral: int) -> bool:
    """Envía el correo de alerta de stock al primer administrador."""
    from configuracion.models import ConfiguracionERP

    config = ConfiguracionERP.get_instance()
    fecha = timezone.localtime().strftime('%d/%m/%Y %H:%M')

    contexto = {
        'productos_bajos': productos_bajos,
        'total_productos': len(productos_bajos),
        'umbral': umbral,
        'fecha': fecha,
        'url_admin': _url_absoluta('admin:productos_producto_changelist'),
        'config': config,
    }

    asunto = f'[ALERTA] {len(productos_bajos)} producto(s) con stock < {umbral}'
    texto_plano = render_to_string('emails/alerta_stock.txt', contexto)
    html_body = render_to_string('emails/alerta_stock.html', contexto)

    _admin_nombre, admin_correo = settings.ADMINS[0]

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[admin_correo],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
    except Exception as exc:
        logger.error('[stock_bajo] Error al enviar alerta: %s', exc)
        return False

    logger.info('[stock_bajo] Alerta enviada a %s. %s productos.',
                admin_correo, len(productos_bajos))
    return True


def _top_productos_del_dia(pedidos, limite: int = 5) -> list:
    """Agrupa las líneas de los pedidos pagados por producto.

    Usa items_snapshot, así que el top refleja los mismos pedidos que los KPI.
    """
    acumulado = {}
    for pedido in pedidos:
        for item in _items_con_subtotal(pedido.items_snapshot):
            clave = item.get('producto_id') or item.get('nombre', 'Sin nombre')
            fila = acumulado.setdefault(clave, {
                'nombre': item.get('nombre', 'Sin nombre'),
                'unidades': 0,
                'ingreso': Decimal('0.00'),
            })
            fila['unidades'] += item['cantidad']
            fila['ingreso'] += item['subtotal']

    return sorted(acumulado.values(), key=lambda f: f['ingreso'], reverse=True)[:limite]


@shared_task(name='ventas.reporte_ventas_diario')
def reporte_ventas_diario(fecha_iso: str | None = None) -> dict:
    """Envía el reporte de ventas.

    Sin fecha_iso usa el día de ayer (para el envío automático de las 8:00).
    Con fecha_iso (formato AAAA-MM-DD) reporta ese día, útil para pruebas.
    """
    from configuracion.models import ConfiguracionERP
    from ventas.models import Pedido

    if fecha_iso:
        fecha = date.fromisoformat(fecha_iso)
    else:
        fecha = timezone.localdate() - timedelta(days=1)

    config = ConfiguracionERP.get_instance()

    pedidos_pagados = list(
        Pedido.objects.filter(fecha_pedido__date=fecha, estado='pagado')
    )
    total_pedidos = len(pedidos_pagados)
    total_facturado = sum(
        (p.total_pagado or Decimal('0.00') for p in pedidos_pagados),
        Decimal('0.00'),
    )
    top_productos = _top_productos_del_dia(pedidos_pagados)

    logger.info('[reporte_diario] %s: %s pedidos, $%s facturados, %s productos top.',
                fecha, total_pedidos, total_facturado, len(top_productos))

    destinatarios = settings.REPORTE_VENTAS_DESTINATARIOS
    if destinatarios:
        _enviar_reporte_ventas(fecha, total_pedidos, total_facturado,
                               top_productos, config, destinatarios)
    else:
        logger.warning('[reporte_diario] REPORTE_VENTAS_DESTINATARIOS está vacío; no se envió.')

    return {
        'fecha': str(fecha),
        'total_pedidos': total_pedidos,
        'total_facturado': str(total_facturado),
        'top_productos': [
            {**p, 'ingreso': str(p['ingreso'])} for p in top_productos
        ],
    }


def _enviar_reporte_ventas(fecha, total_pedidos, total_facturado,
                           top_productos, config, destinatarios) -> None:
    """Envía el reporte diario a la lista de destinatarios.

    Lanza la excepción si falla el envío, para que el error quede en los logs.
    """
    url_admin = _url_absoluta('admin:ventas_pedido_changelist')
    fecha_str = fecha.strftime('%d/%m/%Y')

    contexto = {
        'fecha': fecha_str,
        'config': config,
        'total_pedidos': total_pedidos,
        'total_facturado': total_facturado,
        'top_productos': top_productos,
        'url_admin': url_admin,
    }

    asunto = f'Reporte de ventas del {fecha_str} — {config.nombre_empresa}'
    texto_plano = render_to_string('emails/reporte_ventas.txt', contexto)
    html_body = render_to_string('emails/reporte_ventas.html', contexto)

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=list(destinatarios),
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
    except Exception as exc:
        logger.error('[reporte_diario] Error al enviar reporte: %s', exc)
        raise

    logger.info('[reporte_diario] Reporte enviado a %s.', ', '.join(destinatarios))