## Sprint Backlog — actualización W13

| Tarea | Estado |
|---|---|
| App catalogo + django-filter | ✅ W13 |
| ProductoFilter (nombre/categoría/precio) | ✅ W13 |
| CatalogoView pública con paginación | ✅ W13 |
| Carrito en sesión (agregar/remover/actualizar/vaciar) | ✅ W13 |
| Context processor carrito_info | ✅ W13 |
| Template catalogo.html con tarjetas | ✅ W13 |
| Template carrito.html con tabla | ✅ W13 |
| Contador carrito en navbar base.html | ✅ W13 |
| 8 tests de e-commerce | ✅ W13 |
| Checkout con Stripe sandbox | ⏳ W14 |
| Webhooks y estados de pedido | ⏳ W15 |
## Sprint Backlog — actualización W14

| Tarea | Estado |
|---|---|
| Catálogo + carrito + context processor | ✅ W13 |
| pip install stripe | ✅ W14 |
| STRIPE_* en settings.py y .env | ✅ W14 |
| checkout_utils.py (calcular_totales, obtener_cliente) | ✅ W14 |
| CheckoutView (GET/POST) con PaymentIntent | ✅ W14 |
| Template checkout.html con Stripe.js Card Element | ✅ W14 |
| pago_exitoso: vaciar carrito + template | ✅ W14 |
| pago_error: template con causas y reintento | ✅ W14 |
| Tests con unittest.mock.patch | ✅ W14 |
| Webhooks + actualizar estado pedido | ⏳ W15 |
| Descontar stock al confirmar pago | ⏳ W15 |

## Sprint 4 — Estado final W15

| HU | Estado | Pts |
|---|---|---|
| HU-E5-01 a HU-E5-08 | ✅ Completadas | 26/26 |

## Hito M5 — ALCANZADO ✅
- Catálogo: /catalogo/ → 200 sin auth con filtros
- Carrito: agregar/remover/actualizar/vaciar funcional
- Stripe: tarjeta 4242 → pago exitoso → pedido 'pagado'
- Webhook: payment_intent.succeeded → stock decrementado
- Tests: Ran 147 tests → OK
- Fecha: ___/___/_____
