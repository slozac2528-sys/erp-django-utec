"""Suite de pruebas W14 — Checkout y proceso de pago con Stripe.

Usa unittest.mock.patch para simular stripe.PaymentIntent.create
sin requerir claves reales ni conexión a internet.

W16: pago_exitoso() ya NO encola la tarea de correo (la encola el
webhook). Los tests de pago_exitoso parchean
ventas.tasks.enviar_confirmacion_pedido.delay para comprobar que la
vista no la invoca y para no depender de Redis.

Ejecutar con:
    python manage.py test tests.test_w14_checkout --verbosity=2

Resultado esperado:
    Ran 13 tests in X.XXXs
    OK
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from clientes.models        import Cliente
from configuracion.models   import ConfiguracionERP
from productos.models       import Categoria, Producto
from ventas.models          import Pedido


def _setup_carrito(client, producto):
    """Agrega un producto al carrito de la sesión del test client."""
    client.post(
        reverse('catalogo:agregar', args=[producto.pk]),
        {'cantidad': 2}
    )


def _mock_payment_intent():
    """Mock del PaymentIntent de Stripe con valores serializables.

    Todos los atributos que la vista lee (y puede guardar en la sesión)
    deben ser strings reales; si no, MagicMock devuelve otro MagicMock
    y Django falla al serializar la sesión a JSON.
    """
    return MagicMock(id='pi_test_123', client_secret='pi_test_secret')


class CheckoutAutenticacionTest(TestCase):
    """Tests de autenticación del checkout."""

    def test_checkout_sin_auth_redirige_a_login(self):
        """GET /catalogo/checkout/ sin login → 302 a /accounts/login/."""
        r = self.client.get(reverse('catalogo:checkout'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_checkout_carrito_vacio_redirige_a_catalogo(self):
        """Checkout con carrito vacío → redirect al catálogo."""
        user = User.objects.create_user('empty', password='pass')
        self.client.force_login(user)
        r = self.client.get(reverse('catalogo:checkout'))
        self.assertRedirects(r, reverse('catalogo:catalogo'),
                             fetch_redirect_response=False)

    def test_checkout_get_con_carrito_devuelve_200(self):
        """GET /catalogo/checkout/ con carrito → 200 (resumen visible)."""
        ConfiguracionERP.get_instance()
        cat  = Categoria.objects.create(nombre='Cat')
        prod = Producto.objects.create(
            nombre='P', precio=Decimal('100.00'),
            stock=5, categoria=cat
        )
        user = User.objects.create_user('userco', password='pass',
                                        email='userco@test.com')
        self.client.force_login(user)
        _setup_carrito(self.client, prod)
        r = self.client.get(reverse('catalogo:checkout'))
        self.assertEqual(r.status_code, 200)


class CheckoutPagoTest(TestCase):
    """Tests del proceso POST de checkout con Stripe mockeado."""

    def setUp(self):
        ConfiguracionERP.get_instance()
        cat       = Categoria.objects.create(nombre='Cat')
        self.prod = Producto.objects.create(
            nombre='Laptop', precio=Decimal('500.00'),
            stock=5, categoria=cat
        )
        self.user = User.objects.create_user(
            'payer', password='pass', email='payer@test.com'
        )
        self.client.force_login(self.user)
        _setup_carrito(self.client, self.prod)   # 2 × 500 = 1000

    @patch('catalogo.views.stripe.PaymentIntent.create')
    def test_post_checkout_crea_pedido(self, mock_pi):
        """POST /catalogo/checkout/ → se crea un Pedido en BD."""
        mock_pi.return_value = _mock_payment_intent()
        self.client.post(reverse('catalogo:checkout'))
        self.assertEqual(Pedido.objects.count(), 1)

    @patch('catalogo.views.stripe.PaymentIntent.create')
    def test_post_checkout_pedido_estado_pendiente(self, mock_pi):
        """El Pedido creado debe tener estado 'pendiente'."""
        mock_pi.return_value = _mock_payment_intent()
        self.client.post(reverse('catalogo:checkout'))
        pedido = Pedido.objects.first()
        self.assertEqual(pedido.estado, 'pendiente')

    @patch('catalogo.views.stripe.PaymentIntent.create')
    def test_post_checkout_calcula_iva(self, mock_pi):
        """El total del Pedido debe incluir el IVA configurado."""
        mock_pi.return_value = _mock_payment_intent()
        self.client.post(reverse('catalogo:checkout'))
        pedido    = Pedido.objects.first()
        config    = ConfiguracionERP.get_instance()
        subtotal  = Decimal('1000.00')   # 2 × 500
        iva_pct   = config.iva_porcentaje / 100
        esperado  = (subtotal + subtotal * iva_pct).quantize(Decimal('0.01'))
        self.assertEqual(pedido.total_pagado, esperado)

    @patch('catalogo.views.stripe.PaymentIntent.create')
    def test_post_checkout_crea_cliente_erp(self, mock_pi):
        """Se debe crear (o encontrar) un Cliente ERP para el usuario."""
        mock_pi.return_value = _mock_payment_intent()
        self.client.post(reverse('catalogo:checkout'))
        self.assertTrue(
            Cliente.objects.filter(correo=self.user.email).exists()
        )

    @patch('catalogo.views.stripe.PaymentIntent.create')
    def test_post_checkout_llama_stripe_con_monto_correcto(self, mock_pi):
        """Stripe debe recibir el monto en centavos."""
        mock_pi.return_value = _mock_payment_intent()
        self.client.post(reverse('catalogo:checkout'))
        config   = ConfiguracionERP.get_instance()
        subtotal = Decimal('1000.00')
        total    = subtotal + subtotal * (config.iva_porcentaje / 100)
        centavos = int(total.quantize(Decimal('0.01')) * 100)
        mock_pi.assert_called_once()
        args, kwargs = mock_pi.call_args
        self.assertEqual(kwargs.get('amount') or args[0], centavos)


class PagoExitosoTest(TestCase):
    """Tests de la vista pago_exitoso.

    La vista exige:
      1. Sesión iniciada (@login_required).
      2. session['ultimo_pedido_id'] == pedido_id (si no → 302 a catálogo).
      3. Que Stripe confirme el PaymentIntent como 'succeeded' y que su
         metadata.pedido_id coincida con el pedido (se simula con mock).

    W16: la vista NO encola la tarea de correo; eso lo hace el webhook.
    """

    INTENT_ID = 'pi_test_123'

    def setUp(self):
        # W16: la tarea vive en ventas.tasks. Se parchea ahí para comprobar
        # que pago_exitoso NO la invoca (y para no depender de Redis).
        patch_delay = patch(
            'ventas.tasks.enviar_confirmacion_pedido.delay'
        )
        self.mock_delay = patch_delay.start()
        self.addCleanup(patch_delay.stop)

        # Simula stripe.PaymentIntent.retrieve(...).to_dict()
        patch_retrieve = patch('catalogo.views.stripe.PaymentIntent.retrieve')
        self.mock_retrieve = patch_retrieve.start()
        self.addCleanup(patch_retrieve.stop)

        ConfiguracionERP.get_instance()
        cat  = Categoria.objects.create(nombre='C')
        Producto.objects.create(
            nombre='P', precio=Decimal('100.00'), stock=5, categoria=cat
        )
        cli  = Cliente.objects.create(nombre='C', correo='c@t.com')
        self.pedido = Pedido.objects.create(
            numero_pedido='PED-2025-0001',
            cliente=cli,
            estado='pendiente',
            total_pagado=Decimal('116.00')
        )
        self.user = User.objects.create_user(
            'buyer', password='pass', email='c@t.com'
        )
        self.client.force_login(self.user)

        self._configurar_stripe(status='succeeded',
                                pedido_id=str(self.pedido.pk))

    def _configurar_stripe(self, status, pedido_id):
        """Define qué devuelve Stripe al verificar el PaymentIntent."""
        intent = MagicMock()
        intent.to_dict.return_value = {
            'status':   status,
            'metadata': {'pedido_id': pedido_id},
        }
        self.mock_retrieve.return_value = intent

    def _preparar_sesion(self, con_carrito=True, pedido_id=None):
        """Simula lo que checkout() deja en la sesión antes de pagar."""
        session = self.client.session
        session['ultimo_pedido_id'] = (
            self.pedido.pk if pedido_id is None else pedido_id
        )
        session['ultimo_intent_id'] = self.INTENT_ID
        if con_carrito:
            session['carrito'] = {
                '1': {'nombre': 'P', 'precio': '100', 'cantidad': 1}
            }
        session.save()

    def _get_pago_exitoso(self):
        return self.client.get(
            reverse('catalogo:pago_exitoso', args=[self.pedido.pk])
        )

    def test_pago_exitoso_devuelve_200(self):
        """GET /catalogo/pago-exitoso/<id>/ con pago confirmado → 200."""
        self._preparar_sesion()
        r = self._get_pago_exitoso()
        self.assertEqual(
            r.status_code, 200,
            f"Redirige a: {r.get('Location')}"
        )

    def test_pago_exitoso_vacia_carrito(self):
        """Visitar pago_exitoso vacía la sesión del carrito."""
        self._preparar_sesion(con_carrito=True)
        r = self._get_pago_exitoso()
        self.assertEqual(
            r.status_code, 200,
            f"Redirige a: {r.get('Location')}"
        )
        # El carrito en la sesión debe quedar vacío
        self.assertEqual(
            self.client.session.get('carrito', {}), {}
        )

    def test_pago_exitoso_no_encola_tarea(self):
        """W16: la vista NO encola la tarea; el webhook es el único disparo."""
        self._preparar_sesion()
        r = self._get_pago_exitoso()
        self.assertEqual(
            r.status_code, 200,
            f"Redirige a: {r.get('Location')}"
        )
        self.mock_delay.assert_not_called()

    def test_pago_exitoso_sin_sesion_de_pedido_redirige_a_catalogo(self):
        """Sin ultimo_pedido_id en la sesión → 302 al catálogo y sin tarea."""
        r = self._get_pago_exitoso()
        self.assertRedirects(r, reverse('catalogo:catalogo'),
                             fetch_redirect_response=False)
        self.mock_delay.assert_not_called()

    def test_pago_exitoso_pago_no_confirmado_redirige_a_error(self):
        """Si Stripe no dice 'succeeded' → 302 a pago_error y sin tarea."""
        self._preparar_sesion()
        self._configurar_stripe(status='requires_payment_method',
                                pedido_id=str(self.pedido.pk))
        r = self._get_pago_exitoso()
        self.assertRedirects(r, reverse('catalogo:pago_error'),
                             fetch_redirect_response=False)
        self.mock_delay.assert_not_called()