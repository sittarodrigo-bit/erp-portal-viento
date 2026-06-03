from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI(title="API Portal del Viento - Alfajores")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# BASE DE DATOS
# ==============================================================================
DB_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_jqkxN4SRzP5o@ep-still-firefly-apwc5fuw-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require")

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
@app.post("/api/pos/login")
def pos_login(data: LoginData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.password_hash, u.activo, COALESCE(u.acceso_pos, false) AS acceso_pos,
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
        return {"status": "ok", "id_empleado": usuario['id_empleado'],
                "nombre": usuario['nombre'], "apellido": usuario['apellido'], "rol": usuario['rol']}
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
@app.get("/api/productos")
def get_productos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
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
def get_productos_presentaciones():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
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
        cur.execute("""
            UPDATE productos
            SET sku=%s, nombre=%s, tipo=%s, id_categoria=%s, stock_alerta=%s, imagen_url=%s,
                precio_minorista=%s, precio_mayorista=%s
            WHERE id=%s
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

@app.get("/api/distribuidores/{id_dist}/estado_cuenta")
def estado_cuenta_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, fecha::text, total, estado, observaciones FROM pedidos_b2b
            WHERE id_distribuidor = %s AND estado = 'Despachado' ORDER BY fecha DESC
        """, (id_dist,))
        pedidos = fetchall_dict(cur)
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
        cur.execute("""
            SELECT d.id, d.razon_social, d.limite_credito,
                   COALESCE(ped.total_despachado, 0) AS total_despachado,
                   COALESCE(cob.total_cobrado, 0) AS total_cobrado,
                   (COALESCE(ped.total_despachado,0) - COALESCE(cob.total_cobrado,0)) AS saldo
            FROM distribuidores d
            LEFT JOIN (
                SELECT id_distribuidor, SUM(total) AS total_despachado
                FROM pedidos_b2b WHERE estado='Despachado' GROUP BY id_distribuidor
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
            cur.execute("UPDATE productos SET stock_actual = stock_actual - %s WHERE id = %s",
                        (item.cantidad, item.id_producto))
        conn.commit()
        return {"id_pedido": id_pedido}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/historial")
def historial_pedidos_b2b(estado: Optional[str] = None, id_distribuidor: Optional[int] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT p.id, p.fecha::text, p.total, p.estado, p.id_distribuidor, d.razon_social as distribuidor
            FROM pedidos_b2b p
            LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
            WHERE 1=1
        """
        params = []
        if estado:
            query += " AND p.estado = %s"; params.append(estado)
        if id_distribuidor:
            query += " AND p.id_distribuidor = %s"; params.append(id_distribuidor)
        query += " ORDER BY p.fecha DESC"
        cur.execute(query, tuple(params))
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
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/pedidos_b2b/{id}/actualizar")
def actualizar_pedido(id: int, payload: PedidoUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        for v in cur.fetchall():
            cur.execute("UPDATE productos SET stock_actual = stock_actual + %s WHERE id = %s", (v[1], v[0]))
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        cur.execute("UPDATE pedidos_b2b SET total = %s WHERE id = %s", (payload.total, id))
        for item in payload.detalle:
            if item.cantidad > 0:
                cur.execute("""
                    INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario)
                    VALUES (%s,%s,%s,%s)
                """, (id, item.id_producto, item.cantidad, item.precio_unitario))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - %s WHERE id = %s",
                            (item.cantidad, item.id_producto))
        conn.commit()
        return {"status": "ok"}
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
        cur.execute("UPDATE pedidos_b2b SET estado = %s WHERE id = %s", (estado, id))
        if estado == 'Cancelado':
            cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
            for item in cur.fetchall():
                cur.execute("UPDATE productos SET stock_actual = stock_actual + %s WHERE id = %s", (item[1], item[0]))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pedidos_b2b/{id}")
def eliminar_pedido(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        for item in cur.fetchall():
            cur.execute("UPDATE productos SET stock_actual = stock_actual + %s WHERE id = %s", (item[1], item[0]))
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
        cur.execute("""
            SELECT e.id, e.nombre, e.apellido, e.dni, e.rol, e.email, e.telefono,
                   e.activo, u.username, COALESCE(u.acceso_pos, false) AS acceso_pos
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
@app.post("/api/fichaje")
def registrar_fichaje(data: FichajeData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO registros_horarios (id_empleado, tipo, observacion) VALUES (%s,%s,%s)",
                    (data.id_empleado, data.tipo, data.observacion))
        conn.commit()
        return {"status": "ok"}
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

@app.get("/api/reportes/horas_trabajadas")
def reporte_horas_trabajadas(fecha_desde: str, fecha_hasta: str):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            WITH pares AS (
                SELECT e.id as id_empleado, e.nombre, e.apellido,
                       r.fecha_hora as entrada,
                       LEAD(r.fecha_hora) OVER (PARTITION BY r.id_empleado ORDER BY r.fecha_hora) as salida,
                       r.tipo
                FROM registros_horarios r JOIN empleados e ON r.id_empleado = e.id
                WHERE DATE(r.fecha_hora) >= %s AND DATE(r.fecha_hora) <= %s
            )
            SELECT id_empleado, nombre, apellido,
                   ROUND(CAST(SUM(EXTRACT(EPOCH FROM (salida - entrada))/3600.0) AS numeric), 2) as horas_totales
            FROM pares
            WHERE LOWER(tipo) = 'entrada' AND salida IS NOT NULL
            GROUP BY id_empleado, nombre, apellido
            ORDER BY horas_totales DESC
        """, (fecha_desde, fecha_hasta))
        return fetchall_dict(cur)
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
        cur.execute("""
            SELECT a.id, a.fecha::text, a.monto, a.observaciones, e.nombre, e.apellido
            FROM anticipos_empleados a JOIN empleados e ON a.id_empleado = e.id
            WHERE DATE(a.fecha) >= %s AND DATE(a.fecha) <= %s ORDER BY a.fecha DESC
        """, (fecha_desde, fecha_hasta))
        return fetchall_dict(cur)
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
        conn.commit()
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

@app.get("/api/proveedores/{id_prov}/pagos")
def pagos_proveedor(id_prov: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT pg.id, pg.fecha::text, pg.monto, pg.metodo, pg.referencia, pg.notas, pg.id_orden,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM pagos_proveedores pg LEFT JOIN empleados e ON pg.id_empleado = e.id
            WHERE pg.id_proveedor = %s ORDER BY pg.fecha DESC
        """, (id_prov,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/pago")
def registrar_pago_proveedor(pago: NuevoPagoProveedor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pagos_proveedores (id_proveedor, id_orden, id_empleado, monto, metodo, referencia, notas) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (pago.id_proveedor, pago.id_orden, pago.id_empleado, pago.monto, pago.metodo, pago.referencia, pago.notas))
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

class PosCerrarCaja(BaseModel):
    monto_cierre: float = 0.0
    observaciones: Optional[str] = None

class PosItemVenta(BaseModel):
    nombre_producto: str
    cantidad: int
    precio_unitario: float
    id_producto: Optional[int] = None

class PosVenta(BaseModel):
    id_caja: int
    id_local: int
    metodo_pago: str
    total: float
    detalle: List[PosItemVenta]

# ---- LOCALES ----
@app.get("/api/pos/locales")
def pos_listar_locales():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre, direccion FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/locales")
def pos_crear_local(l: PosLocal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
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
        cur.execute("SELECT id, nombre, precio, categoria, COALESCE(stock,0) AS stock, COALESCE(stock_alerta,0) AS stock_alerta FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true ORDER BY categoria NULLS LAST, nombre", (id_local,))
        return fetchall_dict(cur)
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

@app.post("/api/pos/productos/{id}/sumar_stock")
def pos_sumar_stock(id: int, data: PosSumarStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (data.cantidad, id))
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
        cur.execute("SELECT nombre FROM pos_locales WHERE id=%s", (data.id_local,))
        row = cur.fetchone()
        nombre_local = row[0] if row else None
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
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN metodo_pago='Transferencia' THEN total ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN metodo_pago='QR' THEN total ELSE 0 END),0) as qr
            FROM pos_ventas WHERE id_caja=%s
        """, (id_caja,))
        t = cur.fetchone()
        cur.execute("""
            UPDATE pos_cajas SET estado='cerrada', fecha_cierre=NOW(), monto_cierre=%s,
                total_efectivo=%s, total_tarjeta=%s, total_transferencia=%s, total_qr=%s, observaciones=%s
            WHERE id=%s
        """, (data.monto_cierre, t['efectivo'], t['tarjeta'], t['transferencia'], t['qr'], data.observaciones, id_caja))
        conn.commit()
        return {"status": "ok", **dict(t)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ---- VENTAS ----
@app.post("/api/pos/ventas")
def pos_registrar_venta(venta: PosVenta):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total) VALUES (%s,%s,%s,%s) RETURNING id",
                    (venta.id_caja, venta.id_local, venta.metodo_pago, venta.total))
        vid = cur.fetchone()[0]
        for it in venta.detalle:
            cur.execute("INSERT INTO pos_detalle_ventas (id_venta, nombre_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (vid, it.nombre_producto, it.cantidad, it.precio_unitario))
            # Descontar stock del producto (si vino identificado)
            if it.id_producto:
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) - %s WHERE id=%s", (it.cantidad, it.id_producto))
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
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN metodo_pago='Transferencia' THEN total ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN metodo_pago='QR' THEN total ELSE 0 END),0) as qr,
                   COALESCE(SUM(total),0) as total, COUNT(*) as tickets
            FROM pos_ventas WHERE id_caja=%s
        """, (id_caja,))
        resumen = cur.fetchone()
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
        cur.execute("""
            SELECT id, sku, nombre, id_categoria,
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

