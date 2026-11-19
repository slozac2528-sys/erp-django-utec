"""Suite de pruebas W16 — Celery worker y tareas asíncronas.

Ejecutar con:
    python manage.py test tests.test_w16_celery --verbosity=2

No requiere Redis ni Docker:
    - Las tareas se prueban con .apply() (ejecución local, sin broker).
    - La invocación desde las vistas se prueba con mocks de .delay().

Resultado esperado:
    Ran 9 tests in X.XXXs
    OK
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from clientes.models      import Cliente
from configuracion.models import ConfiguracionERP
from productos.models     import Categoria, Producto
from ventas.models        import Pedido
from ventas.tasks         import (
    enviar_confirmacion_pedido,
    verificar_stock_bajo,
)


class CeleryConfigTest(TestCase):
    """Verifica que Celery está correctamente configurado."""

    def test_celery_app_importable(self):
        """La app Celery debe poder importarse sin errores."""
        from core.celery import app as celery_app
        self.assertIsNotNone(celery_app)
        self.assertEqual(celery_app.main, 'core')

    def test_tareas_registradas_en_celery(self):
        """Las tareas de ventas deben estar registradas en Celery."""
        from core.celery import app as celery_app
        tareas = celery_app.tasks.keys()
        self.assertIn('ventas.enviar_confirmacion_pedido', tareas)
        self.assertIn('ventas.verificar_stock_bajo', tareas)

    def test_sin_redis_url_usa_modo_eager(self):
        """Sin REDIS_URL (laboratorio sin Docker) las tareas son EAGER."""
        from django.conf import settings
        if settings.REDIS_URL:
            self.skipTest('REDIS_URL definida: entorno con Redis.')
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)
        self.assertEqual(settings.CELERY_BROKER_URL, 'memory://')


class EnviarConfirmacionTareaTest(TestCase):
    """Tests de las tareas (se ejecutan con .apply(): local, sin broker)."""

    def setUp(self):
        ConfiguracionERP.get_instance()
        self.cat = Categoria.objects.create(nombre='Cat')
        cli = Cliente.objects.create(nombre='C', correo='c@t.com')
        self.pedido = Pedido.objects.create(
            numero_pedido = 'PED-2025-0001',
            cliente       = cli,
            estado        = 'pagado',
            total_pagado  = Decimal('116.00'),
        )

    def test_tarea_ejecuta_y_retorna_ok(self):
        """La tarea debe ejecutarse y retornar estado 'ok'."""
        data = enviar_confirmacion_pedido.apply(
            args=[self.pedido.pk]
        ).get()
        self.assertEqual(data['estado'], 'ok')
        self.assertEqual(data['pedido_id'], self.pedido.pk)

    def test_tarea_con_pedido_inexistente_retorna_error(self):
        """La tarea con pedido inexistente debe retornar estado 'error'."""
        data = enviar_confirmacion_pedido.apply(args=[9999]).get()
        self.assertEqual(data['estado'], 'error')

    def test_verificar_stock_bajo_detecta_productos(self):
        """verificar_stock_bajo debe detectar productos con stock < umbral."""
        Producto.objects.create(
            nombre='P', precio=Decimal('100.00'), stock=3,
            categoria=self.cat,
        )
        data = verificar_stock_bajo.apply(kwargs={'umbral': 5}).get()
        self.assertGreaterEqual(data['total'], 1)
        nombres = [p['nombre'] for p in data['productos_bajos']]
        self.assertIn('P', nombres)


class TareaInvocadaDesdeVistaTest(TestCase):
    """Mock de .delay() para verificar qué vistas encolan la tarea."""

    def setUp(self):
        ConfiguracionERP.get_instance()
        cli = Cliente.objects.create(nombre='C', correo='test@test.com')
        self.pedido = Pedido.objects.create(
            numero_pedido = 'PED-2025-VISTA',
            cliente       = cli,
            estado        = 'pendiente',
            total_pagado  = Decimal('100.00'),
        )
        self.user = User.objects.create_user('viewer', password='pass')

    @patch('ventas.tasks.enviar_confirmacion_pedido.delay')
    @patch('catalogo.views.stripe.PaymentIntent.retrieve')
    def test_pago_exitoso_no_encola_tarea(self, mock_retrieve, mock_delay):
        """pago_exitoso() NO encola: el webhook es el único disparo."""
        # Simula la respuesta de Stripe (sin salir a internet)
        mock_retrieve.return_value.to_dict.return_value = {
            'status': 'succeeded',
            'metadata': {'pedido_id': str(self.pedido.pk)},
        }
        self.client.force_login(self.user)

        # Simula la sesión que deja el checkout
        sesion = self.client.session
        sesion['ultimo_pedido_id'] = self.pedido.pk
        sesion['ultimo_intent_id'] = 'pi_test'
        sesion.save()

        r = self.client.get(
            reverse('catalogo:pago_exitoso', args=[self.pedido.pk])
        )
        self.assertEqual(
            r.status_code, 200,
            msg=f'Redirige a: {getattr(r, "url", None)}'
        )
        mock_delay.assert_not_called()

    @patch('catalogo.webhook_views.enviar_confirmacion_pedido.delay')
    @patch('catalogo.webhook_views.stripe.Webhook.construct_event')
    def test_webhook_succeeded_llama_a_delay(self, mock_event, mock_delay):
        """El webhook payment_intent.succeeded debe llamar a .delay()."""
        mock_event.return_value = self._evento_succeeded()
        self._post_webhook()
        mock_delay.assert_called_once_with(self.pedido.pk)

    @patch('catalogo.webhook_views.enviar_confirmacion_pedido.delay',
           side_effect=ConnectionError('Redis caído'))
    @patch('catalogo.webhook_views.stripe.Webhook.construct_event')
    def test_webhook_responde_200_aunque_redis_falle(
        self, mock_event, mock_delay
    ):
        """Si Redis falla, el pago se registra y Stripe recibe 200."""
        mock_event.return_value = self._evento_succeeded()
        with self.assertLogs('catalogo.webhook_views', level='ERROR'):
            r = self._post_webhook()
        self.assertEqual(r.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pagado')

    # ── helpers ────────────────────────────────────────────────────────
    def _evento_succeeded(self):
        return {
            'type': 'payment_intent.succeeded',
            'data': {
                'object': {
                    'id': 'pi_test',
                    'metadata': {'pedido_id': str(self.pedido.pk)},
                }
            }
        }

    def _post_webhook(self):
        self.pedido.items_snapshot = []
        self.pedido.save()
        return self.client.post(
            reverse('catalogo:webhook'),
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=ok'
        )