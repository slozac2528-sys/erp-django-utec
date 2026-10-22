# proveedores/urls.py
from django.urls import path
from . import views

app_name = 'proveedores'

urlpatterns = [
    path('',                            views.ProveedorListView.as_view(),   name='lista'),
    path('inicio/',                     views.ProveedorListView.as_view(template_name='proveedores/index.html'), name='inicio'),
    path('<int:proveedor_id>/',         views.ProveedorDetailView.as_view(), name='detalle'),
    path('nuevo/',                      views.ProveedorCreateView.as_view(), name='crear'),
    path('<int:proveedor_id>/editar/',  views.ProveedorUpdateView.as_view(), name='editar'),
    path('<int:proveedor_id>/eliminar/', views.ProveedorDeleteView.as_view(), name='eliminar'),
]