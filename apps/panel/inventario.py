"""Pantallas del inventario: insumos, kardex, compras, recetas y conteos.

El orden en que están pensadas para usarse: primero se crean los insumos, se
registra una compra (que es la que carga el stock y fija el costo), luego se
arman las recetas de los platos, y a partir de ahí el sistema descuenta solo al
facturar. Los reportes salen de eso sin que nadie tenga que llevar un Excel.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.inventory import services as inv
from apps.inventory.forms import (
    BodegaForm,
    CategoriaInsumoForm,
    CompraForm,
    CompraItemFormSet,
    ConteoForm,
    InsumoForm,
    MovimientoManualForm,
    ProveedorForm,
    RecetaForm,
    RecetaItemForm,
)
from apps.inventory.models import (
    Bodega,
    CategoriaInsumo,
    Compra,
    Conteo,
    Insumo,
    Lote,
    Movimiento,
    Proveedor,
    Receta,
    RecetaItem,
)

from .views import panel_view


def _quien(request) -> str:
    return request.user.get_full_name() or request.user.username


# ------------------------------------------------------------------- portada


@panel_view()
def inventario(request):
    """Cómo está el inventario hoy: plata parada, alertas y últimos movimientos."""
    hoy = timezone.localdate()
    return render(
        request,
        "panel/inventario.html",
        {
            "seccion": "inventario",
            "sub": "resumen",
            "resumen": inv.resumen_inventario(),
            "alertas": inv.alertas_inventario(),
            "movimientos": Movimiento.objects.select_related("insumo", "bodega")[:15],
            "food": inv.food_cost(hoy - timedelta(days=29), hoy),
            "bodegas": Bodega.objects.filter(activa=True),
            "vencimientos": Lote.objects.filter(
                cantidad__gt=0, vence__isnull=False, vence__lte=hoy + timedelta(days=10)
            ).select_related("insumo")[:10],
            "compras": Compra.objects.select_related("proveedor")[:6],
        },
    )


# -------------------------------------------------------------------- insumos


@panel_view()
def insumos(request):
    lista = Insumo.objects.select_related("categoria", "proveedor").prefetch_related("existencias")
    filtro = (request.GET.get("q") or "").strip()
    if filtro:
        lista = lista.filter(nombre__icontains=filtro)
    solo = request.GET.get("ver")
    insumos_lista = [i for i in lista if i.activo or solo == "inactivos"]
    if solo == "bajos":
        insumos_lista = [i for i in insumos_lista if i.bajo_minimo or i.stock < 0]
    elif solo == "inactivos":
        insumos_lista = [i for i in lista if not i.activo]

    return render(
        request,
        "panel/insumos.html",
        {
            "seccion": "inventario",
            "sub": "insumos",
            "insumos": insumos_lista,
            "q": filtro,
            "ver": solo or "",
            "total": sum((i.valor_stock for i in insumos_lista), Decimal("0")),
            "categorias": CategoriaInsumo.objects.all(),
        },
    )


@panel_view(solo_admin=True)
def insumo_nuevo(request):
    """El alta va en su propia pantalla: la lista no se llena de campos."""
    form = InsumoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        insumo = form.save()
        messages.success(
            request,
            f"{insumo.nombre} quedó creado. Cárgale stock con una compra o un ajuste.",
        )
        return redirect("panel:insumo-detalle", insumo_id=insumo.id)
    return render(
        request,
        "panel/insumo_form.html",
        {"seccion": "inventario", "sub": "insumos", "form": form, "es_nuevo": True},
    )


@panel_view(solo_admin=True)
def insumo_editar(request, insumo_id):
    insumo = get_object_or_404(Insumo, pk=insumo_id)
    form = InsumoForm(request.POST or None, instance=insumo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{insumo.nombre} actualizado.")
        return redirect("panel:insumo-detalle", insumo_id=insumo.id)
    return render(
        request,
        "panel/insumo_form.html",
        {"seccion": "inventario", "sub": "insumos", "form": form, "insumo": insumo},
    )


@panel_view()
def insumo_detalle(request, insumo_id):
    """El kardex valorado del insumo y el formulario de ajuste."""
    insumo = get_object_or_404(Insumo, pk=insumo_id)
    form = MovimientoManualForm(initial={"bodega": Bodega.predeterminada()})

    if request.method == "POST":
        form = MovimientoManualForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            tipo = datos["tipo"]
            try:
                if tipo in Movimiento.ENTRADAS:
                    inv.registrar_entrada(
                        insumo, datos["bodega"], datos["cantidad"],
                        datos["costo_unitario"] or insumo.costo_promedio,
                        tipo=tipo, motivo=datos["motivo"], usuario=_quien(request),
                    )
                else:
                    inv.registrar_salida(
                        insumo, datos["bodega"], datos["cantidad"],
                        tipo=tipo, motivo=datos["motivo"], usuario=_quien(request),
                    )
            except ValidationError as e:
                messages.warning(request, e.messages[0])
            else:
                messages.success(
                    request,
                    f"Movimiento registrado. {insumo.nombre} queda en "
                    f"{insumo.stock} {insumo.unidad_consumo}.",
                )
                return redirect("panel:insumo-detalle", insumo_id=insumo.id)

    return render(
        request,
        "panel/insumo_detalle.html",
        {
            "seccion": "inventario",
            "sub": "insumos",
            "insumo": insumo,
            "form": form,
            "existencias": insumo.existencias.select_related("bodega"),
            "movimientos": insumo.movimientos.select_related("bodega", "compra__proveedor")[:60],
            "lotes": insumo.lotes.filter(cantidad__gt=0),
            "recetas": insumo.en_recetas.select_related("receta__producto"),
        },
    )


@panel_view(solo_admin=True)
@require_POST
def insumo_activo(request, insumo_id):
    insumo = get_object_or_404(Insumo, pk=insumo_id)
    insumo.activo = not insumo.activo
    insumo.save(update_fields=["activo"])
    messages.success(
        request, f"{insumo.nombre} quedó {'activo' if insumo.activo else 'inactivo'}."
    )
    return redirect("panel:insumos")


# -------------------------------------------------------------------- compras


@panel_view()
def compras(request):
    hoy = timezone.localdate()
    mes = hoy.replace(day=1)
    lista = Compra.objects.select_related("proveedor", "bodega").prefetch_related("items")
    del_mes = [c for c in lista if c.fecha >= mes and c.estado == Compra.REGISTRADA]
    por_medio = {}
    for c in del_mes:
        por_medio[c.get_medio_pago_display()] = por_medio.get(
            c.get_medio_pago_display(), Decimal("0")
        ) + c.total
    return render(
        request,
        "panel/compras.html",
        {
            "seccion": "inventario",
            "sub": "compras",
            "compras": lista[:60],
            "gasto_mes": sum((c.total for c in del_mes), Decimal("0")),
            "por_medio": sorted(por_medio.items(), key=lambda x: -x[1]),
            "por_pagar": [c for c in lista if c.por_pagar],
        },
    )


@panel_view(solo_admin=True)
def compra_nueva(request):
    if not Proveedor.objects.filter(activo=True).exists():
        messages.warning(request, "Primero registra al proveedor al que le compras.")
        return redirect("panel:proveedor-nuevo")

    inicial = {"bodega": Bodega.predeterminada(), "fecha": timezone.localdate()}
    form = CompraForm(request.POST or None, initial=inicial)
    formset = CompraItemFormSet(request.POST or None, prefix="items")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        compra = form.save(commit=False)
        compra.usuario = _quien(request)
        compra.save()
        formset.instance = compra
        formset.save()
        try:
            inv.registrar_compra(compra, usuario=_quien(request))
        except ValidationError as e:
            messages.warning(request, e.messages[0])
            return redirect("panel:compra-detalle", compra_id=compra.id)
        messages.success(
            request,
            f"Compra registrada por ${compra.total:,.0f}. El stock y el costo promedio "
            f"ya quedaron actualizados.".replace(",", "."),
        )
        return redirect("panel:compra-detalle", compra_id=compra.id)

    return render(
        request,
        "panel/compra_form.html",
        {
            "seccion": "inventario",
            "sub": "compras",
            "form": form,
            "formset": formset,
            "insumos": Insumo.objects.filter(activo=True),
        },
    )


@panel_view()
def compra_detalle(request, compra_id):
    compra = get_object_or_404(
        Compra.objects.select_related("proveedor", "bodega"), pk=compra_id
    )
    return render(
        request,
        "panel/compra_detalle.html",
        {
            "seccion": "inventario",
            "sub": "compras",
            "c": compra,
            "items": compra.items.select_related("insumo"),
            "movimientos": compra.movimientos.select_related("insumo"),
        },
    )


@panel_view(solo_admin=True)
@require_POST
def compra_pagar(request, compra_id):
    compra = get_object_or_404(Compra, pk=compra_id)
    compra.pagada = True
    compra.save(update_fields=["pagada"])
    messages.success(request, f"La compra {compra.numero_factura or compra.pk} quedó como pagada.")
    return redirect("panel:compra-detalle", compra_id=compra.id)


# ---------------------------------------------------------------- proveedores


@panel_view()
def proveedores(request):
    return render(
        request,
        "panel/proveedores.html",
        {
            "seccion": "inventario",
            "sub": "proveedores",
            "proveedores": Proveedor.objects.prefetch_related("compras", "insumos"),
        },
    )


@panel_view(solo_admin=True)
def proveedor_nuevo(request):
    form = ProveedorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proveedor = form.save()
        messages.success(request, f"{proveedor.nombre} quedó registrado.")
        return redirect("panel:proveedores")
    return render(
        request,
        "panel/proveedor_form.html",
        {"seccion": "inventario", "sub": "proveedores", "form": form, "es_nuevo": True},
    )


@panel_view(solo_admin=True)
def proveedor_editar(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, pk=proveedor_id)
    form = ProveedorForm(request.POST or None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{proveedor.nombre} actualizado.")
        return redirect("panel:proveedores")
    return render(
        request,
        "panel/proveedor_form.html",
        {"seccion": "inventario", "sub": "proveedores", "form": form, "proveedor": proveedor},
    )


# -------------------------------------------------------------------- recetas


@panel_view()
def recetas(request):
    """Cada plato con su costo real y su margen; y las subrecetas aparte."""
    filas = inv.rentabilidad_por_plato()
    return render(
        request,
        "panel/recetas.html",
        {
            "seccion": "inventario",
            "sub": "recetas",
            "filas": filas,
            "sin_receta": sum(1 for f in filas if not f["tiene_receta"]),
            "subrecetas": Receta.objects.filter(es_subreceta=True).prefetch_related("items"),
        },
    )


def _receta_de_producto(producto):
    receta = getattr(producto, "receta", None)
    if receta is None:
        receta = Receta.objects.create(producto=producto, nombre=producto.name)
    return receta


@panel_view(solo_admin=True)
def receta_editar(request, producto_id=None, receta_id=None):
    """El editor: qué lleva el plato, cuánto cuesta y cuánto deja."""
    if receta_id:
        receta = get_object_or_404(Receta, pk=receta_id)
        producto = receta.producto
    else:
        producto = get_object_or_404(Product, pk=producto_id)
        receta = _receta_de_producto(producto)

    form = RecetaForm(instance=receta)
    form_item = RecetaItemForm(receta=receta)
    accion = request.POST.get("accion") if request.method == "POST" else None

    if accion == "receta":
        form = RecetaForm(request.POST, instance=receta)
        if form.is_valid():
            form.save()
            messages.success(request, "Receta guardada.")
            return redirect(_url_receta(receta))
    elif accion == "item":
        form_item = RecetaItemForm(request.POST, receta=receta)
        if form_item.is_valid():
            item = form_item.save(commit=False)
            item.receta = receta
            item.save()
            messages.success(request, f"{item.que} agregado a la receta.")
            return redirect(_url_receta(receta))
    elif accion == "quitar":
        RecetaItem.objects.filter(pk=request.POST.get("item_id"), receta=receta).delete()
        messages.success(request, "Ingrediente quitado.")
        return redirect(_url_receta(receta))

    costo = receta.costo()
    precio = producto.price if producto else None
    return render(
        request,
        "panel/receta_form.html",
        {
            "seccion": "inventario",
            "sub": "recetas",
            "receta": receta,
            "producto": producto,
            "form": form,
            "form_item": form_item,
            "items": receta.items.select_related("insumo", "subreceta"),
            "costo": costo,
            "precio": precio,
            "margen": (precio - costo) if precio is not None else None,
            "food_cost_pct": (float(costo / precio * 100) if precio else None),
            "faltantes": receta.falta_stock(),
        },
    )


def _url_receta(receta):
    from django.urls import reverse

    if receta.producto_id:
        return reverse("panel:receta-producto", args=[receta.producto_id])
    return reverse("panel:receta", args=[receta.id])


@panel_view(solo_admin=True)
def subreceta_nueva(request):
    """Una preparación intermedia («salsa base») que otros platos van a usar."""
    form = RecetaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        receta = form.save(commit=False)
        receta.es_subreceta = True
        receta.save()
        messages.success(request, f"Subreceta «{receta.titulo}» creada. Agrégale sus insumos.")
        return redirect("panel:receta", receta_id=receta.id)
    return render(
        request,
        "panel/subreceta_form.html",
        {"seccion": "inventario", "sub": "recetas", "form": form},
    )


# -------------------------------------------------------------- conteo físico


@panel_view(solo_admin=True)
def conteos(request):
    form = ConteoForm(request.POST or None, initial={"bodega": Bodega.predeterminada()})
    if request.method == "POST" and form.is_valid():
        conteo = inv.preparar_conteo(
            form.cleaned_data["bodega"],
            responsable=form.cleaned_data["responsable"] or _quien(request),
            solo_con_stock=form.cleaned_data["solo_con_stock"],
        )
        conteo.notas = form.cleaned_data["notas"]
        conteo.save(update_fields=["notas"])
        messages.success(request, "Planilla lista. Escribe lo que contaste de cada insumo.")
        return redirect("panel:conteo-detalle", conteo_id=conteo.id)
    return render(
        request,
        "panel/conteos.html",
        {
            "seccion": "inventario",
            "sub": "conteos",
            "form": form,
            "conteos": Conteo.objects.select_related("bodega").prefetch_related("items")[:30],
        },
    )


@panel_view(solo_admin=True)
def conteo_detalle(request, conteo_id):
    conteo = get_object_or_404(Conteo.objects.select_related("bodega"), pk=conteo_id)
    items = conteo.items.select_related("insumo")

    if request.method == "POST" and conteo.estado == Conteo.BORRADOR:
        if request.POST.get("accion") == "aplicar":
            try:
                resultado = inv.aplicar_conteo(conteo, usuario=_quien(request))
            except ValidationError as e:
                messages.warning(request, e.messages[0])
            else:
                messages.success(
                    request,
                    f"Conteo aplicado: {resultado['faltantes']} faltante(s) y "
                    f"{resultado['sobrantes']} sobrante(s). "
                    f"El inventario quedó igual a lo que contaste.",
                )
                return redirect("panel:conteo-detalle", conteo_id=conteo.id)
        else:
            for item in items:
                valor = request.POST.get(f"contado_{item.id}")
                if valor not in (None, ""):
                    try:
                        item.contado = Decimal(valor.replace(",", "."))
                        item.save(update_fields=["contado"])
                    except Exception:
                        pass
            messages.success(request, "Conteo guardado. Puedes seguir después.")
            return redirect("panel:conteo-detalle", conteo_id=conteo.id)

    con_diferencia = [i for i in items if i.diferencia != 0]
    return render(
        request,
        "panel/conteo_detalle.html",
        {
            "seccion": "inventario",
            "sub": "conteos",
            "c": conteo,
            "items": items,
            "con_diferencia": con_diferencia,
            "valor_diferencia": sum(
                (i.valor_diferencia for i in con_diferencia), Decimal("0")
            ),
        },
    )


# ------------------------------------------------------------------- reportes


@panel_view(solo_admin=True)
def inventario_reportes(request):
    """Food cost real contra teórico, rentabilidad por plato y rotación."""
    dias = max(1, min(int(request.GET.get("dias", 30)), 365))
    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)
    val = inv.valorizacion()
    return render(
        request,
        "panel/inventario_reportes.html",
        {
            "seccion": "inventario",
            "sub": "reportes",
            "dias": dias,
            "desde": desde,
            "hasta": hoy,
            "food": inv.food_cost(desde, hoy),
            "rentabilidad": inv.rentabilidad_por_plato(),
            "rotacion": inv.rotacion(desde, hoy),
            "valorizacion": val,
            "bodegas": [
                {"b": b, "valor": b.valorizacion()} for b in Bodega.objects.filter(activa=True)
            ],
        },
    )


# -------------------------------------------------- maestros (bodegas, etc.)


@panel_view(solo_admin=True)
def inventario_maestros(request):
    """Bodegas y categorías: se tocan una vez y casi nunca más."""
    form_bodega = BodegaForm()
    form_categoria = CategoriaInsumoForm()
    accion = request.POST.get("accion") if request.method == "POST" else None

    if accion == "bodega":
        form_bodega = BodegaForm(request.POST)
        if form_bodega.is_valid():
            bodega = form_bodega.save()
            if bodega.principal:
                Bodega.objects.exclude(pk=bodega.pk).update(principal=False)
            messages.success(request, f"Bodega «{bodega.nombre}» creada.")
            return redirect("panel:inventario-maestros")
    elif accion == "categoria":
        form_categoria = CategoriaInsumoForm(request.POST)
        if form_categoria.is_valid():
            categoria = form_categoria.save()
            messages.success(request, f"Categoría «{categoria.nombre}» creada.")
            return redirect("panel:inventario-maestros")

    return render(
        request,
        "panel/inventario_maestros.html",
        {
            "seccion": "inventario",
            "sub": "maestros",
            "form_bodega": form_bodega,
            "form_categoria": form_categoria,
            "bodegas": [
                {"b": b, "valor": b.valorizacion(), "insumos": b.existencias.count()}
                for b in Bodega.objects.all()
            ],
            "categorias": CategoriaInsumo.objects.prefetch_related("insumos"),
        },
    )
