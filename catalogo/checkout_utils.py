# catalogo/checkout_utils.py
"""Funciones auxiliares del checkout (W14)."""
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from clientes.models import Cliente
from ventas.models import Pedido

TASA_IVA_DEFAULT = Decimal('0.16')
CENTAVOS = Decimal('0.01')


def _redondear(valor):
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _tasa_iva():
    try:
        from configuracion.models import ConfiguracionERP

        config = ConfiguracionERP.get_instance()
        for campo in ('tasa_iva', 'iva', 'porcentaje_iva'):
            valor = getattr(config, campo, None)
            if valor is not None:
                tasa = Decimal(str(valor))
                return tasa / 100 if tasa > 1 else tasa
    except Exception:
        pass
    return TASA_IVA_DEFAULT


def armar_items(carrito):
    items = []
    for prod_id, datos in carrito.items():
        precio = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        items.append({
            'prod_id': prod_id,
            'nombre': datos['nombre'],
            'precio': precio,
            'cantidad': cantidad,
            'subtotal': _redondear(precio * cantidad),
            'imagen': datos.get('imagen'),
        })
    return items


def calcular_totales(carrito):
    subtotal = sum(
        (Decimal(d['precio']) * int(d['cantidad']) for d in carrito.values()),
        Decimal('0.00'),
    )
    subtotal = _redondear(subtotal)
    tasa = _tasa_iva()
    iva = _redondear(subtotal * tasa)
    return {
        'subtotal': subtotal,
        'iva': iva,
        'tasa_iva': tasa,
        'total': subtotal + iva,
    }


def generar_numero_pedido():
    anio = timezone.now().year
    prefijo = f'PED-{anio}-'
    consecutivo = Pedido.objects.filter(
        numero_pedido__startswith=prefijo
    ).count() + 1
    numero = f'{prefijo}{consecutivo:04d}'
    while Pedido.objects.filter(numero_pedido=numero).exists():
        consecutivo += 1
        numero = f'{prefijo}{consecutivo:04d}'
    return numero


def obtener_o_crear_cliente(user):
    correo = (user.email or f'{user.username}@sin-correo.local').lower()
    nombre = user.get_full_name() or user.username
    cliente = Cliente.objects.filter(correo__iexact=correo).first()
    if cliente is None:
        cliente = Cliente.objects.create(nombre=nombre, correo=correo)
    return cliente