from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI(
    title="API Portal del Viento - Alfajores",
    docs_url=None,      # Oculta /docs (mapa público de la API) en producción
    redoc_url=None,     # Oculta /redoc
    openapi_url=None    # Oculta el esquema OpenAPI
)

# CORS: solo se permiten pedidos desde el propio dominio del sistema.
# Si más adelante usás otro dominio (ej: la tienda en otro lado), agregalo a la lista.
ORIGENES_PERMITIDOS = [
    "https://web-production-1588b.up.railway.app",
    "https://erp.portaldelviento.com.ar",
]
# Permite definir orígenes extra por variable de entorno (separados por coma), sin tocar código
_extra = os.environ.get("CORS_ORIGINS", "")
if _extra:
    ORIGENES_PERMITIDOS += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# BASE DE DATOS
# ==============================================================================
# La conexión a la base se toma SOLO de la variable de entorno DATABASE_URL
# (configurada en Railway). No se deja la contraseña escrita en el código.
DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL. Configurala en Railway.")

def obtener_conexion():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SET TIME ZONE 'America/Argentina/Mendoza';")
        cur.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la BD: {e}")

def liberar_conexion(conn):
    if conn:
        conn.close()

def fetchall_dict(cursor):
    return [dict(row) for row in cursor.fetchall()]

def crear_notificacion(tipo, titulo, detalle=None):
    """Crea una notificación. No rompe si la tabla no existe (queda silencioso).
    Usa su propia conexión para no interferir con la transacción en curso."""
    try:
        c = obtener_conexion()
        try:
            cur = c.cursor()
            cur.execute("INSERT INTO notificaciones (tipo, titulo, detalle) VALUES (%s,%s,%s)",
                        (tipo, titulo[:160] if titulo else None, detalle))
            c.commit()
        except Exception:
            c.rollback()
        finally:
            liberar_conexion(c)
    except Exception:
        pass

def registrar_movimiento_stock(cur, id_producto, cantidad, tipo, origen, motivo=None, id_local=None):
    """Registra un movimiento de stock. cantidad positiva=entrada, negativa=salida.
    No rompe si la tabla no existe todavía (queda silencioso)."""
    try:
        if id_local is None:
            cur.execute("SELECT id_local, COALESCE(stock,0) AS stock FROM pos_productos WHERE id=%s", (id_producto,))
            row = cur.fetchone()
            if row:
                # row puede ser dict o tupla según el cursor
                try:
                    id_local = row['id_local']; stock_res = row['stock']
                except Exception:
                    id_local = row[0]; stock_res = row[1]
            else:
                stock_res = None
        else:
            cur.execute("SELECT COALESCE(stock,0) AS stock FROM pos_productos WHERE id=%s", (id_producto,))
            row = cur.fetchone()
            try:
                stock_res = row['stock'] if row else None
            except Exception:
                stock_res = row[0] if row else None
        cur.execute("""
            INSERT INTO pos_movimientos_stock (id_producto, id_local, tipo, cantidad, stock_resultante, motivo, origen)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (id_producto, id_local, tipo, cantidad, stock_res, motivo, origen))
    except Exception:
        pass  # si la tabla no existe aún, no rompe la operación principal

# ==============================================================================
# MODELOS
# ==============================================================================
class Categoria(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class Presentacion(BaseModel):
    nombre: str
    cantidad_unidades: int
    precio_minorista: float = 0.0
    precio_mayorista: float = 0.0

class Producto(BaseModel):
    sku: str
    nombre: str
    tipo: str = 'propio'
    stock_inicial: int = 0
    id_categoria: Optional[int] = None
    stock_alerta: int = 20
    imagen_url: Optional[str] = None
    precio_minorista: float = 0.0
    precio_mayorista: float = 0.0
    unidades_por_caja: Optional[int] = None
    visible_mayorista: Optional[bool] = True

class StockUpdate(BaseModel):
    nuevo_stock: int

class Distribuidor(BaseModel):
    razon_social: str
    dni: Optional[str] = None
    cuit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    provincia: Optional[str] = None
    cp: Optional[str] = None
    limite_credito: float = 0.0
    notas: Optional[str] = None

class DetallePedido(BaseModel):
    id_producto: int
    cantidad: int
    precio_unitario: float
    id_presentacion: Optional[int] = None

class PedidoB2B(BaseModel):
    id_distribuidor: int
    total: float
    detalle: List[DetallePedido]

class ItemReceta(BaseModel):
    id_insumo: int
    cantidad_necesaria: float

class RecetaUpdate(BaseModel):
    id_producto: int
    items: List[ItemReceta]

class ProduccionCreate(BaseModel):
    id_producto: int
    id_empleado: int
    cantidad_producida: int
    observaciones: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    costo_total: float = 0.0
    id_categoria: Optional[int] = None

class ProduccionUpdate(BaseModel):
    cantidad_producida: int
    fecha_vencimiento: Optional[str] = None
    observaciones: Optional[str] = None

class PedidoUpdate(BaseModel):
    detalle: List[DetallePedido]
    total: float

class CobroCreate(BaseModel):
    fecha: Optional[str] = None
    monto: float
    metodo: str = "Efectivo"
    referencia: Optional[str] = None
    notas: Optional[str] = None
    id_pedido: Optional[int] = None
    id_empleado: Optional[int] = None

class LoginData(BaseModel):
    username: str
    password: str

class NuevoEmpleado(BaseModel):
    nombre: str
    apellido: str
    dni: str
    rol: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    crear_usuario: bool = False
    username: Optional[str] = None
    password: Optional[str] = None

class ActualizarEmpleado(BaseModel):
    nombre: str
    apellido: str
    dni: str
    rol: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    valor_hora: float = 0.0

class FichajeData(BaseModel):
    id_empleado: int
    tipo: str
    observacion: Optional[str] = None

class NuevoAnticipo(BaseModel):
    id_empleado: int
    monto: float
    observaciones: Optional[str] = None

class InsumoCompleto(BaseModel):
    nombre: str
    unidad_medida: str
    stock_minimo: float
    costo_unitario: float = 0.0
    presentacion_compra: Optional[str] = None
    cantidad_por_presentacion: float = 1.0
    costo_por_bulto: float = 0.0
    id_proveedor: Optional[int] = None

class SumarStock(BaseModel):
    cantidad: float

class NuevoProveedor(BaseModel):
    razon_social: str
    cuit: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    notas: Optional[str] = None

class ActualizarProveedor(BaseModel):
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    notas: Optional[str] = None

class PrecioInsumo(BaseModel):
    id_insumo: int
    precio_unitario: float

class NuevaTarea(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    prioridad: str = "media"
    id_empleado_asignado: Optional[int] = None

class NuevoCobroDistribuidor(BaseModel):
    id_distribuidor: int
    id_pedido: Optional[int] = None
    id_empleado: Optional[int] = None
    monto: float
    metodo: str
    referencia: Optional[str] = None
    notas: Optional[str] = None

class NuevoPagoProveedor(BaseModel):
    id_proveedor: int
    id_orden: Optional[int] = None
    id_empleado: int
    monto: float
    metodo: str
    referencia: Optional[str] = None
    notas: Optional[str] = None
    fecha: Optional[str] = None  # si no se manda, se usa NOW()

class DatosEmpresa(BaseModel):
    nombre: str
    razon_social: Optional[str] = None
    cuit: Optional[str] = None
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    provincia: Optional[str] = None
    cp: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None

class RegistroDist(BaseModel):
    razon_social: str
    cuit: str
    username: str
    password: str
    dni: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    provincia: Optional[str] = None
    cp: Optional[str] = None
    limite_credito: float = 0.0

# ==============================================================================
# AUTH
# ==============================================================================
import bcrypt

@app.post("/api/login")
def login(data: LoginData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.password_hash, u.activo,
                   e.id as id_empleado, e.nombre, e.apellido, e.rol
            FROM usuarios u JOIN empleados e ON u.id_empleado = e.id
            WHERE u.username = %s
        """, (data.username,))
        usuario = cur.fetchone()
        if not usuario or not usuario['activo']:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        if not bcrypt.checkpw(data.password.encode(), usuario['password_hash'].encode()):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        return {"status": "ok", "id_empleado": usuario['id_empleado'],
                "nombre": usuario['nombre'], "apellido": usuario['apellido'], "rol": usuario['rol']}
    finally:
        liberar_conexion(conn)

# ── LOGIN DEL POS (separado del admin: solo empleados con acceso_pos) ──
class LoginPosData(BaseModel):
    username: str
    password: str
    dispositivo: Optional[str] = None

@app.post("/api/pos/login")
def pos_login(data: LoginPosData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.id AS id_usuario, u.password_hash, u.activo, COALESCE(u.acceso_pos, false) AS acceso_pos,
                   e.id as id_empleado, e.nombre, e.apellido, e.rol
            FROM usuarios u JOIN empleados e ON u.id_empleado = e.id
            WHERE u.username = %s
        """, (data.username,))
        usuario = cur.fetchone()
        if not usuario or not usuario['activo']:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        if not bcrypt.checkpw(data.password.encode(), usuario['password_hash'].encode()):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        if not usuario['acceso_pos']:
            raise HTTPException(status_code=403, detail="Este usuario no tiene acceso al POS")

        # ── Control de sesión única ──
        import uuid as _uuid
        token = _uuid.uuid4().hex
        id_usuario = usuario['id_usuario']
        try:
            # ¿Hay una sesión activa todavía viva? (señal en los últimos 3 minutos)
            cur.execute("""SELECT username, dispositivo, ultima_senal,
                                  EXTRACT(EPOCH FROM (NOW() - ultima_senal)) AS seg
                           FROM pos_sesiones WHERE id_usuario=%s""", (id_usuario,))
            ses = cur.fetchone()
            if ses and ses['seg'] is not None and ses['seg'] < 180:
                # Sesión viva en otro lado → bloquear
                disp = ses['dispositivo'] or 'otro dispositivo'
                raise HTTPException(status_code=409, detail="Este usuario ya tiene una sesión activa en " + disp + ". Cerrá sesión ahí antes de entrar acá.")
            # Crear/actualizar la sesión
            cur.execute("""
                INSERT INTO pos_sesiones (id_usuario, username, token, dispositivo, inicio, ultima_senal)
                VALUES (%s,%s,%s,%s,NOW(),NOW())
                ON CONFLICT (id_usuario) DO UPDATE SET username=EXCLUDED.username, token=EXCLUDED.token,
                    dispositivo=EXCLUDED.dispositivo, inicio=NOW(), ultima_senal=NOW()
            """, (id_usuario, data.username, token, data.dispositivo or 'POS'))
            conn.commit()
        except HTTPException:
            raise
        except Exception:
            # Si la tabla no existe (no corrieron el SQL), no bloqueamos: login normal
            conn.rollback()
            token = ""

        return {"status": "ok", "id_empleado": usuario['id_empleado'], "id_usuario": id_usuario,
                "nombre": usuario['nombre'], "apellido": usuario['apellido'], "rol": usuario['rol'],
                "token": token}
    finally:
        liberar_conexion(conn)

# Mantener viva la sesión (el POS la llama cada tanto)
@app.post("/api/pos/sesion/latido")
def pos_sesion_latido(id_usuario: int, token: str = ""):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE pos_sesiones SET ultima_senal=NOW() WHERE id_usuario=%s AND token=%s", (id_usuario, token))
            conn.commit()
        except Exception:
            conn.rollback()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# Cerrar la sesión (al salir del POS)
@app.post("/api/pos/sesion/cerrar")
def pos_sesion_cerrar(id_usuario: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM pos_sesiones WHERE id_usuario=%s", (id_usuario,))
            conn.commit()
        except Exception:
            conn.rollback()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ── ASIGNAR / ACTUALIZAR ACCESO DE UN EMPLEADO (usuario + clave + acceso_pos) ──
class AccesoEmpleado(BaseModel):
    username: str
    password: Optional[str] = None
    acceso_pos: bool = True

@app.get("/api/empleados/{id_emp}/acceso")
def get_acceso_empleado(id_emp: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT username, COALESCE(acceso_pos,false) AS acceso_pos FROM usuarios WHERE id_empleado=%s", (id_emp,))
        row = cur.fetchone()
        if not row:
            return {"tiene_usuario": False, "username": None, "acceso_pos": False}
        return {"tiene_usuario": True, "username": row['username'], "acceso_pos": row['acceso_pos']}
    finally:
        liberar_conexion(conn)

@app.put("/api/empleados/{id_emp}/acceso")
def set_acceso_empleado(id_emp: int, data: AccesoEmpleado):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # username único (que no lo tenga otro empleado)
        cur.execute("SELECT id_empleado FROM usuarios WHERE username=%s AND id_empleado<>%s", (data.username, id_emp))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso")
        cur.execute("SELECT id_empleado FROM usuarios WHERE id_empleado=%s", (id_emp,))
        existe = cur.fetchone()
        if existe:
            if data.password:
                hash_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
                cur.execute("UPDATE usuarios SET username=%s, password_hash=%s, acceso_pos=%s, activo=true WHERE id_empleado=%s",
                            (data.username, hash_pw, data.acceso_pos, id_emp))
            else:
                cur.execute("UPDATE usuarios SET username=%s, acceso_pos=%s WHERE id_empleado=%s",
                            (data.username, data.acceso_pos, id_emp))
        else:
            if not data.password:
                raise HTTPException(status_code=400, detail="Para crear el acceso hay que poner una contraseña")
            hash_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT INTO usuarios (id_empleado, username, password_hash, acceso_pos, activo) VALUES (%s,%s,%s,%s,true)",
                        (id_emp, data.username, hash_pw, data.acceso_pos))
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# EMPRESA
# ==============================================================================
@app.get("/api/empresa")
def get_empresa():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM empresa LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else {
            "nombre": "Portal del Viento",
            "razon_social": "Portal del Viento",
            "cuit": "",
            "direccion": "Mendoza, Argentina",
            "telefono": ""
        }
    finally:
        liberar_conexion(conn)

@app.put("/api/empresa")
def actualizar_empresa(data: DatosEmpresa):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM empresa LIMIT 1")
        existe = cur.fetchone()
        if existe:
            cur.execute("""
                UPDATE empresa SET nombre=%s, razon_social=%s, cuit=%s, direccion=%s,
                localidad=%s, provincia=%s, cp=%s, telefono=%s, email=%s, logo_url=%s WHERE id=%s
            """, (data.nombre, data.razon_social, data.cuit, data.direccion,
                  data.localidad, data.provincia, data.cp, data.telefono, data.email,
                  data.logo_url, existe[0]))
        else:
            cur.execute("""
                INSERT INTO empresa (nombre, razon_social, cuit, direccion, localidad, provincia, cp, telefono, email, logo_url)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (data.nombre, data.razon_social, data.cuit, data.direccion,
                  data.localidad, data.provincia, data.cp, data.telefono, data.email, data.logo_url))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# CATEGORÍAS  (baja lógica con activo)
# ==============================================================================
@app.get("/api/categorias")
def get_categorias():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre, descripcion FROM categorias WHERE COALESCE(activo, true) = true ORDER BY nombre ASC")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/categorias/nueva")
def crear_categoria(cat: Categoria):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO categorias (nombre, descripcion) VALUES (%s,%s) ON CONFLICT (nombre) DO NOTHING",
                    (cat.nombre, cat.descripcion))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/categorias/{id}")
