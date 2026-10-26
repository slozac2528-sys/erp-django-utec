"""Mixins compartidos del ERP."""
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class PermisoRBACMixin(PermissionRequiredMixin):
    """Control de acceso por permiso con respuesta diferenciada.

    - Usuario anónimo            → 302 a la página de login.
    - Autenticado sin permiso    → 403 (PermissionDenied).
    """

    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path())
        raise PermissionDenied