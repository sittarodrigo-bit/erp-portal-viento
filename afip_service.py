"""
Módulo de facturación electrónica AFIP/ARCA (WSAA + WSFEv1).
Usa zeep (SOAP) + cryptography para firmar el login (CMS/PKCS7).
El certificado y la clave se leen de variables de entorno (no del repo).

Variables de entorno necesarias en Railway:
  AFIP_CUIT            -> 30717499014
  AFIP_PUNTO_VENTA     -> 5
  AFIP_ENTORNO         -> homologacion  (o produccion)
  AFIP_CERT            -> contenido del .crt (texto completo, con BEGIN/END)
  AFIP_KEY             -> contenido del .key (texto completo, con BEGIN/END)

Si falta alguna variable, el módulo informa el error pero no rompe el resto de la app.
"""
import os
import base64
import datetime
from typing import Optional

# URLs de los web services
WSAA_URLS = {
    "homologacion": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl",
    "produccion":   "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl",
}
WSFE_URLS = {
    "homologacion": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL",
    "produccion":   "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL",
}

def _config():
    return {
        "cuit": os.environ.get("AFIP_CUIT", "").strip(),
        "punto_venta": int(os.environ.get("AFIP_PUNTO_VENTA", "5") or "5"),
        "entorno": (os.environ.get("AFIP_ENTORNO", "homologacion") or "homologacion").strip(),
        # Corrección para evitar errores de parseo por saltos de línea inyectados
        "cert": os.environ.get("AFIP_CERT", "").replace('\\n', '\n'),
        "key": os.environ.get("AFIP_KEY", "").replace('\\n', '\n'),
    }

class AfipError(Exception):
    pass

# Caché global del Ticket de Acceso
_TA_CACHE = None

# Caché de clientes zeep (para no descargar el WSDL en cada factura)
_CLIENTES = {}
def _get_client(url):
    from zeep import Client
    from zeep.transports import Transport
    import requests
    if url not in _CLIENTES:
        session = requests.Session()
        transport = Transport(session=session, timeout=30, operation_timeout=30)
        _CLIENTES[url] = Client(url, transport=transport)
    return _CLIENTES[url]

# ---- WSAA: crear el TRA, firmarlo (CMS) y obtener el Token+Sign ----
def _crear_tra(servicio="wsfe"):
    # Usamos hora UTC con offset explícito para que AFIP no la interprete mal.
    ahora = datetime.datetime.now(datetime.timezone.utc)
    desde = ahora - datetime.timedelta(minutes=10)
    hasta = ahora + datetime.timedelta(minutes=10)
    unique_id = int(ahora.timestamp())
    def fmt(dt):
        # Ej: 2026-06-05T12:00:00+00:00
        s = dt.strftime('%Y-%m-%dT%H:%M:%S%z')   # ...+0000
        return s[:-2] + ':' + s[-2:]              # ...+00:00
    tra = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
<header>
<uniqueId>{unique_id}</uniqueId>
<generationTime>{fmt(desde)}</generationTime>
<expirationTime>{fmt(hasta)}</expirationTime>
</header>
<service>{servicio}</service>
</loginTicketRequest>"""
    return tra

def _firmar_tra(tra: str, cert_pem: str, key_pem: str) -> str:
    """Firma el TRA en formato CMS/PKCS7 (lo que pide WSAA)."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, pkcs7, Encoding
    from cryptography.hazmat.primitives import hashes

    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    key = load_pem_private_key(key_pem.encode(), password=None)

    builder = pkcs7.PKCS7SignatureBuilder().set_data(tra.encode())
    builder = builder.add_signer(cert, key, hashes.SHA256())
    # DER, sin envoltura S/MIME; AFIP acepta el CMS en base64
    cms = builder.sign(Encoding.DER, [pkcs7.PKCS7Options.Binary])
    return base64.b64encode(cms).decode()

