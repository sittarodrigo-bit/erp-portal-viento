from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import urllib.request
import json
import bcrypt
import uuid as _uuid
import datetime

app = FastAPI(title="API Portal del Viento - Alfajores")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# BASE DE DATOS Y CONFIGURACIONES
# ==============================================================================
DB_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_jqkxN4SRzP5o@ep-still-firefly-apwc5fuw-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "TU_ACCESS_TOKEN_AQUI")

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

def registrar_movimiento_stock(cur, id_producto, cantidad, tipo, origen, motivo=None, id_local=None):
    """Registra un movimiento de stock. cantidad positiva=entrada, negativa=salida."""
    try:
        if id_local is None:
            cur.execute("SELECT id_local, COALESCE(stock,0) AS stock FROM pos_productos WHERE id=%s", (id_producto,))
            row = cur.fetchone()
            if row:
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
        pass

# ==============================================================================
# MODELOS DE DATOS (Pydantic)
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
    character_set: Optional[str] = None
    unidad_medida: str
    stock_minimo: float
    costo_unitario: float = 0.0
    presentacion_compra: Optional[str] = None
    character_bulto: Optional[str] = None
    cantidad_por_presentacion: float = 1.0
    costo_por_bulto: float = 0.0
    id_proveedor: Optional[int] = None

class SumarStock(BaseModel):
    character_set: Optional[str] = None
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
    character_set: Optional[str] = None
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

class LoginPosData(BaseModel):
    username: str
    password: str
    dispositivo: Optional[str] = None

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

class PagoLibreData(BaseModel):
    id_distribuidor: int
    monto: float

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

class ProveedorImportar(BaseModel):
    character_set: Optional[str] = None
    razon_social: str
    cuit: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    notas: Optional[str] = None

class ImportarProveedores(BaseModel):
    proveedores: List[ProveedorImportar]

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

class FaltanteCreate(BaseModel):
    id_local: int
    descripcion: str
    cantidad: Optional[str] = None
    id_empleado: Optional[int] = None

class GastoLocalCreate(BaseModel):
    id_local: int
    concepto: str
    monto: float
    metodo: str = "Efectivo"
    id_empleado: Optional[int] = None
    notas: Optional[str] = None

class ReposicionItem(BaseModel):
    id_producto: Optional[int] = None
    nombre_producto: str
    cantidad: float
    sabor: Optional[str] = None

class ReposicionCreate(BaseModel):
    id_local: int
    id_empleado: Optional[int] = None
    notas: Optional[str] = None
    detalle: List[ReposicionItem]

class ReposicionEditar(BaseModel):
    detalle: List[ReposicionItem]
    notas: Optional[str] = None

class VarianteModel(BaseModel):
    id_producto: int
    nombre: str
    precio: float = 0.0
    factor: float = 1.0

class SaborModel(BaseModel):
    id_producto: int
    nombre: str

class AjusteStock(BaseModel):
    cantidad: float
    motivo: str

class PosProductoImportar(BaseModel):
    nombre: str
    precio: float = 0.0
    categoria: Optional[str] = None
    stock: float = 0.0
    stock_alerta: float = 0.0

class ImportarPosProductos(BaseModel):
    id_local: int
    productos: List[PosProductoImportar]

class ProductoGlobal(BaseModel):
    nombre: str
    precio: float = 0.0
    categoria: Optional[str] = None
    stock: float = 0.0
    stock_alerta: float = 0.0

class FacturaAfip(BaseModel):
    id_venta: Optional[int] = None
    id_local: Optional[int] = None
    tipo_comprobante: int = 6
    doc_tipo: int = 99
    doc_nro: Optional[str] = None
    total: float = 0.0
    neto: Optional[float] = None
    iva: Optional[float] = None

