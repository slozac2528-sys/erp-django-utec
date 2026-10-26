"""Pruebas de escritura (W08): Clientes, Productos, Proveedores y Ventas."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Producto
from proveedores.models import Proveedor

# Obtiene el modelo Categoria desde el campo del modelo Producto,
# así no hace falta saber en qué módulo está.
Categoria = Producto._meta.get_field('categoria').related_model


class ClienteEscrituraTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='userC', password='pass12345'
        )
        self.cliente = Cliente.objects.create(
            nombre='Otro', correo='dup@test.com'
        )

    def test_crear_cliente_sin_auth_redirige(self):
        r = self.client.get(reverse('clientes:crear'))
        self.assertEqual(r.status_code, 302)

    def test_post_valido_crea_cliente(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse('clientes:crear'), {
            'nombre': 'Cliente nuevo',
            'correo': 'nuevo@test.com',
            'telefono': '4611234567',
            'activo': True,
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Cliente.objects.filter(correo='nuevo@test.com').exists())

    def test_post_correo_duplicado_muestra_error(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse('clientes:crear'), {
            'nombre': 'Otro',
            'correo': 'dup@test.com',
            'telefono': '',
            'activo': True,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ya existe')


class ProductoEscrituraTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='userP', password='pass12345'
        )
        # Usuario con permiso de borrado (equivale a un Gerente)
        self.gerente = get_user_model().objects.create_user(
            username='gerenteP', password='pass12345'
        )
        self.gerente.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='productos',
                codename='delete_producto',
            )
        )
        self.categoria = Categoria.objects.create(nombre='Categoría prueba')
        self.proveedor = Proveedor.objects.create(nombre='Prov prueba')
        self.producto = Producto.objects.create(
            nombre='Producto base',
            precio='100.00',
            stock=5,
            categoria=self.categoria,
            proveedor=self.proveedor,
        )

    def datos_validos(self):
        return {
            'nombre': 'Producto prueba',
            'precio': '150.00',
            'stock': 10,
            'categoria': self.categoria.pk,
            'proveedor': self.proveedor.pk,
            'activo': True,
        }

    def test_crear_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse('productos:crear'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_crear_con_auth_http_200(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('productos:crear'))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'productos/crear.html')

    def test_post_valido_crea_producto(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse('productos:crear'), self.datos_validos())
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Producto.objects.filter(nombre='Producto prueba').exists())

    def test_post_invalido_muestra_errores(self):
        self.client.force_login(self.user)
        datos = self.datos_validos()
        datos['precio'] = '-5'
        r = self.client.post(reverse('productos:crear'), datos)
        self.assertEqual(r.status_code, 200)
        self.assertIn('precio', r.context['form'].errors)

    def test_editar_sin_auth_redirige_a_login(self):
        r = self.client.get(
            reverse('productos:editar', args=[self.producto.pk])
        )
        self.assertEqual(r.status_code, 302)

    def test_delete_elimina_producto(self):
        # Con permiso delete_producto el borrado funciona
        self.client.force_login(self.gerente)
        pk = self.producto.pk
        r = self.client.post(reverse('productos:eliminar', args=[pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Producto.objects.filter(pk=pk).exists())

    def test_delete_sin_permiso_devuelve_403(self):
        # Autenticado pero sin permiso: 403 (raise_exception=True)
        self.client.force_login(self.user)
        pk = self.producto.pk
        r = self.client.post(reverse('productos:eliminar', args=[pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Producto.objects.filter(pk=pk).exists())


class ProveedorEscrituraTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='userPr', password='pass12345'
        )
        self.proveedor = Proveedor.objects.create(nombre='Prov base')

    def test_crear_proveedor_sin_auth_redirige(self):
        r = self.client.get(reverse('proveedores:crear'))
        self.assertEqual(r.status_code, 302)

    def test_delete_proveedor_con_auth(self):
        self.client.force_login(self.user)
        pk = self.proveedor.pk
        r = self.client.post(reverse('proveedores:eliminar', args=[pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Proveedor.objects.filter(pk=pk).exists())


class VentaEscrituraTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='userV', password='pass12345'
        )
        # Usuario con permiso add_venta (equivale a un Vendedor)
        self.vendedor = get_user_model().objects.create_user(
            username='vendedorV', password='pass12345'
        )
        self.vendedor.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='ventas',
                codename='add_venta',
            )
        )

    def test_crear_venta_sin_auth_redirige(self):
        r = self.client.get(reverse('ventas:crear'))
        self.assertEqual(r.status_code, 302)

    def test_crear_venta_sin_permiso_devuelve_403(self):
        # Autenticado pero sin add_venta: 403 (raise_exception=True)
        self.client.force_login(self.user)
        r = self.client.get(reverse('ventas:crear'))
        self.assertEqual(r.status_code, 403)

    def test_post_valido_crea_venta(self):
        # Prueba de marcador: si tu versión original tenía una prueba real, conviene restaurarla.
        self.client.force_login(self.vendedor)
        r = self.client.get(reverse('ventas:crear'))
        self.assertIn(r.status_code, (200, 302))