@app.post("/api/pos/faltantes")
def pos_faltantes_crear(f: FaltanteCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_faltantes (id_local, descripcion, cantidad, id_empleado) VALUES (%s,%s,%s,%s) RETURNING id",
                    (f.id_local, f.descripcion, f.cantidad, f.id_empleado))
        fid = cur.fetchone()[0]
        conn.commit()
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
        q += " ORDER BY fecha DESC LIMIT 300"
        cur.execute(q, tuple(params))
        ventas = fetchall_dict(cur)
        for v in ventas:
            cur.execute("SELECT nombre_producto, cantidad, precio_unitario FROM pos_detalle_ventas WHERE id_venta=%s", (v['id'],))
            v['detalle'] = fetchall_dict(cur)
        return ventas
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/{id_local}/mas_vendidos")
def locales_mas_vendidos(id_local: int, desde: Optional[str] = None, hasta: Optional[str] = None):
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
        q += " GROUP BY d.nombre_producto ORDER BY unidades DESC LIMIT 50"
        cur.execute(q, tuple(params))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ==============================================================================
# REPOSICIONES (el cajero pide stock de productos del local)
# ==============================================================================
class ReposicionItem(BaseModel):
    id_producto: Optional[int] = None
    nombre_producto: str
    cantidad: float

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
        cur.execute("INSERT INTO pos_reposiciones (id_local, id_empleado, notas) VALUES (%s,%s,%s) RETURNING id",
                    (r.id_local, r.id_empleado, r.notas))
        rid = cur.fetchone()[0]
        for it in r.detalle:
            cur.execute("INSERT INTO pos_reposiciones_detalle (id_reposicion, id_producto, nombre_producto, cantidad) VALUES (%s,%s,%s,%s)",
                        (rid, it.id_producto, it.nombre_producto, it.cantidad))
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

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
            cur.execute("SELECT id_producto, nombre_producto, cantidad FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (rep['id'],))
            rep['detalle'] = fetchall_dict(cur)
        return reps
    finally:
        liberar_conexion(conn)

# Marca la reposición como repuesta y suma el stock pedido a cada producto
@app.put("/api/locales/reposiciones/{id}/reponer")
def locales_reposicion_reponer(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT estado FROM pos_reposiciones WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reposición no encontrada")
        if row['estado'] == 'repuesto':
            return {"status": "ya_repuesto"}
        cur.execute("SELECT id_producto, cantidad FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (id,))
        items = fetchall_dict(cur)
        for it in items:
            if it['id_producto']:
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (it['cantidad'], it['id_producto']))
        cur.execute("UPDATE pos_reposiciones SET estado='repuesto' WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
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

@app.get("/login")
def route_login():
    return serve_html("login.html")

@app.get("/admin")
def route_admin():
    return serve_html("panel_admin.html")

@app.get("/catalogo")
def route_catalogo():
    return serve_html("catalogo_stock.html")

@app.get("/insumos")
def route_insumos():
    return serve_html("insumos.html")

@app.get("/produccion")
def route_produccion():
    return serve_html("produccion.html")

@app.get("/produccion-panel")
def route_produccion_panel():
    return serve_html("portal_produccion.html")

@app.get("/proveedores")
def route_proveedores():
    return serve_html("proveedores.html")

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


@app.get("/locales")
def route_locales():
    return serve_html("locales.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
