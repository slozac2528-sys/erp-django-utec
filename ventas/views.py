from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DeleteView, DetailView, ListView

from configuracion.models import ConfiguracionERP
from core.mixins import PermisoRBACMixin
from .forms import DetalleVentaForm, VentaForm
from .models import Venta


def _ruta_local(url_path: str) -> Optional[Path]:
    """Traduce /static/... o /media/... a un archivo en disco (o None)."""
    static_prefix = "/" + settings.STATIC_URL.lstrip("/")
    media_prefix = "/" + settings.MEDIA_URL.lstrip("/")

    if url_path.startswith(static_prefix):
        relativa = url_path[len(static_prefix):]
        if settings.STATIC_ROOT:
            candidata = Path(settings.STATIC_ROOT) / relativa
            if candidata.is_file():
                return candidata
        encontrada = finders.find(relativa)  # útil en desarrollo, sin collectstatic
        return Path(encontrada) if encontrada else None

    if url_path.startswith(media_prefix) and settings.MEDIA_ROOT:
        raiz = Path(settings.MEDIA_ROOT).resolve()
        candidata = (raiz / url_path[len(media_prefix):]).resolve()
        # Evita salir de MEDIA_ROOT con rutas tipo ../
        if raiz in candidata.parents and candidata.is_file():
            return candidata
    return None


def _link_callback(uri: str, rel: str = "") -> str:
    """link_callback de xhtml2pdf: resuelve /static/ y /media/ a rutas en disco.

    Si no es un recurso local conocido, devuelve la URI sin cambios.
    """
    if uri.startswith("data:"):
        return uri

    ruta = _ruta_local(unquote(urlparse(uri).path))
    if ruta is not None:
        return str(ruta)
    return uri


def calcular_totales(subtotal, iva_porcentaje) -> dict:
    """Subtotal, IVA y total con 2 decimales (redondeo comercial)."""
    centavos = Decimal("0.01")
    subtotal = Decimal(subtotal).quantize(centavos, ROUND_HALF_UP)
    iva = (subtotal * Decimal(iva_porcentaje) / 100).quantize(centavos, ROUND_HALF_UP)
    return {"subtotal": subtotal, "iva": iva, "total_con_iva": subtotal + iva}


@login_required
def venta_pdf(request, venta_id: int) -> HttpResponse:
    """Genera y descarga la factura de una venta en formato PDF (xhtml2pdf)."""
    from xhtml2pdf import pisa  # importación diferida: solo se necesita al generar PDF

    venta = get_object_or_404(
        Venta.objects.select_related("cliente").prefetch_related(
            "detalles__producto__categoria"
        ),
        pk=venta_id,
    )
    config = ConfiguracionERP.get_instance()
    context = {
        "venta": venta,
        "config": config,
        "hoy": timezone.localtime(),  # datetime con hora, en TIME_ZONE
        **calcular_totales(venta.total, config.iva_porcentaje),
    }

    html_string = render_to_string("ventas/factura_pdf.html", context, request=request)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="factura_{venta.pk:05d}.pdf"'
    )

    resultado = pisa.CreatePDF(
        src=html_string,
        dest=response,
        encoding="UTF-8",
        link_callback=_link_callback,
    )
    if resultado.err:
        return HttpResponse("Error al generar el PDF de la factura.", status=500)
    return response


class VentaListView(ListView):
    """Lista paginada de ventas en orden cronológico inverso."""

    model               = Venta
    template_name       = 'ventas/lista.html'
    context_object_name = 'ventas'
    paginate_by         = 20

    def get_queryset(self):
        """Pre-carga cliente para evitar N+1 en la tabla de ventas."""
        return (
            Venta.objects
            .select_related('cliente')
            .order_by('-fecha')
        )


class VentaDetailView(DetailView):
    """Detalle de una venta con todas sus líneas de producto."""

    model               = Venta
    template_name       = 'ventas/detalle.html'
    context_object_name = 'venta'
    pk_url_kwarg        = 'venta_id'

    def get_queryset(self):
        """Pre-carga cliente y prefetch líneas de detalle."""
        return (
            Venta.objects
            .select_related('cliente')
            .prefetch_related('detalles__producto')
        )


@login_required
@permission_required('ventas.add_venta', raise_exception=True)
def crear_venta(request):
    """Crea un encabezado de venta con una línea de detalle.

    GET  → muestra los dos formularios vacíos.
    POST → valida ambos, guarda si correctos, muestra errores si no.

    Protección:
      - Anónimo → 302 al login (login_required).
      - Autenticado sin 'ventas.add_venta' → 403.
    Nota: para múltiples líneas usar formsets (implementar en Espiral 5).
    """
    venta_form   = VentaForm(request.POST or None)
    detalle_form = DetalleVentaForm(request.POST or None)

    if request.method == 'POST':
        if venta_form.is_valid() and detalle_form.is_valid():
            venta         = venta_form.save()
            detalle       = detalle_form.save(commit=False)
            detalle.venta = venta
            # precio_unitario se auto-captura en save() si es None
            detalle.save()
            messages.success(
                request,
                f'Venta #{venta.pk} registrada. '
                f'Total: ${venta.total:.2f}'
            )
            return redirect('ventas:detalle', venta_id=venta.pk)

    return render(request, 'ventas/crear.html', {
        'venta_form':   venta_form,
        'detalle_form': detalle_form,
    })


class VentaDeleteView(PermisoRBACMixin, DeleteView):
    """Elimina una venta. Anónimo → 302 login; sin permiso → 403."""

    model               = Venta
    template_name       = 'ventas/eliminar.html'
    pk_url_kwarg        = 'venta_id'
    success_url         = reverse_lazy('ventas:lista')
    permission_required = 'ventas.delete_venta'

    def form_valid(self, form):
        pk       = self.object.pk
        response = super().form_valid(form)
        messages.success(self.request, f'Venta #{pk} eliminada.')
        return response