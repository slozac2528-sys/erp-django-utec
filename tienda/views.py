# tienda/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from productos.models import Producto  # ajusta al nombre real de tu app/modelo

def catalogo(request):
    productos = Producto.objects.all()
    return render(request, "tienda/catalogo.html", {"productos": productos})

def agregar_al_carrito(request, producto_id):
    carrito = request.session.get("carrito", {})
    key = str(producto_id)
    carrito[key] = carrito.get(key, 0) + 1
    request.session["carrito"] = carrito
    return redirect("tienda:carrito")

def ver_carrito(request):
    carrito = request.session.get("carrito", {})
    productos = Producto.objects.filter(id__in=carrito.keys())
    items = []
    total = 0
    for p in productos:
        cant = carrito[str(p.id)]
        subtotal = p.precio * cant
        total += subtotal
        items.append((p, cant, subtotal))
    return render(request, "tienda/carrito.html",
                  {"items": items, "total": total})

def quitar_del_carrito(request, producto_id):
    carrito = request.session.get("carrito", {})
    carrito.pop(str(producto_id), None)
    request.session["carrito"] = carrito
    return redirect("tienda:carrito")