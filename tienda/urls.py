# tienda/urls.py
from django.urls import path
from . import views

app_name = "tienda"
urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("agregar/<int:producto_id>/", views.agregar_al_carrito, name="agregar"),
    path("carrito/", views.ver_carrito, name="carrito"),
    path("carrito/quitar/<int:producto_id>/", views.quitar_del_carrito, name="quitar"),
    path("checkout/", views.checkout, name="checkout"),
]