# ==============================================================================
# ENDPOINTS DE AUTENTICACIÓN
# ==============================================================================
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
# CATEGORÍAS Y PRODUCTOS
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
        for p in productos:
            p['presentaciones'] = [{
                'id': p['id'],
                'nombre': 'Unidad',
                'character_unidades': 1,
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

@app.post("/api/productos/{id}/ingresar_stock")
def ingresar_stock_producto(id: int, data: IngresoStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("UPDATE productos SET stock_actual = COALESCE(stock_actual,0) + %s WHERE id=%s RETURNING stock_actual", (data.character_set if hasattr(data, 'character_set') and data.character_set else data.cantidad, id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        conn.commit()
        return {"status": "ok", "stock_actual": float(row['stock_actual'])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

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
            'id': p['id'], 'nombre': 'Unidad', 'character_unidades': 1,
            'precio_minorista': float(p['precio_minorista'] or 0),
            'precio_mayorista': float(p['precio_mayorista'] or 0)
        }]
    finally:
        liberar_conexion(conn)

@app.post("/api/productos/{id}/presentaciones")
def crear_presentacion(id: int, pres: Presentacion):
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
# DISTRIBUIDORES Y PORTAL MAYORISTA (B2B)
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
              dist.localidad, dist.provincia, dist.cp, dist.limite_credito, dist.notes if hasattr(dist, 'notes') else dist.notas))
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

@app.get("/api/distribuidores/{id_dist}/precios")
def precios_para_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id_categoria, porcentaje FROM descuentos_distribuidor WHERE id_distribuidor=%s", (id_dist,))
        desc = {r['id_categoria']: float(r['porcentaje']) for r in fetchall_dict(cur)}
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
            p['presentaciones'] = [{
                'id': p['id'], 'nombre': 'Unidad', 'character_unidades': 1,
                'precio_minorista': float(p['precio_minorista'] or 0),
                'precio_mayorista': p['precio_final']
            }]
        return productos
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/{id_dist}/acceso")
def asignar_acceso_distribuidor(id_dist: int, data: AccesoDistribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        usuario = (data.username or "").strip()
        if not usuario or not data.password:
            raise HTTPException(status_code=400, detail="Usuario y contraseña son obligatorios")
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

@app.post("/api/distribuidores/importar")
def importar_distribuidores(data: ImportarClientes):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
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
                    (razon_social, dni, cuit, telephone, email, direccion, localidad, provincia, cp, limite_credito, notas, aprobado, activo)
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

@app.post("/api/distribuidores/{id_dist}/saldo_inicial")
def cargar_saldo_inicial(id_dist: int, data: SaldoInicial):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
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
# MOVIMIENTOS CONTABLES Y RANKINGS B2B
# ==============================================================================
@app.get("/api/distribuidores/{id_dist}/ranking_productos")
def ranking_productos_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT pr.nombre AS producto, pr.sku,
                   SUM(dp.cantidad) AS unidades,
                   SUM(dp.character_subtotal) AS total
            FROM detalle_pedidos_b2b dp
            JOIN pedidos_b2b p ON dp.id_pedido = p.id
            JOIN productos pr ON dp.id_producto = pr.id
            WHERE p.id_distribuidor = %s AND p.estado = 'Despachado'
            GROUP BY pr.nombre, pr.sku
            ORDER BY unidades DESC
            LIMIT 50
        """, (id_dist,))
        return fetchall_dict(cur)
    except Exception:
        return []
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
            SELECT c.id, c.character_fecha, c.monto, c.metodo, c.referencia, c.notas, c.id_pedido,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM cobros_distribuidores c
            LEFT JOIN empleados e ON c.id_empleado = e.id
            WHERE c.id_distribuidor = %s ORDER BY c.character_fecha DESC
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
# PEDIDOS B2B
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
                        (item.character_unidades if hasattr(item, 'character_unidades') and item.character_unidades else item.cantidad, item.id_producto))
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
# EMPLEADOS, ANTICIPOS Y HORAS
# ==============================================================================
@app.get("/api/empleados")
def get_empleados():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT e.id, e.nombre, e.apellido, e.dni, e.rol, e.email, e.telefono,
                   e.activo, COALESCE(e.valor_hora,0) AS valor_hora,
                   u.username, COALESCE(u.acceso_pos, false) AS acceso_pos
            FROM empleados e LEFT JOIN usuarios u ON u.id_empleado = e.id
            ORDER BY e.apellido, e.nombre
        """)
        return fetchall_dict(cur)
    except Exception:
        return []
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
            UPDATE empleados SET nombre=%s, apellido=%s, dni=%s, rol=%s, telefono=%s, email=%s, valor_hora=%s WHERE id=%s
        """, (emp.nombre, emp.apellido, emp.dni, emp.rol, emp.telefono, emp.email, emp.valor_hora, id_emp))
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
        cur.execute(f"""
            WITH pares AS (
                SELECT e.id as id_empleado, e.nombre, e.apellido, COALESCE(e.character_valor,0) AS valor_hora,
                       r.fecha_hora as entrada,
                       LEAD(r.character_fecha) OVER (PARTITION BY r.id_empleado ORDER BY r.character_fecha) as salida,
                       r.tipo
                FROM registros_horarios r JOIN empleados e ON r.id_empleado = e.id
                WHERE DATE(r.character_fecha) >= %s AND DATE(r.character_fecha) <= %s
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
    except Exception:
        return []
    finally:
        liberar_conexion(conn)

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
            SELECT a.id, a.fecha::text, a.monto, a.observaciones, e.nombre, e.apellido,
                   COALESCE(a.pagado,false) AS pagado, a.fecha_pago::text AS fecha_pago
            FROM anticipos_empleados a JOIN empleados e ON a.id_empleado = e.id
            WHERE DATE(a.fecha) >= %s AND DATE(a.fecha) <= %s ORDER BY a.fecha DESC
        """, (fecha_desde, fecha_hasta))
        return fetchall_dict(cur)
    except Exception:
        return []
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
# INSUMOS Y PROVEEDORES
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
        """, (ins.nombre, ins.character_set if hasattr(ins, 'character_set') and ins.character_set else ins.unidad_medida, ins.stock_minimo, ins.costo_unitario,
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
        cur.execute("INSERT INTO proveedores (razon_social, cuit, email, telephone, direccion, notas) VALUES (%s,%s,%s,%s,%s,%s)",
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
        cur.execute("UPDATE proveedores SET email=%s, telephone=%s, direccion=%s, notas=%s WHERE id=%s",
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
            SELECT pg.id, pg.character_fecha, pg.monto, pg.metodo, pg.referencia, pg.notas, pg.id_orden,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM pagos_proveedores pg LEFT JOIN empleados e ON pg.id_empleado = e.id
            WHERE pg.id_proveedor = %s ORDER BY pg.character_fecha DESC
        """, (id_prov,))
        return fetchall_dict(cur)
    except Exception:
        return []
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
                    INSERT INTO proveedores (razon_social, cuit, email, telephone, direccion, notas)
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

@app.post("/api/insumos/importar")
def importar_insumos(data: ImportarInsumos):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LOWER(TRIM(nombre)) FROM insumos WHERE COALESCE(activo,true)=true")
        existentes = set(r[0] for r in cur.fetchall())
        insertados = 0; salteados = 0; errores = []
        for idx, it in enumerate(data.insumos, start=1):
            nombre = (it.character_set if hasattr(it, 'character_set') and it.character_set else it.nombre or '').strip()
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
# PRODUCCIÓN TERMINADA Y COMPONENTES
# ==============================================================================
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
# TAREAS GENERALES
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
                    (t.character_set if hasattr(t, 'character_set') and t.character_set else t.titulo, t.descripcion, t.fecha_vencimiento, t.prioridad, t.id_empleado_asignado))
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
# SECCIÓN PANEL GASTOS GENERALES
# ==============================================================================
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
        raise HTTPException(status_code=500, detail=f"{e}")
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
        raise HTTPException(status_code=500, detail=f"{e}")
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
        raise HTTPException(status_code=500, detail=f"{e}")
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
        raise HTTPException(status_code=500, detail=f"{e}")
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

@app.post("/api/gastos/recurrentes/{id}/generar")
def gastos_recurrente_generar(id: int, mes: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM gastos_recurrentes WHERE id=%s AND COALESCE(activo,true)=true", (id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Recurrente no encontrado")
        hoy = datetime.date.today()
        anio = hoy.year; m = hoy.month
        if mes:
            partes = mes.split('-')
            anio = int(partes[0]); m = int(partes[1])
        dia = min(int(r['dia_mes'] or 1), 28)
        fecha = "%04d-%02d-%02d" % (anio, m, dia)
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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

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
# MÓDULO INDEPENDIENTE DE PUNTOS DE VENTA (POS LOCALES)
# ==============================================================================
@app.get("/api/pos/productos")
def pos_listar_productos(id_local: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre, precio, categoria, COALESCE(stock,0) AS stock, COALESCE(stock_alerta,0) AS stock_alerta FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true ORDER BY categoria NULLS LAST, nombre", (id_local,))
        productos = fetchall_dict(cur)
        if not productos:
            return []
        ids = [p['id'] for p in productos]
        variantes_por_prod = {}
        try:
            cur.execute("SELECT id, id_producto, nombre, precio, factor FROM pos_producto_variantes WHERE id_producto = ANY(%s) AND COALESCE(activo,true)=true ORDER BY factor", (ids,))
            for v in fetchall_dict(cur):
                variantes_por_prod.setdefault(v['id_producto'], []).append(v)
        except Exception:
            conn.rollback()
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
        raise HTTPException(status_code=500, detail=f"{e}")
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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

@app.put("/api/pos/caja/{id_caja}/cerrar")
def pos_cerrar_caja(id_caja: int, data: PosCerrarCaja):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT id_usuario_apertura FROM pos_cajas WHERE id=%s", (id_caja,))
            row = cur.fetchone()
            id_abrio = row['id_usuario_apertura'] if row else None
        except Exception:
            conn.rollback()
            id_abrio = None
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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/caja/{id_caja}/cerrar_admin")
def cerrar_caja_admin(id_caja: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        t = _totales_por_metodo_caja(cur, id_caja)
        cur.execute("SELECT COALESCE(monto_apertura,0) AS ap, estado FROM pos_cajas WHERE id=%s", (id_caja,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Caja no encontrada")
        if row['estado'] == 'cerrada':
            return {"status": "ya_cerrada"}
        monto_cierre = float(row['ap'] or 0) + float(t['efectivo'] or 0)
        cur.execute("""
            UPDATE pos_cajas SET estado='cerrada', fecha_cierre=NOW(), monto_cierre=%s,
                total_efectivo=%s, total_tarjeta=%s, total_transferencia=%s, total_qr=%s,
                observaciones=COALESCE(observaciones,'') || ' [Cerrada por administrador]'
            WHERE id=%s
        """, (monto_cierre, t['efectivo'], t['tarjeta'], t['transferencia'], t['qr'], id_caja))
        conn.commit()
        return {"status": "ok", **dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

def _totales_por_metodo_caja(cur, id_caja):
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
        if isinstance(r, dict): return r
        return {"efectivo": r[0], "tarjeta": r[1], "transferencia": r[2], "qr": r[3]}
    except Exception:
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(CASE WHEN metodo_pago='Transferencia' THEN total ELSE 0 END),0) as transferencia,
                   COALESCE(SUM(CASE WHEN metodo_pago='QR' THEN total ELSE 0 END),0) as qr
            FROM pos_ventas WHERE id_caja=%s
        """, (id_caja,))
        r = cur.fetchone()
        if isinstance(r, dict): return r
        return {"efectivo": r[0], "tarjeta": r[1], "transferencia": r[2], "qr": r[3]}

@app.post("/api/pos/ventas")
def pos_registrar_venta(venta: PosVenta):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        pagos = venta.pagos or []
        pagos = [p for p in pagos if p.monto and p.monto > 0]
        metodo_guardar = venta.metodo_pago
        if len(pagos) > 1:
            metodo_guardar = "Mixto"
        elif len(pagos) == 1:
            metodo_guardar = pagos[0].metodo_pago
        try:
            cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total, id_empleado, nombre_cajero) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (venta.id_caja, venta.id_local, metodo_guardar, venta.total, venta.id_empleado, venta.nombre_cajero))
        except Exception:
            conn.rollback()
            cur.execute("INSERT INTO pos_ventas (id_caja, id_local, metodo_pago, total) VALUES (%s,%s,%s,%s) RETURNING id",
                        (venta.id_caja, venta.id_local, metodo_guardar, venta.total))
        vid = cur.fetchone()[0]
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
        for it in venta.detalle:
            cur.execute("INSERT INTO pos_detalle_ventas (id_venta, nombre_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (vid, it.nombre_producto, it.character_unidades if hasattr(it, 'character_unidades') else it.cantidad, it.precio_unitario))
            if it.id_producto:
                baja = it.unidades_stock if it.unidades_stock is not None else it.cantidad
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) - %s WHERE id=%s", (baja, it.id_producto))
                registrar_movimiento_stock(cur, it.id_producto, -baja, 'salida', 'venta', motivo='Venta', id_local=venta.id_local)
        conn.commit()
        return {"id_venta": vid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"{e}")
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
        resumen = {"efectivo": t['efectivo'], "tarjeta": t['tarjeta'], "transferencia": t['transferencia'], "qr": t['qr'], "total": tot['total'], "tickets": tot['tickets']}
        cur.execute("""
            SELECT d.nombre_producto, SUM(d.character_unidades if hasattr(d, 'character_unidades') else d.cantidad) as unidades, SUM((d.character_unidades if hasattr(d, 'character_unidades') else d.character_subtotal) * d.precio_unitario) as total
            FROM pos_detalle_ventas d JOIN pos_ventas v ON d.id_venta=v.id
            WHERE v.id_caja=%s GROUP BY d.nombre_producto ORDER BY unidades DESC LIMIT 50
        """, (id_caja,))
        productos = fetchall_dict(cur)
        return {"resumen": dict(resumen), "productos": productos}
    except Exception:
        return {"resumen": {"efectivo": t['efectivo'], "tarjeta": t['tarjeta'], "transferencia": t['transferencia'], "qr": t['qr'], "total": 0, "tickets": 0}, "productos": []}
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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

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
            cur.execute("SELECT id, monto_apertura, nombre_responsable FROM pos_cajas WHERE id_local=%s AND estado='abierta' LIMIT 1", (lid,))
            caja = cur.fetchone()
            caja_abierta = bool(caja)
            efectivo_en_caja = 0
            if caja:
                cur.execute("SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) AS ef FROM pos_ventas WHERE id_caja=%s", (caja['id'],))
                ef = cur.fetchone()['ef']
                efectivo_en_caja = float(caja['monto_apertura'] or 0) + float(ef or 0)
            salida.append({
                "id": lid, "nombre": loc['nombre'], "direccion": loc['direccion'],
                "caja_abierta": caja_abierta, "efectivo_en_caja": efectivo_en_caja,
                "ventas_hoy": 0, "tickets_hoy": 0, "ventas_mes": 0, "tickets_mes": 0,
                "faltantes_pendientes": 0, "gastos_pendientes": 0, "stock_bajo": 0, "reposiciones_pendientes": 0
            })
        return salida
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/{id_local}/ventas")
def locales_ventas(id_local: int, desde: Optional[str] = None, hasta: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, metodo_pago, total, fecha::text FROM pos_ventas WHERE id_local=%s ORDER BY fecha DESC LIMIT 100", (id_local,))
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
        cur.execute("""
            SELECT d.nombre_producto, SUM(d.cantidad) AS unidades, SUM(d.cantidad*d.precio_unitario) AS total
            FROM pos_detalle_ventas d JOIN pos_ventas v ON d.id_venta=v.id
            WHERE v.id_local=%s GROUP BY d.nombre_producto ORDER BY unidades DESC LIMIT 50
        """, (id_local,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/pos/reposiciones")
def pos_reposicion_crear(r: ReposicionCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pos_reposiciones (id_local, id_empleado, notas) VALUES (%s,%s,%s) RETURNING id", (r.id_local, r.id_empleado, r.notas))
        rid = cur.fetchone()[0]
        for it in r.detalle:
            cur.execute("INSERT INTO pos_reposiciones_detalle (id_reposicion, id_producto, nombre_producto, cantidad, sabor) VALUES (%s,%s,%s,%s,%s)",
                        (rid, it.id_producto, it.nombre_producto, it.cantidad, it.sabor))
        conn.commit()
        return {"id": rid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/reposiciones/{id}")
def locales_reposicion_editar(id: int, data: ReposicionEditar):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (id,))
        for it in data.detalle:
            cur.execute("INSERT INTO pos_reposiciones_detalle (id_reposicion, id_producto, nombre_producto, cantidad, sabor) VALUES (%s,%s,%s,%s,%s)",
                        (id, it.id_producto, it.nombre_producto, it.cantidad, it.sabor))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/reposiciones")
def locales_reposiciones(id_local: Optional[int] = None, estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT r.id, r.id_local, l.nombre AS local, r.estado, r.notas, r.fecha::text, r.id_empleado
            FROM pos_reposiciones r LEFT JOIN pos_locales l ON r.id_local = l.id ORDER BY r.fecha DESC
        """)
        reps = fetchall_dict(cur)
        for rep in reps:
            cur.execute("SELECT id_producto, nombre_producto, cantidad, sabor FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (rep['id'],))
            rep['detalle'] = fetchall_dict(cur)
        return reps
    finally:
        liberar_conexion(conn)

@app.put("/api/locales/reposiciones/{id}/reponer")
def locales_reposicion_reponer(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT estado FROM pos_reposiciones WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row or row['estado'] == 'repuesto': return {"status": "ya_repuesto"}
        cur.execute("SELECT id_producto, cantidad FROM pos_reposiciones_detalle WHERE id_reposicion=%s", (id,))
        for it in fetchall_dict(cur):
            if it['id_producto']:
                cur.execute("UPDATE pos_productos SET stock = COALESCE(stock,0) + %s WHERE id=%s", (it['cantidad'], it['id_producto']))
        cur.execute("UPDATE pos_reposiciones SET estado='repuesto' WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
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

@app.post("/api/pos/productos/importar")
def pos_importar_productos(data: ImportarPosProductos):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LOWER(TRIM(nombre)) FROM pos_productos WHERE id_local=%s AND COALESCE(activo,true)=true", (data.id_local,))
        existentes = set(r[0] for r in cur.fetchall())
        insertados = 0; salteados = 0; errores = []
        for idx, p in enumerate(data.productos, start=1):
            nombre = (p.nombre or '').strip()
            if not nombre or nombre.lower() in existentes:
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
                errores.append({"fila": idx, "nombre": nombre, "error": f"{e}"})
                continue
        conn.commit()
        return {"insertados": insertados, "salteados": salteados, "errores": errores}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

@app.get("/api/locales/stock_comparativo")
def locales_stock_comparativo():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre FROM pos_locales WHERE COALESCE(activo,true)=true ORDER BY nombre")
        locales = fetchall_dict(cur)
        cur.execute("""
            SELECT LOWER(TRIM(nombre)) AS clave, MAX(nombre) AS nombre, id_local, COALESCE(SUM(stock),0) AS stock
            FROM pos_productos WHERE COALESCE(activo,true)=true GROUP BY LOWER(TRIM(nombre)), id_local
        """)
        filas = fetchall_dict(cur)
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
        raise HTTPException(status_code=500, detail=f"{e}")
    finally:
        liberar_conexion(conn)

# ==============================================================================
# INTEGRACIÓN CON MERCADO PAGO
# ==============================================================================
@app.post("/api/mp/crear_pago/{id_pedido}")
def mp_crear_pago_pedido(id_pedido: int, request: Request):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM pedidos_b2b WHERE id=%s", (id_pedido,))
        pedido = cur.fetchone()
        if not pedido: raise HTTPException(status_code=404, detail="Pedido no encontrado")
        base_url = str(request.base_url).rstrip("/")
        preference_data = {
            "items": [{"title": f"Pedido #{id_pedido} - Portal del Viento", "quantity": 1, "unit_price": float(pedido['total'])}],
            "back_urls": {"success": f"{base_url}/b2b?pago=ok", "failure": f"{base_url}/b2b?pago=error", "pending": f"{base_url}/b2b?pago=pendiente"},
            "auto_return": "approved", "external_reference": f"pedido_{id_pedido}"
        }
        req = urllib.request.Request("https://api.mercadopago.com/checkout/preferences", data=json.dumps(preference_data).encode("utf-8"), headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return {"link": data["init_point"]}
    except Exception:
        raise HTTPException(status_code=500, detail="Error al conectar con Mercado Pago")
    finally:
        liberar_conexion(conn)

@app.post("/api/mp/crear_pago_libre")
def mp_crear_pago_libre(data: PagoLibreData, request: Request):
    base_url = str(request.base_url).rstrip("/")
    preference_data = {
        "items": [{"title": "Pago de Saldo - Portal del Viento", "quantity": 1, "unit_price": float(data.monto)}],
        "back_urls": {"success": f"{base_url}/b2b?pago=ok", "failure": f"{base_url}/b2b?pago=error", "pending": f"{base_url}/b2b?pago=pendiente"},
        "auto_return": "approved", "external_reference": f"libre_{data.id_distribuidor}"
    }
    req = urllib.request.Request("https://api.mercadopago.com/checkout/preferences", data=json.dumps(preference_data).encode("utf-8"), headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            mp_data = json.loads(response.read().decode())
            return {"link": mp_data["init_point"], "preferencia_guardada": True}
    except Exception:
        raise HTTPException(status_code=500, detail="Error al conectar con Mercado Pago")

@app.post("/api/mp/verificar_pagos/{id_distribuidor}")
def mp_verificar_pagos(id_distribuidor: int, payment_id: Optional[str] = None, status: Optional[str] = None, external_reference: Optional[str] = None):
    if not payment_id or status != "approved": return {"status": "ignorado"}
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cobros_distribuidores WHERE referencia=%s", (str(payment_id),))
        c = cur.fetchone()[0]
        if c == 0:
            req = urllib.request.Request(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}, method="GET")
            try:
                with urllib.request.urlopen(req) as response: mp_data = json.loads(response.read().decode())
            except Exception: mp_data = {}
            if mp_data.get("status") == "approved":
                monto = float(mp_data.get("transaction_amount") or 0)
                ext_ref = external_reference or mp_data.get("external_reference") or ""
                if ext_ref.startswith("pedido_"):
                    id_pedido = int(ext_ref.split("_")[1])
                    cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                                   VALUES (%s,%s,%s,%s,%s,%s)""", (id_distribuidor, id_pedido, monto, 'Mercado Pago', str(payment_id), 'Pago online aprobado'))
                else:
                    cur.execute("""INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, monto, metodo, referencia, notas)
                                   VALUES (%s,NULL,%s,%s,%s,%s)""", (id_distribuidor, monto, 'Mercado Pago', str(payment_id), 'Pago a cuenta online aprobado'))
                conn.commit()
                return {"status": "registrado", "monto": monto}
        return {"status": "ya_registrado" if c > 0 else "no_aprobado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ==============================================================================
# RUTAS WEB (HTML)
# ==============================================================================
def serve_html(filename: str):
    path = os.path.join(os.path.dirname(__file__), 'pantallas', filename)
    if not os.path.exists(path): return HTMLResponse(content=f"<h1>Archivo no encontrado: {filename}</h1>", status_code=404)
    with open(path, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})

@app.get("/")
def index(): return serve_html("login.html")
@app.get("/login")
def route_login(): return serve_html("login.html")
@app.get("/admin")
def route_admin(): return serve_html("panel_admin.html")
@app.get("/catalogo")
def route_catalogo(): return serve_html("catalogo_stock.html")
@app.get("/insumos")
def route_insumos(): return serve_html("insumos.html")
@app.get("/produccion")
def route_produccion(): return serve_html("produccion.html")
@app.get("/produccion-panel")
def route_produccion_panel(): return serve_html("portal_produccion.html")
@app.get("/proveedores")
def route_proveedores(): return serve_html("proveedores.html")
@app.get("/distribuidores")
def route_distribuidores(): return serve_html("distribuidores.html")
@app.get("/historial-b2b")
def route_historial_b2b(): return serve_html("historial_b2b.html")
@app.get("/empleados")
def route_empleados(): return serve_html("empleados.html")
@app.get("/reportes")
def route_reportes(): return serve_html("reportes.html")
@app.get("/configuracion")
def route_configuracion(): return serve_html("configuracion.html")
@app.get("/b2b")
def route_b2b(): return serve_html("portal_distribuidores_v2.html")
@app.get("/mayoristas")
def route_mayoristas(): return serve_html("portal_distribuidores_v2.html")
@app.get("/fichajes")
def route_fichajes(): return serve_html("portal_fichaje.html")
@app.get("/qr")
def route_qr(): return serve_html("qr_fichaje.html")
@app.get("/pos")
def route_pos(): return serve_html("pos.html")
@app.get("/pos-login")
def route_pos_login(): return serve_html("pos_login.html")
@app.get("/gastos")
def route_gastos(): return serve_html("gastos.html")
@app.get("/locales")
def route_locales(): return serve_html("locales.html")
@app.get("/carga-stock")
def route_carga_stock(): return serve_html("carga_stock_pos.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
