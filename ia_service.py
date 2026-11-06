"""
ia_service.py — Asistente IA del Tablero (Portal del Viento)

El asistente tiene acceso de SOLO LECTURA a toda la base de datos:
  - Recibe el esquema completo (tablas y columnas) en cada pregunta.
  - Puede ejecutar consultas SELECT que él mismo arma para responder.
  - Las consultas corren en una transacción READ ONLY con timeout:
    no puede modificar, borrar ni insertar nada.
  - Columnas sensibles (pin, password, token, clave, certificados, etc.)
    se ocultan del esquema y de los resultados.

Usa la librería estándar (urllib): no hace falta tocar requirements.txt.

Variables de entorno en Railway:
  ANTHROPIC_API_KEY  (obligatoria)
  ANTHROPIC_MODEL    (opcional, default abajo)
"""

import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODELO_DEFAULT = "claude-sonnet-4-5"
TIMEOUT_SEG = 90
MAX_TOKENS = 2048
MAX_VUELTAS = 10          # máximo de consultas SQL por pregunta
MAX_FILAS = 200           # filas devueltas por consulta
MAX_CHARS_RESULTADO = 30000
STATEMENT_TIMEOUT_MS = 15000

# Columnas que NUNCA se muestran a la IA
RE_SENSIBLE = re.compile(
    r"(pin|password|passwd|pass_|_pass|contrasena|contraseña|clave|token|secret|"
    r"api_key|apikey|cert|private|privada|hash|salt|cbu|cvu|tarjeta)",
    re.IGNORECASE,
)

# Palabras que no se permiten en las consultas
RE_PROHIBIDO = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|reindex|cluster|comment|lock|call|do|execute|prepare|listen|notify|"
    r"set|reset|begin|commit|rollback|savepoint|pg_sleep|pg_read|pg_ls|lo_|dblink)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- config

def _api_key():
    return (os.getenv("ANTHROPIC_API_KEY") or "").strip()


def _modelo():
    return (os.getenv("ANTHROPIC_MODEL") or MODELO_DEFAULT).strip()


def esta_configurado():
    return bool(_api_key())


# ---------------------------------------------------------------- base de datos

def _cursor(conn):
    try:
        from psycopg2.extras import RealDictCursor
        return conn.cursor(cursor_factory=RealDictCursor)
    except Exception:
        return conn.cursor()


def _filas_a_dict(cur, filas):
    if filas and isinstance(filas[0], dict):
        return [dict(f) for f in filas]
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, f)) for f in filas]


def _iniciar_solo_lectura(conn, cur):
    if getattr(conn, "autocommit", False):
        cur.execute("BEGIN READ ONLY")
    else:
        conn.rollback()
        cur.execute("SET TRANSACTION READ ONLY")
    cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")


def _cerrar(conn, cur):
    try:
        cur.execute("ROLLBACK")
    except Exception:
        pass
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        cur.close()
    except Exception:
        pass


def obtener_esquema(obtener_conexion, liberar_conexion):
    """Devuelve 'tabla: col (tipo), ...' de todas las tablas públicas."""
    conn = obtener_conexion()
    cur = _cursor(conn)
    try:
        _iniciar_solo_lectura(conn, cur)
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        filas = _filas_a_dict(cur, cur.fetchall())
    finally:
        _cerrar(conn, cur)
        liberar_conexion(conn)

    tablas = {}
    for f in filas:
        col = f["column_name"]
        if RE_SENSIBLE.search(col):
            continue
        tablas.setdefault(f["table_name"], []).append(f"{col} ({f['data_type']})")
    return "\n".join(f"- {t}: {', '.join(c)}" for t, c in tablas.items())


