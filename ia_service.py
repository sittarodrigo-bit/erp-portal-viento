"""
ia_service.py — Asistente IA del Tablero (Portal del Viento)

Usa la API de Anthropic con la librería estándar de Python (urllib),
así que NO hace falta agregar nada a requirements.txt.

Variables de entorno en Railway:
  ANTHROPIC_API_KEY  (obligatoria)  -> la key sk-ant-...
  ANTHROPIC_MODEL    (opcional)     -> modelo a usar (default abajo)
"""

import os
import json
import urllib.request
import urllib.error

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODELO_DEFAULT = "claude-sonnet-4-5"
TIMEOUT_SEG = 60
MAX_TOKENS = 1024


def _api_key():
    return (os.getenv("ANTHROPIC_API_KEY") or "").strip()


def _modelo():
    return (os.getenv("ANTHROPIC_MODEL") or MODELO_DEFAULT).strip()


def esta_configurado():
    """True si hay una API key cargada en Railway."""
    return bool(_api_key())


SYSTEM_PROMPT = """Sos el asistente interno de Portal del Viento, una fábrica artesanal de alfajores
y productos regionales de Mendoza, Argentina (fábrica en Godoy Cruz, locales Portalito y Sarmiento,
venta a distribuidores B2B y online).

Respondés preguntas del dueño sobre el negocio usando SOLO el resumen de datos que te paso en JSON.
Reglas:
- Respondé en español rioplatense, corto, claro y directo.
- Montos en pesos argentinos con separador de miles (ej: $ 1.234.567).
- Si el dato no está en el resumen, decilo claramente; no inventes números.
- Cuando sirva, usá listas cortas.
- Stock de fábrica está en CAJAS."""


def preguntar(pregunta, resumen):
    """
    Manda la pregunta + el resumen de datos a Claude.
    Devuelve {"ok": True, "respuesta": str} o {"ok": False, "error": str}.
    """
    key = _api_key()
    if not key:
        return {"ok": False, "error": "Falta la variable ANTHROPIC_API_KEY en Railway."}

    contenido = (
        "Datos actuales del negocio (JSON):\n"
        + json.dumps(resumen or {}, ensure_ascii=False, default=str, indent=2)
        + "\n\nPregunta: "
        + str(pregunta)
    )

    body = {
        "model": _modelo(),
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": contenido}],
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEG) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detalle = ""
        if e.code == 401:
            msg = "La API key es inválida. Revisá ANTHROPIC_API_KEY en Railway."
        elif e.code == 404:
            msg = f"El modelo '{_modelo()}' no existe. Cargá otro en la variable ANTHROPIC_MODEL."
        elif e.code == 429:
            msg = "Demasiadas consultas o sin crédito. Probá en un rato o revisá Billing en Anthropic."
        elif e.code == 400 and "credit" in detalle.lower():
            msg = "La cuenta de Anthropic no tiene crédito. Cargá saldo en Billing."
        else:
            msg = f"Error de la IA ({e.code}). {detalle}".strip()
        print(f"[ia_service] HTTPError {e.code}: {detalle}")
        return {"ok": False, "error": msg}
    except Exception as e:
        print(f"[ia_service] Error: {e}")
        return {"ok": False, "error": "No se pudo conectar con la IA. Probá de nuevo."}

    texto = "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()
    if not texto:
        return {"ok": False, "error": "La IA no devolvió respuesta."}
    return {"ok": True, "respuesta": texto}
