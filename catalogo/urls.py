from django.urls import path

from . import views
from .webhook_views import stripe_webhook

app_name = 'catalogo'

urlpatterns = [
    path('', views.CatalogoView.as_view(), name='catalogo'),
    path('carrito/', views.ver_carrito, name='carrito'),
    path('agregar/<int:producto_id>/', views.agregar_al_carrito, name='agregar'),
    path('quitar/<int:producto_id>/', views.remover_del_carrito, name='quitar'),
    path('remover/<int:producto_id>/', views.remover_del_carrito, name='remover'),
    path('actualizar/<int:producto_id>/', views.actualizar_cantidad, name='actualizar'),
    path('vaciar/', views.vaciar_carrito, name='vaciar'),
    path('checkout/', views.checkout, name='checkout'),
    path('pago/exito/<int:pedido_id>/', views.pago_exitoso, name='pago_exitoso'),
    path('pago/error/', views.pago_error, name='pago_error'),
    path('webhook/', stripe_webhook, name='webhook'),
]