def ejecutar_consulta(sql, obtener_conexion, liberar_conexion):
    """Ejecuta un SELECT en modo solo lectura. Devuelve texto JSON."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return "ERROR: consulta vacía."
    if ";" in sql:
        return "ERROR: solo se permite UNA consulta, sin ';'."
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        return "ERROR: solo se permiten consultas SELECT (o WITH ... SELECT)."
    if RE_PROHIBIDO.search(sql):
        return "ERROR: la consulta contiene palabras no permitidas (solo lectura)."

    conn = obtener_conexion()
    cur = _cursor(conn)
    try:
        _iniciar_solo_lectura(conn, cur)
        cur.execute(sql)
        filas = _filas_a_dict(cur, cur.fetchmany(MAX_FILAS + 1))
    except Exception as e:
        return f"ERROR SQL: {str(e).strip()[:500]}"
    finally:
        _cerrar(conn, cur)
        liberar_conexion(conn)

    cortado = len(filas) > MAX_FILAS
    filas = filas[:MAX_FILAS]
    limpias = [{k: v for k, v in f.items() if not RE_SENSIBLE.search(str(k))} for f in filas]
    texto = json.dumps(limpias, ensure_ascii=False, default=str)
    if len(texto) > MAX_CHARS_RESULTADO:
        texto = texto[:MAX_CHARS_RESULTADO] + " ...[recortado]"
    nota = f" (se muestran las primeras {MAX_FILAS} filas; usá agregaciones o LIMIT)" if cortado else ""
    return f"{len(limpias)} filas{nota}:\n{texto}"


# ---------------------------------------------------------------- IA

HERRAMIENTAS = [{
    "name": "consultar_bd",
    "description": (
        "Ejecuta UNA consulta SQL de solo lectura (SELECT o WITH...SELECT) en la base "
        "PostgreSQL del ERP y devuelve las filas en JSON (máximo 200). Usala todas las "
        "veces que necesites para responder con datos reales. Preferí agregaciones "
        "(SUM, COUNT, GROUP BY) y LIMIT para no traer filas de más."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Consulta SELECT de PostgreSQL"},
            "motivo": {"type": "string", "description": "Para qué hacés esta consulta (breve)"},
        },
        "required": ["sql"],
    },
}]


def _system_prompt(esquema):
    hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""Sos el asistente interno de Portal del Viento, fábrica artesanal de alfajores y
productos regionales de Mendoza, Argentina (fábrica en Godoy Cruz, locales Portalito y
Sarmiento, venta B2B a distribuidores, reparto y venta online).

Respondés preguntas del dueño consultando la base de datos del ERP con la herramienta
consultar_bd. Fecha y hora del servidor: {hoy}.

Cómo trabajar:
- Mirá el esquema, armá las consultas necesarias y respondé con datos reales. Nunca inventes.
- Si una consulta falla, corregila y probá de nuevo.
- Buscá textos con ILIKE '%...%' (los nombres pueden tener errores de tipeo, ej. "bayles").
- Notas del negocio: stock de fábrica en CAJAS; pedidos B2B en CAJAS; reposiciones a locales
  en UNIDADES (dividir por unidades_por_caja). Pedidos B2B cancelados no cuentan como enviados.
- Respuesta final: español rioplatense, corta y directa. Montos como $ 1.234.567.
  Usá listas o tablas cortas cuando ayude. Incluí número de pedido/fecha cuando corresponda.

Esquema de la base (tabla: columnas):
{esquema}
"""


def _llamar_api(body):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, default=str).encode("utf-8"),
        headers={
            "x-api-key": _api_key(),
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEG) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _mensaje_error_http(e):
    try:
        detalle = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
    except Exception:
        detalle = ""
    print(f"[ia_service] HTTPError {e.code}: {detalle}")
    if e.code == 401:
        return "La API key es inválida. Revisá ANTHROPIC_API_KEY en Railway."
    if e.code == 404:
        return f"El modelo '{_modelo()}' no existe. Cargá otro en la variable ANTHROPIC_MODEL."
    if e.code == 429:
        return "Demasiadas consultas o sin crédito. Probá en un rato o revisá Billing en Anthropic."
    if e.code == 400 and "credit" in detalle.lower():
        return "La cuenta de Anthropic no tiene crédito. Cargá saldo en Billing."
    return f"Error de la IA ({e.code}). {detalle}".strip()


def preguntar(pregunta, obtener_conexion, liberar_conexion, historial=None):
    """
    pregunta: texto del usuario
    obtener_conexion / liberar_conexion: funciones de main.py
    historial: opcional, lista [{"role": "user"|"assistant", "content": str}, ...]
    Devuelve {"ok": True, "respuesta": str, "consultas": int} o {"ok": False, "error": str}
    """
    if not esta_configurado():
        return {"ok": False, "error": "Falta la variable ANTHROPIC_API_KEY en Railway."}

    try:
        esquema = obtener_esquema(obtener_conexion, liberar_conexion)
    except Exception as e:
        print(f"[ia_service] Error leyendo esquema: {e}")
        return {"ok": False, "error": "No se pudo leer la estructura de la base de datos."}

    mensajes = []
    for m in (historial or [])[-10:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            mensajes.append({"role": m["role"], "content": str(m["content"])})
    mensajes.append({"role": "user", "content": str(pregunta)})

    system = _system_prompt(esquema)
    consultas = 0

    for _ in range(MAX_VUELTAS + 1):
        body = {
            "model": _modelo(),
            "max_tokens": MAX_TOKENS,
            "system": system,
            "tools": HERRAMIENTAS,
            "messages": mensajes,
        }
        if consultas >= MAX_VUELTAS:
            body["tool_choice"] = {"type": "none"}

        try:
            data = _llamar_api(body)
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": _mensaje_error_http(e)}
        except Exception as e:
            print(f"[ia_service] Error: {e}")
            return {"ok": False, "error": "No se pudo conectar con la IA. Probá de nuevo."}

        bloques = data.get("content", [])
        usos = [b for b in bloques if b.get("type") == "tool_use"]

        if data.get("stop_reason") != "tool_use" or not usos:
            texto = "".join(b.get("text", "") for b in bloques if b.get("type") == "text").strip()
            if not texto:
                return {"ok": False, "error": "La IA no devolvió respuesta."}
            return {"ok": True, "respuesta": texto, "consultas": consultas}

        mensajes.append({"role": "assistant", "content": bloques})
        resultados = []
        for u in usos:
            consultas += 1
            sql = (u.get("input") or {}).get("sql", "")
            print(f"[ia_service] SQL #{consultas}: {sql[:300]}")
            salida = ejecutar_consulta(sql, obtener_conexion, liberar_conexion)
            resultados.append({
                "type": "tool_result",
                "tool_use_id": u["id"],
                "content": salida,
                "is_error": salida.startswith("ERROR"),
            })
        mensajes.append({"role": "user", "content": resultados})

    return {"ok": False, "error": "La consulta fue demasiado compleja. Probá preguntarlo más específico."}