def eliminar_categoria(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE categorias SET activo=false WHERE id=%s", (id,))
        cur.execute("UPDATE productos SET id_categoria=NULL WHERE id_categoria=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# PRODUCTOS  (stock_actual, baja lógica, precios en la propia tabla)
# ==============================================================================
@app.get("/api/reposicion/diagnostico_mapeo")
def reposicion_diagnostico_mapeo(id_local: int):
    """Muestra, para cada producto de fábrica, a qué producto del local sumaría
    y por qué razón. No ejecuta nada, solo simula el mapeo."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Config manual
        config = {}
        try:
            cur.execute("SELECT id_categoria_fabrica, nombre_producto_local FROM reposicion_config_categoria WHERE activa=true")
            for c in fetchall_dict(cur):
                config[c['id_categoria_fabrica']] = c['nombre_producto_local']
        except Exception:
            conn.rollback()

        # Productos de fábrica (catálogo de reposición)
        cur.execute("""SELECT p.id, p.nombre AS nombre_fabrica, p.id_categoria,
                              LOWER(COALESCE(c.nombre,'')) AS cat_nombre
                       FROM productos p LEFT JOIN categorias c ON p.id_categoria=c.id
                       WHERE COALESCE(p.activo,true)=true
                         AND LOWER(COALESCE(c.nombre,'')) NOT IN ('6 unidades','linea 50g')
                       ORDER BY c.nombre, p.nombre""")
        productos_fabrica = fetchall_dict(cur)

        # Productos del local
        cur.execute("""SELECT id, nombre, LOWER(TRIM(COALESCE(categoria,''))) AS cat
                       FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true""", (id_local,))
        productos_local = fetchall_dict(cur)

        def palabras_comunes(a, b):
            sa = set(w for w in (a or '').lower().split() if len(w) > 2)
            sb = set(w for w in (b or '').lower().split() if len(w) > 2)
            return len(sa & sb)

        # Overrides manuales
        overrides = {}
        try:
            cur.execute("SELECT id_producto_fabrica, id_producto_local FROM reposicion_override_producto WHERE id_local=%s", (id_local,))
            for o in fetchall_dict(cur):
                overrides[o['id_producto_fabrica']] = o['id_producto_local']
        except Exception:
            conn.rollback()

        resultado = []
        for pf in productos_fabrica:
            id_cat = pf.get('id_categoria')
            cat_nombre = (pf.get('cat_nombre') or '').strip()
            nombre_fab = pf.get('nombre_fabrica') or ''
            destino = None; razon = None

            # PASO 0: override
            if pf['id'] in overrides:
                destino = next((p for p in productos_local if p['id'] == overrides[pf['id']]), None)
                if destino: razon = "✋ Manual (vos lo elegiste)"
            # PASO 1: por categoría
            if not destino and cat_nombre:
                candidatos = [p for p in productos_local if p['cat'] == cat_nombre]
                if len(candidatos) == 1:
                    destino = candidatos[0]; razon = "Categoría coincide (único)"
                elif len(candidatos) > 1:
                    mejor = None; ms = -1
                    for p in candidatos:
                        sc = palabras_comunes(nombre_fab, p['nombre'])
                        if sc > ms: ms = sc; mejor = p
                    destino = mejor or candidatos[0]; razon = "Categoría + nombre parecido"
            # PASO 2: config manual
            if not destino and id_cat and id_cat in config:
                p = next((x for x in productos_local if x['nombre'].lower().strip() == config[id_cat].lower().strip()), None)
                if p: destino = p; razon = "Config manual"
            # PASO 3: alfajores
            if not destino and 'alfajor' in cat_nombre:
                p = next((x for x in productos_local if x['nombre'].lower().strip() == 'alfajor pdv unidad'), None)
                if p: destino = p; razon = "Default alfajores"
            # PASO 4: nombre parecido global
            if not destino and nombre_fab:
                mejor = None; ms = 0
                for p in productos_local:
                    sc = palabras_comunes(nombre_fab, p['nombre'])
                    if sc > ms: ms = sc; mejor = p
                if mejor and ms >= 1:
                    destino = mejor; razon = "Nombre parecido"

            resultado.append({
                "id_producto_fabrica": pf['id'],
                "nombre_fabrica": nombre_fab,
                "categoria_fabrica": cat_nombre,
                "id_categoria_fabrica": id_cat,
                "destino_id": destino['id'] if destino else None,
                "destino_nombre": destino['nombre'] if destino else None,
                "razon": razon or "SIN MAPEAR"
            })
        return {"productos_local": productos_local, "mapeos": resultado}
    finally:
        liberar_conexion(conn)

@app.post("/api/reposicion/override_mapeo")
def reposicion_override_mapeo(data: dict = Body(...)):
    """Guarda un override manual: este producto de fábrica → este producto del local.
    Usa la tabla de config pero por producto puntual (categoría especial)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Guardar en una tabla de overrides por producto de fábrica
        try:
            cur.execute("""CREATE TABLE IF NOT EXISTS reposicion_override_producto (
                id SERIAL PRIMARY KEY,
                id_producto_fabrica INTEGER NOT NULL,
                id_local INTEGER NOT NULL,
                id_producto_local INTEGER NOT NULL,
                UNIQUE(id_producto_fabrica, id_local))""")
            cur.execute("""INSERT INTO reposicion_override_producto (id_producto_fabrica, id_local, id_producto_local)
                           VALUES (%s,%s,%s)
                           ON CONFLICT (id_producto_fabrica, id_local)
                           DO UPDATE SET id_producto_local=EXCLUDED.id_producto_local""",
                        (data['id_producto_fabrica'], data['id_local'], data['id_producto_local']))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/reposicion/config_categorias")
def reposicion_config_categorias():
    """Lista la configuración: qué categoría de fábrica → qué producto local."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT rc.id, rc.id_categoria_fabrica, rc.nombre_producto_local, rc.activa,
                       c.nombre AS nombre_categoria_fabrica
                FROM reposicion_config_categoria rc
                JOIN categorias c ON rc.id_categoria_fabrica = c.id
                ORDER BY c.nombre
            """)
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            return []
    finally:
        liberar_conexion(conn)

@app.post("/api/reposicion/config_categorias")
def reposicion_config_crear(data: dict = Body(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO reposicion_config_categoria (id_categoria_fabrica, nombre_producto_local)
                       VALUES (%s,%s) ON CONFLICT (id_categoria_fabrica)
                       DO UPDATE SET nombre_producto_local=%s, activa=true""",
                   (data['id_categoria_fabrica'], data['nombre_producto_local'], data['nombre_producto_local']))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/reposicion/config_categorias/{id}")
def reposicion_config_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM reposicion_config_categoria WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/productos_todos_locales")
def pos_productos_todos_locales():
    """Lista todos los productos de todos los locales para gestión centralizada."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id, p.nombre, p.precio, p.categoria, p.id_local,
                   COALESCE(p.stock,0) AS stock, COALESCE(p.stock_alerta,0) AS stock_alerta,
                   l.nombre AS local_nombre
            FROM pos_productos p
            JOIN pos_locales l ON p.id_local = l.id
            WHERE COALESCE(p.activo, true) = true
            ORDER BY p.nombre, l.nombre
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/productos_todos_locales/{nombre_producto}")
def pos_actualizar_producto_todos_locales(nombre_producto: str, data: dict = Body(...)):
    """Actualiza un producto por nombre en TODOS los locales donde exista."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        campos = []
        valores = []
        if 'precio' in data:
            campos.append("precio=%s"); valores.append(data['precio'])
        if 'categoria' in data:
            campos.append("categoria=%s"); valores.append(data['categoria'])
        if 'stock_alerta' in data:
            campos.append("stock_alerta=%s"); valores.append(data['stock_alerta'])
        if not campos:
            return {"status": "nada que actualizar"}
        valores.append(nombre_producto)
        cur.execute(f"UPDATE pos_productos SET {', '.join(campos)} WHERE LOWER(TRIM(nombre))=LOWER(TRIM(%s)) AND COALESCE(activo,true)=true",
                   tuple(valores))
        conn.commit()
        return {"status": "ok", "actualizados": cur.rowcount}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/productos/catalogo_reposicion")
def catalogo_reposicion():
    """Catálogo de fábrica para el modal de reposición del POS.
    Excluye categorías que no aplican al flujo de reposición de locales."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id, p.nombre, p.stock_actual,
                   COALESCE(p.unidades_por_caja, 1) AS unidades_por_caja,
                   COALESCE(c.nombre, 'Sin categoría') AS categoria,
                   c.id AS id_categoria
            FROM productos p
            LEFT JOIN categorias c ON p.id_categoria = c.id
            WHERE COALESCE(p.activo, true) = true
              AND LOWER(COALESCE(c.nombre,'')) NOT IN ('6 unidades', 'linea 50g')
            ORDER BY c.nombre, p.nombre
        """)
        return fetchall_dict(cur)
    except Exception:
        conn.rollback()
        return []
    finally:
        liberar_conexion(conn)

@app.get("/api/productos")
def get_productos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT id, sku, nombre, tipo, stock_actual AS stock, stock_actual,
                       id_categoria, stock_alerta, imagen_url, unidades_por_caja,
                       COALESCE(visible_mayorista, true) AS visible_mayorista,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true
                ORDER BY nombre ASC
            """)
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT id, sku, nombre, tipo, stock_actual AS stock, stock_actual,
                       id_categoria, stock_alerta, imagen_url,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true
                ORDER BY nombre ASC
            """)
            return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/productos/con_presentaciones")
def get_productos_presentaciones(solo_visibles_mayorista: bool = False):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Si lo pide el portal de distribuidores, oculta los marcados como no visibles.
        filtro_vis = " AND COALESCE(visible_mayorista, true) = true" if solo_visibles_mayorista else ""
        try:
            cur.execute(f"""
                SELECT id, sku, nombre, tipo, stock_actual AS stock, stock_actual,
                       id_categoria, stock_alerta, imagen_url,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true{filtro_vis}
                ORDER BY nombre ASC
            """)
        except Exception:
            # Si la columna no existe todavía, traer sin filtro (no rompe)
            conn.rollback()
            cur.execute("""
                SELECT id, sku, nombre, tipo, stock_actual AS stock, stock_actual,
                       id_categoria, stock_alerta, imagen_url,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true
                ORDER BY nombre ASC
            """)
        productos = fetchall_dict(cur)
        # Presentación virtual "Unidad" usando el precio mayorista del propio producto,
        # para que el portal mayorista y los pedidos sigan funcionando igual.
        for p in productos:
            p['presentaciones'] = [{
                'id': p['id'],
                'nombre': 'Unidad',
                'cantidad_unidades': 1,
                'precio_minorista': float(p['precio_minorista'] or 0),
                'precio_mayorista': float(p['precio_mayorista'] or 0)
            }]
        return productos
    finally:
        liberar_conexion(conn)

@app.post("/api/productos_nuevo")
def crear_producto(prod: Producto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO productos (sku, nombre, tipo, stock_actual, id_categoria, stock_alerta, imagen_url, precio_minorista, precio_mayorista, unidades_por_caja, activo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, true) RETURNING id
            """, (prod.sku, prod.nombre, prod.tipo, prod.stock_inicial, prod.id_categoria,
                  prod.stock_alerta, prod.imagen_url, prod.precio_minorista, prod.precio_mayorista, prod.unidades_por_caja))
        except Exception:
            conn.rollback()
            cur.execute("""
                INSERT INTO productos (sku, nombre, tipo, stock_actual, id_categoria, stock_alerta, imagen_url, precio_minorista, precio_mayorista, activo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, true) RETURNING id
            """, (prod.sku, prod.nombre, prod.tipo, prod.stock_inicial, prod.id_categoria,
                  prod.stock_alerta, prod.imagen_url, prod.precio_minorista, prod.precio_mayorista))
        id_prod = cur.fetchone()[0]
        conn.commit()
        return {"id": id_prod}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/productos/{id}")
def actualizar_producto(id: int, prod: Producto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE productos
                SET sku=%s, nombre=%s, tipo=%s, id_categoria=%s, stock_alerta=%s, imagen_url=%s,
                    precio_minorista=%s, precio_mayorista=%s, unidades_por_caja=%s
                WHERE id=%s
            """, (prod.sku, prod.nombre, prod.tipo, prod.id_categoria, prod.stock_alerta,
                  prod.imagen_url, prod.precio_minorista, prod.precio_mayorista, prod.unidades_por_caja, id))
        except Exception:
            conn.rollback()
            cur.execute("""
                UPDATE productos
                SET sku=%s, nombre=%s, tipo=%s, id_categoria=%s, stock_alerta=%s, imagen_url=%s,
                    precio_minorista=%s, precio_mayorista=%s
                WHERE id=%s
            """, (prod.sku, prod.nombre, prod.tipo, prod.id_categoria, prod.stock_alerta,
                  prod.imagen_url, prod.precio_minorista, prod.precio_mayorista, id))
        # Guardar visibilidad para mayoristas (si la columna existe)
        try:
            vis = True if prod.visible_mayorista is None else bool(prod.visible_mayorista)
            cur.execute("UPDATE productos SET visible_mayorista=%s WHERE id=%s", (vis, id))
        except Exception:
            conn.rollback()
            # reintenta el update principal por si el rollback lo deshizo
            cur.execute("""
                UPDATE productos SET sku=%s, nombre=%s, tipo=%s, id_categoria=%s, stock_alerta=%s,
                    imagen_url=%s, precio_minorista=%s, precio_mayorista=%s WHERE id=%s
            """, (prod.sku, prod.nombre, prod.tipo, prod.id_categoria, prod.stock_alerta,
                  prod.imagen_url, prod.precio_minorista, prod.precio_mayorista, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/productos/{id}")
def eliminar_producto(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/productos/{id}/stock")
def actualizar_stock_directo(id: int, stock: StockUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET stock_actual=%s WHERE id=%s", (stock.nuevo_stock, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Sumar stock de producto terminado (carga desde producción) — suma del lado del servidor
class IngresoStock(BaseModel):
    cantidad: float

@app.post("/api/productos/{id}/ingresar_stock")
def ingresar_stock_producto(id: int, data: IngresoStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id=%s RETURNING stock_actual", (data.cantidad, id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        # Quitar marca "en proceso" (ya se ingresó a stock)
        try:
            cur.execute("DELETE FROM produccion_en_proceso WHERE id_producto=%s", (id,))
        except Exception:
            pass
        conn.commit()
        return {"status": "ok", "stock_actual": float(row['stock_actual'])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Presentaciones: las dejamos como "puente" hacia el precio del producto,
# para no romper los HTML viejos que todavía las llaman.
@app.get("/api/productos/{id}/presentaciones")
def get_presentaciones(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, COALESCE(precio_minorista,0) AS precio_minorista, COALESCE(precio_mayorista,0) AS precio_mayorista FROM productos WHERE id=%s", (id,))
        p = cur.fetchone()
        if not p:
            return []
        return [{
            'id': p['id'], 'nombre': 'Unidad', 'cantidad_unidades': 1,
            'precio_minorista': float(p['precio_minorista'] or 0),
            'precio_mayorista': float(p['precio_mayorista'] or 0)
        }]
    finally:
        liberar_conexion(conn)

@app.post("/api/productos/{id}/presentaciones")
def crear_presentacion(id: int, pres: Presentacion):
    # Compatibilidad: guardar el precio en el producto.
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET precio_minorista=%s, precio_mayorista=%s WHERE id=%s",
                    (pres.precio_minorista, pres.precio_mayorista, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/presentaciones/{id}")
def actualizar_presentacion(id: int, pres: Presentacion):
    # 'id' aquí es el id del producto (la presentación virtual usa el mismo id).
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET precio_minorista=%s, precio_mayorista=%s WHERE id=%s",
                    (pres.precio_minorista, pres.precio_mayorista, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/presentaciones/{id}")
def eliminar_presentacion(id: int):
    return {"status": "ok"}

# ==============================================================================
# DISTRIBUIDORES  (baja lógica)
# ==============================================================================
@app.get("/api/distribuidores_lista")
def get_distribuidores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, razon_social, cuit, limite_credito, direccion, localidad, provincia,
                   cp, telefono, email, dni, aprobado, notas, username,
                   (password_hash IS NOT NULL) AS tiene_clave
            FROM distribuidores WHERE COALESCE(activo, true) = true ORDER BY razon_social ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/distribuidores_nuevo")
def crear_distribuidor(dist: Distribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO distribuidores (razon_social, dni, cuit, telefono, email, direccion, localidad, provincia, cp, limite_credito, notas, aprobado, activo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, true, true)
        """, (dist.razon_social, dist.dni, dist.cuit, dist.telefono, dist.email, dist.direccion,
              dist.localidad, dist.provincia, dist.cp, dist.limite_credito, dist.notas))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class ProspectoData(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    zona: Optional[str] = None
    tipo_comercio: Optional[str] = None
    venta_estimada: Optional[str] = None
    mensaje: Optional[str] = None

@app.post("/api/prospectos")
def crear_prospecto(p: ProspectoData):
    """Recibe el formulario público de 'Quiero ser distribuidor'."""
    if not p.nombre or not p.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO prospectos_distribuidores
                (nombre, telefono, email, zona, tipo_comercio, venta_estimada, mensaje)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (p.nombre.strip(), p.telefono, p.email, p.zona, p.tipo_comercio, p.venta_estimada, p.mensaje))
            pid = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PROSPECTOS.sql en la base.")
        try:
            crear_notificacion("pedido", "Nuevo interesado en ser distribuidor",
                               p.nombre.strip() + (" · " + p.zona if p.zona else ""))
        except Exception:
            pass
        return {"status": "ok", "id": pid}
    finally:
        liberar_conexion(conn)

@app.get("/api/prospectos")
def listar_prospectos(estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            if estado:
                cur.execute("SELECT * FROM prospectos_distribuidores WHERE estado=%s ORDER BY id DESC", (estado,))
            else:
                cur.execute("SELECT * FROM prospectos_distribuidores ORDER BY id DESC")
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            return []
    finally:
        liberar_conexion(conn)

@app.put("/api/prospectos/{id}/estado")
def cambiar_estado_prospecto(id: int, estado: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prospectos_distribuidores SET estado=%s WHERE id=%s", (estado, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.post("/api/prospectos/{id}/convertir")
def convertir_prospecto(id: int):
    """Convierte un prospecto aprobado en distribuidor real."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM prospectos_distribuidores WHERE id=%s", (id,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Prospecto no encontrado")
        if p.get('id_distribuidor'):
            raise HTTPException(status_code=409, detail="Este prospecto ya fue convertido en distribuidor")
        notas = "Captado por embudo."
        if p.get('venta_estimada'): notas += " Venta estimada: " + str(p['venta_estimada']) + "."
        if p.get('tipo_comercio'): notas += " Comercio: " + str(p['tipo_comercio']) + "."
        cur.execute("""
            INSERT INTO distribuidores (razon_social, telefono, email, localidad, notas, aprobado, activo)
            VALUES (%s,%s,%s,%s,%s, true, true) RETURNING id
        """, (p['nombre'], p.get('telefono'), p.get('email'), p.get('zona'), notas))
        id_dist = cur.fetchone()['id']
        cur.execute("UPDATE prospectos_distribuidores SET estado='convertido', id_distribuidor=%s WHERE id=%s", (id_dist, id))
        conn.commit()
        return {"status": "ok", "id_distribuidor": id_dist}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/{id}")
def actualizar_distribuidor(id: int, dist: Distribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE distribuidores SET
            razon_social=%s, dni=%s, cuit=%s, telefono=%s, email=%s,
            direccion=%s, localidad=%s, provincia=%s, cp=%s, limite_credito=%s, notas=%s
            WHERE id=%s
        """, (dist.razon_social, dist.dni, dist.cuit, dist.telefono, dist.email, dist.direccion,
              dist.localidad, dist.provincia, dist.cp, dist.limite_credito, dist.notas, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/{id}/aprobar")
def aprobar_distribuidor(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE distribuidores SET aprobado = true WHERE id = %s", (id,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/distribuidores/{id}")
def eliminar_distribuidor(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE distribuidores SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# MÓDULO CONTABLE DISTRIBUIDORES
# ==============================================================================
@app.post("/api/distribuidores/{id_dist}/cobros")
def registrar_cobro(id_dist: int, cobro: CobroCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        id_emp = cobro.id_empleado
        if not id_emp:
            cur.execute("SELECT id FROM empleados ORDER BY id LIMIT 1")
            row = cur.fetchone()
            id_emp = row[0] if row else None
        if cobro.fecha:
            cur.execute("""
                INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, id_empleado, fecha, monto, metodo, referencia, notas)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (id_dist, cobro.id_pedido, id_emp, cobro.fecha, cobro.monto, cobro.metodo, cobro.referencia, cobro.notas))
        else:
            cur.execute("""
                INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, id_empleado, monto, metodo, referencia, notas)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (id_dist, cobro.id_pedido, id_emp, cobro.monto, cobro.metodo, cobro.referencia, cobro.notas))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Alias para el panel admin / tablero
@app.post("/api/distribuidores/cobro")
def registrar_cobro_admin(cobro: NuevoCobroDistribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        id_emp = cobro.id_empleado
        if not id_emp:
            cur.execute("SELECT id FROM empleados ORDER BY id LIMIT 1")
            row = cur.fetchone()
            id_emp = row[0] if row else None
        cur.execute("""
            INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, id_empleado, monto, metodo, referencia, notas)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (cobro.id_distribuidor, cobro.id_pedido, id_emp, cobro.monto, cobro.metodo, cobro.referencia, cobro.notas))
        conn.commit()
        try:
            crear_notificacion("pago", "Pago de distribuidor registrado",
                               "$" + str(cobro.monto) + " - " + (cobro.metodo or ""))
        except Exception:
            pass
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)



@app.post("/api/cobros_distribuidores/nuevo")
def registrar_cobro_distribuidor(cobro: NuevoCobroDistribuidor):
    return registrar_cobro_admin(cobro)

@app.delete("/api/distribuidores/cobro/{id_cobro}")
def eliminar_cobro_distribuidor(id_cobro: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM cobros_distribuidores WHERE id=%s", (id_cobro,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores/{id_dist}/cobros")
def cobros_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.id, c.fecha::text, c.monto, c.metodo, c.referencia, c.notas, c.id_pedido,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM cobros_distribuidores c
            LEFT JOIN empleados e ON c.id_empleado = e.id
            WHERE c.id_distribuidor = %s ORDER BY c.fecha DESC
        """, (id_dist,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# Ranking de productos más pedidos por un distribuidor (solo pedidos despachados)
@app.get("/api/distribuidores/{id_dist}/ranking_productos")
def ranking_productos_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT pr.nombre AS producto, pr.sku,
                   SUM(dp.cantidad) AS unidades,
                   SUM(dp.cantidad * dp.precio_unitario) AS total
            FROM detalle_pedidos_b2b dp
            JOIN pedidos_b2b p ON dp.id_pedido = p.id
            JOIN productos pr ON dp.id_producto = pr.id
            WHERE p.id_distribuidor = %s AND p.estado = 'Despachado'
            GROUP BY pr.nombre, pr.sku
            ORDER BY unidades DESC
            LIMIT 50
        """, (id_dist,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/ingresos_distribuidores")
def ingresos_distribuidores(fecha_desde: str, fecha_hasta: str):
    """Consolidado del dinero que ingresa de distribuidores en un rango de fechas:
    lista completa de cobros, total general, desglose por método y por distribuidor."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.id, c.fecha::text AS fecha, COALESCE(c.monto,0) AS monto,
                   COALESCE(c.metodo,'') AS metodo, c.referencia, c.notas, c.id_pedido,
                   c.id_distribuidor, COALESCE(d.razon_social,'(sin nombre)') AS distribuidor
            FROM cobros_distribuidores c
            LEFT JOIN distribuidores d ON c.id_distribuidor = d.id
            WHERE DATE(c.fecha) >= %s AND DATE(c.fecha) <= %s
            ORDER BY c.fecha DESC
        """, (fecha_desde, fecha_hasta))
        cobros = fetchall_dict(cur)
        total = 0.0
        por_metodo = {}
        por_dist = {}
        for c in cobros:
            m = float(c['monto'] or 0)
            total += m
            met = (c['metodo'] or 'otro').strip().lower()
            por_metodo[met] = por_metodo.get(met, 0) + m
            dn = c['distribuidor']
            por_dist[dn] = por_dist.get(dn, 0) + m
        # Ordenar distribuidores por monto desc
        ranking = sorted([{"distribuidor": k, "total": round(v, 2)} for k, v in por_dist.items()],
                         key=lambda x: x['total'], reverse=True)
        metodos = [{"metodo": k, "total": round(v, 2)} for k, v in por_metodo.items()]
        return {
            "total": round(total, 2),
            "cantidad": len(cobros),
            "por_metodo": metodos,
            "por_distribuidor": ranking,
            "cobros": cobros
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores/{id_dist}/estado_cuenta")
def estado_cuenta_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, fecha::text, total, estado, observaciones FROM pedidos_b2b
            WHERE id_distribuidor = %s AND estado IN ('Despachado','Despachado parcial') ORDER BY fecha DESC
        """, (id_dist,))
        pedidos = fetchall_dict(cur)
        # Para cada pedido, calcular el monto REAL despachado:
        # si hay armado registrado, se cobra lo armado (precio x cantidad armada); si no, el total pedido.
        for p in pedidos:
            monto_real = None
            try:
                cur.execute("""
                    SELECT COALESCE(SUM(pi.cantidad * dp.precio_unitario), 0) AS monto, COUNT(*) AS n
                    FROM preparacion_items pi
                    JOIN detalle_pedidos_b2b dp ON dp.id_pedido = pi.id_pedido AND dp.id_producto = pi.id_producto
                    WHERE pi.id_pedido = %s
                """, (p['id'],))
                row = cur.fetchone()
                if row and row['n'] and int(row['n']) > 0:
                    monto_real = float(row['monto'] or 0)
            except Exception:
                conn.rollback()
                monto_real = None
            p['total_pedido'] = float(p['total'] or 0)
            p['total'] = monto_real if monto_real is not None else float(p['total'] or 0)
        cur.execute("""
            SELECT c.id, c.fecha::text, c.monto, c.metodo, c.referencia, c.notas, c.id_pedido,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM cobros_distribuidores c
            LEFT JOIN empleados e ON c.id_empleado = e.id
            WHERE c.id_distribuidor = %s ORDER BY c.fecha DESC
        """, (id_dist,))
        cobros = fetchall_dict(cur)
        total_pedidos = sum(float(p['total'] or 0) for p in pedidos)
        total_cobrado = sum(float(c['monto'] or 0) for c in cobros)
        return {
            "total_pedidos": total_pedidos,
            "total_cobrado": total_cobrado,
            "saldo_pendiente": total_pedidos - total_cobrado,
            "pedidos": pedidos,
            "cobros": cobros
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores/cuenta_corriente")
def cuenta_corriente_global():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Total despachado por distribuidor: si el pedido tiene armado registrado,
        # se toma lo armado (cantidad x precio); si no, el total del pedido.
        cur.execute("""
            WITH pedidos_real AS (
                SELECT pb.id, pb.id_distribuidor,
                    CASE WHEN EXISTS (SELECT 1 FROM preparacion_items pi WHERE pi.id_pedido = pb.id)
                         THEN COALESCE((
                            SELECT SUM(pi.cantidad * dp.precio_unitario)
                            FROM preparacion_items pi
                            JOIN detalle_pedidos_b2b dp ON dp.id_pedido = pi.id_pedido AND dp.id_producto = pi.id_producto
                            WHERE pi.id_pedido = pb.id
                         ), 0)
                         ELSE COALESCE(pb.total, 0)
                    END AS monto_real
                FROM pedidos_b2b pb
                WHERE pb.estado IN ('Despachado','Despachado parcial')
            )
            SELECT d.id, d.razon_social, d.limite_credito,
                   COALESCE(ped.total_despachado, 0) AS total_despachado,
                   COALESCE(cob.total_cobrado, 0) AS total_cobrado,
                   (COALESCE(ped.total_despachado,0) - COALESCE(cob.total_cobrado,0)) AS saldo
            FROM distribuidores d
            LEFT JOIN (
                SELECT id_distribuidor, SUM(monto_real) AS total_despachado
                FROM pedidos_real GROUP BY id_distribuidor
            ) ped ON ped.id_distribuidor = d.id
            LEFT JOIN (
                SELECT id_distribuidor, SUM(monto) AS total_cobrado
                FROM cobros_distribuidores GROUP BY id_distribuidor
            ) cob ON cob.id_distribuidor = d.id
            WHERE COALESCE(d.activo, true) = true
            ORDER BY saldo DESC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ==============================================================================
# LOGIN / REGISTRO MAYORISTAS
# ==============================================================================
@app.post("/api/distribuidores/registro")
def registro_distribuidor(data: RegistroDist):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        hash_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        cur.execute("""
            INSERT INTO distribuidores
            (razon_social, dni, cuit, telefono, email, direccion, localidad, provincia, cp, username, password_hash, limite_credito, aprobado, activo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, false, true) RETURNING id
        """, (data.razon_social, data.dni, data.cuit, data.telefono, data.email, data.direccion,
              data.localidad, data.provincia, data.cp, data.username, hash_pw, data.limite_credito))
        id_dist = cur.fetchone()[0]
        conn.commit()
        return {"id": id_dist, "razon_social": data.razon_social, "cuit": data.cuit, "aprobado": False}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.post("/api/distribuidores/login")
def login_distribuidor(data: LoginData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, razon_social, cuit, dni, telefono, email, direccion, localidad, provincia, cp, password_hash, aprobado, activo
            FROM distribuidores WHERE username = %s
        """, (data.username,))
        user = cur.fetchone()
        if not user or not user['activo']:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        if not user.get('password_hash') or not bcrypt.checkpw(data.password.encode(), user['password_hash'].encode()):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        user = dict(user)
        del user['password_hash']
        return user
    finally:
        liberar_conexion(conn)

# ==============================================================================
# PEDIDOS B2B  (stock_actual)
# ==============================================================================
@app.post("/api/pedidos_b2b")
def crear_pedido_b2b(pedido: PedidoB2B):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pedidos_b2b (id_distribuidor, total, estado)
            VALUES (%s, %s, 'Pendiente') RETURNING id
        """, (pedido.id_distribuidor, pedido.total))
        id_pedido = cur.fetchone()[0]
        for item in pedido.detalle:
            cur.execute("""
                INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario)
                VALUES (%s,%s,%s,%s)
            """, (id_pedido, item.id_producto, item.cantidad, item.precio_unitario))
        # NOTA: el stock NO se descuenta al crear el pedido. Se descuenta al despachar.
        conn.commit()
        try:
            crear_notificacion("pedido", "Nuevo pedido de distribuidor",
                               "Pedido #" + str(id_pedido) + " por $" + str(pedido.total))
        except Exception:
            pass
        return {"id_pedido": id_pedido}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class EnProcesoData(BaseModel):
    id_producto: int
    marcado_por: Optional[str] = None

@app.post("/api/produccion/en_proceso")
def marcar_en_proceso(data: EnProcesoData):
    """Marca o desmarca (toggle) un producto como en proceso de producción."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM produccion_en_proceso WHERE id_producto=%s", (data.id_producto,))
            existe = cur.fetchone()
            if existe:
                cur.execute("DELETE FROM produccion_en_proceso WHERE id_producto=%s", (data.id_producto,))
                conn.commit()
                return {"status": "ok", "en_proceso": False}
            else:
                cur.execute("INSERT INTO produccion_en_proceso (id_producto, marcado_por) VALUES (%s,%s)",
                            (data.id_producto, data.marcado_por))
                conn.commit()
                return {"status": "ok", "en_proceso": True}
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_EN_PROCESO.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.get("/api/produccion/en_proceso")
def listar_en_proceso():
    """Devuelve los ids de productos marcados como en proceso."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT id_producto, marcado_por, fecha::text FROM produccion_en_proceso")
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            return []
    finally:
        liberar_conexion(conn)

@app.get("/api/produccion/necesidades")
def produccion_necesidades():
    """Suma todo lo pedido en pedidos PENDIENTES y lo compara con el stock disponible.
    Devuelve, por producto: pedido, stock, cuánto falta (en cajas) y la conversión a unidades."""
    import re
    def unidades_por_caja(nombre, factor_col):
        # 1) Si el producto tiene un factor guardado, usarlo
        try:
            if factor_col and float(factor_col) > 0:
                return int(float(factor_col))
        except Exception:
            pass
        # 2) Si no, leer del nombre: busca patrones tipo x12, x 6, X24, etc.
        if nombre:
            m = re.search(r'[xX]\s*(\d{1,3})', nombre)
            if m:
                return int(m.group(1))
        # 3) Por defecto, 1 unidad por caja (no convierte)
        return 1

    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Intentar traer un posible campo unidades_por_caja; si no existe, sin él
        try:
            cur.execute("""
                SELECT d.id_producto, p.nombre, p.sku, p.unidades_por_caja AS factor,
                       COALESCE(SUM(d.cantidad),0) AS pedido, COALESCE(p.stock_actual,0) AS stock
                FROM detalle_pedidos_b2b d
                JOIN pedidos_b2b pb ON d.id_pedido = pb.id
                LEFT JOIN productos p ON d.id_producto = p.id
                WHERE pb.estado = 'Pendiente'
                GROUP BY d.id_producto, p.nombre, p.sku, p.unidades_por_caja, p.stock_actual
                ORDER BY (COALESCE(SUM(d.cantidad),0) - COALESCE(p.stock_actual,0)) DESC
            """)
            filas = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT d.id_producto, p.nombre, p.sku, NULL AS factor,
                       COALESCE(SUM(d.cantidad),0) AS pedido, COALESCE(p.stock_actual,0) AS stock
                FROM detalle_pedidos_b2b d
                JOIN pedidos_b2b pb ON d.id_pedido = pb.id
                LEFT JOIN productos p ON d.id_producto = p.id
                WHERE pb.estado = 'Pendiente'
                GROUP BY d.id_producto, p.nombre, p.sku, p.stock_actual
                ORDER BY (COALESCE(SUM(d.cantidad),0) - COALESCE(p.stock_actual,0)) DESC
            """)
            filas = fetchall_dict(cur)
        out = []
        for f in filas:
            pedido = float(f['pedido'] or 0)
            stock = float(f['stock'] or 0)
            falta_cajas = max(0, pedido - stock)
            upc = unidades_por_caja(f.get('nombre'), f.get('factor'))
            out.append({
                "id_producto": f['id_producto'],
                "nombre": f['nombre'],
                "sku": f['sku'],
                "pedido": pedido,
                "stock": stock,
                "falta_producir": falta_cajas,
                "unidades_por_caja": upc,
                "falta_unidades": int(falta_cajas * upc)
            })
        return out
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/{id}/faltantes")
def pedido_faltantes(id: int):
    """Para un pedido puntual: por cada producto, cuánto se pidió, cuánto hay y cuánto falta (cajas y unidades)."""
    import re
    def upc(nombre, factor_col):
        try:
            if factor_col and float(factor_col) > 0:
                return int(float(factor_col))
        except Exception:
            pass
        if nombre:
            m = re.search(r'[xX]\s*(\d{1,3})', nombre)
            if m:
                return int(m.group(1))
        return 1
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT d.id_producto, p.nombre, p.unidades_por_caja AS factor,
                       d.cantidad AS pedido, COALESCE(p.stock_actual,0) AS stock
                FROM detalle_pedidos_b2b d
                LEFT JOIN productos p ON d.id_producto = p.id
                WHERE d.id_pedido = %s
            """, (id,))
            filas = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT d.id_producto, p.nombre, NULL AS factor,
                       d.cantidad AS pedido, COALESCE(p.stock_actual,0) AS stock
                FROM detalle_pedidos_b2b d
                LEFT JOIN productos p ON d.id_producto = p.id
                WHERE d.id_pedido = %s
            """, (id,))
            filas = fetchall_dict(cur)
        out = []
        for f in filas:
            pedido = float(f['pedido'] or 0)
            stock = float(f['stock'] or 0)
            falta = max(0, pedido - stock)
            factor = upc(f.get('nombre'), f.get('factor'))
            out.append({
                "id_producto": f['id_producto'], "nombre": f['nombre'],
                "pedido": pedido, "stock": stock,
                "falta_producir": falta,
                "unidades_por_caja": factor,
                "falta_unidades": int(falta * factor)
            })
        return out
    finally:
        liberar_conexion(conn)

@app.get("/api/armado/historial")
def armado_historial():
    """Pedidos B2B y reposiciones ya despachados/terminados, para el historial del armado."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        salida = []
        # Pedidos B2B despachados/terminados
        try:
            cur.execute("""
                SELECT p.id, p.estado, p.total, p.fecha::text AS fecha, d.razon_social AS distribuidor
                FROM pedidos_b2b p LEFT JOIN distribuidores d ON p.id_distribuidor=d.id
                WHERE p.estado IN ('Despachado','Despachado parcial','Terminado')
                ORDER BY p.id DESC LIMIT 100
            """)
            for p in fetchall_dict(cur):
                # Quién armó: tomamos el preparado_por de los ítems preparados
                armado_por = ''
                try:
                    cur.execute("SELECT preparado_por FROM preparacion_items WHERE id_pedido=%s AND preparado_por IS NOT NULL AND preparado_por<>'' LIMIT 1", (p['id'],))
                    qa = cur.fetchone()
                    if qa: armado_por = qa['preparado_por']
                except Exception:
                    conn.rollback()
                salida.append({
                    "id": p['id'], "tipo": "b2b", "estado": p['estado'],
                    "nombre": p.get('distribuidor') or 'Distribuidor',
                    "total": p.get('total'), "fecha": p['fecha'],
                    "armado_por": armado_por
                })
        except Exception:
            conn.rollback()
        # Reposiciones repuestas
        try:
            cur.execute("""
                SELECT r.id, r.estado, r.fecha::text AS fecha, l.nombre AS local
                FROM pos_reposiciones r LEFT JOIN pos_locales l ON r.id_local=l.id
                WHERE r.estado='repuesto'
                ORDER BY r.id DESC LIMIT 100
            """)
            for r in fetchall_dict(cur):
                armado_por = ''
                try:
                    cur.execute("SELECT preparado_por FROM preparacion_reposicion WHERE id_reposicion=%s AND preparado_por IS NOT NULL AND preparado_por<>'' LIMIT 1", (r['id'],))
                    qa = cur.fetchone()
                    if qa: armado_por = qa['preparado_por']
                except Exception:
                    conn.rollback()
                salida.append({
                    "id": "r"+str(r['id']), "tipo": "reposicion", "estado": "Repuesto",
                    "nombre": "🏪 " + (r.get('local') or 'Local'),
                    "total": None, "fecha": r['fecha'],
                    "armado_por": armado_por
                })
        except Exception:
            conn.rollback()
        # Ordenar todo por fecha desc
        salida.sort(key=lambda x: (x.get('fecha') or ''), reverse=True)
        return salida
    finally:
        liberar_conexion(conn)

@app.get("/api/armado/pedidos")
def armado_listar_pedidos():
    """Lista pedidos B2B (de distribuidores) y reposiciones de locales habilitadas,
    para la pantalla de armado. Cada uno marcado con su tipo."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id, p.estado, p.total, p.fecha::text AS fecha,
                   d.razon_social AS distribuidor
            FROM pedidos_b2b p
            LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
            WHERE p.estado IN ('Pendiente','En preparación')
            ORDER BY CASE WHEN p.estado='En preparación' THEN 0 WHEN p.estado='Despachado parcial' THEN 1 WHEN p.estado='Pendiente' THEN 2 ELSE 3 END, p.id ASC
        """)
        pedidos = fetchall_dict(cur)
        for p in pedidos:
            p['tipo'] = 'b2b'
            p['nombre'] = p.get('distribuidor') or 'Distribuidor'
        # Reposiciones de locales habilitadas para armar
        try:
            cur.execute("""
                SELECT r.id, r.estado, r.fecha::text AS fecha, l.nombre AS local
                FROM pos_reposiciones r
                LEFT JOIN pos_locales l ON r.id_local = l.id
                WHERE r.estado IN ('habilitada','en_preparacion')
                ORDER BY r.id ASC
            """)
            for r in fetchall_dict(cur):
                pedidos.append({
                    "id": "r" + str(r['id']), "estado": ('En preparación' if r['estado']=='en_preparacion' else 'Pendiente'),
                    "total": None, "fecha": r['fecha'],
                    "tipo": "reposicion",
                    "nombre": "🏪 " + (r.get('local') or 'Local')
                })
        except Exception:
            conn.rollback()
        return pedidos
    finally:
        liberar_conexion(conn)

@app.get("/api/armado/pedidos/{id}")
def armado_detalle_pedido(id: str):
    """Detalle del pedido para armar. Si el id viene con prefijo 'r' es una
    reposición de local; si es numérico, un pedido B2B de distribuidor."""
    # --- Caso reposición de local (id tipo 'r45') ---
    if isinstance(id, str) and id.startswith('r'):
        try:
            rid = int(id[1:])
        except ValueError:
            raise HTTPException(status_code=400, detail="ID inválido")
        conn = obtener_conexion()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""SELECT r.id, r.estado, l.nombre AS local
                           FROM pos_reposiciones r LEFT JOIN pos_locales l ON r.id_local=l.id
                           WHERE r.id=%s""", (rid,))
            cab = cur.fetchone()
            if not cab:
                raise HTTPException(status_code=404, detail="Reposición no encontrada")

            # Detalle: traer producto de fábrica con su categoría, stock y unidades por caja
            cur.execute("""SELECT d.id_producto_fabrica, d.nombre_producto, d.cantidad,
                                  COALESCE(d.unidades_por_caja, 1) AS unidades_por_caja,
                                  pf.nombre AS nombre_fabrica,
                                  COALESCE(pf.stock_actual, 0) AS stock_fabrica,
                                  COALESCE(pf.unidades_por_caja, 1) AS upc_fabrica,
                                  LOWER(COALESCE(cf.nombre,'')) AS cat_fabrica
                           FROM pos_reposiciones_detalle d
                           LEFT JOIN productos pf ON d.id_producto_fabrica = pf.id
                           LEFT JOIN categorias cf ON pf.id_categoria = cf.id
                           WHERE d.id_reposicion=%s
                           ORDER BY cf.nombre, pf.nombre""", (rid,))
            detalle = fetchall_dict(cur)

            # Lo ya preparado, indexado por id_producto_fabrica
            preparados = {}
            try:
                cur.execute("SELECT id_producto_fabrica, cantidad FROM preparacion_reposicion WHERE id_reposicion=%s", (rid,))
                for pr in fetchall_dict(cur):
                    if pr['id_producto_fabrica'] is not None:
                        preparados[pr['id_producto_fabrica']] = float(pr['cantidad'] or 0)
            except Exception:
                conn.rollback()

            items = []
            for d in detalle:
                id_fab = d.get('id_producto_fabrica')
                nombre = d.get('nombre_fabrica') or d.get('nombre_producto') or 'Producto'
                cant = float(d['cantidad'] or 0)  # en unidades
                # unidades por caja: la de fábrica manda
                upc = float(d.get('upc_fabrica') or d.get('unidades_por_caja') or 1) or 1
                cat = d.get('cat_fabrica') or ''
                # es_caja si la categoría es alfajores y trae más de 1 por caja
                es_caja = (upc >= 2 and 'alfajor' in cat)
                stock_fab = float(d.get('stock_fabrica') or 0)
                prep = preparados.get(id_fab, 0)
                items.append({
                    "id_producto": None,
                    "id_producto_fabrica": id_fab,
                    "nombre": nombre,
                    "sku": "",
                    "sabor": "",
                    "cantidad": cant,
                    "stock": stock_fab,
                    "preparado": prep,
                    "completo": prep >= cant and cant > 0,
                    "unidades_por_caja": upc,
                    "es_caja": es_caja
                })
            estado_txt = 'En preparación' if cab['estado'] == 'en_preparacion' else 'Pendiente'
            return {"id": "r"+str(cab['id']), "estado": estado_txt,
                    "distribuidor": "🏪 " + (cab.get('local') or 'Local'),
                    "tipo": "reposicion", "items": items}
        finally:
            liberar_conexion(conn)

    # --- Caso pedido B2B de distribuidor (id numérico) ---
    try:
        id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT p.id, p.estado, p.total, d.razon_social AS distribuidor FROM pedidos_b2b p LEFT JOIN distribuidores d ON p.id_distribuidor=d.id WHERE p.id=%s", (id,))
        cab = cur.fetchone()
        if not cab:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        # Cantidad ya preparada de cada producto
        preparados = {}
        try:
            cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido=%s", (id,))
            for r in cur.fetchall():
                preparados[r['id_producto']] = float(r['cantidad'] or 0)
        except Exception:
            conn.rollback()
        cur.execute("""
            SELECT d.id_producto, p.nombre, p.sku, d.cantidad, COALESCE(p.stock_actual,0) AS stock
            FROM detalle_pedidos_b2b d LEFT JOIN productos p ON d.id_producto=p.id
            WHERE d.id_pedido=%s ORDER BY p.nombre
        """, (id,))
        items = []
        for r in fetchall_dict(cur):
            prep = preparados.get(r['id_producto'], 0)
            items.append({
                "id_producto": r['id_producto'], "nombre": r['nombre'], "sku": r['sku'],
                "cantidad": float(r['cantidad'] or 0), "stock": float(r['stock'] or 0),
                "preparado": prep,
                "completo": prep >= float(r['cantidad'] or 0)
            })
        return {"id": cab['id'], "estado": cab['estado'], "distribuidor": cab['distribuidor'], "items": items}
    finally:
        liberar_conexion(conn)

@app.put("/api/armado/pedidos/{id}/iniciar")
def armado_iniciar(id: str):
    """Marca como En preparación. Funciona para pedidos B2B y reposiciones (prefijo 'r')."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if isinstance(id, str) and id.startswith('r'):
            try:
                rid = int(id[1:])
            except ValueError:
                raise HTTPException(status_code=400, detail="ID inválido")
            cur.execute("UPDATE pos_reposiciones SET estado='en_preparacion' WHERE id=%s AND estado='habilitada'", (rid,))
            conn.commit()
            return {"status": "ok"}
        cur.execute("UPDATE pedidos_b2b SET estado='En preparación' WHERE id=%s AND estado='Pendiente'", (int(id),))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

class SetearCantidad(BaseModel):
    id_producto: Optional[int] = None
    id_producto_fabrica: Optional[int] = None
    cantidad: float
    preparado_por: Optional[str] = None
    sabor: Optional[str] = None

@app.post("/api/armado/pedidos/{id}/setear_cantidad")
def armado_setear_cantidad(id: str, data: SetearCantidad):
    """Setea cuánto preparó el empleado de un ítem."""
    # --- Reposición de local (id 'r45') ---
    if isinstance(id, str) and id.startswith('r'):
        try:
            rid = int(id[1:])
        except ValueError:
            raise HTTPException(status_code=400, detail="ID inválido")
        if not data.id_producto_fabrica:
            raise HTTPException(status_code=400, detail="Falta id_producto_fabrica")
        conn = obtener_conexion()
        try:
            cur = conn.cursor()
            # Traer lo pedido de ese producto de fábrica (para no pasarse)
            cur.execute("""SELECT cantidad FROM pos_reposiciones_detalle
                           WHERE id_reposicion=%s AND id_producto_fabrica=%s LIMIT 1""",
                        (rid, data.id_producto_fabrica))
            it = cur.fetchone()
            if not it:
                raise HTTPException(status_code=404, detail="Producto no está en la reposición")
            pedido_cant = float(it[0] or 0)
            nueva = float(data.cantidad or 0)
            if nueva < 0: nueva = 0
            if nueva > pedido_cant: nueva = pedido_cant
            try:
                cur.execute("""INSERT INTO preparacion_reposicion
                               (id_reposicion, id_producto_fabrica, cantidad, preparado_por)
                               VALUES (%s,%s,%s,%s)
                               ON CONFLICT (id_reposicion, id_producto_fabrica)
                               DO UPDATE SET cantidad=EXCLUDED.cantidad, preparado_por=EXCLUDED.preparado_por""",
                            (rid, data.id_producto_fabrica, nueva, data.preparado_por))
                # marcar como en preparación
                cur.execute("UPDATE pos_reposiciones SET estado='en_preparacion' WHERE id=%s AND estado IN ('habilitada','pendiente')", (rid,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail="Falta correr REPOSICION_ESTRUCTURA_LIMPIA.sql en la base.")
            return {"status": "ok", "cantidad": nueva}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            liberar_conexion(conn)

    # --- Pedido B2B de distribuidor ---
    try:
        id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT cantidad FROM detalle_pedidos_b2b WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
        ped = cur.fetchone()
        if not ped:
            raise HTTPException(status_code=404, detail="Producto no está en el pedido")
        pedido_cant = float(ped[0] or 0)
        try:
            cur.execute("SELECT cantidad FROM preparacion_items WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
            row = cur.fetchone()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PREPARACION.sql en la base.")
        actual = float(row[0]) if row else 0.0
        nueva = float(data.cantidad or 0)
        if nueva < 0: nueva = 0
        if nueva > pedido_cant: nueva = pedido_cant   # no más de lo pedido
        cambio = nueva - actual
        if cambio > 0:
            cur.execute("UPDATE productos SET stock_actual = GREATEST(COALESCE(stock_actual,0) - %s, 0) WHERE id=%s", (cambio, data.id_producto))
        elif cambio < 0:
            cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id=%s", (abs(cambio), data.id_producto))
        if row:
            if nueva <= 0:
                cur.execute("DELETE FROM preparacion_items WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
            else:
                cur.execute("UPDATE preparacion_items SET cantidad=%s, preparado_por=%s WHERE id_pedido=%s AND id_producto=%s",
                            (nueva, data.preparado_por, id, data.id_producto))
        else:
            if nueva > 0:
                cur.execute("INSERT INTO preparacion_items (id_pedido, id_producto, cantidad, preparado_por) VALUES (%s,%s,%s,%s)",
                            (id, data.id_producto, nueva, data.preparado_por))
        conn.commit()
        return {"status": "ok", "cantidad": nueva}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class AjusteCantidad(BaseModel):
    id_producto: int
    delta: float          # +1 o -1 (o el paso que se cargue)
    preparado_por: Optional[str] = None

@app.post("/api/armado/pedidos/{id}/cantidad")
def armado_ajustar_cantidad(id: int, data: AjusteCantidad):
    """Sube o baja la cantidad preparada de un ítem. Cada unidad cargada descuenta
    del stock al instante; al bajar, devuelve al stock. No permite pasar lo pedido."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Cantidad pedida (tope)
        cur.execute("SELECT cantidad FROM detalle_pedidos_b2b WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
        ped = cur.fetchone()
        if not ped:
            raise HTTPException(status_code=404, detail="Producto no está en el pedido")
        pedido_cant = float(ped[0] or 0)
        # Cantidad ya preparada
        try:
            cur.execute("SELECT cantidad FROM preparacion_items WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
            row = cur.fetchone()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PREPARACION.sql en la base.")
        actual = float(row[0]) if row else 0.0
        nueva = actual + data.delta
        if nueva < 0: nueva = 0
        if nueva > pedido_cant: nueva = pedido_cant
        cambio = nueva - actual  # lo que realmente se mueve
        if cambio == 0:
            return {"status": "ok", "cantidad": actual, "sin_cambio": True}
        # Mover stock: si cambio>0 descuenta; si <0 devuelve
        if cambio > 0:
            cur.execute("UPDATE productos SET stock_actual = GREATEST(COALESCE(stock_actual,0) - %s, 0) WHERE id=%s", (cambio, data.id_producto))
        else:
            cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id=%s", (abs(cambio), data.id_producto))
        # Guardar la nueva cantidad
        if row:
            if nueva <= 0:
                cur.execute("DELETE FROM preparacion_items WHERE id_pedido=%s AND id_producto=%s", (id, data.id_producto))
            else:
                cur.execute("UPDATE preparacion_items SET cantidad=%s, preparado_por=%s WHERE id_pedido=%s AND id_producto=%s",
                            (nueva, data.preparado_por, id, data.id_producto))
        else:
            if nueva > 0:
                cur.execute("INSERT INTO preparacion_items (id_pedido, id_producto, cantidad, preparado_por) VALUES (%s,%s,%s,%s)",
                            (id, data.id_producto, nueva, data.preparado_por))
        conn.commit()
        return {"status": "ok", "cantidad": nueva}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/armado/pedidos/{id}/preparado")
def armado_preparado(id: str):
    """El empleado marca el pedido B2B como PREPARADO (terminado de armar).
    Sale de la lista de pendientes. El admin lo despacha después desde el panel.
    Para reposiciones (prefijo 'r') redirige a la lógica de 'armada'."""
    # --- Reposición de local ---
    if isinstance(id, str) and id.startswith('r'):
        try:
            rid = int(id[1:])
        except ValueError:
            raise HTTPException(status_code=400, detail="ID inválido")
        conn = obtener_conexion()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE pos_reposiciones SET estado='armada' WHERE id=%s", (rid,))
            conn.commit()
            return {"status": "ok", "estado": "armada"}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            liberar_conexion(conn)

    # --- Pedido B2B de distribuidor ---
    try:
        id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pedidos_b2b SET estado='Preparado' WHERE id=%s", (id,))
        conn.commit()
        try:
            crear_notificacion("pedido", "Pedido preparado por depósito", "Pedido #" + str(id))
        except Exception:
            pass
        return {"status": "ok", "estado": "Preparado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/armado/pedidos/{id}/listo")
def armado_listo(id: str):
    """El empleado marca la reposición/pedido como TERMINADO.
    Para reposiciones: pasa a estado 'armada' (NO descuenta ni suma todavía).
    El descuento de fábrica y la suma al local los hace el admin con
    'Despachar' y 'Repuesto' desde el panel de locales."""
    # --- Reposición de local ---
    if isinstance(id, str) and id.startswith('r'):
        try:
            rid = int(id[1:])
        except ValueError:
            raise HTTPException(status_code=400, detail="ID inválido")
        conn = obtener_conexion()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE pos_reposiciones SET estado='armada' WHERE id=%s", (rid,))
            conn.commit()
            try:
                crear_notificacion("reposicion", "Reposición terminada por depósito", "Reposición #" + str(rid))
            except Exception:
                pass
            return {"status": "ok", "estado": "armada"}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            liberar_conexion(conn)

    # --- Pedido B2B de distribuidor ---
    try:
        id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # El armado deja el pedido TERMINADO ('Preparado'). El admin lo despacha
        # después desde el panel de pedidos B2B.
        cur.execute("UPDATE pedidos_b2b SET estado='Preparado' WHERE id=%s", (id,))
        conn.commit()
        try:
            crear_notificacion("pedido", "Pedido terminado por depósito", "Pedido #" + str(id))
        except Exception:
            pass
        return {"status": "ok", "estado": "Preparado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/armado/pedidos/{id}/despacho_parcial")
def armado_despacho_parcial(id: str):
    """Despacha lo que ya está armado y finaliza. Para reposiciones (prefijo 'r')
    descuenta lo preparado (igual que 'listo') y cierra la reposición."""
    # --- Reposición de local: despachar lo armado = finalizar con descuento de lo preparado ---
    if isinstance(id, str) and id.startswith('r'):
        return armado_listo(id)

    # --- Pedido B2B de distribuidor ---
    try:
        id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Cantidades preparadas por producto
        prep = {}
        try:
            cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido=%s", (id,))
            for r in cur.fetchall():
                prep[r['id_producto']] = float(r['cantidad'] or 0)
        except Exception:
            conn.rollback()
        cur.execute("""SELECT d.id_producto, p.nombre, d.cantidad, d.precio_unitario
                       FROM detalle_pedidos_b2b d LEFT JOIN productos p ON d.id_producto=p.id
                       WHERE d.id_pedido=%s""", (id,))
        items = fetchall_dict(cur)
        faltantes = []
        nuevo_total = 0.0
        for i in items:
            pedido_c = float(i['cantidad'] or 0)
            armado_c = prep.get(i['id_producto'], 0)
            precio = float(i['precio_unitario'] or 0)
            # Ajustar el detalle a lo realmente entregado (lo armado)
            cur.execute("UPDATE detalle_pedidos_b2b SET cantidad=%s WHERE id_pedido=%s AND id_producto=%s",
                        (armado_c, id, i['id_producto']))
            nuevo_total += armado_c * precio
            if armado_c < pedido_c:
                faltantes.append({"nombre": i['nombre'], "falta": pedido_c - armado_c})
        nota = ""
        if faltantes:
            nota = "Faltó entregar: " + ", ".join([(f['nombre'] or '?') + " x" + str(int(f['falta'])) for f in faltantes])
        # Recalcular el total del pedido a lo realmente entregado (para que la deuda sea correcta)
        try:
            cur.execute("UPDATE pedidos_b2b SET estado='Despachado parcial', total=%s, fecha_entrega=COALESCE(fecha_entrega, NOW()) WHERE id=%s", (nuevo_total, id))
        except Exception:
            conn.rollback()
            cur.execute("UPDATE pedidos_b2b SET estado='Despachado parcial', total=%s WHERE id=%s", (nuevo_total, id))
        conn.commit()
        try:
            crear_notificacion("pedido", "Pedido despachado PARCIAL", "Pedido #" + str(id) + ". " + nota)
        except Exception:
            pass
        return {"status": "ok", "faltantes": faltantes, "nota": nota}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/historial")
def historial_pedidos_b2b(estado: Optional[str] = None, id_distribuidor: Optional[int] = None, desde: Optional[str] = None, limite: Optional[int] = 200, modo: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT p.id, p.fecha::text, p.total, p.estado, p.id_distribuidor, d.razon_social as distribuidor,
                   d.telefono AS dist_telefono, d.cuit AS dist_cuit,
                   COALESCE(p.guia_transporte,'') AS guia_transporte, COALESCE(p.guia_numero,'') AS guia_numero
            FROM pedidos_b2b p
            LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
            WHERE 1=1
        """
        params = []
        if estado:
            query += " AND p.estado = %s"; params.append(estado)
        if id_distribuidor:
            query += " AND p.id_distribuidor = %s"; params.append(id_distribuidor)
        if desde:
            query += " AND p.fecha >= %s"; params.append(desde)
        # Modo "para hacer": pendientes/sin despachar (cualquier fecha) + todo lo de hoy
        if modo == 'pendientes_hoy':
            query += " AND (p.estado NOT IN ('Despachado','Cancelado') OR p.fecha >= CURRENT_DATE)"
        query += " ORDER BY p.fecha DESC"
        try:
            lim = int(limite) if limite else 200
        except Exception:
            lim = 200
        query += " LIMIT %s"; params.append(lim)
        try:
            cur.execute(query, tuple(params))
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            # Fallback si todavía no existen las columnas de guía
            q2 = """
                SELECT p.id, p.fecha::text, p.total, p.estado, p.id_distribuidor, d.razon_social as distribuidor,
                       d.telefono AS dist_telefono, d.cuit AS dist_cuit,
                       '' AS guia_transporte, '' AS guia_numero
                FROM pedidos_b2b p
                LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
                WHERE 1=1
            """
            p2 = []
            if estado:
                q2 += " AND p.estado = %s"; p2.append(estado)
            if id_distribuidor:
                q2 += " AND p.id_distribuidor = %s"; p2.append(id_distribuidor)
            if desde:
                q2 += " AND p.fecha >= %s"; p2.append(desde)
            if modo == 'pendientes_hoy':
                q2 += " AND (p.estado NOT IN ('Despachado','Cancelado') OR p.fecha >= CURRENT_DATE)"
            q2 += " ORDER BY p.fecha DESC LIMIT %s"; p2.append(lim)
            cur.execute(q2, tuple(p2))
            return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/{id}/detalle")
def detalle_pedido_b2b(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT dp.id_producto, dp.cantidad, dp.precio_unitario,
                   (dp.cantidad * dp.precio_unitario) AS subtotal,
                   pr.nombre as producto, pr.sku
            FROM detalle_pedidos_b2b dp
            JOIN productos pr ON dp.id_producto = pr.id
            WHERE dp.id_pedido = %s
        """, (id,))
        items = fetchall_dict(cur)
        # Sumar lo realmente preparado/armado (si existe), para reflejarlo en el remito
        preparado = {}
        hay_preparado = False
        try:
            cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido=%s", (id,))
            for pr in fetchall_dict(cur):
                preparado[pr['id_producto']] = float(pr['cantidad'] or 0)
                hay_preparado = True
        except Exception:
            conn.rollback()
        for it in items:
            it['armado'] = preparado.get(it['id_producto'], None) if hay_preparado else None
        return items
    finally:
        liberar_conexion(conn)

@app.put("/api/pedidos_b2b/{id}/actualizar")
def actualizar_pedido(id: int, payload: PedidoUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT estado FROM pedidos_b2b WHERE id=%s", (id,))
        er = cur.fetchone()
        estado_actual = er[0] if er else None
        # Estados editables: ahora incluye 'Preparado'. NO se puede editar si ya está despachado/cancelado.
        NO_EDITABLES = ('Despachado', 'Despachado parcial', 'Cancelado')
        if estado_actual in NO_EDITABLES:
            raise HTTPException(status_code=409, detail="No se puede editar un pedido ya despachado o cancelado.")

        # Qué productos quedan en el pedido nuevo
        ids_nuevos = set(item.id_producto for item in payload.detalle if item.cantidad > 0)

        # Traer lo que ya estaba preparado para conservarlo
        preparado_previo = {}
        try:
            cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido = %s", (id,))
            for v in cur.fetchall():
                preparado_previo[v[0]] = float(v[1] or 0)
        except Exception:
            conn.rollback()

        # Para los productos QUITADOS del pedido: devolver su stock preparado y borrarlos de preparación
        for id_prod, cant_prep in list(preparado_previo.items()):
            if id_prod not in ids_nuevos and cant_prep > 0:
                cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id = %s", (cant_prep, id_prod))
                cur.execute("DELETE FROM preparacion_items WHERE id_pedido = %s AND id_producto = %s", (id, id_prod))

        # Reescribir el detalle del pedido (el stock se mueve al armar, no acá)
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        cur.execute("UPDATE pedidos_b2b SET total = %s WHERE id = %s", (payload.total, id))
        for item in payload.detalle:
            if item.cantidad > 0:
                cur.execute("""
                    INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario)
                    VALUES (%s,%s,%s,%s)
                """, (id, item.id_producto, item.cantidad, item.precio_unitario))
                # Si lo preparado supera la nueva cantidad pedida, ajustar (devolver el excedente)
                if item.id_producto in preparado_previo:
                    prep = preparado_previo[item.id_producto]
                    if prep > item.cantidad:
                        exceso = prep - item.cantidad
                        cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id = %s", (exceso, item.id_producto))
                        cur.execute("UPDATE preparacion_items SET cantidad = %s WHERE id_pedido = %s AND id_producto = %s", (item.cantidad, id, item.id_producto))

        # El pedido vuelve a "En preparación" (no a Pendiente) para conservar lo armado
        # y que el empleado solo complete lo nuevo.
        if estado_actual in ('Preparado', 'En preparación'):
            cur.execute("UPDATE pedidos_b2b SET estado='En preparación' WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pedidos/{id}/estado")
def cambiar_estado_pedido(id: int, estado: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT estado FROM pedidos_b2b WHERE id=%s", (id,))
        er = cur.fetchone()
        estado_previo = er[0] if er else None

        # Estados que implican stock ya descontado (lo preparado/tildado salió del depósito)
        CON_STOCK = ('Terminado', 'Despachado', 'Despachado parcial')
        # Estados "abiertos" donde el pedido se puede editar/re-armar
        ABIERTOS = ('Pendiente', 'En preparación')

        # Si REVERTIMOS de un estado con stock descontado a uno abierto:
        # devolver al stock lo preparado y limpiar los tildes, para poder editar/re-armar.
        if estado_previo in CON_STOCK and estado in ABIERTOS:
            try:
                cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido = %s", (id,))
                for item in cur.fetchall():
                    cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id = %s", (item[1], item[0]))
                cur.execute("DELETE FROM preparacion_items WHERE id_pedido = %s", (id,))
            except Exception:
                conn.rollback()

        # Si CANCELAMOS: devolver lo preparado (si había) y limpiar
        if estado == 'Cancelado' and estado_previo != 'Cancelado':
            try:
                cur.execute("SELECT id_producto, cantidad FROM preparacion_items WHERE id_pedido = %s", (id,))
                for item in cur.fetchall():
                    cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id = %s", (item[1], item[0]))
                cur.execute("DELETE FROM preparacion_items WHERE id_pedido = %s", (id,))
            except Exception:
                conn.rollback()

        # Registrar la fecha de entrega cuando pasa a Despachado (para seguimiento post-entrega)
        if estado in ('Despachado', 'Despachado parcial') and estado_previo not in ('Despachado', 'Despachado parcial'):
            try:
                cur.execute("UPDATE pedidos_b2b SET estado = %s, fecha_entrega = NOW() WHERE id = %s", (estado, id))
            except Exception:
                conn.rollback()
                cur.execute("UPDATE pedidos_b2b SET estado = %s WHERE id = %s", (estado, id))
        else:
            cur.execute("UPDATE pedidos_b2b SET estado = %s WHERE id = %s", (estado, id))
        conn.commit()
        return {"status": "ok", "estado": estado, "estado_previo": estado_previo}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class GuiaTransporte(BaseModel):
    transporte: Optional[str] = None
    numero: Optional[str] = None

@app.put("/api/pedidos_b2b/{id}/guia")
def guardar_guia_transporte(id: int, data: GuiaTransporte):
    """Guarda los datos de la guía de transporte en el pedido."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE pedidos_b2b SET guia_transporte=%s, guia_numero=%s WHERE id=%s",
                        (data.transporte, data.numero, id))
            conn.commit()
            return {"status": "ok"}
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_GUIA_TRANSPORTE.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.delete("/api/pedidos_b2b/{id}")
def eliminar_pedido(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Solo devolver stock si el pedido estaba despachado (es lo único que descontó)
        cur.execute("SELECT estado FROM pedidos_b2b WHERE id=%s", (id,))
        er = cur.fetchone()
        if er and er[0] == 'Despachado':
            cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
            for item in cur.fetchall():
                cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id = %s", (item[1], item[0]))
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        cur.execute("DELETE FROM pedidos_b2b WHERE id = %s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# EMPLEADOS
# ==============================================================================
@app.get("/api/empleados")
def get_empleados():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT e.id, e.nombre, e.apellido, e.dni, e.rol, e.email, e.telefono,
                       e.activo, COALESCE(e.valor_hora,0) AS valor_hora,
                       u.username, COALESCE(u.acceso_pos, false) AS acceso_pos
                FROM empleados e LEFT JOIN usuarios u ON u.id_empleado = e.id
                ORDER BY e.apellido, e.nombre
            """)
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT e.id, e.nombre, e.apellido, e.dni, e.rol, e.email, e.telefono,
                       e.activo, 0 AS valor_hora,
                       u.username, COALESCE(u.acceso_pos, false) AS acceso_pos
                FROM empleados e LEFT JOIN usuarios u ON u.id_empleado = e.id
                ORDER BY e.apellido, e.nombre
            """)
            return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/empleados_nuevo")
def crear_empleado(emp: NuevoEmpleado):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO empleados (nombre, apellido, dni, rol, email, telefono) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (emp.nombre, emp.apellido, emp.dni, emp.rol, emp.email, emp.telefono))
        id_empleado = cur.fetchone()[0]
        if emp.crear_usuario and emp.username and emp.password:
            hash_pw = bcrypt.hashpw(emp.password.encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT INTO usuarios (id_empleado, username, password_hash) VALUES (%s,%s,%s)",
                        (id_empleado, emp.username, hash_pw))
        conn.commit()
        return {"status": "ok", "id_empleado": id_empleado}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/empleados/{id_emp}")
def actualizar_empleado(id_emp: int, emp: ActualizarEmpleado):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE empleados SET nombre=%s, apellido=%s, dni=%s, rol=%s, telefono=%s, email=%s, valor_hora=%s WHERE id=%s
            """, (emp.nombre, emp.apellido, emp.dni, emp.rol, emp.telefono, emp.email, emp.valor_hora, id_emp))
        except Exception:
            conn.rollback()
            cur.execute("""
                UPDATE empleados SET nombre=%s, apellido=%s, dni=%s, rol=%s, telefono=%s, email=%s WHERE id=%s
            """, (emp.nombre, emp.apellido, emp.dni, emp.rol, emp.telefono, emp.email, id_emp))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/empleados/{id_emp}/estado")
def cambiar_estado_empleado(id_emp: int, activo: bool):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE empleados SET activo=%s WHERE id=%s", (activo, id_emp))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# FICHAJES
# ==============================================================================
# ==============================================================================
# RELOJ DE FICHAJE POR PIN (tablet fija del local, sin GPS)
# ==============================================================================
class PinLookup(BaseModel):
    pin: str

@app.post("/api/fichaje/empleado_por_pin")
def empleado_por_pin(data: PinLookup):
    """Devuelve el empleado dueño del PIN (para mostrar nombre/foto antes de fichar)."""
    pin = (data.pin or '').strip()
    if len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN incompleto")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""SELECT id, nombre, apellido, COALESCE(foto_url,'') AS foto_url
                           FROM empleados WHERE pin_fichaje=%s AND COALESCE(activo,true)=true""", (pin,))
        except Exception:
            conn.rollback()
            cur.execute("""SELECT id, nombre, apellido, '' AS foto_url
                           FROM empleados WHERE pin_fichaje=%s AND COALESCE(activo,true)=true""", (pin,))
        emp = cur.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="PIN no reconocido")
        # Último fichaje para sugerir si toca entrada o salida
        cur.execute("SELECT tipo FROM registros_horarios WHERE id_empleado=%s ORDER BY fecha_hora DESC LIMIT 1", (emp['id'],))
        ult = cur.fetchone()
        ultimo_tipo = (ult['tipo'] if ult else None)
        proximo = 'salida' if (ultimo_tipo and ultimo_tipo.strip().lower() == 'entrada') else 'entrada'
        return {"id": emp['id'], "nombre": emp['nombre'], "apellido": emp['apellido'],
                "foto_url": emp['foto_url'], "proximo": proximo}
    finally:
        liberar_conexion(conn)

class FichajePin(BaseModel):
    pin: str
    tipo: str
    id_local: Optional[int] = None
    nombre_local: Optional[str] = None

@app.post("/api/fichaje/por_pin")
def fichaje_por_pin(data: FichajePin):
    """Ficha entrada/salida usando el PIN. Mantiene el bloqueo de duplicados."""
    pin = (data.pin or '').strip()
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, apellido FROM empleados WHERE pin_fichaje=%s AND COALESCE(activo,true)=true", (pin,))
        emp = cur.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="PIN no reconocido")
        id_emp = emp[0]
        tipo_nuevo = (data.tipo or '').strip().lower()
        # Bloqueo de duplicados consecutivos
        cur.execute("SELECT tipo FROM registros_horarios WHERE id_empleado=%s ORDER BY fecha_hora DESC LIMIT 1", (id_emp,))
        ultimo = cur.fetchone()
        if ultimo:
            tipo_ultimo = (ultimo[0] or '').strip().lower()
            if tipo_ultimo == tipo_nuevo:
                if tipo_nuevo == 'entrada':
                    raise HTTPException(status_code=409, detail="Ya tenés una entrada registrada. Fichá la salida primero.")
                else:
                    raise HTTPException(status_code=409, detail="Ya tenés una salida registrada. Fichá una entrada primero.")
        else:
            if tipo_nuevo == 'salida':
                raise HTTPException(status_code=409, detail="No tenés una entrada registrada. Fichá la entrada primero.")
        obs = ("Local: " + data.nombre_local) if data.nombre_local else None
        cur.execute("INSERT INTO registros_horarios (id_empleado, tipo, observacion) VALUES (%s,%s,%s)",
                    (id_emp, data.tipo, obs))
        conn.commit()
        return {"status": "ok", "nombre": emp[1], "apellido": emp[2], "tipo": tipo_nuevo}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class AsignarPin(BaseModel):
    pin: str

@app.put("/api/empleados/{id_emp}/pin")
def asignar_pin(id_emp: int, data: AsignarPin):
    """Asigna un PIN de 4 dígitos a un empleado. Valida que sea único."""
    pin = (data.pin or '').strip()
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(status_code=400, detail="El PIN debe ser de 4 dígitos numéricos")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM empleados WHERE pin_fichaje=%s AND id<>%s", (pin, id_emp))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Ese PIN ya lo usa otro empleado. Elegí otro.")
            cur.execute("UPDATE empleados SET pin_fichaje=%s WHERE id=%s", (pin, id_emp))
            conn.commit()
            return {"status": "ok"}
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PIN_FICHAJE.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.post("/api/fichaje")
def registrar_fichaje(data: FichajeData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Ver el último fichaje del empleado para evitar dobles consecutivos
        cur.execute("""SELECT tipo, fecha_hora FROM registros_horarios
                       WHERE id_empleado=%s ORDER BY fecha_hora DESC LIMIT 1""", (data.id_empleado,))
        ultimo = cur.fetchone()
        tipo_nuevo = (data.tipo or '').strip().lower()
        if ultimo:
            tipo_ultimo = (ultimo[0] or '').strip().lower()
            # No permitir dos entradas seguidas ni dos salidas seguidas
            if tipo_ultimo == tipo_nuevo:
                if tipo_nuevo == 'entrada':
                    raise HTTPException(status_code=409, detail="Ya fichaste tu entrada. Tenés que fichar la salida antes de marcar otra entrada.")
                elif tipo_nuevo == 'salida':
                    raise HTTPException(status_code=409, detail="Ya fichaste tu salida. Tenés que fichar una entrada antes de marcar otra salida.")
                else:
                    raise HTTPException(status_code=409, detail="Ya registraste ese mismo movimiento.")
        else:
            # Primer fichaje del empleado: debería ser una entrada
            if tipo_nuevo == 'salida':
                raise HTTPException(status_code=409, detail="No tenés una entrada registrada. Fichá la entrada primero.")
        cur.execute("INSERT INTO registros_horarios (id_empleado, tipo, observacion) VALUES (%s,%s,%s)",
                    (data.id_empleado, data.tipo, data.observacion))
        conn.commit()
        return {"status": "ok", "tipo": tipo_nuevo}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/fichajes")
def listar_fichajes(fecha: Optional[str] = None, id_empleado: Optional[int] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        filtros, params = [], []
        if fecha: filtros.append("DATE(r.fecha_hora) = %s"); params.append(fecha)
        if id_empleado: filtros.append("r.id_empleado = %s"); params.append(id_empleado)
        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        cur.execute(f"""
            SELECT r.id, r.tipo, r.fecha_hora::text, r.observacion, e.nombre, e.apellido, e.rol
            FROM registros_horarios r JOIN empleados e ON r.id_empleado = e.id
            {where} ORDER BY r.fecha_hora DESC LIMIT 200
        """, params)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.delete("/api/liquidacion/historial/{id}")
def eliminar_pago_sueldo(id: int):
    """Elimina un pago del historial (para corregir errores)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pagos_sueldo WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/liquidacion/historial")
def historial_pagos_sueldo(id_empleado: Optional[int] = None):
    """Historial de pagos de sueldos. Si se pasa id_empleado, filtra por ese empleado."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """SELECT ps.id, ps.fecha_desde::text, ps.fecha_hasta::text,
                      ps.total_horas, ps.pago_horas, ps.anticipos_descontados,
                      ps.neto_pagado, ps.detalle, ps.fecha_pago::text,
                      e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
               FROM pagos_sueldo ps JOIN empleados e ON ps.id_empleado=e.id
               WHERE 1=1"""
        params = []
        if id_empleado:
            q += " AND ps.id_empleado=%s"; params.append(id_empleado)
        q += " ORDER BY ps.fecha_pago DESC LIMIT 200"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    except Exception:
        conn.rollback()
        return []
    finally:
        liberar_conexion(conn)

@app.get("/api/liquidacion/ultimo_pago/{id_empleado}")
def ultimo_pago_empleado(id_empleado: int):
    """Devuelve la fecha hasta la que se pagó por última vez a este empleado."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""SELECT fecha_hasta::text, fecha_pago::text, neto_pagado
                           FROM pagos_sueldo WHERE id_empleado=%s
                           ORDER BY fecha_hasta DESC LIMIT 1""", (id_empleado,))
            r = cur.fetchone()
            return r if r else {}
        except Exception:
            conn.rollback()
            return {}
    finally:
        liberar_conexion(conn)

@app.get("/api/liquidacion/detalle")
def liquidacion_detalle(fecha_desde: str, fecha_hasta: str):
    """Liquidación por rango de fechas: por cada empleado, el detalle día por día
    (horas, entrada, salida) más el valor hora. El pago doble y los descuentos de
    anticipos se aplican en el frontend (el usuario los marca y recalcula)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='empleados' AND column_name='valor_hora'")
        tiene_vh = bool(cur.fetchone())
        vh_sel = "COALESCE(e.valor_hora,0)" if tiene_vh else "0"
        # Emparejar entrada->salida y agrupar por DÍA
        cur.execute(f"""
            WITH pares AS (
                SELECT e.id AS id_empleado, e.nombre, e.apellido, {vh_sel} AS valor_hora,
                       r.fecha_hora AS entrada,
                       LEAD(r.fecha_hora) OVER (PARTITION BY r.id_empleado ORDER BY r.fecha_hora) AS salida,
                       r.tipo
                FROM registros_horarios r JOIN empleados e ON r.id_empleado = e.id
                WHERE DATE(r.fecha_hora) >= %s AND DATE(r.fecha_hora) <= %s
            )
            SELECT id_empleado, nombre, apellido, valor_hora,
                   DATE(entrada) AS dia,
                   MIN(entrada) AS primera_entrada,
                   MAX(salida) AS ultima_salida,
                   ROUND(CAST(SUM(EXTRACT(EPOCH FROM (salida - entrada))/3600.0) AS numeric), 2) AS horas
            FROM pares
            WHERE LOWER(tipo)='entrada' AND salida IS NOT NULL
            GROUP BY id_empleado, nombre, apellido, valor_hora, DATE(entrada)
            ORDER BY nombre, apellido, dia
        """, (fecha_desde, fecha_hasta))
        filas = fetchall_dict(cur)
        # Agrupar por empleado
        empleados = {}
        for f in filas:
            eid = f['id_empleado']
            if eid not in empleados:
                empleados[eid] = {
                    "id_empleado": eid, "nombre": f['nombre'], "apellido": f['apellido'],
                    "valor_hora": float(f['valor_hora'] or 0), "dias": [], "horas_totales": 0
                }
            horas = float(f['horas'] or 0)
            empleados[eid]['dias'].append({
                "dia": str(f['dia']),
                "entrada": str(f['primera_entrada'])[11:16] if f['primera_entrada'] else '',
                "salida": str(f['ultima_salida'])[11:16] if f['ultima_salida'] else '',
                "horas": horas
            })
            empleados[eid]['horas_totales'] += horas
        # Anticipos pendientes de cada empleado en general (no solo del período)
        for eid, emp in empleados.items():
            emp['horas_totales'] = round(emp['horas_totales'], 2)
            emp['pago_base'] = round(emp['horas_totales'] * emp['valor_hora'], 2)
            try:
                cur.execute("""
                    SELECT a.id, a.monto, COALESCE(a.observaciones,'') AS obs, a.fecha::text AS fecha,
                           COALESCE((SELECT SUM(d.monto) FROM descuentos_anticipos d WHERE d.id_anticipo=a.id),0) AS descontado
                    FROM anticipos_empleados a
                    WHERE a.id_empleado=%s AND COALESCE(a.pagado,false)=false
                    ORDER BY a.fecha
                """, (eid,))
                ants = []
                for a in fetchall_dict(cur):
                    monto = float(a['monto'] or 0)
                    desc = float(a['descontado'] or 0)
                    saldo = round(monto - desc, 2)
                    if saldo > 0:
                        ants.append({"id": a['id'], "monto": monto, "descontado": desc,
                                     "saldo": saldo, "obs": a['obs'], "fecha": a['fecha']})
                emp['anticipos'] = ants
            except Exception:
                conn.rollback()
                emp['anticipos'] = []
        return list(empleados.values())
    finally:
        liberar_conexion(conn)

@app.post("/api/liquidacion/descontar_anticipo")
def descontar_anticipo(data: dict = Body(...)):
    """Registra un descuento (parcial o total) sobre un anticipo.
    Si el saldo llega a 0, marca el anticipo como pagado."""
    id_anticipo = data.get('id_anticipo')
    monto = float(data.get('monto') or 0)
    id_empleado = data.get('id_empleado')
    obs = data.get('observacion')
    if not id_anticipo or monto <= 0:
        raise HTTPException(status_code=400, detail="Datos incompletos")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT monto FROM anticipos_empleados WHERE id=%s", (id_anticipo,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Anticipo no encontrado")
            total = float(row['monto'] or 0)
            cur.execute("SELECT COALESCE(SUM(monto),0) AS d FROM descuentos_anticipos WHERE id_anticipo=%s", (id_anticipo,))
            ya = float(cur.fetchone()['d'] or 0)
            saldo = total - ya
            if monto > saldo + 0.01:
                raise HTTPException(status_code=400, detail=f"El descuento (${monto}) supera el saldo del anticipo (${round(saldo,2)})")
            cur.execute("INSERT INTO descuentos_anticipos (id_anticipo, id_empleado, monto, observacion) VALUES (%s,%s,%s,%s)",
                        (id_anticipo, id_empleado, monto, obs))
            # ¿Quedó saldado?
            nuevo_saldo = saldo - monto
            if nuevo_saldo <= 0.01:
                cur.execute("UPDATE anticipos_empleados SET pagado=true, fecha_pago=NOW() WHERE id=%s", (id_anticipo,))
            conn.commit()
            return {"status": "ok", "saldo_restante": round(max(0, nuevo_saldo), 2)}
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_DESCUENTOS_ANTICIPOS.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.post("/api/liquidacion/marcar_pagado")
def marcar_pagado(data: dict = Body(...)):
    """Registra el pago del sueldo de un empleado por un período y salda
    automáticamente sus anticipos pendientes (descuento total)."""
    id_emp = data.get('id_empleado')
    desde = data.get('fecha_desde')
    hasta = data.get('fecha_hasta')
    total_horas = float(data.get('total_horas') or 0)
    pago_horas = float(data.get('pago_horas') or 0)
    detalle = data.get('detalle') or ''
    if not id_emp:
        raise HTTPException(status_code=400, detail="Falta el empleado")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # ANTI-DUPLICADO: verificar si ya existe un pago para este empleado en este período
        try:
            cur.execute("""SELECT id FROM pagos_sueldo
                           WHERE id_empleado=%s AND fecha_desde=%s AND fecha_hasta=%s LIMIT 1""",
                       (id_emp, desde, hasta))
            ya_pagado = cur.fetchone()
            if ya_pagado:
                raise HTTPException(status_code=409,
                    detail=f"Este período ya fue pagado (pago #{ya_pagado['id']}). Si querés corregirlo, eliminá el pago anterior desde el historial.")
        except HTTPException:
            raise
        except Exception:
            conn.rollback()  # la tabla puede no tener el campo — seguimos
        anticipos_desc = 0.0
        try:
            cur.execute("""SELECT a.id, a.monto,
                                  COALESCE((SELECT SUM(d.monto) FROM descuentos_anticipos d WHERE d.id_anticipo=a.id),0) AS descontado
                           FROM anticipos_empleados a
                           WHERE a.id_empleado=%s AND COALESCE(a.pagado,false)=false""", (id_emp,))
            for a in fetchall_dict(cur):
                saldo = float(a['monto'] or 0) - float(a['descontado'] or 0)
                if saldo > 0:
                    cur.execute("INSERT INTO descuentos_anticipos (id_anticipo, id_empleado, monto, observacion) VALUES (%s,%s,%s,%s)",
                                (a['id'], id_emp, saldo, 'Saldado al pagar sueldo'))
                    cur.execute("UPDATE anticipos_empleados SET pagado=true, fecha_pago=NOW() WHERE id=%s", (a['id'],))
                    anticipos_desc += saldo
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr los SQL de anticipos. Corré CREAR_DESCUENTOS_ANTICIPOS.sql.")
        neto = pago_horas - anticipos_desc
        # Registrar el pago
        try:
            cur.execute("""INSERT INTO pagos_sueldo
                (id_empleado, fecha_desde, fecha_hasta, total_horas, pago_horas, anticipos_descontados, neto_pagado, detalle)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_emp, desde, hasta, total_horas, pago_horas, anticipos_desc, neto, detalle))
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PAGOS_SUELDO.sql en la base.")
        # Notificación
        try:
            crear_notificacion("pago", "Sueldo pagado", "Neto: $" + str(round(neto)))
        except Exception:
            pass
        return {"status": "ok", "anticipos_descontados": round(anticipos_desc,2), "neto_pagado": round(neto,2)}
    finally:
        liberar_conexion(conn)

@app.get("/api/costos/productos")
def listar_costos_productos():
    """Lista los productos del local (únicos por nombre) con su precio de costo,
    precio de venta y sus variantes, para la planilla de costos/precios."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""SELECT nombre, COALESCE(categoria,'') AS categoria,
                                  MAX(COALESCE(precio,0)) AS precio,
                                  MAX(COALESCE(precio_costo,0)) AS precio_costo
                           FROM pos_productos WHERE COALESCE(activo,true)=true
                           GROUP BY nombre, categoria ORDER BY categoria, nombre""")
            productos = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PRECIO_COSTO.sql en la base.")
        # Variantes por nombre de producto (caja, pack, etc.)
        try:
            cur.execute("""SELECT pp.nombre AS base, v.nombre AS variante,
                                  COALESCE(v.precio,0) AS precio, COALESCE(v.factor,1) AS factor,
                                  MIN(v.id) AS id_variante
                           FROM pos_producto_variantes v
                           JOIN pos_productos pp ON v.id_producto = pp.id
                           WHERE COALESCE(v.activo,true)=true
                           GROUP BY pp.nombre, v.nombre, v.precio, v.factor
                           ORDER BY factor""")
            varmap = {}
            for r in fetchall_dict(cur):
                base = (r['base'] or '')
                varmap.setdefault(base, []).append({
                    "id": r['id_variante'], "nombre": r['variante'],
                    "precio": float(r['precio'] or 0), "factor": float(r['factor'] or 1)
                })
            for p in productos:
                p['variantes'] = varmap.get(p['nombre'], [])
        except Exception:
            conn.rollback()
            for p in productos:
                p['variantes'] = []
        return productos
    finally:
        liberar_conexion(conn)

@app.post("/api/costos/guardar")
def guardar_costos(data: dict = Body(...)):
    """Guarda el precio de costo para un producto (por nombre, en todos los locales)."""
    nombre = (data.get('nombre') or '').strip()
    costo = float(data.get('precio_costo') or 0)
    if not nombre:
        raise HTTPException(status_code=400, detail="Falta el nombre")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE pos_productos SET precio_costo=%s WHERE nombre=%s", (costo, nombre))
            conn.commit()
            return {"status": "ok"}
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_PRECIO_COSTO.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.post("/api/costos/guardar_precio")
def guardar_precio_venta(data: dict = Body(...)):
    """Actualiza el precio de venta de un producto (por nombre, en todos los locales)."""
    nombre = (data.get('nombre') or '').strip()
    precio = float(data.get('precio') or 0)
    if not nombre:
        raise HTTPException(status_code=400, detail="Falta el nombre")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET precio=%s WHERE nombre=%s", (precio, nombre))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.post("/api/costos/guardar_precio_variante")
def guardar_precio_variante(data: dict = Body(...)):
    """Actualiza el precio de venta de una variante (por nombre base + nombre variante,
    en todos los locales)."""
    base = (data.get('nombre_base') or '').strip()
    variante = (data.get('nombre_variante') or '').strip()
    precio = float(data.get('precio') or 0)
    if not base or not variante:
        raise HTTPException(status_code=400, detail="Faltan datos")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""UPDATE pos_producto_variantes SET precio=%s
                       WHERE nombre=%s AND id_producto IN (SELECT id FROM pos_productos WHERE nombre=%s)""",
                    (precio, variante, base))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/ganancia_local")
def reporte_ganancia_local(fecha_desde: str, fecha_hasta: str, id_local: int):
    """Ganancia del local = (precio de venta − precio de costo cargado) × cantidad.
    Usa el precio_costo de los productos del local. Los productos sin costo cargado
    se listan aparte."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Mapa nombre del producto base → costo
        costos = {}
        try:
            cur.execute("SELECT nombre, MAX(COALESCE(precio_costo,0)) AS c FROM pos_productos GROUP BY nombre")
            for r in fetchall_dict(cur):
                costos[(r['nombre'] or '').strip().lower()] = float(r['c'] or 0)
        except Exception:
            conn.rollback()
        # Mapa de variantes: "nombre base (variante)" → (costo_base_unitario, factor)
        # El POS guarda la venta como "NombreBase (NombreVariante)".
        variantes = {}
        try:
            cur.execute("""SELECT pp.nombre AS base, v.nombre AS variante, COALESCE(v.factor,1) AS factor
                           FROM pos_producto_variantes v
                           JOIN pos_productos pp ON v.id_producto = pp.id
                           WHERE COALESCE(v.activo,true)=true""")
            for r in fetchall_dict(cur):
                base = (r['base'] or '').strip()
                varn = (r['variante'] or '').strip()
                clave = (base + ' (' + varn + ')').lower()
                costo_base = costos.get(base.lower(), 0)
                variantes[clave] = (costo_base, float(r['factor'] or 1))
        except Exception:
            conn.rollback()
        # Ventas del período por producto
        cur.execute("""
            SELECT d.nombre_producto,
                   SUM(d.cantidad) AS cantidad,
                   SUM(d.cantidad * d.precio_unitario) AS total_vendido
            FROM pos_detalle_ventas d
            JOIN pos_ventas v ON d.id_venta = v.id
            WHERE v.id_local = %s AND DATE(v.fecha) >= %s AND DATE(v.fecha) <= %s
            GROUP BY d.nombre_producto
            ORDER BY total_vendido DESC
        """, (id_local, fecha_desde, fecha_hasta))
        ventas = fetchall_dict(cur)

        con_costo = []
        sin_costo = []
        total_vendido = 0.0
        total_costo = 0.0
        total_ganancia = 0.0
        total_sin_costo = 0.0

        for v in ventas:
            nombre = v['nombre_producto'] or ''
            cant = float(v['cantidad'] or 0)
            vendido = float(v['total_vendido'] or 0)
            total_vendido += vendido
            nclave = nombre.strip().lower()
            costo_unit = 0
            # 1) ¿Es una variante? (nombre con presentación) → costo base × factor
            if nclave in variantes:
                cbase, factor = variantes[nclave]
                costo_unit = cbase * factor
            else:
                # 2) Producto base directo
                costo_unit = costos.get(nclave, 0)
            if costo_unit and costo_unit > 0:
                costo = costo_unit * cant
                ganancia = vendido - costo
                total_costo += costo
                total_ganancia += ganancia
                con_costo.append({
                    "producto": nombre, "cantidad": cant,
                    "vendido": round(vendido, 2), "costo_mayorista": round(costo, 2),
                    "ganancia": round(ganancia, 2)
                })
            else:
                total_sin_costo += vendido
                sin_costo.append({"producto": nombre, "cantidad": cant, "vendido": round(vendido, 2)})

        return {
            "total_vendido": round(total_vendido, 2),
            "total_con_costo": round(total_vendido - total_sin_costo, 2),
            "total_costo_mayorista": round(total_costo, 2),
            "total_ganancia": round(total_ganancia, 2),
            "total_sin_costo": round(total_sin_costo, 2),
            "con_costo": con_costo,
            "sin_costo": sin_costo
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/ganancia_local_OLD_DESUSO")
def reporte_ganancia_local_old(fecha_desde: str, fecha_hasta: str, id_local: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Todo lo vendido en el período por ese local (sumado por producto)
        cur.execute("""
            SELECT d.nombre_producto,
                   SUM(d.cantidad) AS cantidad,
                   SUM(d.cantidad * d.precio_unitario) AS total_vendido,
                   AVG(d.precio_unitario) AS precio_prom
            FROM pos_detalle_ventas d
            JOIN pos_ventas v ON d.id_venta = v.id
            WHERE v.id_local = %s AND DATE(v.fecha) >= %s AND DATE(v.fecha) <= %s
            GROUP BY d.nombre_producto
            ORDER BY total_vendido DESC
        """, (id_local, fecha_desde, fecha_hasta))
        ventas = fetchall_dict(cur)

        con_costo = []
        sin_costo = []
        total_vendido = 0.0
        total_costo = 0.0
        total_ganancia = 0.0
        total_sin_costo = 0.0

        for v in ventas:
            nombre = v['nombre_producto'] or ''
            cant = float(v['cantidad'] or 0)
            vendido = float(v['total_vendido'] or 0)
            total_vendido += vendido
            # Buscar precio mayorista en fábrica por nombre (exacto o contiene)
            mayorista = None
            if nombre.strip():
                cur.execute("SELECT precio_mayorista FROM productos WHERE LOWER(nombre)=LOWER(%s) AND COALESCE(activo,true)=true LIMIT 1", (nombre.strip(),))
                f = cur.fetchone()
                if not f:
                    cur.execute("SELECT precio_mayorista FROM productos WHERE LOWER(nombre) LIKE LOWER(%s) AND COALESCE(activo,true)=true ORDER BY LENGTH(nombre) LIMIT 1", ('%'+nombre.strip()+'%',))
                    f = cur.fetchone()
                if f and f['precio_mayorista'] is not None and float(f['precio_mayorista']) > 0:
                    mayorista = float(f['precio_mayorista'])
            if mayorista is not None:
                costo = mayorista * cant
                ganancia = vendido - costo
                total_costo += costo
                total_ganancia += ganancia
                con_costo.append({
                    "producto": nombre, "cantidad": cant,
                    "vendido": round(vendido, 2), "costo_mayorista": round(costo, 2),
                    "ganancia": round(ganancia, 2)
                })
            else:
                total_sin_costo += vendido
                sin_costo.append({"producto": nombre, "cantidad": cant, "vendido": round(vendido, 2)})

        return {
            "total_vendido": round(total_vendido, 2),
            "total_con_costo": round(total_vendido - total_sin_costo, 2),
            "total_costo_mayorista": round(total_costo, 2),
            "total_ganancia": round(total_ganancia, 2),
            "total_sin_costo": round(total_sin_costo, 2),
            "con_costo": con_costo,
            "sin_costo": sin_costo
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/horas_trabajadas")
def reporte_horas_trabajadas(fecha_desde: str, fecha_hasta: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Detectar si existe la columna valor_hora
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='empleados' AND column_name='valor_hora'")
        tiene_vh = bool(cur.fetchone())
        vh_sel = "COALESCE(e.valor_hora,0)" if tiene_vh else "0"
        cur.execute(f"""
            WITH pares AS (
                SELECT e.id as id_empleado, e.nombre, e.apellido, {vh_sel} AS valor_hora,
                       r.fecha_hora as entrada,
                       LEAD(r.fecha_hora) OVER (PARTITION BY r.id_empleado ORDER BY r.fecha_hora) as salida,
                       r.tipo
                FROM registros_horarios r JOIN empleados e ON r.id_empleado = e.id
                WHERE DATE(r.fecha_hora) >= %s AND DATE(r.fecha_hora) <= %s
            )
            SELECT id_empleado, nombre, apellido, MAX(valor_hora) AS valor_hora,
                   ROUND(CAST(SUM(EXTRACT(EPOCH FROM (salida - entrada))/3600.0) AS numeric), 2) as horas_totales
            FROM pares
            WHERE LOWER(tipo) = 'entrada' AND salida IS NOT NULL
            GROUP BY id_empleado, nombre, apellido
            ORDER BY horas_totales DESC
        """, (fecha_desde, fecha_hasta))
        filas = fetchall_dict(cur)
        for f in filas:
            horas = float(f['horas_totales'] or 0)
            vh = float(f['valor_hora'] or 0)
            f['pago_calculado'] = round(horas * vh, 2)
        return filas
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ANTICIPOS
# ==============================================================================
@app.post("/api/anticipos/nuevo")
def registrar_anticipo(data: NuevoAnticipo):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO anticipos_empleados (id_empleado, monto, observaciones) VALUES (%s,%s,%s)",
                    (data.id_empleado, data.monto, data.observaciones))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/anticipos")
def listar_anticipos(fecha_desde: str, fecha_hasta: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT a.id, a.fecha::text, a.monto, a.observaciones, e.nombre, e.apellido,
                       COALESCE(a.pagado,false) AS pagado, a.fecha_pago::text AS fecha_pago
                FROM anticipos_empleados a JOIN empleados e ON a.id_empleado = e.id
                WHERE DATE(a.fecha) >= %s AND DATE(a.fecha) <= %s ORDER BY a.fecha DESC
            """, (fecha_desde, fecha_hasta))
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT a.id, a.fecha::text, a.monto, a.observaciones, e.nombre, e.apellido,
                       false AS pagado, NULL AS fecha_pago
                FROM anticipos_empleados a JOIN empleados e ON a.id_empleado = e.id
                WHERE DATE(a.fecha) >= %s AND DATE(a.fecha) <= %s ORDER BY a.fecha DESC
            """, (fecha_desde, fecha_hasta))
            return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/anticipos/{id_anticipo}/pagar")
def marcar_anticipo_pagado(id_anticipo: int, pagado: bool = True):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if pagado:
            cur.execute("UPDATE anticipos_empleados SET pagado=true, fecha_pago=NOW() WHERE id=%s", (id_anticipo,))
        else:
            cur.execute("UPDATE anticipos_empleados SET pagado=false, fecha_pago=NULL WHERE id=%s", (id_anticipo,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# INSUMOS
# ==============================================================================
@app.get("/api/insumos")
def get_insumos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, nombre, unidad_medida as unidad, stock_actual as stock, stock_minimo as minimo,
                   costo_unitario as costo, costo_por_bulto, presentacion_compra,
                   cantidad_por_presentacion, id_proveedor
            FROM insumos WHERE COALESCE(activo, true) = true ORDER BY nombre ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/insumos_nuevo")
def crear_insumo(ins: InsumoCompleto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO insumos (nombre, unidad_medida, stock_minimo, costo_unitario,
                presentacion_compra, cantidad_por_presentacion, costo_por_bulto, id_proveedor)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (ins.nombre, ins.unidad_medida, ins.stock_minimo, ins.costo_unitario,
              ins.presentacion_compra, ins.cantidad_por_presentacion, ins.costo_por_bulto, ins.id_proveedor))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/insumos/{id_insumo}")
def actualizar_insumo(id_insumo: int, ins: InsumoCompleto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE insumos SET nombre=%s, unidad_medida=%s, stock_minimo=%s, costo_unitario=%s,
                presentacion_compra=%s, cantidad_por_presentacion=%s, costo_por_bulto=%s, id_proveedor=%s
            WHERE id=%s
        """, (ins.nombre, ins.unidad_medida, ins.stock_minimo, ins.costo_unitario,
              ins.presentacion_compra, ins.cantidad_por_presentacion, ins.costo_por_bulto, ins.id_proveedor, id_insumo))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.post("/api/insumos/{id_insumo}/sumar_stock")
def sumar_stock_insumo(id_insumo: int, data: SumarStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE insumos SET stock_actual = stock_actual + %s WHERE id=%s", (data.cantidad, id_insumo))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/insumos/{id_insumo}")
def eliminar_insumo(id_insumo: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE insumos SET activo=false WHERE id=%s", (id_insumo,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# RECETAS
# ==============================================================================
@app.get("/api/recetas/{id_producto}")
def get_receta(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT r.id, r.id_insumo, r.cantidad_necesaria,
                   i.nombre as insumo, i.unidad_medida as unidad, i.costo_unitario as costo
            FROM recetas r JOIN insumos i ON r.id_insumo = i.id
            WHERE r.id_producto = %s
        """, (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/recetas/guardar")
def guardar_receta(receta: RecetaUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM recetas WHERE id_producto = %s", (receta.id_producto,))
        for item in receta.items:
            cur.execute("INSERT INTO recetas (id_producto, id_insumo, cantidad_necesaria) VALUES (%s,%s,%s)",
                        (receta.id_producto, item.id_insumo, item.cantidad_necesaria))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# PRODUCCIÓN  (tabla ordenes_produccion, descuenta insumos)
# ==============================================================================
@app.get("/api/produccion/historial")
def historial_produccion():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT o.id, o.fecha::text, o.cantidad_producida, o.observaciones,
                   o.fecha_vencimiento::text, o.costo_total, o.id_categoria, o.id_empleado, o.id_producto,
                   p.nombre as producto, p.sku,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM ordenes_produccion o
            JOIN productos p ON o.id_producto = p.id
            JOIN empleados e ON o.id_empleado = e.id
            ORDER BY o.fecha DESC LIMIT 200
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/produccion/registrar")
def registrar_produccion(prod: ProduccionCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ordenes_produccion
            (id_producto, id_empleado, cantidad_producida, fecha_vencimiento, observaciones, costo_total, id_categoria)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (prod.id_producto, prod.id_empleado, prod.cantidad_producida, prod.fecha_vencimiento,
              prod.observaciones, prod.costo_total, prod.id_categoria))
        # Descontar insumos según receta
        cur.execute("SELECT id_insumo, cantidad_necesaria FROM recetas WHERE id_producto = %s", (prod.id_producto,))
        for item in cur.fetchall():
            cant_descontar = float(item[1]) * prod.cantidad_producida
            cur.execute("UPDATE insumos SET stock_actual = stock_actual - %s WHERE id = %s", (cant_descontar, item[0]))
        # Quitar el marcado "en proceso" de este producto (ya se ingresó)
        try:
            cur.execute("DELETE FROM produccion_en_proceso WHERE id_producto=%s", (prod.id_producto,))
        except Exception:
            conn.rollback()
        conn.commit()
        try:
            crear_notificacion("produccion", "Producción registrada",
                               str(prod.cantidad_producida) + " unidades")
        except Exception:
            pass
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/produccion/{id}")
def editar_produccion(id: int, payload: ProduccionUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE ordenes_produccion SET cantidad_producida=%s, fecha_vencimiento=%s, observaciones=%s WHERE id=%s
        """, (payload.cantidad_producida, payload.fecha_vencimiento, payload.observaciones, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/produccion/{id}")
def eliminar_produccion(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ordenes_produccion WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# PROVEEDORES
# ==============================================================================
@app.get("/api/proveedores")
def listar_proveedores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id, p.razon_social, p.cuit, p.email, p.telefono, p.direccion, p.notas,
                   COUNT(DISTINCT pi.id_insumo) as cant_insumos,
                   COUNT(DISTINCT oc.id) as cant_ordenes
            FROM proveedores p
            LEFT JOIN proveedor_insumos pi ON pi.id_proveedor = p.id
            LEFT JOIN ordenes_compra oc ON oc.id_proveedor = p.id
            WHERE COALESCE(p.activo, true) = true GROUP BY p.id ORDER BY p.razon_social
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/nuevo")
def crear_proveedor(prov: NuevoProveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO proveedores (razon_social, cuit, email, telefono, direccion, notas) VALUES (%s,%s,%s,%s,%s,%s)",
                    (prov.razon_social, prov.cuit, prov.email, prov.telefono, prov.direccion, prov.notas))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/proveedores/{id_prov}")
def actualizar_proveedor(id_prov: int, data: ActualizarProveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE proveedores SET email=%s, telefono=%s, direccion=%s, notas=%s WHERE id=%s",
                    (data.email, data.telefono, data.direccion, data.notas, id_prov))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/proveedores/todos/pagos")
def todos_pagos_proveedores(desde: Optional[str] = None, hasta: Optional[str] = None):
    """Lista todos los pagos a proveedores, con nombre del proveedor."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """SELECT pg.id, COALESCE(pg.fecha::text, NOW()::text) AS fecha,
                      pg.monto, pg.metodo, pg.referencia, pg.notas, pg.id_orden,
                      p.nombre AS proveedor_nombre,
                      e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
               FROM pagos_proveedores pg
               LEFT JOIN proveedores p ON pg.id_proveedor = p.id
               LEFT JOIN empleados e ON pg.id_empleado = e.id
               WHERE 1=1"""
        params = []
        if desde: q += " AND COALESCE(pg.fecha, NOW())::date >= %s"; params.append(desde)
        if hasta: q += " AND COALESCE(pg.fecha, NOW())::date <= %s"; params.append(hasta)
        q += " ORDER BY COALESCE(pg.fecha, NOW()) DESC"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/proveedores/{id_prov}/pagos")
def pagos_proveedor(id_prov: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT pg.id, COALESCE(pg.fecha::text, NOW()::text) AS fecha,
                   pg.monto, pg.metodo, pg.referencia, pg.notas, pg.id_orden,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM pagos_proveedores pg LEFT JOIN empleados e ON pg.id_empleado = e.id
            WHERE pg.id_proveedor = %s ORDER BY COALESCE(pg.fecha, NOW()) DESC
        """, (id_prov,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/pago")
def registrar_pago_proveedor(pago: NuevoPagoProveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 1) Registrar el pago al proveedor
        if pago.fecha:
            cur.execute("INSERT INTO pagos_proveedores (id_proveedor, id_orden, id_empleado, monto, metodo, referencia, notas, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (pago.id_proveedor, pago.id_orden, pago.id_empleado, pago.monto, pago.metodo, pago.referencia, pago.notas, pago.fecha))
        else:
            cur.execute("INSERT INTO pagos_proveedores (id_proveedor, id_orden, id_empleado, monto, metodo, referencia, notas) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (pago.id_proveedor, pago.id_orden, pago.id_empleado, pago.monto, pago.metodo, pago.referencia, pago.notas))
        # 2) Buscar o crear categoría "Proveedores" en gastos
        try:
            cur.execute("SELECT id FROM gastos_categorias WHERE LOWER(nombre)='proveedores' LIMIT 1")
            cat = cur.fetchone()
            if not cat:
                cur.execute("INSERT INTO gastos_categorias (nombre) VALUES ('Proveedores') RETURNING id")
                cat = cur.fetchone()
            id_cat = cat['id'] if cat else None
            # Nombre del proveedor para el concepto
            cur.execute("SELECT nombre FROM proveedores WHERE id=%s", (pago.id_proveedor,))
            prov = cur.fetchone()
            concepto = 'Pago proveedor: ' + (prov['nombre'] if prov else str(pago.id_proveedor))
            if pago.referencia:
                concepto += ' · ' + pago.referencia
            # 3) Insertar en gastos
            cur.execute("""INSERT INTO gastos (id_categoria, concepto, monto, metodo, id_empleado, notas)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                       (id_cat, concepto, pago.monto, pago.metodo, pago.id_empleado,
                        'Auto: pago a proveedor' + (' · ' + pago.notas if pago.notas else '')))
        except Exception:
            pass  # Si falla el gasto, el pago ya está registrado — no bloqueamos
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# TAREAS
# ==============================================================================
@app.get("/api/tareas")
def listar_tareas():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.id, t.titulo, t.descripcion, t.fecha_vencimiento::text,
                   t.prioridad, t.estado, t.id_empleado_asignado,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM tareas t LEFT JOIN empleados e ON t.id_empleado_asignado = e.id
            WHERE t.estado = 'pendiente'
            ORDER BY CASE t.prioridad WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
                     t.fecha_vencimiento ASC NULLS LAST
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/tareas/nueva")
def crear_tarea(t: NuevaTarea):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO tareas (titulo, descripcion, fecha_vencimiento, prioridad, id_empleado_asignado) VALUES (%s,%s,%s,%s,%s)",
                    (t.titulo, t.descripcion, t.fecha_vencimiento, t.prioridad, t.id_empleado_asignado))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/tareas/{id_tarea}/completar")
def completar_tarea(id_tarea: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tareas SET estado='completada' WHERE id=%s", (id_tarea,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ADMIN / TABLERO
# ==============================================================================
@app.get("/api/admin/pedidos_pendientes")
def pedidos_pendientes():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id as id_pedido, d.razon_social as distribuidor, p.estado, p.total
            FROM pedidos_b2b p JOIN distribuidores d ON p.id_distribuidor = d.id
            WHERE p.estado NOT IN ('Despachado','Cancelado') ORDER BY p.fecha DESC LIMIT 20
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/notificaciones")
def listar_notificaciones(solo_nuevas: bool = False):
    """Lista notificaciones (las 50 más recientes). Si solo_nuevas, solo las no leídas."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            if solo_nuevas:
                cur.execute("SELECT id, tipo, titulo, detalle, leida, fecha::text FROM notificaciones WHERE leida=false ORDER BY id DESC LIMIT 50")
            else:
                cur.execute("SELECT id, tipo, titulo, detalle, leida, fecha::text FROM notificaciones ORDER BY id DESC LIMIT 50")
            filas = fetchall_dict(cur)
            cur.execute("SELECT COUNT(*) AS c FROM notificaciones WHERE leida=false")
            nuevas = cur.fetchone()['c']
            return {"nuevas": nuevas, "notificaciones": filas}
        except Exception:
            conn.rollback()
            return {"nuevas": 0, "notificaciones": []}
    finally:
        liberar_conexion(conn)

@app.put("/api/notificaciones/leer_todas")
def marcar_notificaciones_leidas():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE notificaciones SET leida=true WHERE leida=false")
            conn.commit()
        except Exception:
            conn.rollback()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/stock_bajo_productos")
def stock_bajo_productos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, sku, nombre, stock_actual, stock_alerta
            FROM productos
            WHERE COALESCE(activo, true) = true AND (stock_actual <= stock_alerta OR stock_actual <= 0)
            ORDER BY stock_actual ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/stock_bajo_insumos")
def stock_bajo_insumos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, nombre, unidad_medida as unidad, stock_actual as stock, stock_minimo as minimo
            FROM insumos WHERE COALESCE(activo, true) = true AND stock_actual <= stock_minimo
            ORDER BY stock_actual ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

class DeudaProveedorManual(BaseModel):
    id_proveedor: int
    concepto: str
    monto: float
    fecha: Optional[str] = None
    notas: Optional[str] = None

@app.get("/api/proveedores/deudas")
def listar_deudas_proveedores():
    """Lista deudas de órdenes de compra sin pagar + deudas manuales, unificadas."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Deudas automáticas (órdenes de compra recibidas sin pagar)
        try:
            cur.execute("""
                SELECT 'orden' AS tipo, oc.id AS id_ref, p.nombre AS proveedor,
                       oc.total AS monto, oc.fecha::text AS fecha,
                       EXTRACT(DAY FROM NOW() - oc.fecha)::int AS dias,
                       COALESCE(oc.notas,'') AS concepto
                FROM ordenes_compra oc JOIN proveedores p ON oc.id_proveedor=p.id
                WHERE oc.estado='Recibida'
                  AND oc.id NOT IN (SELECT DISTINCT id_orden FROM pagos_proveedores WHERE id_orden IS NOT NULL)
                ORDER BY oc.fecha ASC
            """)
            automaticas = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            automaticas = []
        # Deudas manuales sin pagar
        try:
            cur.execute("""
                SELECT 'manual' AS tipo, d.id AS id_ref, p.nombre AS proveedor,
                       d.monto, d.fecha::text AS fecha,
                       EXTRACT(DAY FROM NOW() - d.fecha)::int AS dias,
                       d.concepto
                FROM deudas_proveedores_manual d JOIN proveedores p ON d.id_proveedor=p.id
                WHERE d.pagada=false
                ORDER BY d.fecha ASC
            """)
            manuales = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            manuales = []
        todas = automaticas + manuales
        total = sum(float(d.get('monto') or 0) for d in todas)
        return {"deudas": todas, "total": total}
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/deudas")
def crear_deuda_manual(d: DeudaProveedorManual):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if d.fecha:
            cur.execute("INSERT INTO deudas_proveedores_manual (id_proveedor,concepto,monto,fecha,notas) VALUES (%s,%s,%s,%s,%s)",
                       (d.id_proveedor, d.concepto, d.monto, d.fecha, d.notas))
        else:
            cur.execute("INSERT INTO deudas_proveedores_manual (id_proveedor,concepto,monto,notas) VALUES (%s,%s,%s,%s)",
                       (d.id_proveedor, d.concepto, d.monto, d.notas))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/proveedores/deudas/{id}/pagar")
def marcar_deuda_pagada(id: int):
    """Marca una deuda manual como pagada y genera un gasto automáticamente."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM deudas_proveedores_manual WHERE id=%s", (id,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        cur.execute("UPDATE deudas_proveedores_manual SET pagada=true, fecha_pago=CURRENT_DATE WHERE id=%s", (id,))
        # Generar gasto automático igual que el pago de proveedor
        try:
            cur.execute("SELECT id FROM gastos_categorias WHERE LOWER(nombre)='proveedores' LIMIT 1")
            cat = cur.fetchone()
            if not cat:
                cur.execute("INSERT INTO gastos_categorias (nombre) VALUES ('Proveedores') RETURNING id")
                cat = cur.fetchone()
            cur.execute("SELECT nombre FROM proveedores WHERE id=%s", (d['id_proveedor'],))
            prov = cur.fetchone()
            concepto = 'Pago deuda: ' + (prov['nombre'] if prov else '') + ' · ' + str(d['concepto'])
            cur.execute("INSERT INTO gastos (id_categoria, concepto, monto, notas) VALUES (%s,%s,%s,%s)",
                       (cat['id'], concepto, d['monto'], 'Auto: pago deuda proveedor'))
        except Exception:
            pass
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/proveedores/deudas/{id}")
def eliminar_deuda_manual(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM deudas_proveedores_manual WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ===== CUENTA CORRIENTE DE PROVEEDORES =====

@app.get("/api/proveedores/{id_prov}/cuenta")
def proveedor_cuenta(id_prov: int):
    """Ficha completa: saldo (deuda inicial + facturas - pagos), facturas, pagos, insumos."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Datos del proveedor + deuda inicial
        cur.execute("SELECT id, nombre, COALESCE(deuda_inicial,0) AS deuda_inicial, cuit, telefono, email FROM proveedores WHERE id=%s", (id_prov,))
        prov = cur.fetchone()
        if not prov:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")

        # Facturas
        try:
            cur.execute("""SELECT id, numero, tipo, fecha::text, fecha_vencimiento::text, total, notas
                           FROM proveedor_facturas WHERE id_proveedor=%s ORDER BY fecha DESC, id DESC""", (id_prov,))
            facturas = fetchall_dict(cur)
        except Exception:
            conn.rollback(); facturas = []
        total_facturas = sum(float(f['total'] or 0) for f in facturas)

        # Pagos: directos al proveedor O asociados a órdenes de ese proveedor
        try:
            cur.execute("""SELECT pg.id, COALESCE(pg.fecha::text, NOW()::text) AS fecha,
                                  pg.monto, pg.metodo, pg.referencia
                           FROM pagos_proveedores pg
                           WHERE pg.id_proveedor=%s
                              OR pg.id_orden IN (SELECT id FROM ordenes_compra WHERE id_proveedor=%s)
                           ORDER BY COALESCE(pg.fecha,NOW()) DESC""", (id_prov, id_prov))
            pagos = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            # Fallback: solo por id_proveedor
            try:
                cur.execute("""SELECT id, COALESCE(fecha::text, NOW()::text) AS fecha, monto, metodo, referencia
                               FROM pagos_proveedores WHERE id_proveedor=%s ORDER BY COALESCE(fecha,NOW()) DESC""", (id_prov,))
                pagos = fetchall_dict(cur)
            except Exception:
                conn.rollback(); pagos = []
        total_pagos = sum(float(p['monto'] or 0) for p in pagos)

        # Insumos que suministra
        try:
            cur.execute("""SELECT pi.id, pi.id_insumo, pi.precio_referencia, i.nombre AS insumo_nombre, i.unidad_medida AS unidad
                           FROM proveedor_insumos pi LEFT JOIN insumos i ON pi.id_insumo=i.id
                           WHERE pi.id_proveedor=%s ORDER BY i.nombre""", (id_prov,))
            insumos = fetchall_dict(cur)
        except Exception:
            conn.rollback(); insumos = []

        deuda_inicial = float(prov['deuda_inicial'] or 0)
        saldo = deuda_inicial + total_facturas - total_pagos

        return {
            "proveedor": prov,
            "deuda_inicial": deuda_inicial,
            "facturas": facturas, "total_facturas": total_facturas,
            "pagos": pagos, "total_pagos": total_pagos,
            "insumos": insumos,
            "saldo": saldo
        }
    finally:
        liberar_conexion(conn)

@app.put("/api/proveedores/{id_prov}/deuda_inicial")
def proveedor_set_deuda_inicial(id_prov: int, data: dict = Body(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE proveedores SET deuda_inicial=%s WHERE id=%s", (data.get('deuda_inicial', 0), id_prov))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

class FacturaItem(BaseModel):
    id_insumo: Optional[int] = None
    descripcion: str
    cantidad: float = 1
    precio_unitario: float = 0

class FacturaProveedor(BaseModel):
    id_proveedor: int
    numero: Optional[str] = None
    tipo: str = 'A'
    fecha: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    notas: Optional[str] = None
    items: List[FacturaItem] = []

@app.post("/api/proveedores/facturas")
def crear_factura_proveedor(f: FacturaProveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        total = sum(it.cantidad * it.precio_unitario for it in f.items)
        cur.execute("""INSERT INTO proveedor_facturas (id_proveedor, numero, tipo, fecha, fecha_vencimiento, total, notas)
                       VALUES (%s,%s,%s,COALESCE(%s,CURRENT_DATE),%s,%s,%s) RETURNING id""",
                    (f.id_proveedor, f.numero, f.tipo, f.fecha, f.fecha_vencimiento, total, f.notas))
        id_fact = cur.fetchone()[0]
        for it in f.items:
            sub = it.cantidad * it.precio_unitario
            cur.execute("""INSERT INTO proveedor_factura_items (id_factura, id_insumo, descripcion, cantidad, precio_unitario, subtotal)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (id_fact, it.id_insumo, it.descripcion, it.cantidad, it.precio_unitario, sub))
        conn.commit()
        return {"id": id_fact, "total": total}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/proveedores/facturas/{id_factura}/items")
def factura_items(id_factura: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT fi.*, i.nombre AS insumo_nombre
                       FROM proveedor_factura_items fi LEFT JOIN insumos i ON fi.id_insumo=i.id
                       WHERE fi.id_factura=%s""", (id_factura,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.delete("/api/proveedores/facturas/{id_factura}")
def eliminar_factura(id_factura: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM proveedor_facturas WHERE id=%s", (id_factura,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/{id_prov}/insumos")
def agregar_insumo_proveedor(id_prov: int, data: dict = Body(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO proveedor_insumos (id_proveedor, id_insumo, precio_referencia)
                       VALUES (%s,%s,%s) ON CONFLICT (id_proveedor, id_insumo)
                       DO UPDATE SET precio_referencia=EXCLUDED.precio_referencia""",
                    (id_prov, data['id_insumo'], data.get('precio_referencia')))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/proveedores/insumos/{id}")
def quitar_insumo_proveedor(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM proveedor_insumos WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/deudas_proveedores")
def deudas_proveedores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT oc.id as id_orden, oc.id_proveedor, p.razon_social as proveedor,
                   oc.total, oc.fecha::text,
                   EXTRACT(DAY FROM NOW() - oc.fecha)::int as dias_atraso
            FROM ordenes_compra oc JOIN proveedores p ON oc.id_proveedor = p.id
            WHERE oc.estado = 'Recibida'
              AND oc.id NOT IN (SELECT DISTINCT pg.id_orden FROM pagos_proveedores pg WHERE pg.id_orden IS NOT NULL)
              AND oc.fecha <= NOW() - INTERVAL '15 days'
            ORDER BY oc.fecha ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/cobros_pendientes")
def cobros_pendientes():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT pb.id as id_pedido, pb.id_distribuidor, d.razon_social as distribuidor,
                   pb.total, pb.fecha::text,
                   EXTRACT(DAY FROM NOW() - pb.fecha)::int as dias_atraso
            FROM pedidos_b2b pb JOIN distribuidores d ON pb.id_distribuidor = d.id
            WHERE pb.estado = 'Despachado'
              AND pb.id NOT IN (SELECT DISTINCT cd.id_pedido FROM cobros_distribuidores cd WHERE cd.id_pedido IS NOT NULL)
              AND pb.fecha <= NOW() - INTERVAL '15 days'
            ORDER BY pb.fecha ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)


# ==============================================================================
# MÓDULO POS  (locales independientes: productos, caja y ventas por local)
# ==============================================================================
class PosLocal(BaseModel):
    nombre: str
    direccion: Optional[str] = None
    punto_venta_afip: Optional[int] = None

class PosProducto(BaseModel):
    id_local: int
    nombre: str
    precio: float = 0.0
    categoria: Optional[str] = None
    stock: float = 0.0
    stock_alerta: float = 0.0

class PosAbrirCaja(BaseModel):
    id_local: int
    nombre_responsable: Optional[str] = None
    monto_apertura: float = 0.0
    id_usuario: Optional[int] = None

class PosCerrarCaja(BaseModel):
    monto_cierre: float = 0.0
    id_usuario: Optional[int] = None
    es_admin: Optional[bool] = False
    observaciones: Optional[str] = None

class PosItemVenta(BaseModel):
    nombre_producto: str
    cantidad: float
    precio_unitario: float
    id_producto: Optional[int] = None
    unidades_stock: Optional[float] = None

class PosPago(BaseModel):
    metodo_pago: str
    monto: float

class PosVenta(BaseModel):
    id_caja: int
    id_local: int
    metodo_pago: str
    total: float
    detalle: List[PosItemVenta]
    id_empleado: Optional[int] = None
    nombre_cajero: Optional[str] = None
    pagos: Optional[List[PosPago]] = None
    ref_unica: Optional[str] = None   # llave única generada por el POS para evitar duplicados

# ---- LOCALES ----
@app.get("/api/pos/locales")
def pos_listar_locales():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT id, nombre, direccion, punto_venta_afip FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, nombre, direccion FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
            return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/locales")
def pos_crear_local(l: PosLocal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO pos_locales (nombre, direccion, punto_venta_afip) VALUES (%s,%s,%s) RETURNING id", (l.nombre, l.direccion, l.punto_venta_afip))
        except Exception:
            conn.rollback()
            cur.execute("INSERT INTO pos_locales (nombre, direccion) VALUES (%s,%s) RETURNING id", (l.nombre, l.direccion))
        lid = cur.fetchone()[0]
        conn.commit()
        return {"id": lid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/locales/{id}")
def pos_actualizar_local(id: int, l: PosLocal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE pos_locales SET nombre=%s, direccion=%s, punto_venta_afip=%s WHERE id=%s", (l.nombre, l.direccion, l.punto_venta_afip, id))
        except Exception:
            conn.rollback()
            cur.execute("UPDATE pos_locales SET nombre=%s, direccion=%s WHERE id=%s", (l.nombre, l.direccion, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pos/locales/{id}")
def pos_eliminar_local(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_locales SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- PRODUCTOS (por local) ----
@app.get("/api/pos/productos")
def pos_listar_productos(id_local: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""SELECT p.id, p.nombre, p.precio, p.categoria,
                                  COALESCE(p.stock,0) AS stock, COALESCE(p.stock_alerta,0) AS stock_alerta,
                                  p.id_producto_fabrica, p.unidades_por_caja_local,
                                  pf.nombre AS nombre_producto_fabrica
                           FROM pos_productos p
                           LEFT JOIN productos pf ON p.id_producto_fabrica = pf.id
                           WHERE p.id_local=%s AND COALESCE(p.activo,true)=true
                           ORDER BY p.categoria NULLS LAST, p.nombre""", (id_local,))
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, nombre, precio, categoria, COALESCE(stock,0) AS stock, COALESCE(stock_alerta,0) AS stock_alerta FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true ORDER BY categoria NULLS LAST, nombre", (id_local,))
        productos = fetchall_dict(cur)
        if not productos:
            return []
        ids = [p['id'] for p in productos]
        # Variantes de todos los productos en UNA consulta
        variantes_por_prod = {}
        try:
            cur.execute("SELECT id, id_producto, nombre, precio, factor FROM pos_producto_variantes WHERE id_producto = ANY(%s) AND COALESCE(activo,true)=true ORDER BY factor", (ids,))
            for v in fetchall_dict(cur):
                variantes_por_prod.setdefault(v['id_producto'], []).append(v)
        except Exception:
            conn.rollback()
        # Sabores de todos los productos en UNA consulta
        sabores_por_prod = {}
        try:
            cur.execute("SELECT id, id_producto, nombre FROM pos_producto_sabores WHERE id_producto = ANY(%s) AND COALESCE(activo,true)=true ORDER BY nombre", (ids,))
            for s in fetchall_dict(cur):
                sabores_por_prod.setdefault(s['id_producto'], []).append(s)
        except Exception:
            conn.rollback()
        for p in productos:
            p['variantes'] = variantes_por_prod.get(p['id'], [])
            p['sabores'] = sabores_por_prod.get(p['id'], [])
        return productos
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/productos")
def pos_crear_producto(p: PosProducto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_productos (id_local, nombre, precio, categoria, stock, stock_alerta) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p.id_local, p.nombre, p.precio, p.categoria, p.stock, p.stock_alerta))
        pid = cur.fetchone()[0]
        conn.commit()
        return {"id": pid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/productos/{id}/mapeo_fabrica")
def pos_mapeo_fabrica(id: int, data: dict = Body(...)):
    """Guarda el link entre un producto del local y su equivalente en fábrica."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        id_fab = data.get('id_producto_fabrica')
        upc = data.get('unidades_por_caja_local', 1)
        try:
            cur.execute("""UPDATE pos_productos
                           SET id_producto_fabrica=%s, unidades_por_caja_local=%s
                           WHERE id=%s""", (id_fab, upc, id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400,
                detail="Falta correr CREAR_MAPEO_PRODUCTO_LOCAL_FABRICA.sql en la base.")
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/productos/{id}")
def pos_actualizar_producto(id: int, p: PosProducto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET nombre=%s, precio=%s, categoria=%s, stock=%s, stock_alerta=%s WHERE id=%s",
                    (p.nombre, p.precio, p.categoria, p.stock, p.stock_alerta, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Sumar stock a un producto del local (reposición)
class PosSumarStock(BaseModel):
    cantidad: float
    motivo: Optional[str] = None

@app.post("/api/pos/productos/{id}/sumar_stock")
def pos_sumar_stock(id: int, data: PosSumarStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (data.cantidad, id))
        tipo = 'entrada' if data.cantidad >= 0 else 'salida'
        registrar_movimiento_stock(cur, id, data.cantidad, tipo, 'manual',
                                   motivo=getattr(data, 'motivo', None) or 'Carga manual de stock')
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pos/productos/{id}")
def pos_eliminar_producto(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- CAJA (por local) ----
@app.get("/api/pos/caja/estado")
def pos_estado_caja(id_local: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM pos_cajas WHERE id_local=%s AND estado='abierta' ORDER BY fecha_apertura DESC LIMIT 1", (id_local,))
        caja = cur.fetchone()
        if not caja:
            return {"caja_abierta": False}
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN metodo_pago='Transferencia' THEN total ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN metodo_pago='QR' THEN total ELSE 0 END),0) as qr,
                   COALESCE(SUM(total),0) as total, COUNT(*) as tickets
            FROM pos_ventas WHERE id_caja=%s
        """, (caja['id'],))
        resumen = cur.fetchone()
        return {"caja_abierta": True, **dict(caja), **dict(resumen)}
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/caja/abrir")
def pos_abrir_caja(data: PosAbrirCaja):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM pos_cajas WHERE id_local=%s AND estado='abierta'", (data.id_local,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ya hay una caja abierta en este local")
        # Impedir que el mismo usuario tenga otra caja abierta en otro local
        if data.id_usuario:
            try:
                cur.execute("SELECT pc.id, pl.nombre AS local FROM pos_cajas pc LEFT JOIN pos_locales pl ON pc.id_local=pl.id WHERE pc.id_usuario_apertura=%s AND pc.estado='abierta'", (data.id_usuario,))
                otra = cur.fetchone()
                if otra:
                    nombre_otro = otra[1] if not isinstance(otra, dict) else otra.get('local')
                    raise HTTPException(status_code=400, detail="Ya tenés una caja abierta en " + (nombre_otro or "otro local") + ". Cerrala antes de abrir otra.")
            except HTTPException:
                raise
            except Exception:
                conn.rollback()
        cur.execute("SELECT nombre FROM pos_locales WHERE id=%s", (data.id_local,))
        row = cur.fetchone()
        nombre_local = row[0] if row else None
        try:
            cur.execute("""
                INSERT INTO pos_cajas (id_local, nombre_local, nombre_responsable, monto_apertura, id_usuario_apertura)
                VALUES (%s,%s,%s,%s,%s) RETURNING id
            """, (data.id_local, nombre_local, data.nombre_responsable, data.monto_apertura, data.id_usuario))
        except Exception:
            conn.rollback()
            cur.execute("""
                INSERT INTO pos_cajas (id_local, nombre_local, nombre_responsable, monto_apertura)
                VALUES (%s,%s,%s,%s) RETURNING id
            """, (data.id_local, nombre_local, data.nombre_responsable, data.monto_apertura))
        cid = cur.fetchone()[0]
        conn.commit()
        return {"id_caja": cid}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/caja/{id_caja}/cerrar")
def pos_cerrar_caja(id_caja: int, data: PosCerrarCaja):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Verificar quién abrió la caja
        try:
            cur.execute("SELECT id_usuario_apertura FROM pos_cajas WHERE id=%s", (id_caja,))
            row = cur.fetchone()
            id_abrio = row['id_usuario_apertura'] if row else None
        except Exception:
            conn.rollback()
            id_abrio = None
        # Solo puede cerrar quien la abrió, o un admin
        if id_abrio is not None and not data.es_admin and data.id_usuario != id_abrio:
            raise HTTPException(status_code=403, detail="Solo puede cerrar esta caja el usuario que la abrió o un administrador.")
        t = _totales_por_metodo_caja(cur, id_caja)
        cur.execute("""
            UPDATE pos_cajas SET estado='cerrada', fecha_cierre=NOW(), monto_cierre=%s,
                total_efectivo=%s, total_tarjeta=%s, total_transferencia=%s, total_qr=%s, observaciones=%s
            WHERE id=%s
        """, (data.monto_cierre, t['efectivo'], t['tarjeta'], t['transferencia'], t['qr'], data.observaciones, id_caja))
        conn.commit()
        return {"status": "ok", **dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/caja/{id_caja}/cerrar_admin")
def cerrar_caja_admin(id_caja: int):
    """Cierre rápido de caja desde el panel admin: usa los totales registrados,
    sin contar efectivo. Pensado para cuando el cajero se fue sin cerrar."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, estado, monto_apertura FROM pos_cajas WHERE id=%s", (id_caja,))
        caja = cur.fetchone()
        if not caja:
            raise HTTPException(status_code=404, detail="Caja no encontrada")
        if caja['estado'] == 'cerrada':
            return {"status": "ya_cerrada"}
        t = _totales_por_metodo_caja(cur, id_caja)
        esperado = float(caja['monto_apertura'] or 0) + float(t['efectivo'] or 0)
        cur.execute("""
            UPDATE pos_cajas SET estado='cerrada', fecha_cierre=NOW(), monto_cierre=%s,
                total_efectivo=%s, total_tarjeta=%s, total_transferencia=%s, total_qr=%s,
                observaciones=COALESCE(observaciones,'') || ' [Cerrada por administrador]'
            WHERE id=%s
        """, (esperado, t['efectivo'], t['tarjeta'], t['transferencia'], t['qr'], id_caja))
        conn.commit()
        return {"status": "ok", **dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ---- VENTAS ----
def _totales_por_metodo_caja(cur, id_caja):
    """Devuelve dict con efectivo/tarjeta/transferencia/qr de una caja.
    Usa el desglose de pos_pagos_venta si existe; si no, cae al metodo_pago de la venta."""
    try:
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN p.metodo_pago='Efectivo' THEN p.monto ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN p.metodo_pago='Tarjeta' THEN p.monto ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN p.metodo_pago='Transferencia' THEN p.monto ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN p.metodo_pago='QR' THEN p.monto ELSE 0 END),0) as qr
            FROM pos_pagos_venta p JOIN pos_ventas v ON p.id_venta = v.id
            WHERE v.id_caja=%s
        """, (id_caja,))
        r = cur.fetchone()
        # r puede ser RealDict o tupla según el cursor
        if isinstance(r, dict):
            return r
        return {"efectivo": r[0], "tarjeta": r[1], "transferencia": r[2], "qr": r[3]}
    except Exception:
        # Fallback: tabla de pagos no existe, sumar por metodo_pago de la venta
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN metodo_pago='Transferencia' THEN total ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN metodo_pago='QR' THEN total ELSE 0 END),0) as qr
            FROM pos_ventas WHERE id_caja=%s
        """, (id_caja,))
        r = cur.fetchone()
        if isinstance(r, dict):
            return r
        return {"efectivo": r[0], "tarjeta": r[1], "transferencia": r[2], "qr": r[3]}

@app.post("/api/pos/ventas")
def pos_registrar_venta(venta: PosVenta):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # ANTI-DUPLICADO nivel 1: chequeo rápido por ref_unica
        if venta.ref_unica:
            try:
                cur.execute("SELECT id FROM pos_ventas WHERE ref_unica=%s LIMIT 1", (venta.ref_unica,))
                ya = cur.fetchone()
                if ya:
                    return {"id_venta": ya[0], "duplicada": True}
            except Exception:
                conn.rollback()
        # Determinar método a guardar en la venta: si hay varios pagos, "Mixto"
        pagos = venta.pagos or []
        pagos = [p for p in pagos if p.monto and p.monto > 0]
        metodo_guardar = venta.metodo_pago
        if len(pagos) > 1:
            metodo_guardar = "Mixto"
        elif len(pagos) == 1:
            metodo_guardar = pagos[0].metodo_pago
        # ANTI-DUPLICADO nivel 2: el INSERT puede fallar por la restricción UNIQUE
        # en ref_unica (si dos requests llegan casi simultáneos). En ese caso,
        # devolvemos la venta que sí se guardó en vez de crear otra.
        try:
            cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total, id_empleado, nombre_cajero, ref_unica) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (venta.id_caja, venta.id_local, metodo_guardar, venta.total, venta.id_empleado, venta.nombre_cajero, venta.ref_unica))
        except Exception as e_dup:
            conn.rollback()
            # ¿Fue por la restricción única? Buscar la venta existente y devolverla.
            if venta.ref_unica:
                try:
                    cur.execute("SELECT id FROM pos_ventas WHERE ref_unica=%s LIMIT 1", (venta.ref_unica,))
                    ya = cur.fetchone()
                    if ya:
                        return {"id_venta": ya[0], "duplicada": True}
                except Exception:
                    conn.rollback()
            # Si no fue por duplicado, intentar el INSERT sin ref_unica (compatibilidad)
            try:
                cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total, id_empleado, nombre_cajero) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                            (venta.id_caja, venta.id_local, metodo_guardar, venta.total, venta.id_empleado, venta.nombre_cajero))
            except Exception:
                conn.rollback()
                cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total) VALUES (%s,%s,%s,%s) RETURNING id",
                            (venta.id_caja, venta.id_local, metodo_guardar, venta.total))
        vid = cur.fetchone()[0]
        # Guardar el desglose de pagos (si la tabla existe). Si no hay desglose, registrar el único método.
        try:
            if pagos:
                for p in pagos:
                    cur.execute("INSERT INTO pos_pagos_venta (id_venta, metodo_pago, monto) VALUES (%s,%s,%s)",
                                (vid, p.metodo_pago, p.monto))
            else:
                cur.execute("INSERT INTO pos_pagos_venta (id_venta, metodo_pago, monto) VALUES (%s,%s,%s)",
                            (vid, venta.metodo_pago, venta.total))
        except Exception:
            conn.rollback()
            # Si la tabla no existe todavía, no rompemos: la venta ya quedó registrada en el reintento
            cur.execute("SELECT 1")
        for it in venta.detalle:
            cur.execute("INSERT INTO pos_detalle_ventas (id_venta, nombre_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (vid, it.nombre_producto, it.cantidad, it.precio_unitario))
            # Descontar stock del producto (si vino identificado).
            # unidades_stock = cantidad x factor de variante; si no vino, usa cantidad.
            if it.id_producto:
                baja = it.unidades_stock if it.unidades_stock is not None else it.cantidad
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) - %s WHERE id=%s", (baja, it.id_producto))
                registrar_movimiento_stock(cur, it.id_producto, -baja, 'salida', 'venta',
                                           motivo='Venta', id_local=venta.id_local)
        conn.commit()
        return {"id_venta": vid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/ventas/dia")
def pos_ventas_dia(id_caja: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, metodo_pago, total, fecha::text FROM pos_ventas WHERE id_caja=%s ORDER BY fecha DESC", (id_caja,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/reportes/caja/{id_caja}")
def pos_reporte_caja(id_caja: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        t = _totales_por_metodo_caja(cur, id_caja)
        cur.execute("SELECT COALESCE(SUM(total),0) as total, COUNT(*) as tickets FROM pos_ventas WHERE id_caja=%s", (id_caja,))
        tot = cur.fetchone()
        resumen = {"efectivo": t['efectivo'], "tarjeta": t['tarjeta'], "transferencia": t['transferencia'],
                   "qr": t['qr'], "total": tot['total'], "tickets": tot['tickets']}
        cur.execute("""
            SELECT d.nombre_producto, SUM(d.cantidad) as unidades, SUM(d.cantidad*d.precio_unitario) as total
            FROM pos_detalle_ventas d JOIN pos_ventas v ON d.id_venta=v.id
            WHERE v.id_caja=%s GROUP BY d.nombre_producto ORDER BY unidades DESC LIMIT 50
        """, (id_caja,))
        productos = fetchall_dict(cur)
        return {"resumen": dict(resumen), "productos": productos}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# IMPORTAR CLIENTES (distribuidores) en lote
# ==============================================================================
class ClienteImportar(BaseModel):
    razon_social: str
    dni: Optional[str] = None
    cuit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    provincia: Optional[str] = None
    cp: Optional[str] = None
    limite_credito: float = 0.0
    notas: Optional[str] = None

class ImportarClientes(BaseModel):
    clientes: List[ClienteImportar]

@app.post("/api/distribuidores/importar")
def importar_distribuidores(data: ImportarClientes):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # CUITs ya existentes para no duplicar
        cur.execute("SELECT cuit FROM distribuidores WHERE cuit IS NOT NULL AND cuit <> ''")
        existentes = set((r[0] or '').strip() for r in cur.fetchall())

        insertados = 0
        salteados = 0
        errores = []
        for i, c in enumerate(data.clientes, start=1):
            nombre = (c.razon_social or '').strip()
            if not nombre:
                salteados += 1
                continue
            cuit = (c.cuit or '').strip()
            if cuit and cuit in existentes:
                salteados += 1
                continue
            try:
                cur.execute("""
                    INSERT INTO distribuidores
                    (razon_social, dni, cuit, telefono, email, direccion, localidad, provincia, cp, limite_credito, notas, aprobado, activo)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, true, true)
                """, (nombre, c.dni, cuit or None, c.telefono, c.email, c.direccion,
                       c.localidad, c.provincia, c.cp, c.limite_credito or 0, c.notas))
                if cuit:
                    existentes.add(cuit)
                insertados += 1
            except Exception as e:
                conn.rollback()
                errores.append({"fila": i, "nombre": nombre, "error": str(e)})
                continue
        conn.commit()
        return {"insertados": insertados, "salteados": salteados, "errores": errores}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# SALDO INICIAL (deuda arrastrada del sistema anterior)
# ==============================================================================
class SaldoInicial(BaseModel):
    monto: float
    fecha: Optional[str] = None
    nota: Optional[str] = None

@app.post("/api/distribuidores/{id_dist}/saldo_inicial")
def cargar_saldo_inicial(id_dist: int, data: SaldoInicial):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Evitar duplicar: si ya tiene un pedido de saldo inicial, avisar
        cur.execute("""
            SELECT id FROM pedidos_b2b
            WHERE id_distribuidor=%s AND estado='Despachado'
              AND id IN (SELECT id_pedido FROM detalle_pedidos_b2b WHERE id_producto IS NULL)
        """, (id_dist,))
        # Insertar el pedido de saldo inicial (estado Despachado para que cuente en el saldo)
        if data.fecha:
            cur.execute("""
                INSERT INTO pedidos_b2b (id_distribuidor, total, estado, fecha, observaciones)
                VALUES (%s, %s, 'Despachado', %s, %s) RETURNING id
            """, (id_dist, data.monto, data.fecha, data.nota))
        else:
            cur.execute("""
                INSERT INTO pedidos_b2b (id_distribuidor, total, estado, observaciones)
                VALUES (%s, %s, 'Despachado', %s) RETURNING id
            """, (id_dist, data.monto, data.nota))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ASIGNAR ACCESO AL PORTAL (usuario y clave) a un distribuidor
# ==============================================================================
class AccesoDistribuidor(BaseModel):
    username: str
    password: str
    aprobar: bool = True

@app.put("/api/distribuidores/{id_dist}/acceso")
def asignar_acceso_distribuidor(id_dist: int, data: AccesoDistribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        usuario = (data.username or "").strip()
        if not usuario or not data.password:
            raise HTTPException(status_code=400, detail="Usuario y contraseña son obligatorios")
        # Verificar que el username no esté tomado por OTRO distribuidor
        cur.execute("SELECT id FROM distribuidores WHERE username = %s AND id <> %s", (usuario, id_dist))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso por otro cliente")
        hash_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        if data.aprobar:
            cur.execute("UPDATE distribuidores SET username=%s, password_hash=%s, aprobado=true WHERE id=%s",
                        (usuario, hash_pw, id_dist))
        else:
            cur.execute("UPDATE distribuidores SET username=%s, password_hash=%s WHERE id=%s",
                        (usuario, hash_pw, id_dist))
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores/{id_dist}/acceso")
def ver_acceso_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT username, (password_hash IS NOT NULL) AS tiene_clave, aprobado FROM distribuidores WHERE id=%s", (id_dist,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# DESCUENTOS POR CLIENTE + CATEGORÍA (solo B2B)
# ==============================================================================
class DescuentoItem(BaseModel):
    id_categoria: int
    porcentaje: float

class DescuentosUpdate(BaseModel):
    descuentos: List[DescuentoItem]

@app.get("/api/distribuidores/{id_dist}/descuentos")
def get_descuentos(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.id AS id_categoria, c.nombre AS categoria,
                   COALESCE(d.porcentaje, 0) AS porcentaje
            FROM categorias c
            LEFT JOIN descuentos_distribuidor d
              ON d.id_categoria = c.id AND d.id_distribuidor = %s
            WHERE COALESCE(c.activo, true) = true
            ORDER BY c.nombre
        """, (id_dist,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/{id_dist}/descuentos")
def guardar_descuentos(id_dist: int, data: DescuentosUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        for item in data.descuentos:
            pct = item.porcentaje or 0
            if pct <= 0:
                # Si es 0 o negativo, borramos el descuento (no aplica)
                cur.execute("DELETE FROM descuentos_distribuidor WHERE id_distribuidor=%s AND id_categoria=%s",
                            (id_dist, item.id_categoria))
            else:
                cur.execute("""
                    INSERT INTO descuentos_distribuidor (id_distribuidor, id_categoria, porcentaje)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (id_distribuidor, id_categoria)
                    DO UPDATE SET porcentaje = EXCLUDED.porcentaje
                """, (id_dist, item.id_categoria, pct))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Devuelve los productos con el precio YA ajustado por los descuentos del cliente
@app.get("/api/distribuidores/{id_dist}/precios")
def precios_para_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Mapa de descuentos del cliente por categoría
        cur.execute("SELECT id_categoria, porcentaje FROM descuentos_distribuidor WHERE id_distribuidor=%s", (id_dist,))
        desc = {r['id_categoria']: float(r['porcentaje']) for r in fetchall_dict(cur)}
        try:
            cur.execute("""
                SELECT id, sku, nombre, id_categoria, imagen_url,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true AND COALESCE(visible_mayorista, true) = true
                ORDER BY nombre ASC
            """)
        except Exception:
            conn.rollback()
            cur.execute("""
                SELECT id, sku, nombre, id_categoria, imagen_url,
                       COALESCE(precio_minorista,0) AS precio_minorista,
                       COALESCE(precio_mayorista,0) AS precio_mayorista
                FROM productos
                WHERE COALESCE(activo, true) = true
                ORDER BY nombre ASC
            """)
        productos = fetchall_dict(cur)
        for p in productos:
            base = float(p['precio_mayorista'] or 0)
            pct = desc.get(p['id_categoria'], 0)
            p['descuento'] = pct
            p['precio_base'] = base
            p['precio_final'] = round(base * (1 - pct/100.0), 2)
            # presentación virtual con el precio ya descontado
            p['presentaciones'] = [{
                'id': p['id'], 'nombre': 'Unidad', 'cantidad_unidades': 1,
                'precio_minorista': float(p['precio_minorista'] or 0),
                'precio_mayorista': p['precio_final']
            }]
        return productos
    finally:
        liberar_conexion(conn)

# ==============================================================================
# IMPORTAR INSUMOS en lote
# ==============================================================================
class InsumoImportar(BaseModel):
    nombre: str
    unidad_medida: str = "unidad"
    stock_minimo: float = 0.0
    presentacion_compra: Optional[str] = None
    cantidad_por_presentacion: float = 1.0
    costo_por_bulto: float = 0.0
    costo_unitario: float = 0.0

class ImportarInsumos(BaseModel):
    insumos: List[InsumoImportar]

@app.post("/api/insumos/importar")
def importar_insumos(data: ImportarInsumos):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LOWER(TRIM(nombre)) FROM insumos WHERE COALESCE(activo,true)=true")
        existentes = set(r[0] for r in cur.fetchall())
        insertados = 0; salteados = 0; errores = []
        for idx, it in enumerate(data.insumos, start=1):
            nombre = (it.nombre or '').strip()
            if not nombre:
                salteados += 1; continue
            if nombre.lower() in existentes:
                salteados += 1; continue
            try:
                cur.execute("""
                    INSERT INTO insumos (nombre, unidad_medida, stock_minimo, costo_unitario,
                        presentacion_compra, cantidad_por_presentacion, costo_por_bulto)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (nombre, it.unidad_medida or 'unidad', it.stock_minimo or 0, it.costo_unitario or 0,
                      it.presentacion_compra, it.cantidad_por_presentacion or 1, it.costo_por_bulto or 0))
                existentes.add(nombre.lower())
                insertados += 1
            except Exception as e:
                conn.rollback()
                errores.append({"fila": idx, "nombre": nombre, "error": str(e)})
                continue
        conn.commit()
        return {"insertados": insertados, "salteados": salteados, "errores": errores}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# IMPORTAR PROVEEDORES en lote
# ==============================================================================
class ProveedorImportar(BaseModel):
    razon_social: str
    cuit: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    notas: Optional[str] = None

class ImportarProveedores(BaseModel):
    proveedores: List[ProveedorImportar]

@app.post("/api/proveedores/importar")
def importar_proveedores(data: ImportarProveedores):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LOWER(TRIM(COALESCE(cuit,''))), LOWER(TRIM(razon_social)) FROM proveedores WHERE COALESCE(activo,true)=true")
        rows = cur.fetchall()
        cuits = set(r[0] for r in rows if r[0])
        nombres = set(r[1] for r in rows)
        insertados = 0; salteados = 0; errores = []
        for idx, p in enumerate(data.proveedores, start=1):
            nombre = (p.razon_social or '').strip()
            if not nombre:
                salteados += 1; continue
            cuit = (p.cuit or '').strip()
            if (cuit and cuit.lower() in cuits) or (nombre.lower() in nombres):
                salteados += 1; continue
            try:
                cur.execute("""
                    INSERT INTO proveedores (razon_social, cuit, email, telefono, direccion, notas)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (nombre, cuit or None, p.email, p.telefono, p.direccion, p.notas))
                if cuit: cuits.add(cuit.lower())
                nombres.add(nombre.lower())
                insertados += 1
            except Exception as e:
                conn.rollback()
                errores.append({"fila": idx, "nombre": nombre, "error": str(e)})
                continue
        conn.commit()
        return {"insertados": insertados, "salteados": salteados, "errores": errores}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# PANEL DE GASTOS GENERALES
# ==============================================================================
class GastoCategoria(BaseModel):
    nombre: str

class GastoCreate(BaseModel):
    id_categoria: Optional[int] = None
    concepto: str
    monto: float
    metodo: str = "Efectivo"
    id_empleado: Optional[int] = None
    fecha: Optional[str] = None
    notas: Optional[str] = None

class GastoRecurrente(BaseModel):
    id_categoria: Optional[int] = None
    concepto: str
    monto: float
    metodo: str = "Efectivo"
    dia_mes: int = 1

# ---- CATEGORÍAS ----
@app.get("/api/gastos/categorias")
def gastos_categorias():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre FROM gastos_categorias WHERE COALESCE(activo,true)=true ORDER BY nombre")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/gastos/categorias")
def gastos_crear_categoria(c: GastoCategoria):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO gastos_categorias (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (c.nombre,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/gastos/categorias/{id}")
def gastos_eliminar_categoria(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE gastos_categorias SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- GASTOS ----
class CuentaTesoreria(BaseModel):
    nombre: str
    tipo: str
    saldo_actual: float = 0
    orden: Optional[int] = 0

@app.get("/api/tesoreria/cuentas")
def tesoreria_listar():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tesoreria_cuentas WHERE activa=true ORDER BY orden, id")
        return fetchall_dict(cur)
    except Exception:
        conn.rollback()
        return []
    finally:
        liberar_conexion(conn)

@app.post("/api/tesoreria/cuentas")
def tesoreria_crear(c: CuentaTesoreria):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO tesoreria_cuentas (nombre, tipo, saldo_actual, orden) VALUES (%s,%s,%s,%s)",
                   (c.nombre, c.tipo, c.saldo_actual, c.orden))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/tesoreria/cuentas/{id}/saldo")
def tesoreria_actualizar_saldo(id: int, data: dict = Body(...)):
    """Actualiza el saldo manual de una cuenta."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tesoreria_cuentas SET saldo_actual=%s, ultima_actualizacion=NOW() WHERE id=%s",
                   (data.get('saldo', 0), id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/tesoreria/cuentas/{id}")
def tesoreria_editar(id: int, c: CuentaTesoreria):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tesoreria_cuentas SET nombre=%s, tipo=%s, orden=%s WHERE id=%s",
                   (c.nombre, c.tipo, c.orden, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/tesoreria/cuentas/{id}")
def tesoreria_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tesoreria_cuentas SET activa=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/tesoreria/movimientos_dia")
def tesoreria_movimientos_dia(fecha: Optional[str] = None):
    """Suma los movimientos del día por método de pago para cada tipo de cuenta."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        dia = fecha if fecha else None
        mov = {}

        # Ventas POS por método
        try:
            if dia:
                cur.execute("SELECT metodo_pago, SUM(total) AS total FROM pos_ventas WHERE fecha::date=%s GROUP BY metodo_pago", (dia,))
            else:
                cur.execute("SELECT metodo_pago, SUM(total) AS total FROM pos_ventas WHERE fecha::date=CURRENT_DATE GROUP BY metodo_pago")
            for r in fetchall_dict(cur):
                m = (r['metodo_pago'] or '').lower()
                mov[m] = mov.get(m, 0) + float(r['total'] or 0)
        except Exception:
            conn.rollback()

        # Cobros de distribuidores por método
        try:
            if dia:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM cobros_distribuidores WHERE fecha::date=%s GROUP BY metodo", (dia,))
            else:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM cobros_distribuidores WHERE fecha::date=CURRENT_DATE GROUP BY metodo")
            for r in fetchall_dict(cur):
                m = (r['metodo'] or '').lower()
                mov[m] = mov.get(m, 0) + float(r['total'] or 0)
        except Exception:
            conn.rollback()

        # Pagos a proveedores (egresos) por método
        try:
            if dia:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM pagos_proveedores WHERE fecha::date=%s GROUP BY metodo", (dia,))
            else:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM pagos_proveedores WHERE fecha::date=CURRENT_DATE GROUP BY metodo")
            for r in fetchall_dict(cur):
                m = (r['metodo'] or '').lower()
                mov[m] = mov.get(m, 0) - float(r['total'] or 0)  # egreso
        except Exception:
            conn.rollback()

        # Gastos (egresos) por método
        try:
            if dia:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM gastos WHERE fecha::date=%s GROUP BY metodo", (dia,))
            else:
                cur.execute("SELECT metodo, SUM(monto) AS total FROM gastos WHERE fecha::date=CURRENT_DATE GROUP BY metodo")
            for r in fetchall_dict(cur):
                m = (r['metodo'] or '').lower()
                mov[m] = mov.get(m, 0) - float(r['total'] or 0)  # egreso
        except Exception:
            conn.rollback()

        return mov
    finally:
        liberar_conexion(conn)

@app.get("/api/caja_diaria")
def caja_diaria(fecha: Optional[str] = None):
    """Resumen del día: ventas de locales + cobros de distribuidores + gastos."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        dia = fecha or "CURRENT_DATE"
        param_dia = fecha if fecha else None

        # Ventas por local del día
        if param_dia:
            cur.execute("""
                SELECT l.nombre AS local, v.metodo_pago, SUM(v.total) AS total, COUNT(*) AS tickets
                FROM pos_ventas v JOIN pos_locales l ON v.id_local=l.id
                WHERE v.fecha::date = %s GROUP BY l.nombre, v.metodo_pago ORDER BY l.nombre
            """, (param_dia,))
        else:
            cur.execute("""
                SELECT l.nombre AS local, v.metodo_pago, SUM(v.total) AS total, COUNT(*) AS tickets
                FROM pos_ventas v JOIN pos_locales l ON v.id_local=l.id
                WHERE v.fecha::date = CURRENT_DATE GROUP BY l.nombre, v.metodo_pago ORDER BY l.nombre
            """)
        ventas = fetchall_dict(cur)
        total_ventas = sum(float(r['total'] or 0) for r in ventas)

        # Cobros de distribuidores del día
        if param_dia:
            cur.execute("""
                SELECT d.razon_social AS distribuidor, c.metodo, c.monto, c.referencia
                FROM cobros_distribuidores c LEFT JOIN distribuidores d ON c.id_distribuidor=d.id
                WHERE c.fecha::date = %s ORDER BY c.fecha DESC
            """, (param_dia,))
        else:
            cur.execute("""
                SELECT d.razon_social AS distribuidor, c.metodo, c.monto, c.referencia
                FROM cobros_distribuidores c LEFT JOIN distribuidores d ON c.id_distribuidor=d.id
                WHERE c.fecha::date = CURRENT_DATE ORDER BY c.fecha DESC
            """)
        cobros = fetchall_dict(cur)
        total_cobros = sum(float(r['monto'] or 0) for r in cobros)

        # Gastos del día
        if param_dia:
            cur.execute("""
                SELECT g.concepto, g.monto, g.metodo, cat.nombre AS categoria
                FROM gastos g LEFT JOIN gastos_categorias cat ON g.id_categoria=cat.id
                WHERE g.fecha::date = %s ORDER BY g.fecha DESC
            """, (param_dia,))
        else:
            cur.execute("""
                SELECT g.concepto, g.monto, g.metodo, cat.nombre AS categoria
                FROM gastos g LEFT JOIN gastos_categorias cat ON g.id_categoria=cat.id
                WHERE g.fecha::date = CURRENT_DATE ORDER BY g.fecha DESC
            """)
        gastos = fetchall_dict(cur)
        total_gastos = sum(float(r['monto'] or 0) for r in gastos)

        return {
            "ventas": ventas, "total_ventas": total_ventas,
            "cobros": cobros, "total_cobros": total_cobros,
            "gastos": gastos, "total_gastos": total_gastos,
            "total_ingresos": total_ventas + total_cobros,
            "resultado_neto": total_ventas + total_cobros - total_gastos
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/gastos")
def gastos_listar(desde: Optional[str] = None, hasta: Optional[str] = None, id_categoria: Optional[int] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """
            SELECT g.id, g.concepto, g.monto, g.metodo, g.fecha::text, g.notas, g.id_categoria,
                   c.nombre AS categoria, g.id_empleado,
                   e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
            FROM gastos g
            LEFT JOIN gastos_categorias c ON g.id_categoria = c.id
            LEFT JOIN empleados e ON g.id_empleado = e.id
            WHERE COALESCE(g.activo,true)=true
        """
        params = []
        if desde: q += " AND g.fecha >= %s"; params.append(desde)
        if hasta: q += " AND g.fecha <= %s"; params.append(hasta)
        if id_categoria: q += " AND g.id_categoria = %s"; params.append(id_categoria)
        q += " ORDER BY g.fecha DESC, g.id DESC"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/gastos")
def gastos_crear(g: GastoCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if g.fecha:
            cur.execute("""
                INSERT INTO gastos (id_categoria, concepto, monto, metodo, id_empleado, fecha, notas)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (g.id_categoria, g.concepto, g.monto, g.metodo, g.id_empleado, g.fecha, g.notas))
        else:
            cur.execute("""
                INSERT INTO gastos (id_categoria, concepto, monto, metodo, id_empleado, notas)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (g.id_categoria, g.concepto, g.monto, g.metodo, g.id_empleado, g.notas))
        gid = cur.fetchone()[0]
        conn.commit()
        return {"id": gid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/gastos/{id}")
def gastos_editar(id: int, g: GastoCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE gastos SET id_categoria=%s, concepto=%s, monto=%s, metodo=%s, fecha=COALESCE(%s, fecha), notas=%s
            WHERE id=%s
        """, (g.id_categoria, g.concepto, g.monto, g.metodo, g.fecha, g.notas, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/gastos/{id}")
def gastos_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE gastos SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- RECURRENTES ----
@app.get("/api/gastos/recurrentes")
def gastos_recurrentes_listar():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT r.id, r.concepto, r.monto, r.metodo, r.dia_mes, r.id_categoria, c.nombre AS categoria
            FROM gastos_recurrentes r LEFT JOIN gastos_categorias c ON r.id_categoria=c.id
            WHERE COALESCE(r.activo,true)=true ORDER BY r.dia_mes
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/gastos/recurrentes")
def gastos_recurrentes_crear(r: GastoRecurrente):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gastos_recurrentes (id_categoria, concepto, monto, metodo, dia_mes)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (r.id_categoria, r.concepto, r.monto, r.metodo, r.dia_mes))
        rid = cur.fetchone()[0]
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/gastos/recurrentes/{id}")
def gastos_recurrentes_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE gastos_recurrentes SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# Genera los gastos del mes a partir de los recurrentes (no duplica si ya se generaron ese mes)
@app.post("/api/gastos/recurrentes/{id}/generar")
def gastos_recurrente_generar(id: int, mes: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM gastos_recurrentes WHERE id=%s AND COALESCE(activo,true)=true", (id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Recurrente no encontrado")
        import datetime
        hoy = datetime.date.today()
        anio = hoy.year; m = hoy.month
        if mes:
            partes = mes.split('-')
            anio = int(partes[0]); m = int(partes[1])
        dia = min(int(r['dia_mes'] or 1), 28)
        fecha = "%04d-%02d-%02d" % (anio, m, dia)
        # Evitar duplicado: mismo concepto y mes
        cur.execute("""
            SELECT id FROM gastos WHERE concepto=%s AND EXTRACT(YEAR FROM fecha)=%s AND EXTRACT(MONTH FROM fecha)=%s AND COALESCE(activo,true)=true
        """, (r['concepto'], anio, m))
        if cur.fetchone():
            return {"status": "ya_existe"}
        cur.execute("""
            INSERT INTO gastos (id_categoria, concepto, monto, metodo, fecha, notas)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (r['id_categoria'], r['concepto'], r['monto'], r['metodo'], fecha, 'Gasto recurrente generado'))
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ---- REPORTE ----
@app.get("/api/gastos/reporte")
def gastos_reporte(desde: str, hasta: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT COALESCE(SUM(monto),0) AS total, COUNT(*) AS cantidad
            FROM gastos WHERE COALESCE(activo,true)=true AND fecha>=%s AND fecha<=%s
        """, (desde, hasta))
        resumen = cur.fetchone()
        cur.execute("""
            SELECT COALESCE(c.nombre,'Sin categoría') AS categoria, SUM(g.monto) AS total, COUNT(*) AS cantidad
            FROM gastos g LEFT JOIN gastos_categorias c ON g.id_categoria=c.id
            WHERE COALESCE(g.activo,true)=true AND g.fecha>=%s AND g.fecha<=%s
            GROUP BY c.nombre ORDER BY total DESC
        """, (desde, hasta))
        por_categoria = fetchall_dict(cur)
        cur.execute("""
            SELECT metodo, SUM(monto) AS total, COUNT(*) AS cantidad
            FROM gastos WHERE COALESCE(activo,true)=true AND fecha>=%s AND fecha<=%s
            GROUP BY metodo ORDER BY total DESC
        """, (desde, hasta))
        por_metodo = fetchall_dict(cur)
        return {"resumen": dict(resumen), "por_categoria": por_categoria, "por_metodo": por_metodo}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# GESTIÓN DE LOCALES (panel admin): resumen, faltantes, gastos por local
# ==============================================================================

# ---- FALTANTES (el cajero marca qué falta) ----
class FaltanteCreate(BaseModel):
    id_local: int
    descripcion: str
    cantidad: Optional[str] = None
    id_empleado: Optional[int] = None

@app.get("/api/pos/faltantes")
def pos_faltantes_listar(id_local: Optional[int] = None, estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """
            SELECT f.id, f.id_local, l.nombre AS local, f.descripcion, f.cantidad,
                   f.estado, f.fecha::text, f.id_empleado,
                   e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
            FROM pos_faltantes f
            LEFT JOIN pos_locales l ON f.id_local = l.id
            LEFT JOIN empleados e ON f.id_empleado = e.id
            WHERE 1=1
        """
        params = []
        if id_local: q += " AND f.id_local=%s"; params.append(id_local)
        if estado: q += " AND f.estado=%s"; params.append(estado)
        q += " ORDER BY f.fecha DESC"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

class NovedadCreate(BaseModel):
    id_local: Optional[int] = None
    nombre_local: Optional[str] = None
    mensaje: str
    cargada_por: Optional[str] = None

@app.post("/api/pos/novedades")
def crear_novedad(n: NovedadCreate):
    if not n.mensaje or not n.mensaje.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO novedades_pos (id_local, nombre_local, mensaje, cargada_por) VALUES (%s,%s,%s,%s) RETURNING id",
                        (n.id_local, n.nombre_local, n.mensaje.strip(), n.cargada_por))
            nid = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_NOVEDADES.sql en la base.")
        # Notificación a la campanita
        try:
            crear_notificacion("novedad", "Novedad de " + (n.nombre_local or "un local"),
                               (n.cargada_por + ": " if n.cargada_por else "") + n.mensaje.strip()[:140])
        except Exception:
            pass
        return {"id": nid}
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/novedades")
def listar_novedades(id_local: Optional[int] = None, limit: int = 50):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            if id_local:
                cur.execute("SELECT id, id_local, nombre_local, mensaje, cargada_por, leida, fecha::text FROM novedades_pos WHERE id_local=%s ORDER BY id DESC LIMIT %s", (id_local, limit))
            else:
                cur.execute("SELECT id, id_local, nombre_local, mensaje, cargada_por, leida, fecha::text FROM novedades_pos ORDER BY id DESC LIMIT %s", (limit,))
            return fetchall_dict(cur)
        except Exception:
            conn.rollback()
            return []
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/novedades/{id}/leer")
def leer_novedad(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE novedades_pos SET leida=true WHERE id=%s", (id,))
            conn.commit()
        except Exception:
            conn.rollback()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/faltantes")
def pos_faltantes_crear(f: FaltanteCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_faltantes (id_local, descripcion, cantidad, id_empleado) VALUES (%s,%s,%s,%s) RETURNING id",
                    (f.id_local, f.descripcion, f.cantidad, f.id_empleado))
        fid = cur.fetchone()[0]
        conn.commit()
        try:
            crear_notificacion("faltante", "Cajero reportó un faltante",
                               (f.descripcion or "") + (" (x" + str(f.cantidad) + ")" if f.cantidad else ""))
        except Exception:
            pass
        return {"id": fid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/faltantes/{id}/resolver")
def pos_faltantes_resolver(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_faltantes SET estado='resuelto' WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/pos/faltantes/{id}")
def pos_faltantes_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pos_faltantes WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- GASTOS POR LOCAL (cajero carga -> pendiente -> admin aprueba) ----
class GastoLocalCreate(BaseModel):
    id_local: int
    concepto: str
    monto: float
    metodo: str = "Efectivo"
    id_empleado: Optional[int] = None
    notas: Optional[str] = None

@app.post("/api/pos/gastos")
def pos_gasto_crear(g: GastoLocalCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gastos (concepto, monto, metodo, id_empleado, notas, id_local, estado)
            VALUES (%s,%s,%s,%s,%s,%s,'pendiente') RETURNING id
        """, (g.concepto, g.monto, g.metodo, g.id_empleado, g.notas, g.id_local))
        gid = cur.fetchone()[0]
        conn.commit()
        return {"id": gid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/gastos")
def locales_gastos(id_local: Optional[int] = None, estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """
            SELECT g.id, g.concepto, g.monto, g.metodo, g.fecha::text, g.notas,
                   COALESCE(g.estado,'aprobado') AS estado, g.id_local, l.nombre AS local,
                   e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
            FROM gastos g
            LEFT JOIN pos_locales l ON g.id_local = l.id
            LEFT JOIN empleados e ON g.id_empleado = e.id
            WHERE COALESCE(g.activo,true)=true AND g.id_local IS NOT NULL
        """
        params = []
        if id_local: q += " AND g.id_local=%s"; params.append(id_local)
        if estado: q += " AND COALESCE(g.estado,'aprobado')=%s"; params.append(estado)
        q += " ORDER BY g.fecha DESC, g.id DESC"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/gastos/{id}/aprobar")
def locales_gasto_aprobar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE gastos SET estado='aprobado' WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/gastos/{id}/rechazar")
def locales_gasto_rechazar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE gastos SET estado='rechazado', activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- RESUMEN GENERAL DE LOCALES (para las tarjetas del panel) ----
@app.get("/api/locales/resumen")
def locales_resumen():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT id, nombre, direccion, punto_venta_afip FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
            locales = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, nombre, direccion FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
            locales = fetchall_dict(cur)
        salida = []
        for loc in locales:
            lid = loc['id']
            # Caja abierta?
            cur.execute("SELECT id, monto_apertura, nombre_responsable, fecha_apertura::text FROM pos_cajas WHERE id_local=%s AND estado='abierta' ORDER BY fecha_apertura DESC LIMIT 1", (lid,))
            caja = cur.fetchone()
            caja_abierta = bool(caja)
            efectivo_en_caja = 0
            id_caja = None
            responsable = None
            if caja:
                id_caja = caja['id']
                responsable = caja['nombre_responsable']
                cur.execute("SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) AS ef FROM pos_ventas WHERE id_caja=%s", (id_caja,))
                ef = cur.fetchone()['ef']
                efectivo_en_caja = float(caja['monto_apertura'] or 0) + float(ef or 0)
            # Ventas de hoy
            cur.execute("""SELECT COALESCE(SUM(total),0) AS total, COUNT(*) AS tickets
                           FROM pos_ventas WHERE id_local=%s AND fecha::date = CURRENT_DATE""", (lid,))
            hoy = cur.fetchone()
            # Ventas del mes
            cur.execute("""SELECT COALESCE(SUM(total),0) AS total, COUNT(*) AS tickets
                           FROM pos_ventas WHERE id_local=%s AND EXTRACT(YEAR FROM fecha)=EXTRACT(YEAR FROM CURRENT_DATE)
                           AND EXTRACT(MONTH FROM fecha)=EXTRACT(MONTH FROM CURRENT_DATE)""", (lid,))
            mes = cur.fetchone()
            # Faltantes pendientes
            cur.execute("SELECT COUNT(*) AS c FROM pos_faltantes WHERE id_local=%s AND estado='pendiente'", (lid,))
            faltantes = cur.fetchone()['c']
            # Gastos pendientes de aprobar
            cur.execute("SELECT COUNT(*) AS c FROM gastos WHERE id_local=%s AND COALESCE(estado,'aprobado')='pendiente' AND COALESCE(activo,true)=true", (lid,))
            gastos_pend = cur.fetchone()['c']
            # Productos con stock bajo
            cur.execute("SELECT COUNT(*) AS c FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true AND COALESCE(stock_alerta,0)>0 AND COALESCE(stock,0)<=COALESCE(stock_alerta,0)", (lid,))
            stock_bajo = cur.fetchone()['c']
            # Reposiciones pendientes
            repos_pend = 0
            try:
                cur.execute("SELECT COUNT(*) AS c FROM pos_reposiciones WHERE id_local=%s AND estado='pendiente'", (lid,))
                repos_pend = cur.fetchone()['c']
            except Exception:
                conn.rollback()
            salida.append({
                "id": lid, "nombre": loc['nombre'], "direccion": loc['direccion'],
                "punto_venta_afip": loc.get('punto_venta_afip'),
                "caja_abierta": caja_abierta, "id_caja": id_caja, "responsable": responsable,
                "efectivo_en_caja": efectivo_en_caja,
                "ventas_hoy": float(hoy['total'] or 0), "tickets_hoy": hoy['tickets'],
                "ventas_mes": float(mes['total'] or 0), "tickets_mes": mes['tickets'],
                "faltantes_pendientes": faltantes, "gastos_pendientes": gastos_pend, "stock_bajo": stock_bajo,
                "reposiciones_pendientes": repos_pend
            })
        return salida
    finally:
        liberar_conexion(conn)

# ---- DETALLE DE UN LOCAL: ventas con su detalle + más vendidos ----
@app.get("/api/locales/{id_local}/ventas")
def locales_ventas(id_local: int, desde: Optional[str] = None, hasta: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = "SELECT id, metodo_pago, total, fecha::text FROM pos_ventas WHERE id_local=%s"
        params = [id_local]
        if desde: q += " AND fecha::date >= %s"; params.append(desde)
        if hasta: q += " AND fecha::date <= %s"; params.append(hasta)
        q += " ORDER BY fecha DESC LIMIT 100"
        cur.execute(q, tuple(params))
        ventas = fetchall_dict(cur)
        if ventas:
            ids = [v['id'] for v in ventas]
            # Traer TODO el detalle en una sola consulta (mucho más rápido que una por venta)
            cur.execute("""SELECT id_venta, nombre_producto, cantidad, precio_unitario
                           FROM pos_detalle_ventas WHERE id_venta = ANY(%s)""", (ids,))
            detalles = fetchall_dict(cur)
            por_venta = {}
            for d in detalles:
                por_venta.setdefault(d['id_venta'], []).append(d)
            for v in ventas:
                v['detalle'] = por_venta.get(v['id'], [])
        return ventas
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/{id_local}/mas_vendidos")
def locales_mas_vendidos(id_local: int, desde: Optional[str] = None, hasta: Optional[str] = None, orden: Optional[str] = "unidades"):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """
            SELECT d.nombre_producto, SUM(d.cantidad) AS unidades, SUM(d.cantidad*d.precio_unitario) AS total
            FROM pos_detalle_ventas d JOIN pos_ventas v ON d.id_venta=v.id
            WHERE v.id_local=%s
        """
        params = [id_local]
        if desde: q += " AND v.fecha::date >= %s"; params.append(desde)
        if hasta: q += " AND v.fecha::date <= %s"; params.append(hasta)
        # Ordenar por plata (total) o por cantidad (unidades)
        col_orden = "total" if (orden == "total" or orden == "plata") else "unidades"
        q += f" GROUP BY d.nombre_producto ORDER BY {col_orden} DESC LIMIT 50"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ==============================================================================
# REPOSICIONES (el cajero pide stock de productos del local)
# ==============================================================================
class ReposicionItem(BaseModel):
    id_producto_fabrica: int           # producto del catálogo de fábrica
    nombre_producto: Optional[str] = None
    cantidad: float                    # cantidad pedida EN UNIDADES
    unidades_por_caja: Optional[float] = 1

class ReposicionCreate(BaseModel):
    id_local: int
    id_empleado: Optional[int] = None
    notas: Optional[str] = None
    detalle: List[ReposicionItem]

@app.post("/api/pos/reposiciones")
def pos_reposicion_crear(r: ReposicionCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_reposiciones (id_local, id_empleado, notas, estado) VALUES (%s,%s,%s,'habilitada') RETURNING id",
                    (r.id_local, r.id_empleado, r.notas))
        rid = cur.fetchone()[0]
        for it in r.detalle:
            cur.execute("""INSERT INTO pos_reposiciones_detalle
                           (id_reposicion, id_producto_fabrica, nombre_producto, cantidad, unidades_por_caja)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (rid, it.id_producto_fabrica, it.nombre_producto, it.cantidad, it.unidades_por_caja or 1))
        conn.commit()
        try:
            crear_notificacion("reposicion", "Nueva reposición de local", f"Local #{r.id_local} - {len(r.detalle)} productos")
        except Exception:
            pass
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Reemplaza el detalle de una reposición (admin edita: cantidades, quita, agrega)
class ReposicionEditar(BaseModel):
    detalle: List[ReposicionItem]
    notas: Optional[str] = None

@app.put("/api/locales/reposiciones/{id}")
def locales_reposicion_editar(id: int, data: ReposicionEditar):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Productos que quedan en la reposición nueva
        ids_nuevos = set(it.id_producto_fabrica for it in data.detalle)
        # Limpiar lo preparado de los productos QUITADOS (los que ya no están)
        try:
            cur.execute("SELECT id_producto_fabrica FROM preparacion_reposicion WHERE id_reposicion=%s", (id,))
            for row in cur.fetchall():
                if row[0] not in ids_nuevos:
                    cur.execute("DELETE FROM preparacion_reposicion WHERE id_reposicion=%s AND id_producto_fabrica=%s", (id, row[0]))
        except Exception:
            conn.rollback()
        # Reescribir el detalle. Lo preparado de los productos que SIGUEN se conserva
        # (preparacion_reposicion se indexa por id_producto_fabrica, no se toca).
        cur.execute("DELETE FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (id,))
        for it in data.detalle:
            cur.execute("""INSERT INTO pos_reposiciones_detalle
                           (id_reposicion, id_producto_fabrica, nombre_producto, cantidad, unidades_por_caja)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (id, it.id_producto_fabrica, it.nombre_producto, it.cantidad, it.unidades_por_caja or 1))
        if data.notas is not None:
            cur.execute("UPDATE pos_reposiciones SET notas=%s WHERE id=%s", (data.notas, id))
        # Si estaba 'armada', vuelve a 'en_preparacion' para que el empleado complete lo nuevo
        cur.execute("UPDATE pos_reposiciones SET estado='en_preparacion' WHERE id=%s AND estado='armada'", (id,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# LISTAR las reposiciones (esto es lo que usa el panel admin)
@app.get("/api/locales/reposiciones")
def locales_reposiciones(id_local: Optional[int] = None, estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """
            SELECT r.id, r.id_local, l.nombre AS local, r.estado, r.notas, r.fecha::text, r.id_empleado,
                   e.nombre AS empleado_nombre, e.apellido AS empleado_apellido
            FROM pos_reposiciones r
            LEFT JOIN pos_locales l ON r.id_local = l.id
            LEFT JOIN empleados e ON r.id_empleado = e.id
            WHERE 1=1
        """
        params = []
        if id_local: q += " AND r.id_local=%s"; params.append(id_local)
        if estado: q += " AND r.estado=%s"; params.append(estado)
        q += " ORDER BY r.fecha DESC"
        cur.execute(q, tuple(params))
        reps = fetchall_dict(cur)
        for rep in reps:
            cur.execute("""SELECT d.id_producto_fabrica, d.nombre_producto, d.cantidad,
                                  COALESCE(d.unidades_por_caja,1) AS unidades_por_caja,
                                  pf.nombre AS nombre_fabrica
                           FROM pos_reposiciones_detalle d
                           LEFT JOIN productos pf ON d.id_producto_fabrica = pf.id
                           WHERE d.id_reposicion=%s""", (rep['id'],))
            det = fetchall_dict(cur)
            # Lo armado por id_producto_fabrica
            preparado = {}
            try:
                cur.execute("SELECT id_producto_fabrica, cantidad FROM preparacion_reposicion WHERE id_reposicion=%s", (rep['id'],))
                for pr in fetchall_dict(cur):
                    if pr['id_producto_fabrica'] is not None:
                        preparado[pr['id_producto_fabrica']] = float(pr['cantidad'] or 0)
            except Exception:
                conn.rollback()
            hay_preparado = len(preparado) > 0
            for d in det:
                d['armado'] = preparado.get(d.get('id_producto_fabrica'), None) if hay_preparado else None
            rep['detalle'] = det
            rep['tiene_armado'] = hay_preparado
        return reps
    finally:
        liberar_conexion(conn)

# Marca la reposición como repuesta y suma el stock pedido a cada producto
@app.put("/api/locales/reposiciones/{id}/habilitar")
def locales_reposicion_habilitar(id: int):
    """Habilita una reposición para que aparezca en el panel de armado del empleado."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT estado FROM pos_reposiciones WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reposición no encontrada")
        if row['estado'] == 'repuesto':
            raise HTTPException(status_code=409, detail="Esta reposición ya fue repuesta")
        cur.execute("UPDATE pos_reposiciones SET estado='habilitada' WHERE id=%s", (id,))
        conn.commit()
        try:
            crear_notificacion("pedido", "Reposición habilitada para armado", "Reposición #" + str(id))
        except Exception:
            pass
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/reposiciones/{id}/despachar")
def locales_reposicion_despachar(id: int):
    """DESPACHAR: descuenta de FÁBRICA lo que el empleado realmente armó (en cajas).
    Usa id_producto_fabrica directo. Pasa la reposición a estado 'despachada'."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT estado, COALESCE(stock_descontado,false) AS desc FROM pos_reposiciones WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reposición no encontrada")
        if row['desc']:
            cur.execute("UPDATE pos_reposiciones SET estado='despachada' WHERE id=%s", (id,))
            conn.commit()
            return {"status": "ok", "nota": "Ya estaba descontado de fábrica"}

        # Traer lo ARMADO con su producto de fábrica y unidades por caja
        cur.execute("""SELECT pr.id_producto_fabrica, pr.cantidad,
                              COALESCE(pf.unidades_por_caja, 1) AS upc
                       FROM preparacion_reposicion pr
                       LEFT JOIN productos pf ON pr.id_producto_fabrica = pf.id
                       WHERE pr.id_reposicion=%s AND pr.id_producto_fabrica IS NOT NULL""", (id,))
        armado = fetchall_dict(cur)

        descontados = 0
        for a in armado:
            cant_unid = float(a['cantidad'] or 0)  # cantidad en unidades
            if cant_unid <= 0:
                continue
            upc = float(a['upc'] or 1) or 1
            cajas = cant_unid / upc  # convertir a cajas para descontar de fábrica
            cur.execute("UPDATE productos SET stock_actual = GREATEST(COALESCE(stock_actual,0) - %s, 0) WHERE id=%s",
                       (cajas, a['id_producto_fabrica']))
            descontados += 1

        cur.execute("UPDATE pos_reposiciones SET estado='despachada', stock_descontado=true WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok", "productos_descontados": descontados}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/reposiciones/{id}/reponer")
def locales_reposicion_reponer(id: int):
    """REPUESTO: suma al stock del LOCAL lo que el empleado armó.
    - Alfajores (categoría ALFAJORES en fábrica) → suman al producto local configurado
      para esa categoría (o 'ALFAJOR PDV UNIDAD' por defecto).
    - Otros productos → al producto local configurado para esa categoría.
    Pasa la reposición a estado 'repuesto'."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT estado, id_local FROM pos_reposiciones WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reposición no encontrada")
        if row['estado'] == 'repuesto':
            return {"status": "ya_repuesto"}
        id_local = row['id_local']

        # Config: categoría fábrica → nombre producto local
        config = {}
        try:
            cur.execute("SELECT id_categoria_fabrica, nombre_producto_local FROM reposicion_config_categoria WHERE activa=true")
            for c in fetchall_dict(cur):
                config[c['id_categoria_fabrica']] = c['nombre_producto_local']
        except Exception:
            conn.rollback()

        # Traer lo ARMADO con la categoría Y el nombre del producto de fábrica
        cur.execute("""SELECT pr.id_producto_fabrica, pr.cantidad,
                              pf.id_categoria, pf.nombre AS nombre_fabrica,
                              LOWER(COALESCE(cf.nombre,'')) AS cat_nombre
                       FROM preparacion_reposicion pr
                       LEFT JOIN productos pf ON pr.id_producto_fabrica = pf.id
                       LEFT JOIN categorias cf ON pf.id_categoria = cf.id
                       WHERE pr.id_reposicion=%s AND pr.id_producto_fabrica IS NOT NULL""", (id,))
        armado = fetchall_dict(cur)

        # Traer TODOS los productos del local una sola vez (para buscar por categoría/nombre)
        cur.execute("""SELECT id, nombre, LOWER(TRIM(COALESCE(categoria,''))) AS cat
                       FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true""", (id_local,))
        productos_local = fetchall_dict(cur)

        def palabras_comunes(a, b):
            """Cuenta palabras en común entre dos nombres (para medir parecido)."""
            sa = set(w for w in (a or '').lower().split() if len(w) > 2)
            sb = set(w for w in (b or '').lower().split() if len(w) > 2)
            return len(sa & sb)

        # Overrides manuales por producto (tienen prioridad sobre todo)
        overrides = {}
        try:
            cur.execute("SELECT id_producto_fabrica, id_producto_local FROM reposicion_override_producto WHERE id_local=%s", (id_local,))
            for o in fetchall_dict(cur):
                overrides[o['id_producto_fabrica']] = o['id_producto_local']
        except Exception:
            conn.rollback()

        sumados = 0
        no_mapeados = []
        for a in armado:
            cant_unid = float(a['cantidad'] or 0)  # en unidades
            if cant_unid <= 0:
                continue
            id_fab = a.get('id_producto_fabrica')
            id_cat = a.get('id_categoria')
            cat_nombre = (a.get('cat_nombre') or '').strip()
            nombre_fab = a.get('nombre_fabrica') or ''

            id_destino = None

            # ── PASO 0: Override manual por producto (máxima prioridad) ──
            if id_fab in overrides:
                # Verificar que ese producto del local exista
                if any(p['id'] == overrides[id_fab] for p in productos_local):
                    id_destino = overrides[id_fab]

            # ── PASO 1: Coincidencia por CATEGORÍA (fábrica BOMBAS = local BOMBAS) ──
            if not id_destino and cat_nombre:
                candidatos_cat = [p for p in productos_local if p['cat'] == cat_nombre]
                if len(candidatos_cat) == 1:
                    # Un solo producto en esa categoría → directo
                    id_destino = candidatos_cat[0]['id']
                elif len(candidatos_cat) > 1:
                    # Varios productos en la categoría → el de nombre más parecido al de fábrica
                    mejor = None; mejor_score = -1
                    for p in candidatos_cat:
                        sc = palabras_comunes(nombre_fab, p['nombre'])
                        if sc > mejor_score:
                            mejor_score = sc; mejor = p
                    id_destino = (mejor or candidatos_cat[0])['id']

            # ── PASO 2: Config manual (por si la categoría no coincide) ──
            if not id_destino and id_cat and id_cat in config:
                nombre_local = config[id_cat]
                p = next((x for x in productos_local if x['nombre'].lower().strip() == nombre_local.lower().strip()), None)
                if p: id_destino = p['id']

            # ── PASO 3: Default alfajores ──
            if not id_destino and 'alfajor' in cat_nombre:
                p = next((x for x in productos_local if x['nombre'].lower().strip() == 'alfajor pdv unidad'), None)
                if p: id_destino = p['id']

            # ── PASO 4: Búsqueda global por nombre parecido (último recurso) ──
            if not id_destino and nombre_fab:
                mejor = None; mejor_score = 0
                for p in productos_local:
                    sc = palabras_comunes(nombre_fab, p['nombre'])
                    if sc > mejor_score:
                        mejor_score = sc; mejor = p
                if mejor and mejor_score >= 1:
                    id_destino = mejor['id']

            if id_destino:
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (cant_unid, id_destino))
                sumados += 1
            else:
                no_mapeados.append(nombre_fab or cat_nombre or 'sin categoría')

        cur.execute("UPDATE pos_reposiciones SET estado='repuesto' WHERE id=%s", (id,))
        conn.commit()
        resultado = {"status": "ok", "productos_sumados": sumados}
        if no_mapeados:
            resultado["aviso"] = "Sin mapear (no se sumó): " + ", ".join(set(no_mapeados))
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/locales/reposiciones/{id}")
def locales_reposicion_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (id,))
        cur.execute("DELETE FROM pos_reposiciones WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# VARIANTES Y SABORES de productos del POS
# ==============================================================================
class VarianteModel(BaseModel):
    id_producto: int
    nombre: str
    precio: float = 0.0
    factor: float = 1.0

class SaborModel(BaseModel):
    id_producto: int
    nombre: str

@app.get("/api/pos/productos/{id_producto}/variantes")
def pos_variantes_listar(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre, precio, factor FROM pos_producto_variantes WHERE id_producto=%s AND COALESCE(activo,true)=true ORDER BY factor", (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/variantes")
def pos_variante_crear(v: VarianteModel):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_producto_variantes (id_producto, nombre, precio, factor) VALUES (%s,%s,%s,%s) RETURNING id",
                    (v.id_producto, v.nombre, v.precio, v.factor))
        vid = cur.fetchone()[0]
        conn.commit()
        return {"id": vid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/variantes/{id}")
def pos_variante_editar(id: int, v: VarianteModel):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_producto_variantes SET nombre=%s, precio=%s, factor=%s WHERE id=%s",
                    (v.nombre, v.precio, v.factor, id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pos/variantes/{id}")
def pos_variante_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_producto_variantes SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/productos/{id_producto}/sabores")
def pos_sabores_listar(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre FROM pos_producto_sabores WHERE id_producto=%s AND COALESCE(activo,true)=true ORDER BY nombre", (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/sabores")
def pos_sabor_crear(s: SaborModel):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_producto_sabores (id_producto, nombre) VALUES (%s,%s) RETURNING id",
                    (s.id_producto, s.nombre))
        sid = cur.fetchone()[0]
        conn.commit()
        return {"id": sid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pos/sabores/{id}")
def pos_sabor_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_producto_sabores SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# HISTORIAL DE STOCK + AJUSTE MANUAL + IMPORTAR PRODUCTOS (locales POS)
# ==============================================================================
@app.get("/api/pos/productos/{id_producto}/movimientos")
def pos_movimientos_producto(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, tipo, cantidad, stock_resultante, motivo, origen, fecha::text
            FROM pos_movimientos_stock
            WHERE id_producto=%s ORDER BY fecha DESC, id DESC LIMIT 200
        """, (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/{id_local}/movimientos")
def pos_movimientos_local(id_local: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT m.id, m.id_producto, p.nombre AS producto, m.tipo, m.cantidad,
                   m.stock_resultante, m.motivo, m.origen, m.fecha::text
            FROM pos_movimientos_stock m
            LEFT JOIN pos_productos p ON m.id_producto = p.id
            WHERE m.id_local=%s ORDER BY m.fecha DESC, m.id DESC LIMIT 300
        """, (id_local,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# Ajuste manual de stock (fija un valor o suma/resta) con motivo obligatorio
class AjusteStock(BaseModel):
    cantidad: float          # positiva suma, negativa resta
    motivo: str

@app.post("/api/pos/productos/{id}/ajustar_stock")
def pos_ajustar_stock(id: int, data: AjusteStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (data.cantidad, id))
        tipo = 'entrada' if data.cantidad >= 0 else 'salida'
        registrar_movimiento_stock(cur, id, data.cantidad, 'ajuste', 'ajuste', motivo=data.motivo)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# Importar productos en lote a UN local
class PosProductoImportar(BaseModel):
    nombre: str
    precio: float = 0.0
    categoria: Optional[str] = None
    stock: float = 0.0
    stock_alerta: float = 0.0

class ImportarPosProductos(BaseModel):
    id_local: int
    productos: List[PosProductoImportar]

@app.post("/api/pos/productos/importar")
def pos_importar_productos(data: ImportarPosProductos):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # nombres ya existentes en ese local (para no duplicar)
        cur.execute("SELECT LOWER(TRIM(nombre)) FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true", (data.id_local,))
        existentes = set(r[0] for r in cur.fetchall())
        insertados = 0; salteados = 0; errores = []
        for idx, p in enumerate(data.productos, start=1):
            nombre = (p.nombre or '').strip()
            if not nombre:
                salteados += 1; continue
            if nombre.lower() in existentes:
                salteados += 1; continue
            try:
                cur.execute("INSERT INTO pos_productos (id_local, nombre, precio, categoria, stock, stock_alerta) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                            (data.id_local, nombre, p.precio or 0, p.categoria, p.stock or 0, p.stock_alerta or 0))
                pid = cur.fetchone()[0]
                if (p.stock or 0) > 0:
                    registrar_movimiento_stock(cur, pid, p.stock, 'entrada', 'importacion', motivo='Carga inicial por importación', id_local=data.id_local)
                existentes.add(nombre.lower())
                insertados += 1
            except Exception as e:
                conn.rollback()
                errores.append({"fila": idx, "nombre": nombre, "error": str(e)})
                continue
        conn.commit()
        return {"insertados": insertados, "salteados": salteados, "errores": errores}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# STOCK CONSOLIDADO + CREAR PRODUCTO EN TODOS LOS LOCALES
# ==============================================================================
# Tabla comparativa: una fila por nombre de producto, stock por local + total
@app.get("/api/locales/stock_comparativo")
def locales_stock_comparativo():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
        locales = fetchall_dict(cur)
        cur.execute("""
            SELECT LOWER(TRIM(nombre)) AS clave, MAX(nombre) AS nombre, id_local, COALESCE(SUM(stock),0) AS stock
            FROM pos_productos
            WHERE COALESCE(activo,true)=true
            GROUP BY LOWER(TRIM(nombre)), id_local
        """)
        filas = fetchall_dict(cur)
        # Armar mapa producto -> {id_local: stock}
        productos = {}
        for f in filas:
            clave = f['clave']
            if clave not in productos:
                productos[clave] = {"nombre": f['nombre'], "por_local": {}, "total": 0}
            productos[clave]["por_local"][f['id_local']] = float(f['stock'] or 0)
            productos[clave]["total"] += float(f['stock'] or 0)
        salida = []
        for clave in sorted(productos.keys()):
            p = productos[clave]
            salida.append({
                "nombre": p["nombre"],
                "stock_por_local": [{"id_local": l['id'], "local": l['nombre'], "stock": p["por_local"].get(l['id'], None)} for l in locales],
                "total": p["total"]
            })
        return {"locales": locales, "productos": salida}
    finally:
        liberar_conexion(conn)

# Crear un producto en TODOS los locales activos de una sola vez
class ProductoGlobal(BaseModel):
    nombre: str
    precio: float = 0.0
    categoria: Optional[str] = None
    stock: float = 0.0
    stock_alerta: float = 0.0

@app.post("/api/locales/productos_global")
def crear_producto_global(p: ProductoGlobal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM pos_locales WHERE COALESCE(activo,true)=true")
        locales = [r[0] for r in cur.fetchall()]
        if not locales:
            raise HTTPException(status_code=400, detail="No hay locales activos")
        creados = 0; salteados = 0
        nombre = (p.nombre or '').strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")
        for lid in locales:
            # no duplicar por nombre en el mismo local
            cur.execute("SELECT id FROM pos_productos WHERE id_local=%s AND LOWER(TRIM(nombre))=LOWER(TRIM(%s)) AND COALESCE(activo,true)=true", (lid, nombre))
            if cur.fetchone():
                salteados += 1
                continue
            cur.execute("INSERT INTO pos_productos (id_local, nombre, precio, categoria, stock, stock_alerta) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (lid, nombre, p.precio or 0, p.categoria, p.stock or 0, p.stock_alerta or 0))
            pid = cur.fetchone()[0]
            if (p.stock or 0) > 0:
                registrar_movimiento_stock(cur, pid, p.stock, 'entrada', 'manual', motivo='Alta de producto', id_local=lid)
            creados += 1
        conn.commit()
        return {"creados": creados, "salteados": salteados, "total_locales": len(locales)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# MERCADO PAGO (pago online de pedidos B2B por distribuidores)
# ==============================================================================
try:
    import mp_service
except Exception:
    mp_service = None

@app.get("/api/mp/estado")
def mp_estado():
    return {"configurado": bool(mp_service and mp_service.configurado())}

class PagoLibre(BaseModel):
    id_distribuidor: int
    monto: float

@app.post("/api/mp/crear_pago_libre")
def mp_crear_pago_libre(data: PagoLibre, request: Request):
    if not mp_service or not mp_service.configurado():
        raise HTTPException(status_code=400, detail="Mercado Pago no está configurado (falta MP_ACCESS_TOKEN).")
    if data.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Datos del distribuidor
        try:
            cur.execute("SELECT id, razon_social, email FROM distribuidores WHERE id=%s", (data.id_distribuidor,))
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, razon_social, NULL AS email FROM distribuidores WHERE id=%s", (data.id_distribuidor,))
        dist = cur.fetchone()
        if not dist:
            raise HTTPException(status_code=404, detail="Distribuidor no encontrado")
        # Calcular deuda actual (pedidos despachados - cobros)
        cur.execute("SELECT COALESCE(SUM(total),0) AS t FROM pedidos_b2b WHERE id_distribuidor=%s AND estado='Despachado'", (data.id_distribuidor,))
        total_ped = float(cur.fetchone()['t'] or 0)
        cur.execute("SELECT COALESCE(SUM(monto),0) AS t FROM cobros_distribuidores WHERE id_distribuidor=%s", (data.id_distribuidor,))
        total_cob = float(cur.fetchone()['t'] or 0)
        deuda = round(total_ped - total_cob, 2)
        if deuda <= 0:
            raise HTTPException(status_code=400, detail="No tenés deuda pendiente para pagar.")
        if data.monto > deuda + 0.5:
            raise HTTPException(status_code=400, detail="El monto supera tu deuda actual ($" + str(deuda) + ").")
        base_url = str(request.base_url).rstrip("/")
        import uuid as _uuid
        ref_unica = "distpago-" + str(data.id_distribuidor) + "-" + _uuid.uuid4().hex[:12]
        try:
            pref = mp_service.crear_preferencia(
                titulo="Pago a cuenta - Portal del Viento",
                monto=data.monto,
                referencia_externa=ref_unica,
                base_url=base_url,
                payer_email=dist.get('email')
            )
        except Exception as e:
            msg = str(e)
            if msg.startswith("HTTP "):
                raise HTTPException(status_code=502, detail="Mercado Pago respondió: " + msg)
            raise HTTPException(status_code=502, detail="Mercado Pago: " + msg)
        link = pref.get("init_point") or pref.get("sandbox_init_point")
        # Guardar la preferencia + su referencia única para reconciliar el pago después.
        guardado_ok = False
        guardado_error = None
        conn2 = obtener_conexion()
        try:
            cur2 = conn2.cursor()
            try:
                cur2.execute("""INSERT INTO mp_preferencias (preference_id, id_distribuidor, id_pedido, monto, tipo, referencia)
                               VALUES (%s,%s,NULL,%s,'libre',%s)
                               ON CONFLICT (preference_id) DO NOTHING""",
                            (str(pref.get("id")), data.id_distribuidor, data.monto, ref_unica))
            except Exception:
                conn2.rollback()
                # Fallback si la columna referencia no existe todavía
                cur2.execute("""INSERT INTO mp_preferencias (preference_id, id_distribuidor, id_pedido, monto, tipo)
                               VALUES (%s,%s,NULL,%s,'libre')
                               ON CONFLICT (preference_id) DO NOTHING""",
                            (str(pref.get("id")), data.id_distribuidor, data.monto))
            conn2.commit()
            guardado_ok = True
        except Exception as e2:
            conn2.rollback()
            guardado_error = str(e2)[:200]
        finally:
            liberar_conexion(conn2)
        return {"link": link, "preference_id": pref.get("id"),
                "preferencia_guardada": guardado_ok, "guardado_error": guardado_error}
    finally:
        liberar_conexion(conn)

@app.post("/api/mp/crear_pago/{id_pedido}")
def mp_crear_pago(id_pedido: int, request: Request):
    if not mp_service or not mp_service.configurado():
        raise HTTPException(status_code=400, detail="Mercado Pago no está configurado (falta MP_ACCESS_TOKEN).")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""SELECT p.id, p.total, p.estado, p.id_distribuidor,
                                  d.razon_social AS dist_nombre, d.email AS dist_email
                           FROM pedidos_b2b p LEFT JOIN distribuidores d ON p.id_distribuidor=d.id
                           WHERE p.id=%s""", (id_pedido,))
            pedido = cur.fetchone()
        except Exception:
            conn.rollback()
            # Fallback: sin email (por si la columna no existe)
            try:
                cur.execute("""SELECT p.id, p.total, p.estado, p.id_distribuidor,
                                      d.razon_social AS dist_nombre, NULL AS dist_email
                               FROM pedidos_b2b p LEFT JOIN distribuidores d ON p.id_distribuidor=d.id
                               WHERE p.id=%s""", (id_pedido,))
                pedido = cur.fetchone()
            except Exception:
                conn.rollback()
                # Último fallback: solo el pedido
                cur.execute("SELECT id, total, estado, id_distribuidor, NULL AS dist_nombre, NULL AS dist_email FROM pedidos_b2b WHERE id=%s", (id_pedido,))
                pedido = cur.fetchone()
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        # Evitar cobrar dos veces: ¿ya tiene cobro registrado?
        cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE id_pedido=%s", (id_pedido,))
        if cur.fetchone()['c'] > 0:
            raise HTTPException(status_code=400, detail="Este pedido ya tiene un cobro registrado.")
        total = float(pedido['total'] or 0)
        if total <= 0:
            raise HTTPException(status_code=400, detail="El pedido no tiene un total válido.")
        # base_url a partir del request
        base_url = str(request.base_url).rstrip("/")
        try:
            pref = mp_service.crear_preferencia(
                titulo="Pedido #" + str(id_pedido) + " - Portal del Viento",
                monto=total,
                referencia_externa="pedido-" + str(id_pedido),
                base_url=base_url,
                payer_email=pedido.get('dist_email')
            )
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            # Si viene el detalle crudo de MP (HTTP ...), lo mostramos tal cual para diagnosticar
            if msg.startswith("HTTP "):
                raise HTTPException(status_code=502, detail="Mercado Pago respondió: " + msg)
            if 'timeout' in low or 'timed out' in low:
                detalle = "El servidor no pudo conectarse a Mercado Pago a tiempo (timeout)."
            elif 'connection' in low or 'resolve' in low or 'failed to establish' in low:
                detalle = "El servidor no logró alcanzar a Mercado Pago (conexión/dominio)."
            else:
                detalle = msg
            raise HTTPException(status_code=502, detail="Mercado Pago: " + detalle)
        # Link: en producción init_point; si usás credenciales de prueba, sandbox_init_point
        link = pref.get("init_point") or pref.get("sandbox_init_point")
        return {"link": link, "preference_id": pref.get("id")}
    finally:
        liberar_conexion(conn)

@app.post("/api/mp/webhook")
async def mp_webhook(request: Request):
    """Mercado Pago llama acá cuando cambia el estado de un pago.
    Si el pago está aprobado, registramos el cobro del pedido (si no existía)."""
    if not mp_service:
        return {"status": "sin_mp"}
    try:
        # MP manda el id del pago por query (?id=...&topic=payment) o en el body
        payment_id = request.query_params.get("id") or request.query_params.get("data.id")
        if not payment_id:
            try:
                body = await request.json()
                payment_id = (body.get("data") or {}).get("id") or body.get("id")
            except Exception:
                payment_id = None
        if not payment_id:
            return {"status": "sin_id"}
        info = mp_service.consultar_pago(payment_id)
        if info.get("estado") != "approved":
            return {"status": "no_aprobado"}
        ext = info.get("external_reference") or ""
        monto = float(info.get("monto") or 0)
        payment_id_str = str(payment_id)
        conn = obtener_conexion()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Evitar duplicar: ¿ya registramos este pago de MP?
            try:
                cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE referencia=%s", (payment_id_str,))
                if cur.fetchone()['c'] > 0:
                    return {"status": "ya_registrado"}
            except Exception:
                conn.rollback()

            if ext.startswith("pedido-"):
                id_pedido = int(ext.split("-")[1])
                cur.execute("SELECT id_distribuidor FROM pedidos_b2b WHERE id=%s", (id_pedido,))
                ped = cur.fetchone()
                if not ped:
                    return {"status": "pedido_inexistente"}
                cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE id_pedido=%s", (id_pedido,))
                if cur.fetchone()['c'] == 0:
                    cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                                   VALUES (%s,%s,%s,%s,%s,%s)""",
                                (ped['id_distribuidor'], id_pedido, monto, 'Mercado Pago', payment_id_str, 'Pago online aprobado'))
                    conn.commit()
                return {"status": "ok"}

            elif ext.startswith("distpago-"):
                id_dist = int(ext.split("-")[1])
                # Pago a cuenta (sin pedido puntual)
                cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                               VALUES (%s,NULL,%s,%s,%s,%s)""",
                            (id_dist, monto, 'Mercado Pago', payment_id_str, 'Pago a cuenta online aprobado'))
                conn.commit()
                return {"status": "ok"}
            else:
                return {"status": "ref_desconocida"}
        finally:
            liberar_conexion(conn)
    except Exception as e:
        # Nunca devolvemos error a MP para que no reintente infinito por un bug nuestro
        return {"status": "error", "detail": str(e)[:200]}

@app.post("/api/mp/sincronizar_todos")
def mp_sincronizar_todos():
    """Verifica TODAS las preferencias pendientes (de todos los distribuidores) y registra
    los pagos aprobados que falten. Se llama al abrir el panel o con el botón Sincronizar."""
    if not mp_service or not mp_service.configurado():
        return {"status": "mp_no_configurado", "registrados": 0}
    registrados = 0
    detalle = []
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT preference_id, id_distribuidor, monto, referencia FROM mp_preferencias WHERE COALESCE(estado,'pendiente')<>'pagada' AND referencia IS NOT NULL")
            prefs = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            return {"status": "sin_tabla", "registrados": 0}
        for pref in prefs:
            ref = pref.get('referencia')
            if not ref:
                continue
            try:
                pagos = mp_service.buscar_pagos_por_referencia(ref)
            except Exception:
                continue
            for p in pagos:
                if p.get("estado") != "approved":
                    continue
                pid = str(p.get("id"))
                cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE referencia=%s", (pid,))
                if cur.fetchone()['c'] > 0:
                    continue
                cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                               VALUES (%s,NULL,%s,%s,%s,%s)""",
                            (pref['id_distribuidor'], float(p.get("monto") or 0), 'Mercado Pago', pid, 'Pago a cuenta online'))
                cur.execute("UPDATE mp_preferencias SET estado='pagada' WHERE preference_id=%s", (pref['preference_id'],))
                conn.commit()
                registrados += 1
                detalle.append({"distribuidor": pref['id_distribuidor'], "monto": float(p.get("monto") or 0)})
                try:
                    crear_notificacion("pago", "Pago online de distribuidor (Mercado Pago)",
                                       "$" + str(float(p.get("monto") or 0)))
                except Exception:
                    pass
        return {"status": "ok", "registrados": registrados, "detalle": detalle}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "detail": str(e)[:200], "registrados": registrados}
    finally:
        liberar_conexion(conn)

@app.get("/api/mp/diagnostico_general")
def mp_diagnostico_general():
    """Muestra TODAS las preferencias guardadas (de cualquier distribuidor) y los cobros MP registrados."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        out = {}
        try:
            cur.execute("SELECT preference_id, id_distribuidor, monto, tipo, estado, creada::text FROM mp_preferencias ORDER BY creada DESC LIMIT 20")
            out["preferencias_totales"] = fetchall_dict(cur)
        except Exception as e:
            conn.rollback()
            out["error_tabla_preferencias"] = str(e)[:200]
        try:
            cur.execute("SELECT id, id_distribuidor, id_pedido, monto, metodo, referencia, fecha::text FROM cobros_distribuidores WHERE metodo='Mercado Pago' ORDER BY id DESC LIMIT 20")
            out["cobros_mp"] = fetchall_dict(cur)
        except Exception as e:
            conn.rollback()
            out["error_cobros"] = str(e)[:200]
        return out
    finally:
        liberar_conexion(conn)

@app.get("/api/mp/diagnostico/{id_distribuidor}")
def mp_diagnostico(id_distribuidor: int):
    """Diagnóstico: muestra las preferencias del distribuidor y los pagos que MP asocia a cada una."""
    if not mp_service or not mp_service.configurado():
        return {"error": "Mercado Pago no configurado (falta MP_ACCESS_TOKEN)"}
    out = {"id_distribuidor": id_distribuidor}
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT preference_id, monto, tipo, estado, referencia, creada::text FROM mp_preferencias WHERE id_distribuidor=%s ORDER BY creada DESC", (id_distribuidor,))
            prefs = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            out["error"] = "Falta crear la tabla mp_preferencias o la columna referencia (corré CREAR_MP_PREFERENCIAS.sql)."
            return out
        out["preferencias"] = prefs
        detalle = []
        registrados_ahora = 0
        for pref in prefs:
            item = {"preference_id": pref['preference_id'], "estado_pref": pref['estado'], "referencia": pref.get('referencia')}
            ref = pref.get('referencia')
            if ref:
                try:
                    pagos = mp_service.buscar_pagos_por_referencia(ref)
                    item["pagos"] = pagos
                    # Registrar los aprobados que falten
                    for p in pagos:
                        if p.get("estado") != "approved":
                            continue
                        pid = str(p.get("id"))
                        cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE referencia=%s", (pid,))
                        if cur.fetchone()['c'] > 0:
                            item["registro"] = "ya estaba registrado"
                            continue
                        cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                                       VALUES (%s,NULL,%s,%s,%s,%s)""",
                                    (id_distribuidor, float(p.get("monto") or 0), 'Mercado Pago', pid, 'Pago a cuenta online'))
                        cur.execute("UPDATE mp_preferencias SET estado='pagada' WHERE preference_id=%s", (pref['preference_id'],))
                        conn.commit()
                        registrados_ahora += 1
                        item["registro"] = "REGISTRADO ahora"
                except Exception as e:
                    conn.rollback()
                    item["error"] = str(e)[:200]
            else:
                item["nota"] = "preferencia vieja sin referencia (creada antes de la corrección)"
            detalle.append(item)
        out["detalle_pagos"] = detalle
        out["registrados_ahora"] = registrados_ahora
        return out
    finally:
        liberar_conexion(conn)

@app.post("/api/mp/verificar_pagos/{id_distribuidor}")
def mp_verificar_pagos(id_distribuidor: int):
    """Consulta a MP los pagos de las preferencias de este distribuidor y registra
    los aprobados que falten. Respaldo confiable del webhook."""
    if not mp_service or not mp_service.configurado():
        raise HTTPException(status_code=400, detail="Mercado Pago no está configurado.")
    registrados = 0
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Preferencias de este distribuidor que todavía no se confirmaron
        try:
            cur.execute("SELECT preference_id, monto, referencia FROM mp_preferencias WHERE id_distribuidor=%s AND COALESCE(estado,'pendiente')<>'pagada'", (id_distribuidor,))
            prefs = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            prefs = []
        for pref in prefs:
            ref = pref.get('referencia')
            if not ref:
                continue
            try:
                pagos = mp_service.buscar_pagos_por_referencia(ref)
            except Exception:
                continue
            for p in pagos:
                if p.get("estado") != "approved":
                    continue
                pid = str(p.get("id"))
                cur.execute("SELECT COUNT(*) AS c FROM cobros_distribuidores WHERE referencia=%s", (pid,))
                if cur.fetchone()['c'] > 0:
                    continue
                cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                               VALUES (%s,NULL,%s,%s,%s,%s)""",
                            (id_distribuidor, float(p.get("monto") or 0), 'Mercado Pago', pid, 'Pago a cuenta online (verificado)'))
                registrados += 1
                # Marcar la preferencia como pagada
                try:
                    cur.execute("UPDATE mp_preferencias SET estado='pagada' WHERE preference_id=%s", (pref['preference_id'],))
                except Exception:
                    conn.rollback()
        conn.commit()
        return {"status": "ok", "registrados": registrados}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# FACTURACIÓN ELECTRÓNICA AFIP / ARCA
# ==============================================================================
try:
    import afip_service
except Exception:
    afip_service = None

class FacturaAfip(BaseModel):
    id_venta: Optional[int] = None
    id_local: Optional[int] = None
    tipo_comprobante: int = 6      # 6=Factura B (consumidor final), 1=Factura A, 11=Factura C
    doc_tipo: int = 99             # 99=consumidor final, 80=CUIT, 96=DNI
    doc_nro: Optional[str] = None
    total: float = 0.0
    # Si no mandan neto/iva, se calculan asumiendo IVA 21% incluido en el total
    neto: Optional[float] = None
    iva: Optional[float] = None

@app.get("/api/afip/estado")
def afip_estado():
    if not afip_service:
        return {"disponible": False, "error": "El módulo afip_service no está cargado en el servidor."}
    try:
        return {"disponible": True, **afip_service.estado_servidores()}
    except Exception as e:
        return {"disponible": False, "error": str(e)}

@app.post("/api/afip/facturar")
def afip_facturar(f: FacturaAfip):
    if not afip_service:
        raise HTTPException(status_code=500, detail="Módulo AFIP no disponible en el servidor.")
    # Calcular neto/iva si no vinieron (IVA 21% incluido en el total)
    total = round(float(f.total or 0), 2)
    if f.neto is not None and f.iva is not None:
        neto = round(float(f.neto), 2); iva = round(float(f.iva), 2)
    elif f.tipo_comprobante == 11:  # Factura C no discrimina IVA
        neto = total; iva = 0.0
    else:
        neto = round(total / 1.21, 2); iva = round(total - neto, 2)

    try:
        # Punto de venta del local (si está configurado); si no, usa el de la variable de entorno
        pv_local = None
        if f.id_local:
            try:
                conn0 = obtener_conexion(); cur0 = conn0.cursor(cursor_factory=RealDictCursor)
                cur0.execute("SELECT punto_venta_afip FROM pos_locales WHERE id=%s", (f.id_local,))
                row0 = cur0.fetchone()
                if row0 and row0.get('punto_venta_afip'):
                    pv_local = int(row0['punto_venta_afip'])
                liberar_conexion(conn0)
            except Exception:
                pv_local = None
        # Condición IVA del receptor: Factura A -> Responsable Inscripto (1); resto -> Consumidor Final (5)
        cond_iva = 1 if f.tipo_comprobante == 1 else 5
        r = afip_service.emitir_factura(
            tipo_cbte=f.tipo_comprobante, doc_tipo=f.doc_tipo, doc_nro=f.doc_nro or "",
            neto=neto, iva=iva, total=total, cond_iva_receptor=cond_iva, punto_venta=pv_local
        )
    except Exception as e:
        # Guardar el intento fallido
        try:
            conn = obtener_conexion(); cur = conn.cursor()
            cur.execute("""INSERT INTO afip_facturas (id_venta, id_local, punto_venta, tipo_comprobante, numero, doc_tipo, doc_nro, neto, iva, total, estado, error_detalle)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'error',%s)""",
                        (f.id_venta, f.id_local, 0, f.tipo_comprobante, 0, f.doc_tipo, f.doc_nro, neto, iva, total, str(e)))
            conn.commit(); liberar_conexion(conn)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"AFIP rechazó o falló: {e}")

    # Guardar la factura emitida
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO afip_facturas (id_venta, id_local, punto_venta, tipo_comprobante, numero, doc_tipo, doc_nro, neto, iva, total, cae, cae_vto, estado, entorno)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'emitida',%s) RETURNING id""",
                    (f.id_venta, f.id_local, r["punto_venta"], r["tipo_comprobante"], r["numero"],
                     f.doc_tipo, f.doc_nro, neto, iva, total, r["cae"], r["cae_vto"], r["entorno"]))
        fid = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Factura emitida en AFIP pero error al guardar: {e}")
    finally:
        liberar_conexion(conn)

    return {"status": "ok", "id": fid, **r, "neto": neto, "iva": iva, "total": total}

@app.get("/resultados")
def route_resultados():
    return serve_html("resultados.html")

@app.get("/api/resultados")
def estado_resultados(desde: Optional[str] = None, hasta: Optional[str] = None):
    """Estado de resultados: ingresos - egresos = resultado neto."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        rango = []
        cond = " WHERE 1=1"
        if desde: cond += " AND fecha::date >= %s"; rango.append(desde)
        if hasta: cond += " AND fecha::date <= %s"; rango.append(hasta)

        # 1) Ventas locales
        try:
            cur.execute("SELECT l.nombre AS local, SUM(v.total) AS total FROM pos_ventas v JOIN pos_locales l ON v.id_local=l.id" + cond + " GROUP BY l.nombre ORDER BY l.nombre", tuple(rango))
            ventas_local = fetchall_dict(cur)
        except Exception: conn.rollback(); ventas_local = []

        # 2) Cobros distribuidores
        try:
            cur.execute("SELECT d.razon_social AS nombre, SUM(c.monto) AS total FROM cobros_distribuidores c LEFT JOIN distribuidores d ON c.id_distribuidor=d.id" + cond.replace('fecha','c.fecha') + " GROUP BY d.razon_social ORDER BY total DESC", tuple(rango))
            cobros_dist = fetchall_dict(cur)
        except Exception: conn.rollback(); cobros_dist = []

        # 3) Gastos por categoría
        try:
            cur.execute("SELECT COALESCE(cat.nombre,'Sin categoría') AS categoria, SUM(g.monto) AS total FROM gastos g LEFT JOIN gastos_categorias cat ON g.id_categoria=cat.id" + cond.replace('fecha','g.fecha') + " GROUP BY cat.nombre ORDER BY total DESC", tuple(rango))
            gastos_cat = fetchall_dict(cur)
        except Exception: conn.rollback(); gastos_cat = []

        # 4) Pagos a proveedores
        try:
            cur.execute("SELECT p.nombre AS proveedor, SUM(pg.monto) AS total FROM pagos_proveedores pg LEFT JOIN proveedores p ON pg.id_proveedor=p.id" + cond.replace('fecha','pg.fecha') + " GROUP BY p.nombre ORDER BY total DESC", tuple(rango))
            pagos_prov = fetchall_dict(cur)
        except Exception: conn.rollback(); pagos_prov = []

        # 5) Deudas pendientes (sin filtro de fecha — son las que aún deben)
        try:
            cur.execute("SELECT p.nombre AS proveedor, SUM(d.monto) AS total FROM deudas_proveedores_manual d JOIN proveedores p ON d.id_proveedor=p.id WHERE d.pagada=false GROUP BY p.nombre ORDER BY total DESC")
            deudas_manual = fetchall_dict(cur)
        except Exception: conn.rollback(); deudas_manual = []
        try:
            cur.execute("SELECT p.nombre AS proveedor, SUM(oc.total) AS total FROM ordenes_compra oc JOIN proveedores p ON oc.id_proveedor=p.id WHERE oc.estado='Recibida' AND oc.id NOT IN (SELECT DISTINCT id_orden FROM pagos_proveedores WHERE id_orden IS NOT NULL) GROUP BY p.nombre ORDER BY total DESC")
            deudas_auto = fetchall_dict(cur)
        except Exception: conn.rollback(); deudas_auto = []

        tv = sum(float(r['total'] or 0) for r in ventas_local)
        tc = sum(float(r['total'] or 0) for r in cobros_dist)
        tg = sum(float(r['total'] or 0) for r in gastos_cat)
        tp = sum(float(r['total'] or 0) for r in pagos_prov)
        td = sum(float(r['total'] or 0) for r in deudas_manual + deudas_auto)
        ti = tv + tc
        te = tg + tp + td

        return {
            "desde": desde, "hasta": hasta,
            "ingresos": {"ventas_local": ventas_local, "cobros_dist": cobros_dist, "total_ventas": tv, "total_cobros": tc, "total": ti},
            "egresos":  {"gastos": gastos_cat, "pagos_prov": pagos_prov, "deudas_manual": deudas_manual, "deudas_auto": deudas_auto, "total_gastos": tg, "total_pagos": tp, "total_deudas": td, "total": te},
            "resultado": ti - te
        }
    finally:
        liberar_conexion(conn)

@app.get("/contabilidad")
def route_contabilidad():
    return serve_html("contabilidad.html")

@app.get("/api/contabilidad/exportar")
def contabilidad_exportar(desde: Optional[str] = None, hasta: Optional[str] = None):
    """Devuelve facturas emitidas + pagos a proveedores + gastos para exportar al contador."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        params_rango = []
        rango_sql = ""
        if desde: rango_sql += " AND fecha::date >= %s"; params_rango.append(desde)
        if hasta: rango_sql += " AND fecha::date <= %s"; params_rango.append(hasta)

        # Facturas emitidas AFIP
        try:
            q = """SELECT f.fecha::text, f.tipo_comprobante, f.numero, f.cae,
                          l.nombre AS local, f.total
                   FROM afip_facturas f LEFT JOIN pos_locales l ON f.id_local=l.id
                   WHERE 1=1""" + rango_sql + " ORDER BY f.fecha DESC"
            cur.execute(q, tuple(params_rango))
            facturas = fetchall_dict(cur)
        except Exception:
            conn.rollback(); facturas = []

        # Pagos a proveedores
        try:
            q2 = """SELECT pg.fecha::text, p.nombre AS proveedor, pg.monto,
                           pg.metodo, pg.referencia, pg.notas
                    FROM pagos_proveedores pg LEFT JOIN proveedores p ON pg.id_proveedor=p.id
                    WHERE 1=1""" + rango_sql.replace('fecha', 'pg.fecha') + " ORDER BY pg.fecha DESC"
            cur.execute(q2, tuple(params_rango))
            pagos = fetchall_dict(cur)
        except Exception:
            conn.rollback(); pagos = []

        # Gastos
        try:
            q3 = """SELECT g.fecha::text, cat.nombre AS categoria, g.concepto,
                           g.monto, g.metodo, g.notas
                    FROM gastos g LEFT JOIN gastos_categorias cat ON g.id_categoria=cat.id
                    WHERE 1=1""" + rango_sql.replace('fecha', 'g.fecha') + " ORDER BY g.fecha DESC"
            cur.execute(q3, tuple(params_rango))
            gastos = fetchall_dict(cur)
        except Exception:
            conn.rollback(); gastos = []

        return {
            "desde": desde, "hasta": hasta,
            "facturas_emitidas": facturas,
            "pagos_proveedores": pagos,
            "gastos": gastos,
            "totales": {
                "facturas": sum(float(f.get('total') or 0) for f in facturas),
                "pagos": sum(float(p.get('monto') or 0) for p in pagos),
                "gastos": sum(float(g.get('monto') or 0) for g in gastos),
            }
        }
    finally:
        liberar_conexion(conn)

@app.post("/api/afip/factura_manual")
def afip_factura_manual(data: dict = Body(...)):
    """Carga una factura que YA se emitió en AFIP pero no quedó guardada en el sistema.
    No emite nada nuevo: solo registra el dato fiscal que ya existe."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        total = float(data.get('total') or 0)
        neto = data.get('neto')
        iva = data.get('iva')
        # Si no mandan neto/iva, calcularlos del total (IVA 21% incluido)
        if neto is None or iva is None:
            neto = round(total / 1.21, 2)
            iva = round(total - neto, 2)
        # Anti-duplicado: misma factura (PV + número + tipo) no se carga dos veces
        try:
            cur.execute("""SELECT id FROM afip_facturas
                           WHERE punto_venta=%s AND numero=%s AND tipo_comprobante=%s LIMIT 1""",
                        (data.get('punto_venta'), data.get('numero'), data.get('tipo_comprobante')))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Esa factura (mismo PV, número y tipo) ya está cargada.")
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
        cur.execute("""INSERT INTO afip_facturas
                       (id_local, id_pedido_b2b, punto_venta, tipo_comprobante, numero,
                        doc_tipo, doc_nro, neto, iva, total, cae, cae_vto, estado, entorno, fecha)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'emitida','manual',COALESCE(%s::timestamptz, NOW()))
                       RETURNING id""",
                    (data.get('id_local'), data.get('id_pedido_b2b'), data.get('punto_venta'),
                     data.get('tipo_comprobante', 6), data.get('numero'),
                     data.get('doc_tipo', 99), str(data.get('doc_nro') or '0'),
                     neto, iva, total, data.get('cae'), data.get('cae_vto'),
                     data.get('fecha')))
        fid = cur.fetchone()[0]
        conn.commit()
        return {"id": fid, "status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/afip/facturas")
def afip_listar_facturas(id_local: Optional[int] = None, punto_venta: Optional[int] = None,
                          desde: Optional[str] = None, hasta: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = """SELECT f.*, l.nombre AS local_nombre,
                      COALESCE(d.razon_social, '') AS cliente_b2b,
                      COALESCE(d.cuit, '') AS cliente_cuit,
                      COALESCE(d.direccion, '') AS cliente_direccion,
                      COALESCE(d.localidad, '') AS cliente_localidad,
                      COALESCE(d.provincia, '') AS cliente_provincia,
                      COALESCE(d.cp, '') AS cliente_cp
               FROM afip_facturas f
               LEFT JOIN pos_locales l ON f.id_local = l.id
               LEFT JOIN pedidos_b2b p ON f.id_pedido_b2b = p.id
               LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
               WHERE 1=1"""
        params = []
        if id_local: q += " AND f.id_local=%s"; params.append(id_local)
        if punto_venta: q += " AND f.punto_venta=%s"; params.append(punto_venta)
        if desde: q += " AND f.fecha::date >= %s"; params.append(desde)
        if hasta: q += " AND f.fecha::date <= %s"; params.append(hasta)
        q += " ORDER BY f.fecha DESC LIMIT 500"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/afip/puntos_venta")
def afip_puntos_venta():
    """Lista los puntos de venta que tienen facturas, para el filtro."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT DISTINCT f.punto_venta,
                              (SELECT nombre FROM pos_locales WHERE id = f.id_local LIMIT 1) AS local
                       FROM afip_facturas f WHERE f.punto_venta IS NOT NULL
                       ORDER BY f.punto_venta""")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/afip/empresa")
def afip_datos_empresa():
    """Datos fiscales de la empresa para el PDF de factura."""
    return {
        "razon_social": os.environ.get("EMPRESA_RAZON_SOCIAL", "ALFAJORES PORTAL DEL VIENTO SAS"),
        "cuit": os.environ.get("AFIP_CUIT", "30717499014"),
        "direccion": os.environ.get("EMPRESA_DIRECCION", "Mendoza, Argentina"),
        "iva": os.environ.get("EMPRESA_COND_IVA", "IVA Responsable Inscripto"),
        "ingresos_brutos": os.environ.get("EMPRESA_IIBB", ""),
        "inicio_actividades": os.environ.get("EMPRESA_INICIO", "")
    }

@app.post("/api/afip/facturar_pedido_b2b/{id_pedido}")
def afip_facturar_pedido_b2b(id_pedido: int, data: dict = Body(...)):
    """Emite una factura AFIP para un pedido B2B de distribuidor.
    data: { tipo_comprobante: 1|6, doc_tipo: 80|99, doc_nro: str, id_local: int }
    ATENCIÓN: llama a AFIP en producción real. La factura tiene CAE y es válida fiscalmente."""
    if not afip_service:
        raise HTTPException(status_code=503, detail="El servicio AFIP no está disponible.")
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Verificar que el pedido existe y no tiene factura
        cur.execute("SELECT p.id, p.total, p.id_distribuidor, d.razon_social, d.cuit FROM pedidos_b2b p LEFT JOIN distribuidores d ON p.id_distribuidor=d.id WHERE p.id=%s", (id_pedido,))
        ped = cur.fetchone()
        if not ped:
            raise HTTPException(status_code=404, detail="Pedido no encontrado.")
        # Ver si ya tiene factura
        try:
            cur.execute("SELECT id FROM afip_facturas WHERE id_pedido_b2b=%s LIMIT 1", (id_pedido,))
            ya = cur.fetchone()
            if ya:
                raise HTTPException(status_code=409, detail="Este pedido ya tiene una factura emitida.")
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
        total = float(ped.get('total') or 0)
        if total <= 0:
            raise HTTPException(status_code=400, detail="El total del pedido es 0 o inválido.")
        tipo = int(data.get('tipo_comprobante', 6))
        doc_tipo = int(data.get('doc_tipo', 99))
        # Limpiar el CUIT/DNI: quitar guiones, puntos y espacios (AFIP espera solo números)
        doc_nro = str(data.get('doc_nro') or '0').replace('-', '').replace('.', '').replace(' ', '').strip()
        if not doc_nro or not doc_nro.isdigit():
            doc_nro = '0'
        id_local = int(data.get('id_local') or 1)
        # Punto de venta según el local
        cur.execute("SELECT punto_venta_afip FROM pos_locales WHERE id=%s", (id_local,))
        loc = cur.fetchone()
        pv = int(loc['punto_venta_afip']) if loc and loc.get('punto_venta_afip') else int(os.environ.get('AFIP_PUNTO_VENTA', 5))
        # Calcular neto e IVA (IVA 21% incluido en el total)
        neto = round(total / 1.21, 2)
        iva  = round(total - neto, 2)
        # CondicionIVAReceptorId: código numérico que espera AFIP (1=RI, 5=Consumidor Final)
        cond_iva = 1 if tipo == 1 else 5
        resultado = afip_service.emitir_factura(
            tipo_cbte=tipo, doc_tipo=doc_tipo, doc_nro=doc_nro,
            neto=neto, iva=iva, total=total, cond_iva_receptor=cond_iva, punto_venta=pv
        )
        # Guardar en la base (mismas columnas que el POS: cae_vto, estado, entorno)
        try:
            cur.execute("""INSERT INTO afip_facturas
                           (id_local, id_pedido_b2b, punto_venta, tipo_comprobante, numero,
                            doc_tipo, doc_nro, neto, iva, total, cae, cae_vto, estado, entorno, fecha)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'emitida',%s,NOW())""",
                       (id_local, id_pedido, pv, tipo, resultado.get('numero'),
                        doc_tipo, doc_nro, neto, iva, total,
                        resultado.get('cae'), resultado.get('cae_vto'), resultado.get('entorno')))
            conn.commit()
        except Exception as e_guardar:
            conn.rollback()
            # NO tragar el error: la factura se emitió en AFIP pero no se guardó.
            # Avisar para no perder el registro fiscal.
            raise HTTPException(status_code=500,
                detail=f"⚠️ La factura se emitió en AFIP (CAE {resultado.get('cae')}) pero NO se pudo guardar: {e_guardar}. Anotá el CAE.")
        return {"status": "ok", "cae": resultado.get('cae'), "numero": resultado.get('numero'),
                "tipo": tipo, "total": total, "distribuidor": ped.get('razon_social')}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)


# ==============================================================================
# LISTADO DE VENTAS CON COMPROBANTE (para reporte al contador)
# ==============================================================================
@app.get("/api/ventas/listado")
def ventas_listado(desde: Optional[str] = None, hasta: Optional[str] = None,
                   id_local: Optional[int] = None, metodo_pago: Optional[str] = None,
                   comprobante: Optional[str] = None):
    """
    Lista ventas del POS con su comprobante.
    comprobante: 'afip' (solo facturadas), 'ticket' (sin factura AFIP), o None (todas).
    """
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Detectar si pos_ventas tiene columna de cajero (para no romper si no se corrió el SQL)
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='pos_ventas' AND column_name='nombre_cajero'""")
        tiene_cajero = bool(cur.fetchone())
        cajero_sel = "v.nombre_cajero" if tiene_cajero else "NULL AS nombre_cajero"

        q = f"""
            SELECT v.id, v.fecha::text AS fecha, v.metodo_pago, v.total,
                   v.id_local, l.nombre AS local,
                   {cajero_sel},
                   f.id AS id_factura, f.cae, f.tipo_comprobante, f.numero AS nro_factura,
                   f.punto_venta, f.estado AS estado_factura
            FROM pos_ventas v
            LEFT JOIN pos_locales l ON v.id_local = l.id
            LEFT JOIN afip_facturas f ON f.id_venta = v.id AND f.estado='emitida'
            WHERE 1=1
        """
        params = []
        if desde: q += " AND v.fecha::date >= %s"; params.append(desde)
        if hasta: q += " AND v.fecha::date <= %s"; params.append(hasta)
        if id_local: q += " AND v.id_local = %s"; params.append(id_local)
        if metodo_pago: q += " AND v.metodo_pago = %s"; params.append(metodo_pago)
        if comprobante == 'afip': q += " AND f.id IS NOT NULL"
        elif comprobante == 'ticket': q += " AND f.id IS NULL"
        q += " ORDER BY v.fecha DESC LIMIT 1000"
        cur.execute(q, tuple(params))
        ventas = fetchall_dict(cur)

        # Totales del listado
        total_general = sum(float(v['total'] or 0) for v in ventas)
        total_afip = sum(float(v['total'] or 0) for v in ventas if v.get('id_factura'))
        total_ticket = total_general - total_afip
        por_metodo = {}
        for v in ventas:
            m = v['metodo_pago'] or 'Otro'
            por_metodo[m] = por_metodo.get(m, 0) + float(v['total'] or 0)

        return {
            "ventas": ventas,
            "resumen": {
                "cantidad": len(ventas),
                "total_general": total_general,
                "total_afip": total_afip,
                "total_ticket": total_ticket,
                "por_metodo": por_metodo
            }
        }
    finally:
        liberar_conexion(conn)

@app.get("/api/ventas/{id_venta}/comprobante")
def venta_comprobante(id_venta: int):
    """Devuelve todo lo necesario para reimprimir el comprobante de una venta:
    detalle de productos, datos del local, pagos, y datos de factura AFIP si la tiene."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Venta + local
        try:
            cur.execute("""SELECT v.id, v.fecha::text AS fecha, v.metodo_pago, v.total, v.id_local,
                                  l.nombre AS local_nombre, l.direccion AS local_direccion
                           FROM pos_ventas v LEFT JOIN pos_locales l ON v.id_local=l.id
                           WHERE v.id=%s""", (id_venta,))
        except Exception:
            conn.rollback()
            cur.execute("""SELECT v.id, v.fecha::text AS fecha, v.metodo_pago, v.total, v.id_local
                           FROM pos_ventas v WHERE v.id=%s""", (id_venta,))
        venta = cur.fetchone()
        if not venta:
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        venta = dict(venta)
        # Detalle
        cur.execute("SELECT nombre_producto, cantidad, precio_unitario FROM pos_detalle_ventas WHERE id_venta=%s", (id_venta,))
        venta['detalle'] = fetchall_dict(cur)
        # Pagos (si existe la tabla)
        try:
            cur.execute("SELECT metodo_pago, monto FROM pos_pagos_venta WHERE id_venta=%s", (id_venta,))
            venta['pagos'] = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            venta['pagos'] = []
        # Factura AFIP (si fue facturada)
        try:
            cur.execute("""SELECT punto_venta, tipo_comprobante, numero, doc_tipo, doc_nro,
                                  neto, iva, total, cae, cae_vto::text AS cae_vto, entorno
                           FROM afip_facturas WHERE id_venta=%s AND estado='emitida' ORDER BY id DESC LIMIT 1""", (id_venta,))
            f = cur.fetchone()
            venta['factura'] = dict(f) if f else None
        except Exception:
            conn.rollback()
            venta['factura'] = None
        return venta
    finally:
        liberar_conexion(conn)
@app.delete("/api/locales/{id_local}/reiniciar")
def reiniciar_datos_local(id_local: int, confirmar: Optional[str] = None):
    """Borra ventas, reposiciones, faltantes y gastos del local para arrancar de cero.
    NO borra productos ni el local. Requiere confirmar='SI'."""
    if confirmar != "SI":
        raise HTTPException(status_code=400, detail="Falta confirmación")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Ventas: borrar detalle, luego ventas
        cur.execute("DELETE FROM pos_detalle_ventas WHERE id_venta IN (SELECT id FROM pos_ventas WHERE id_local=%s)", (id_local,))
        cur.execute("DELETE FROM pos_ventas WHERE id_local=%s", (id_local,))
        # Cajas del local
        try:
            cur.execute("DELETE FROM pos_cajas WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        # Movimientos de stock del local
        try:
            cur.execute("DELETE FROM pos_movimientos_stock WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        # Reposiciones (detalle y cabecera)
        try:
            cur.execute("DELETE FROM pos_reposiciones_detalle WHERE id_reposicion IN (SELECT id FROM pos_reposiciones WHERE id_local=%s)", (id_local,))
            cur.execute("DELETE FROM pos_reposiciones WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        # Faltantes
        try:
            cur.execute("DELETE FROM pos_faltantes WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        # Gastos del local
        try:
            cur.execute("DELETE FROM gastos WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        # Facturas AFIP del local (opcional, solo registros internos; AFIP ya las tiene)
        try:
            cur.execute("DELETE FROM afip_facturas WHERE id_local=%s", (id_local,))
        except Exception:
            conn.rollback()
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# HISTORIAL DE CIERRES DE CAJA (por local)
# ==============================================================================
@app.get("/api/locales/{id_local}/cierres")
def locales_cierres_caja(id_local: int, desde: Optional[str] = None, hasta: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cols_control = """, COALESCE(controlado,false) AS controlado, controlado_por, fecha_control::text AS fecha_control,
                          COALESCE(retirado,false) AS retirado, retirado_por, fecha_retiro::text AS fecha_retiro"""
        base = """
            SELECT id, nombre_responsable, fecha_apertura::text, fecha_cierre::text,
                   COALESCE(monto_apertura,0) AS monto_apertura,
                   COALESCE(monto_cierre,0) AS monto_cierre,
                   COALESCE(total_efectivo,0) AS total_efectivo,
                   COALESCE(total_tarjeta,0) AS total_tarjeta,
                   COALESCE(total_transferencia,0) AS total_transferencia,
                   COALESCE(total_qr,0) AS total_qr,
                   observaciones{control}
            FROM pos_cajas
            WHERE id_local=%s AND estado='cerrada'
        """
        params = [id_local]
        cond = ""
        if desde: cond += " AND fecha_cierre::date >= %s"; params.append(desde)
        if hasta: cond += " AND fecha_cierre::date <= %s"; params.append(hasta)
        cond += " ORDER BY fecha_cierre DESC LIMIT 200"
        try:
            cur.execute(base.format(control=cols_control) + cond, tuple(params))
            cierres = fetchall_dict(cur)
        except Exception:
            conn.rollback()
            cur.execute(base.format(control="") + cond, tuple(params))
            cierres = fetchall_dict(cur)
            for c in cierres:
                c['controlado'] = False; c['controlado_por'] = None; c['fecha_control'] = None
                c['retirado'] = False; c['retirado_por'] = None; c['fecha_retiro'] = None
        for c in cierres:
            ef = float(c['total_efectivo'] or 0)
            ap = float(c['monto_apertura'] or 0)
            contado = float(c['monto_cierre'] or 0)
            esperado_efectivo = ap + ef
            c['esperado_efectivo'] = esperado_efectivo
            c['diferencia'] = round(contado - esperado_efectivo, 2)  # + sobra / - falta
            c['total_vendido'] = round(ef + float(c['total_tarjeta'] or 0) + float(c['total_transferencia'] or 0) + float(c['total_qr'] or 0), 2)
        return cierres
    finally:
        liberar_conexion(conn)


@app.put("/api/locales/cierres/{id_caja}/controlar")
def controlar_cierre_caja(id_caja: int, controlado_por: str = ""):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_cajas SET controlado=true, controlado_por=%s, fecha_control=NOW() WHERE id=%s",
                    (controlado_por or None, id_caja))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

class RetiroCierre(BaseModel):
    retirado_por: str

@app.put("/api/pos/cierres/{id_caja}/retirar")
def marcar_cierre_retirado(id_caja: int, data: RetiroCierre):
    """Marca un cierre de caja como retirado (registra quién se llevó la plata)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE pos_cajas SET retirado=true, retirado_por=%s, fecha_retiro=NOW() WHERE id=%s",
                        (data.retirado_por or None, id_caja))
            conn.commit()
            return {"status": "ok"}
        except Exception:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Falta correr CREAR_RETIRO_CIERRES.sql en la base.")
    finally:
        liberar_conexion(conn)

@app.get("/api/pos/cierres_pendientes")
def cierres_pendientes_retiro(id_local: Optional[int] = None):
    """Devuelve la cantidad y lista de cierres cerrados que aún no fueron retirados.
    Si se pasa id_local, filtra por ese local."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            if id_local:
                cur.execute("""SELECT id, nombre_local, nombre_responsable, fecha_cierre::text,
                                      COALESCE(monto_cierre,0) AS monto_cierre, COALESCE(total_efectivo,0) AS total_efectivo
                               FROM pos_cajas
                               WHERE estado='cerrada' AND COALESCE(retirado,false)=false AND id_local=%s
                               ORDER BY fecha_cierre DESC""", (id_local,))
            else:
                cur.execute("""SELECT id, nombre_local, nombre_responsable, fecha_cierre::text,
                                      COALESCE(monto_cierre,0) AS monto_cierre, COALESCE(total_efectivo,0) AS total_efectivo
                               FROM pos_cajas
                               WHERE estado='cerrada' AND COALESCE(retirado,false)=false
                               ORDER BY fecha_cierre DESC""")
            lista = fetchall_dict(cur)
            total_efectivo = sum(float(c.get('total_efectivo') or 0) for c in lista)
            total_general = sum(float(c.get('monto_cierre') or 0) for c in lista)
            return {
                "cantidad": len(lista),
                "cierres": lista,
                "total_efectivo": total_efectivo,
                "total_general": total_general
            }
        except Exception:
            conn.rollback()
            # Si la columna retirado no existe todavía, no hay pendientes
            return {"cantidad": 0, "cierres": [], "total_efectivo": 0, "total_general": 0}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# RUTAS WEB (HTML)
# ==============================================================================
def serve_html(filename: str):
    path = os.path.join(os.path.dirname(__file__), 'pantallas', filename)
    if not os.path.exists(path):
        return HTMLResponse(content=f"<h1>Archivo no encontrado: {filename}</h1>", status_code=404)
    with open(path, 'r', encoding='utf-8') as f:
        return HTMLResponse(
            content=f.read(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"}
        )

@app.get("/")
def index():
    return serve_html("login.html")

@app.get("/static/auth.js")
def serve_auth_js():
    path = os.path.join(os.path.dirname(__file__), 'pantallas', 'auth.js')
    if not os.path.exists(path):
        return HTMLResponse(content="// auth.js no encontrado", status_code=404, media_type="application/javascript")
    with open(path, 'r', encoding='utf-8') as f:
        return Response(content=f.read(), media_type="application/javascript",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

@app.get("/api/ia/estado")
def ia_estado():
    try:
        import ia_service
        return {"configurado": ia_service.esta_configurado()}
    except Exception:
        return {"configurado": False}

@app.post("/api/ia/preguntar")
def ia_preguntar(data: dict = Body(...)):
    """Responde una pregunta del admin sobre los datos del negocio.
    Arma un resumen (ventas, stock, deudas, ingresos) y lo manda a la IA."""
    pregunta = (data.get("pregunta") or "").strip()
    if not pregunta:
        raise HTTPException(status_code=400, detail="Escribí una pregunta")
    try:
        import ia_service
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo cargar el asistente")
    if not ia_service.esta_configurado():
        raise HTTPException(status_code=400, detail="El asistente no está configurado. Falta cargar la API key de Anthropic en Railway (variable ANTHROPIC_API_KEY).")

    resumen = {}
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # --- Ventas POS últimos 30 días ---
        try:
            cur.execute("""SELECT COALESCE(SUM(total),0) AS total, COUNT(*) AS cant
                           FROM pos_ventas WHERE fecha >= NOW() - INTERVAL '30 days'""")
            r = cur.fetchone()
            resumen["ventas_pos_ultimos_30_dias"] = {"total": float(r["total"] or 0), "cantidad_ventas": r["cant"]}
        except Exception:
            conn.rollback()
        # --- Ventas POS hoy ---
        try:
            cur.execute("SELECT COALESCE(SUM(total),0) AS total, COUNT(*) AS cant FROM pos_ventas WHERE DATE(fecha)=CURRENT_DATE")
            r = cur.fetchone()
            resumen["ventas_pos_hoy"] = {"total": float(r["total"] or 0), "cantidad_ventas": r["cant"]}
        except Exception:
            conn.rollback()
        # --- Stock bajo ---
        try:
            cur.execute("""SELECT nombre, stock_actual, stock_alerta FROM productos
                           WHERE COALESCE(activo,true)=true AND COALESCE(stock_actual,0) <= COALESCE(stock_alerta,0)
                           ORDER BY stock_actual ASC LIMIT 20""")
            resumen["productos_con_stock_bajo"] = [
                {"producto": x["nombre"], "stock": float(x["stock_actual"] or 0), "alerta": float(x["stock_alerta"] or 0)}
                for x in fetchall_dict(cur)
            ]
        except Exception:
            conn.rollback()
        # --- Ingresos de distribuidores últimos 30 días ---
        try:
            cur.execute("""SELECT COALESCE(SUM(monto),0) AS total, COUNT(*) AS cant
                           FROM cobros_distribuidores WHERE fecha >= NOW() - INTERVAL '30 days'""")
            r = cur.fetchone()
            resumen["ingresos_distribuidores_ultimos_30_dias"] = {"total": float(r["total"] or 0), "cantidad_cobros": r["cant"]}
        except Exception:
            conn.rollback()
        # --- Deudas de distribuidores (pedidos despachados - cobros) ---
        try:
            cur.execute("""
                SELECT d.razon_social AS distribuidor,
                    COALESCE((SELECT SUM(p.total) FROM pedidos_b2b p WHERE p.id_distribuidor=d.id AND p.estado IN ('Despachado','Despachado parcial')),0) AS pedidos,
                    COALESCE((SELECT SUM(c.monto) FROM cobros_distribuidores c WHERE c.id_distribuidor=d.id),0) AS cobrado
                FROM distribuidores d WHERE COALESCE(d.activo,true)=true
            """)
            deudas = []
            for x in fetchall_dict(cur):
                saldo = float(x["pedidos"] or 0) - float(x["cobrado"] or 0)
                if saldo > 0:
                    deudas.append({"distribuidor": x["distribuidor"], "debe": round(saldo, 2)})
            deudas.sort(key=lambda z: z["debe"], reverse=True)
            resumen["distribuidores_que_deben"] = deudas[:20]
            resumen["total_a_cobrar_distribuidores"] = round(sum(d["debe"] for d in deudas), 2)
        except Exception:
            conn.rollback()
        # --- Pedidos pendientes ---
        try:
            cur.execute("SELECT COUNT(*) AS c FROM pedidos_b2b WHERE estado IN ('Pendiente','En preparación')")
            resumen["pedidos_b2b_pendientes"] = cur.fetchone()["c"]
        except Exception:
            conn.rollback()
    finally:
        liberar_conexion(conn)

    res = ia_service.preguntar(pregunta, resumen)
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail=res.get("error", "Error del asistente"))
    return {"respuesta": res["respuesta"]}

@app.get("/api/deudas_distribuidores")
def deudas_distribuidores():
    """Deuda de cada distribuidor (pedidos despachados − cobros), ordenada de mayor a menor,
    con la antigüedad de su pedido despachado más viejo (para detectar deuda vieja)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT d.id, d.razon_social AS distribuidor, d.telefono,
                COALESCE((
                    SELECT SUM(
                        CASE WHEN EXISTS (SELECT 1 FROM preparacion_items pi WHERE pi.id_pedido = p.id)
                             THEN COALESCE((
                                SELECT SUM(pi.cantidad * dp.precio_unitario)
                                FROM preparacion_items pi
                                JOIN detalle_pedidos_b2b dp ON dp.id_pedido = pi.id_pedido AND dp.id_producto = pi.id_producto
                                WHERE pi.id_pedido = p.id
                             ), 0)
                             ELSE COALESCE(p.total, 0)
                        END
                    )
                    FROM pedidos_b2b p
                    WHERE p.id_distribuidor=d.id AND p.estado IN ('Despachado','Despachado parcial')
                ),0) AS pedidos,
                COALESCE((SELECT SUM(c.monto) FROM cobros_distribuidores c WHERE c.id_distribuidor=d.id),0) AS cobrado,
                (SELECT MIN(p.fecha) FROM pedidos_b2b p
                 WHERE p.id_distribuidor=d.id AND p.estado IN ('Despachado','Despachado parcial')) AS pedido_mas_viejo
            FROM distribuidores d
            WHERE COALESCE(d.activo,true)=true
        """)
        filas = fetchall_dict(cur)
        deudores = []
        total = 0.0
        from datetime import datetime, timezone
        ahora = datetime.now(timezone.utc)
        for f in filas:
            saldo = float(f['pedidos'] or 0) - float(f['cobrado'] or 0)
            if saldo > 0.5:
                dias = None
                if f.get('pedido_mas_viejo'):
                    try:
                        pv = f['pedido_mas_viejo']
                        if pv.tzinfo is None:
                            pv = pv.replace(tzinfo=timezone.utc)
                        dias = (ahora - pv).days
                    except Exception:
                        dias = None
                deudores.append({
                    "id": f['id'], "distribuidor": f['distribuidor'], "telefono": f.get('telefono'),
                    "debe": round(saldo, 2),
                    "dias_deuda": dias
                })
                total += saldo
        deudores.sort(key=lambda x: x['debe'], reverse=True)
        return {"total": round(total, 2), "cantidad": len(deudores), "deudores": deudores}
    finally:
        liberar_conexion(conn)

@app.get("/login")
def route_login():
    return serve_html("login.html")

@app.get("/admin")
def route_admin():
    return serve_html("panel_admin.html")

@app.get("/catalogo")
def route_catalogo():
    return serve_html("catalogo_stock.html")

@app.get("/tienda")
def route_tienda():
    return serve_html("tienda.html")

@app.get("/armado")
def route_armado():
    return serve_html("armado_pedidos.html")

@app.get("/insumos")
def route_insumos():
    return serve_html("insumos.html")

@app.get("/produccion")
def route_produccion():
    return serve_html("produccion.html")

@app.get("/produccion-panel")
def route_produccion_panel():
    return serve_html("portal_produccion.html")

# ============================================================
#  MÓDULO PROVEEDORES 2.0 — Endpoints
# ============================================================

# ---- Dashboard ----
@app.get("/api/prov2/dashboard")
def prov2_dashboard():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Deuda total = suma de (deuda_inicial + facturas - pagos) de todos los proveedores
        cur.execute("""
            SELECT COALESCE(SUM(
                p.deuda_inicial
                + COALESCE((SELECT SUM(monto) FROM prov2_movimientos m WHERE m.id_proveedor=p.id AND m.tipo='factura'),0)
                - COALESCE((SELECT SUM(monto) FROM prov2_movimientos m WHERE m.id_proveedor=p.id AND m.tipo='pago'),0)
            ),0) AS deuda_total
            FROM prov2_proveedores p WHERE p.activo=true
        """)
        deuda_total = float(cur.fetchone()['deuda_total'] or 0)
        # Órdenes pendientes (no completadas)
        cur.execute("SELECT COUNT(*) AS c FROM prov2_ordenes WHERE estado <> 'Completada'")
        ordenes_pendientes = cur.fetchone()['c']
        # Facturas este mes
        cur.execute("""SELECT COALESCE(SUM(monto),0) AS total, COUNT(*) AS cant
                       FROM prov2_movimientos
                       WHERE tipo='factura' AND date_trunc('month', fecha)=date_trunc('month', CURRENT_DATE)""")
        fila = cur.fetchone()
        facturas_mes = float(fila['total'] or 0)
        facturas_mes_cant = fila['cant']
        # Últimos movimientos (pagos y remitos recientes)
        cur.execute("""SELECT m.tipo, m.fecha::text, m.monto, m.numero, m.concepto,
                              p.razon_social
                       FROM prov2_movimientos m
                       JOIN prov2_proveedores p ON m.id_proveedor=p.id
                       ORDER BY m.fecha DESC, m.id DESC LIMIT 15""")
        movimientos = fetchall_dict(cur)
        return {
            "deuda_total": deuda_total,
            "ordenes_pendientes": ordenes_pendientes,
            "facturas_mes": facturas_mes,
            "facturas_mes_cant": facturas_mes_cant,
            "movimientos": movimientos
        }
    finally:
        liberar_conexion(conn)

# ---- Proveedores ----
@app.get("/api/prov2/proveedores")
def prov2_listar():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*,
                (p.deuda_inicial
                 + COALESCE((SELECT SUM(monto) FROM prov2_movimientos m WHERE m.id_proveedor=p.id AND m.tipo='factura'),0)
                 - COALESCE((SELECT SUM(monto) FROM prov2_movimientos m WHERE m.id_proveedor=p.id AND m.tipo='pago'),0)
                ) AS saldo
            FROM prov2_proveedores p WHERE p.activo=true ORDER BY p.razon_social
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

class Prov2Proveedor(BaseModel):
    razon_social: str
    cuit: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    categoria: str = 'Materia prima'
    dias_plazo: int = 0
    deuda_inicial: float = 0
    notas: Optional[str] = None

@app.post("/api/prov2/proveedores")
def prov2_crear(p: Prov2Proveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO prov2_proveedores (razon_social, cuit, contacto, telefono, email, categoria, dias_plazo, deuda_inicial, notas)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (p.razon_social, p.cuit, p.contacto, p.telefono, p.email, p.categoria, p.dias_plazo, p.deuda_inicial, p.notas))
        rid = cur.fetchone()[0]
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/prov2/proveedores/{id}")
def prov2_editar(id: int, p: Prov2Proveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""UPDATE prov2_proveedores SET razon_social=%s, cuit=%s, contacto=%s, telefono=%s,
                       email=%s, categoria=%s, dias_plazo=%s, deuda_inicial=%s, notas=%s WHERE id=%s""",
                    (p.razon_social, p.cuit, p.contacto, p.telefono, p.email, p.categoria, p.dias_plazo, p.deuda_inicial, p.notas, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/prov2/proveedores/{id}")
def prov2_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prov2_proveedores SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- Insumos ----
@app.get("/api/prov2/insumos")
def prov2_insumos_listar():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT i.*, p.razon_social AS proveedor_nombre
                       FROM prov2_insumos i LEFT JOIN prov2_proveedores p ON i.id_proveedor=p.id
                       WHERE i.activo=true ORDER BY i.nombre""")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

class Prov2Insumo(BaseModel):
    nombre: str
    id_proveedor: Optional[int] = None
    unidad: str = 'u'
    ultimo_precio: float = 0

@app.post("/api/prov2/insumos")
def prov2_insumo_crear(i: Prov2Insumo):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO prov2_insumos (nombre, id_proveedor, unidad, ultimo_precio, fecha_precio)
                       VALUES (%s,%s,%s,%s,CURRENT_DATE) RETURNING id""",
                    (i.nombre, i.id_proveedor, i.unidad, i.ultimo_precio))
        rid = cur.fetchone()[0]
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/prov2/insumos/{id}")
def prov2_insumo_editar(id: int, i: Prov2Insumo):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Si cambió el precio, actualizar la fecha
        cur.execute("SELECT ultimo_precio FROM prov2_insumos WHERE id=%s", (id,))
        row = cur.fetchone()
        precio_cambio = row and float(row[0] or 0) != float(i.ultimo_precio)
        if precio_cambio:
            cur.execute("""UPDATE prov2_insumos SET nombre=%s, id_proveedor=%s, unidad=%s,
                           ultimo_precio=%s, fecha_precio=CURRENT_DATE WHERE id=%s""",
                        (i.nombre, i.id_proveedor, i.unidad, i.ultimo_precio, id))
        else:
            cur.execute("""UPDATE prov2_insumos SET nombre=%s, id_proveedor=%s, unidad=%s WHERE id=%s""",
                        (i.nombre, i.id_proveedor, i.unidad, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/prov2/insumos/{id}")
def prov2_insumo_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prov2_insumos SET activo=false WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- Cuenta corriente (ficha del proveedor) ----
@app.get("/api/prov2/proveedores/{id}/cuenta")
def prov2_cuenta(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM prov2_proveedores WHERE id=%s", (id,))
        prov = cur.fetchone()
        if not prov:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        # Movimientos cronológicos
        cur.execute("""SELECT id, tipo, fecha::text, numero, monto, concepto, metodo, detalle_remito
                       FROM prov2_movimientos WHERE id_proveedor=%s ORDER BY fecha ASC, id ASC""", (id,))
        movs = fetchall_dict(cur)
        # Calcular saldo línea por línea (arranca en deuda_inicial)
        saldo = float(prov['deuda_inicial'] or 0)
        historial = []
        if saldo != 0:
            historial.append({"tipo": "saldo_inicial", "fecha": "", "numero": "", "concepto": "Deuda inicial",
                              "monto": saldo, "saldo": saldo})
        for m in movs:
            monto = float(m['monto'] or 0)
            if m['tipo'] == 'factura':
                saldo += monto
            elif m['tipo'] == 'pago':
                saldo -= monto
            # remito no afecta saldo
            m['saldo'] = saldo
            historial.append(m)
        # Insumos del proveedor
        cur.execute("SELECT * FROM prov2_insumos WHERE id_proveedor=%s AND activo=true ORDER BY nombre", (id,))
        insumos = fetchall_dict(cur)
        return {"proveedor": prov, "historial": historial, "saldo": saldo, "insumos": insumos}
    finally:
        liberar_conexion(conn)

class Prov2Movimiento(BaseModel):
    id_proveedor: int
    tipo: str               # factura, pago, remito
    fecha: Optional[str] = None
    numero: Optional[str] = None
    monto: float = 0
    concepto: Optional[str] = None
    metodo: Optional[str] = None
    detalle_remito: Optional[str] = None

@app.post("/api/prov2/movimientos")
def prov2_movimiento_crear(m: Prov2Movimiento):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO prov2_movimientos (id_proveedor, tipo, fecha, numero, monto, concepto, metodo, detalle_remito)
                       VALUES (%s,%s,COALESCE(%s,CURRENT_DATE),%s,%s,%s,%s,%s) RETURNING id""",
                    (m.id_proveedor, m.tipo, m.fecha, m.numero, m.monto, m.concepto, m.metodo, m.detalle_remito))
        rid = cur.fetchone()[0]
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/prov2/movimientos/{id}")
def prov2_movimiento_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM prov2_movimientos WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ---- Órdenes de pedido ----
@app.get("/api/prov2/ordenes")
def prov2_ordenes_listar():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT o.*, p.razon_social AS proveedor_nombre
                       FROM prov2_ordenes o JOIN prov2_proveedores p ON o.id_proveedor=p.id
                       ORDER BY o.fecha DESC, o.id DESC""")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/prov2/ordenes/{id}")
def prov2_orden_detalle(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT o.*, p.razon_social AS proveedor_nombre, p.cuit AS proveedor_cuit,
                              p.telefono AS proveedor_telefono, p.email AS proveedor_email
                       FROM prov2_ordenes o JOIN prov2_proveedores p ON o.id_proveedor=p.id WHERE o.id=%s""", (id,))
        orden = cur.fetchone()
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        cur.execute("SELECT * FROM prov2_orden_items WHERE id_orden=%s ORDER BY id", (id,))
        items = fetchall_dict(cur)
        return {"orden": orden, "items": items}
    finally:
        liberar_conexion(conn)

class Prov2OrdenItem(BaseModel):
    id_insumo: Optional[int] = None
    nombre_insumo: str
    cantidad: float = 1
    precio_unitario: float = 0

class Prov2Orden(BaseModel):
    id_proveedor: int
    fecha: Optional[str] = None
    estado: str = 'Borrador'
    notas: Optional[str] = None
    items: List[Prov2OrdenItem] = []

@app.post("/api/prov2/ordenes")
def prov2_orden_crear(o: Prov2Orden):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        total = sum(it.cantidad * it.precio_unitario for it in o.items)
        cur.execute("""INSERT INTO prov2_ordenes (id_proveedor, fecha, estado, total_estimado, notas)
                       VALUES (%s,COALESCE(%s,CURRENT_DATE),%s,%s,%s) RETURNING id""",
                    (o.id_proveedor, o.fecha, o.estado, total, o.notas))
        oid = cur.fetchone()[0]
        for it in o.items:
            sub = it.cantidad * it.precio_unitario
            cur.execute("""INSERT INTO prov2_orden_items (id_orden, id_insumo, nombre_insumo, cantidad, precio_unitario, subtotal)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (oid, it.id_insumo, it.nombre_insumo, it.cantidad, it.precio_unitario, sub))
        conn.commit()
        return {"id": oid, "total": total}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/prov2/ordenes/{id}/estado")
def prov2_orden_estado(id: int, data: dict = Body(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prov2_ordenes SET estado=%s WHERE id=%s", (data.get('estado'), id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/prov2/ordenes/{id}")
def prov2_orden_eliminar(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM prov2_ordenes WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/proveedores2")
def route_proveedores2():
    return serve_html("proveedores2.html")

@app.get("/proveedores")
def route_proveedores():
    return serve_html("proveedores.html")

@app.get("/api/distribuidores/seguimiento_entregas")
def distribuidores_seguimiento_entregas():
    """Pedidos entregados hace 24h o más, sin seguimiento hecho.
    Para hacer el control post-entrega con el cliente."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT p.id, p.fecha_entrega::text, p.total, p.estado,
                       d.razon_social, d.telefono, d.localidad,
                       EXTRACT(EPOCH FROM (NOW() - p.fecha_entrega))/3600 AS horas_desde_entrega
                FROM pedidos_b2b p
                JOIN distribuidores d ON p.id_distribuidor = d.id
                WHERE p.estado IN ('Despachado', 'Despachado parcial')
                  AND p.fecha_entrega IS NOT NULL
                  AND COALESCE(p.seguimiento_hecho, false) = false
                  AND p.fecha_entrega <= NOW() - INTERVAL '24 hours'
                  AND p.fecha_entrega >= NOW() - INTERVAL '15 days'
                ORDER BY p.fecha_entrega ASC
            """)
            pedidos = fetchall_dict(cur)
            # Calcular días para cada uno
            for p in pedidos:
                horas = float(p.get('horas_desde_entrega') or 0)
                p['dias_desde_entrega'] = int(horas // 24)
            return {"cantidad": len(pedidos), "pedidos": pedidos}
        except Exception:
            conn.rollback()
            return {"cantidad": 0, "pedidos": []}
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/seguimiento/{id_pedido}/hecho")
def marcar_seguimiento_hecho(id_pedido: int):
    """Marca el seguimiento post-entrega como hecho (sale de la lista de pendientes)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pedidos_b2b SET seguimiento_hecho = true WHERE id = %s", (id_pedido,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/distribuidores")
def route_distribuidores():
    return serve_html("distribuidores.html")

@app.get("/historial-b2b")
def route_historial_b2b():
    return serve_html("historial_b2b.html")

@app.get("/empleados")
def route_empleados():
    return serve_html("empleados.html")

@app.get("/reportes")
def route_reportes():
    return serve_html("reportes.html")

@app.get("/liquidacion")
def route_liquidacion():
    return serve_html("liquidacion.html")

@app.get("/ganancia-local")
def route_ganancia_local():
    return serve_html("ganancia_local.html")

@app.get("/costos-productos")
def route_costos_productos():
    return serve_html("costos_productos.html")

@app.get("/ser-distribuidor")
def route_ser_distribuidor():
    return serve_html("ser_distribuidor.html")

@app.get("/prospectos")
def route_prospectos():
    return serve_html("prospectos.html")

@app.get("/ingresos-distribuidores")
def route_ingresos_dist():
    return serve_html("ingresos_distribuidores.html")

@app.get("/deudas-distribuidores")
def route_deudas_dist():
    return serve_html("deudas_distribuidores.html")

@app.get("/configuracion")
def route_configuracion():
    return serve_html("configuracion.html")

@app.get("/b2b")
def route_b2b():
    return serve_html("portal_distribuidores_v2.html")

@app.get("/mayoristas")
def route_mayoristas():
    return serve_html("portal_distribuidores_v2.html")

@app.get("/fichajes")
def route_fichajes():
    return serve_html("portal_fichaje.html")

@app.get("/reloj")
def route_reloj():
    return serve_html("reloj_fichaje.html")

@app.get("/qr")
def route_qr():
    return serve_html("qr_fichaje.html")


@app.get("/pos")
def route_pos():
    return serve_html("pos.html")

@app.get("/pos-login")
def route_pos_login():
    return serve_html("pos_login.html")


@app.get("/gastos")
def route_gastos():
    return serve_html("gastos.html")


@app.get("/productos-locales")
def route_productos_locales():
    return serve_html("productos_locales.html")

@app.get("/locales")
def route_locales():
    return serve_html("locales.html")

@app.get("/carga-stock")
def route_carga_stock():
    return serve_html("carga_stock_pos.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
