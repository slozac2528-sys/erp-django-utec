from django.db import transaction
from ventas.tasks import enviar_confirmacion_pedido, verificar_stock_bajo
from ventas.models import Pedido

with transaction.atomic():
    p = Pedido.objects.filter(estado='pagado').first() or Pedido.objects.first()
    if p:
        p.estado = 'pagado'
        p.correo_enviado = False
        p.save()
        print('Resultado 1:', enviar_confirmacion_pedido.delay(p.pk).get())
        print('Resultado 2:', enviar_confirmacion_pedido.delay(p.pk).get())
    else:
        print('No hay pedidos. Crea uno en /catalogo/checkout/')
    r = verificar_stock_bajo.delay(umbral=5).get()
    print('Stock bajo:', r['total'], '· alerta enviada:', r['alerta_enviada'])
    transaction.set_rollback(True)