def _obtener_ta(cfg):
    """Devuelve (token, sign) autenticando contra WSAA.
    Cachea el TA en memoria y lo reutiliza hasta poco antes de que expire,
    porque AFIP no permite pedir uno nuevo si todavía hay uno válido."""
    import time
    global _TA_CACHE

    ahora = time.time()
    if _TA_CACHE and _TA_CACHE.get("exp", 0) > ahora + 60:
        return _TA_CACHE["token"], _TA_CACHE["sign"]

    if not cfg["cert"] or not cfg["key"]:
        raise AfipError("Faltan AFIP_CERT y/o AFIP_KEY en las variables de entorno.")
    tra = _crear_tra("wsfe")
    cms = _firmar_tra(tra, cfg["cert"], cfg["key"])
    client = _get_client(WSAA_URLS[cfg["entorno"]])
    try:
        resp = client.service.loginCms(cms)
    except Exception as e:
        msg = str(e)
        if "ya posee un TA valido" in msg or "TA valido" in msg:
            # AFIP todavía tiene vigente el TA anterior. Esperamos y reintentamos.
            import time as _t
            _t.sleep(8)
            try:
                tra2 = _crear_tra("wsfe")
                cms2 = _firmar_tra(tra2, cfg["cert"], cfg["key"])
                resp = client.service.loginCms(cms2)
            except Exception as e2:
                raise AfipError("AFIP todavía tiene un Token de Acceso anterior vigente. "
                                "Esperá unos minutos y volvé a intentar (esto pasa al pedir logins seguidos).")
        else:
            raise AfipError(f"Error en WSAA (login): {msg}")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(resp)
    token = root.findtext(".//token")
    sign = root.findtext(".//sign")
    # El TA dura 12hs; lo guardamos por 11hs para reutilizarlo.
    _TA_CACHE = {"token": token, "sign": sign, "exp": ahora + 11 * 3600}
    return token, sign

# ---- WSFEv1: pedir el próximo número y autorizar el comprobante (CAE) ----
def emitir_factura(tipo_cbte: int, doc_tipo: int, doc_nro: str,
                   neto: float, iva: float, total: float,
                   cond_iva_receptor: int = 5, punto_venta: int = None):
    """
    Emite un comprobante y devuelve dict con cae, vencimiento, numero.
    tipo_cbte: 6=Factura B, 1=Factura A, 11=Factura C
    doc_tipo: 80=CUIT, 96=DNI, 99=Consumidor Final
    punto_venta: si se pasa, usa ese (el del local); si no, el de la variable de entorno.
    """
    cfg = _config()
    if not cfg["cuit"]:
        raise AfipError("Falta AFIP_CUIT en las variables de entorno.")

    token, sign = _obtener_ta(cfg)
    cuit = int(cfg["cuit"])
    pv = int(punto_venta) if punto_venta else cfg["punto_venta"]

    client = _get_client(WSFE_URLS[cfg["entorno"]])
    auth = {"Token": token, "Sign": sign, "Cuit": cuit}

    # Último número autorizado para ese punto de venta y tipo
    ult = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=pv, CbteTipo=tipo_cbte)
    proximo = int(ult.CbteNro) + 1

    hoy = datetime.datetime.now().strftime("%Y%m%d")
    # Si es consumidor final sin identificar, doc_tipo=99 y doc_nro=0
    if not doc_nro:
        doc_tipo = 99; doc_nro = "0"

    detalle = {
        "Concepto": 1,            # productos
        "DocTipo": doc_tipo,
        "DocNro": int(doc_nro),
        "CbteDesde": proximo,
        "CbteHasta": proximo,
        "CbteFch": hoy,
        "ImpTotal": round(total, 2),
        "ImpTotConc": 0,
        "ImpNeto": round(neto, 2),
        "ImpOpEx": 0,
        "ImpIVA": round(iva, 2),
        "ImpTrib": 0,
        "MonId": "PES",
        "MonCotiz": 1,
        "CondicionIVAReceptorId": cond_iva_receptor, # <-- Campo obligatorio RG 5616
    }
    # Para Factura A/B se informa el IVA; para C no.
    if tipo_cbte in (1, 6) and iva > 0:
        detalle["Iva"] = {"AlicIva": [{"Id": 5, "BaseImp": round(neto, 2), "Importe": round(iva, 2)}]}  # Id 5 = 21%

    req = {
        "FeCabReq": {"CantReg": 1, "PtoVta": pv, "CbteTipo": tipo_cbte},
        "FeDetReq": {"FECAEDetRequest": [detalle]},
    }
    resp = client.service.FECAESolicitar(Auth=auth, FeCAEReq=req)

    # Procesar respuesta
    try:
        det = resp.FeDetResp.FECAEDetResponse[0]
        resultado = det.Resultado
        cae = det.CAE
        cae_vto = det.CAEFchVto
    except Exception:
        resultado = None; cae = None; cae_vto = None

    if resultado != "A" or not cae:
        # Buscar mensaje de error
        msg = "Rechazado por AFIP"
        try:
            obs = resp.FeDetResp.FECAEDetResponse[0].Observaciones.Obs[0]
            msg = f"{obs.Code}: {obs.Msg}"
        except Exception:
            try:
                err = resp.Errors.Err[0]
                msg = f"{err.Code}: {err.Msg}"
            except Exception:
                pass
        raise AfipError(msg)

    return {
        "cae": str(cae),
        "cae_vto": str(cae_vto),
        "numero": proximo,
        "punto_venta": pv,
        "tipo_comprobante": tipo_cbte,
        "entorno": cfg["entorno"],
        "fecha_cbte": hoy,            # YYYYMMDD del comprobante (para el QR)
        "cuit_emisor": cuit,          # CUIT de la empresa (para el QR)
        "doc_tipo": doc_tipo,         # tipo doc receptor (para el QR)
        "doc_nro": doc_nro,           # nro doc receptor (para el QR)
    }

