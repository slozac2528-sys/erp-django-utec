from django.core.management.base import BaseCommand

from ventas.tasks import reporte_ventas_diario


class Command(BaseCommand):
    help = 'Envía ahora el reporte diario de ventas a REPORTE_VENTAS_DESTINATARIOS'

    def handle(self, *args, **options):
        resultado = reporte_ventas_diario()
        self.stdout.write(self.style.SUCCESS(
            f"Reporte enviado: {resultado['total_pedidos']} pedidos, "
            f"${resultado['total_facturado']} facturados."
        ))