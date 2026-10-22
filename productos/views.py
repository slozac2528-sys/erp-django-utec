# productos/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView
)

from .forms import ProductoForm
from .models import Producto


# ---------------------------------------------------------------
# Lectura (W07)
# ---------------------------------------------------------------
class ProductoListView(ListView):
    """Lista de productos."""

    model = Producto
    template_name = 'productos/lista.html'
    context_object_name = 'productos'
    paginate_by = 20


class ProductoDetailView(DetailView):
    """Detalle de un producto."""

    model = Producto
    template_name = 'productos/detalle.html'
    context_object_name = 'producto'
    pk_url_kwarg = 'producto_id'


# ---------------------------------------------------------------
# Escritura (W08)
# ---------------------------------------------------------------
class ProductoCreateView(LoginRequiredMixin, CreateView):
    """Formulario para crear un nuevo producto.

    LoginRequiredMixin PRIMERO en la herencia (obligatorio).
    """

    model = Producto
    form_class = ProductoForm
    template_name = 'productos/crear.html'
    success_url = reverse_lazy('productos:lista')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Producto "{self.object.nombre}" creado exitosamente.'
        )
        return response


class ProductoUpdateView(LoginRequiredMixin, UpdateView):
    """Formulario para editar un producto existente."""

    model = Producto
    form_class = ProductoForm
    template_name = 'productos/editar.html'
    pk_url_kwarg = 'producto_id'
    success_url = reverse_lazy('productos:lista')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Producto "{self.object.nombre}" actualizado.'
        )
        return response


class ProductoDeleteView(LoginRequiredMixin, DeleteView):
    """Confirmación y borrado de un producto (solo POST)."""

    model = Producto
    template_name = 'productos/eliminar.html'
    pk_url_kwarg = 'producto_id'
    success_url = reverse_lazy('productos:lista')

    def form_valid(self, form):
        nombre = self.object.nombre
        response = super().form_valid(form)
        messages.success(self.request, f'Producto "{nombre}" eliminado.')
        return response