def estado_servidores():
    """Chequeo simple: devuelve si las variables están y si responde el dummy de AFIP."""
    cfg = _config()
    info = {
        "cuit_cargado": bool(cfg["cuit"]),
        "cert_cargado": bool(cfg["cert"]),
        "key_cargada": bool(cfg["key"]),
        "punto_venta": cfg["punto_venta"],
        "entorno": cfg["entorno"],
    }
    try:
        client = _get_client(WSFE_URLS[cfg["entorno"]])
        dummy = client.service.FEDummy()
        info["afip_app"] = dummy.AppServer
        info["afip_db"] = dummy.DbServer
        info["afip_auth"] = dummy.AuthServer
    except Exception as e:
        info["error"] = str(e)
    return info

if __name__ == "__main__":
    print("Iniciando test de conexión con AFIP/ARCA...")
    try:
        status = estado_servidores()
        print("\n--- Estado de Servidores ---")
        for clave, valor in status.items():
            print(f"{clave}: {valor}")

        # --- Ejemplo de uso sugerido ---
        # Descomentar el bloque inferior para probar generar un comprobante.
        # (Ej: Venta de caja x12 a $15.200 a un Consumidor Final)

        # print("\nEmitiendo comprobante de prueba...")
        # total_venta = 15200.00
        # neto_venta = round(total_venta / 1.21, 2)
        # iva_venta = round(total_venta - neto_venta, 2)
        #
        # resultado = emitir_factura(
        #     tipo_cbte=6,         # 6 = Factura B
        #     doc_tipo=99,         # 99 = Consumidor Final
        #     doc_nro="0",         # 0 = Sin documentar
        #     neto=neto_venta,
        #     iva=iva_venta,
        #     total=total_venta,
        #     cond_iva_receptor=5  # 5 = Consumidor Final
        # )
        # print(f"¡Factura generada con éxito! N° {resultado['numero']} | CAE: {resultado['cae']}")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
