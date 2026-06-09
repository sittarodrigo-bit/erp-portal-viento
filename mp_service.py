"""
Módulo de integración con Mercado Pago (Checkout Pro).
Crea preferencias de pago y consulta el estado de los pagos.
Usa la API REST de MP directamente con requests (no requiere SDK).

Variable de entorno necesaria en Railway:
  MP_ACCESS_TOKEN  -> Access Token de Mercado Pago (APP_USR-... o TEST-...)

Opcional:
  MP_BASE_URL      -> URL pública del sistema (para las redirecciones de vuelta).
                      Ej: https://erp.portaldelviento.com.ar
                      Si no se setea, se usa el valor que pase el backend.
"""
import os
import requests

MP_API = "https://api.mercadopago.com"

def _token():
    return os.environ.get("MP_ACCESS_TOKEN", "").strip()

def configurado():
    return bool(_token())

class MPError(Exception):
    pass

def crear_preferencia(titulo, monto, referencia_externa, base_url,
                      payer_email=None, notif_url=None):
    """
    Crea una preferencia de pago (Checkout Pro) y devuelve el link de pago.
    - titulo: descripción que ve el comprador (ej: "Pedido #123 - Portal del Viento")
    - monto: importe total (float)
    - referencia_externa: identificador propio (ej: "pedido-123") para reconciliar
    - base_url: URL pública del sistema, para las pantallas de retorno
    - payer_email: email del distribuidor (opcional)
    - notif_url: URL del webhook que MP llamará al confirmarse el pago
    """
    if not _token():
        raise MPError("Falta MP_ACCESS_TOKEN en las variables de entorno.")
    base = (os.environ.get("MP_BASE_URL", "") or base_url or "").rstrip("/")
    pref = {
        "items": [{
            "id": str(referencia_externa),
            "title": str(titulo)[:250],
            "description": str(titulo)[:250],
            "category_id": "food",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": round(float(monto), 2),
        }],
        "external_reference": str(referencia_externa),
        "statement_descriptor": "PORTALVIENTO",
        "binary_mode": False,
    }
    # back_urls + auto_return solo si tenemos una URL pública https válida
    if base and base.startswith("https://"):
        pref["back_urls"] = {
            "success": base + "/portal-distribuidores?pago=ok",
            "pending": base + "/portal-distribuidores?pago=pendiente",
            "failure": base + "/portal-distribuidores?pago=error",
        }
        pref["auto_return"] = "approved"
        pref["notification_url"] = base + "/api/mp/webhook"
    if payer_email:
        pref["payer"] = {"email": payer_email}
    if notif_url:
        pref["notification_url"] = notif_url

    r = requests.post(MP_API + "/checkout/preferences",
                      json=pref,
                      headers={"Authorization": "Bearer " + _token()},
                      timeout=45)
    if r.status_code not in (200, 201):
        # Devolvemos el cuerpo crudo de MP para poder diagnosticar (status + mensaje)
        raise MPError("HTTP " + str(r.status_code) + " :: " + r.text[:500])
    data = r.json()
    return {
        "id": data.get("id"),
        "init_point": data.get("init_point"),              # link de pago (producción)
        "sandbox_init_point": data.get("sandbox_init_point"),  # link de prueba
    }

def buscar_pagos_por_preferencia(preference_id):
    """Busca pagos aprobados asociados a una preferencia. Más confiable que external_reference."""
    if not _token():
        raise MPError("Falta MP_ACCESS_TOKEN.")
    r = requests.get(MP_API + "/v1/payments/search",
                     params={"preference_id": preference_id, "sort": "date_created", "criteria": "desc"},
                     headers={"Authorization": "Bearer " + _token()},
                     timeout=45)
    if r.status_code != 200:
        raise MPError("HTTP " + str(r.status_code) + " :: " + r.text[:400])
    d = r.json()
    out = []
    for p in d.get("results", []):
        out.append({
            "id": p.get("id"),
            "estado": p.get("status"),
            "monto": p.get("transaction_amount"),
            "external_reference": p.get("external_reference"),
        })
    return out

def buscar_pagos(external_reference):
    """Busca pagos en MP por external_reference. Devuelve lista de pagos aprobados."""
    if not _token():
        raise MPError("Falta MP_ACCESS_TOKEN.")
    r = requests.get(MP_API + "/v1/payments/search",
                     params={"external_reference": external_reference, "sort": "date_created", "criteria": "desc"},
                     headers={"Authorization": "Bearer " + _token()},
                     timeout=45)
    if r.status_code != 200:
        raise MPError("HTTP " + str(r.status_code) + " :: " + r.text[:400])
    d = r.json()
    out = []
    for p in d.get("results", []):
        out.append({
            "id": p.get("id"),
            "estado": p.get("status"),
            "monto": p.get("transaction_amount"),
            "external_reference": p.get("external_reference"),
        })
    return out

def consultar_pago(payment_id):
    """Consulta un pago por su id y devuelve (estado, external_reference, monto)."""
    if not _token():
        raise MPError("Falta MP_ACCESS_TOKEN.")
    r = requests.get(MP_API + "/v1/payments/" + str(payment_id),
                     headers={"Authorization": "Bearer " + _token()},
                     timeout=45)
    if r.status_code != 200:
        raise MPError("Error consultando pago: " + r.text[:300])
    d = r.json()
    return {
        "estado": d.get("status"),                      # approved, pending, rejected...
        "external_reference": d.get("external_reference"),
        "monto": d.get("transaction_amount"),
        "metodo": d.get("payment_method_id"),
    }
