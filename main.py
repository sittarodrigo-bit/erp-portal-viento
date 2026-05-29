from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
import bcrypt
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="ERP Portal del Viento")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = "postgresql://neondb_owner:npg_jqkxN4SRzP5o@ep-still-firefly-apwc5fuw-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require"

from psycopg2 import pool as pg_pool

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=2, maxconn=10, dsn=DATABASE_URL
        )
    return _pool

def obtener_conexion():
    conn = get_pool().getconn()
    conn.autocommit = False
    
    # Forzamos la zona horaria correcta para todos los registros
    cur = conn.cursor()
    cur.execute("SET TIME ZONE 'America/Argentina/Mendoza';")
    cur.close()
    
    return conn

def liberar_conexion(conn):
    try:
        get_pool().putconn(conn)
    except Exception:
        pass

def fetchall_dict(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def fetchone_dict(cursor):
    cols = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    return dict(zip(cols, row)) if row else None

# ═══════════════════════════════════════════════════════════════
#  MODELOS
# ═══════════════════════════════════════════════════════════════

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

class FichajeData(BaseModel):
    id_empleado: int
    tipo: str
    observacion: Optional[str] = None

class AperturaCaja(BaseModel):
    id_sucursal: int
    id_empleado: int
    monto_apertura: float

class CierreCaja(BaseModel):
    id_empleado: int
    monto_cierre: float
    observaciones: Optional[str] = None

class NuevoInsumo(BaseModel):
    nombre: str
    unidad_medida: str
    stock_minimo: float
    costo_unitario: float = 0.0

class NuevoProducto(BaseModel):
    sku: str
    nombre: str
    tipo: str = "propio"
    stock_inicial: int = 0

class ActualizarStock(BaseModel):
    nuevo_stock: int

class Presentacion(BaseModel):
    nombre: str
    cantidad_unidades: int
    precio_minorista: float
    precio_mayorista: float

class NuevoDistribuidor(BaseModel):
    razon_social: str
    cuit: str
    limite_credito: float

class ActualizarCredito(BaseModel):
    nuevo_limite: float

class ItemReceta(BaseModel):
    id_insumo: int
    cantidad_necesaria: float

class GuardarReceta(BaseModel):
    id_producto: int
    items: List[ItemReceta]

class OrdenProduccion(BaseModel):
    id_producto: int
    id_empleado: int
    cantidad_producida: int
    observaciones: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    costo_total: float = 0.0
    id_categoria: Optional[int] = None

class DetalleVenta(BaseModel):
    id_producto: int
    id_presentacion: int
    cantidad: int
    precio_unitario: float
    unidades_por_presentacion: int = 1

class NuevaVenta(BaseModel):
    id_sucursal: int
    id_empleado: int
    id_caja: Optional[int] = None
    es_fiscal: bool
    metodo_pago: str
    total: float
    detalle: List[DetalleVenta]

class DetallePedido(BaseModel):
    id_producto: int
    id_presentacion: Optional[int] = None
    cantidad: int
    precio_unitario: float
    unidades_por_presentacion: int = 1

class NuevoPedidoB2B(BaseModel):
    id_distribuidor: int
    total: float
    detalle: List[DetallePedido]

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

class ItemOrdenCompra(BaseModel):
    id_insumo: int
    cantidad: float
    precio_unitario: float

class NuevaOrdenCompra(BaseModel):
    id_proveedor: int
    id_empleado: int
    fecha_entrega_estimada: Optional[str] = None
    notas: Optional[str] = None
    detalle: List[ItemOrdenCompra]

class NuevoPago(BaseModel):
    id_proveedor: int
    id_orden: Optional[int] = None
    id_empleado: int
    monto: float
    metodo: str
    referencia: Optional[str] = None
    notas: Optional[str] = None

class PrecioInsumo(BaseModel):
    id_insumo: int
    precio_unitario: float

class NuevaSucursal(BaseModel):
    nombre: str
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None

# ═══════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════

@app.post("/api/login")
def login(data: LoginData):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.password_hash, u.activo,
                   e.id as id_empleado, e.nombre, e.apellido, e.rol
            FROM usuarios u JOIN empleados e ON u.id_empleado = e.id
            WHERE u.username = %s
        """, (data.username,))
        usuario = fetchone_dict(cur)
        if not usuario or not usuario['activo']:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        if not bcrypt.checkpw(data.password.encode(), usuario['password_hash'].encode()):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        return {"status": "ok", "id_empleado": usuario['id_empleado'], "nombre": usuario['nombre'], "apellido": usuario['apellido'], "rol": usuario['rol']}
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  SUCURSALES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/sucursales")
def listar_sucursales():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, direccion, telefono, email, activo FROM sucursales ORDER BY id")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/sucursales/nueva")
def crear_sucursal(s: NuevaSucursal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO sucursales (nombre, direccion, telefono, email) VALUES (%s,%s,%s,%s)",
                    (s.nombre, s.direccion, s.telefono, s.email))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/sucursales/{id_suc}")
def actualizar_sucursal(id_suc: int, s: NuevaSucursal):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE sucursales SET nombre=%s, direccion=%s, telefono=%s, email=%s WHERE id=%s",
                    (s.nombre, s.direccion, s.telefono, s.email, id_suc))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  EMPLEADOS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/empleados")
def listar_empleados():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.nombre, e.apellido, e.dni, e.rol, e.email, e.telefono,
                   e.fecha_alta::text, e.activo, u.username
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

@app.put("/api/empleados/{id_emp}/estado")
def cambiar_estado_empleado(id_emp: int, activo: bool = Query(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE empleados SET activo=%s WHERE id=%s", (activo, id_emp))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  FICHAJES
# ═══════════════════════════════════════════════════════════════

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
        cur = conn.cursor()
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
        # ═══════════════════════════════════════════════════════════════
#  REPORTE DE HORAS TRABAJADAS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/reportes/horas_trabajadas")
def reporte_horas_trabajadas(fecha_desde: str = Query(...), fecha_hasta: str = Query(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            WITH pares AS (
                SELECT 
                    e.id as id_empleado,
                    e.nombre,
                    e.apellido,
                    r.fecha_hora as entrada,
                    LEAD(r.fecha_hora) OVER (PARTITION BY r.id_empleado ORDER BY r.fecha_hora) as salida,
                    r.tipo
                FROM registros_horarios r
                JOIN empleados e ON r.id_empleado = e.id
                WHERE DATE(r.fecha_hora) >= %s AND DATE(r.fecha_hora) <= %s
            )
            SELECT 
                id_empleado,
                nombre,
                apellido,
                ROUND(CAST(SUM(EXTRACT(EPOCH FROM (salida - entrada))/3600.0) AS numeric), 2) as horas_totales
            FROM pares
            WHERE tipo = 'Entrada' AND salida IS NOT NULL
            GROUP BY id_empleado, nombre, apellido
            ORDER BY horas_totales DESC
        """, (fecha_desde, fecha_hasta))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  ANTICIPOS DE SUELDO
# ═══════════════════════════════════════════════════════════════

class NuevoAnticipo(BaseModel):
    id_empleado: int
    monto: float
    observaciones: Optional[str] = None

@app.post("/api/anticipos/nuevo")
def registrar_anticipo(data: NuevoAnticipo):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Se asegura de crear la tabla si no existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS anticipos_empleados (
                id SERIAL PRIMARY KEY,
                id_empleado INTEGER REFERENCES empleados(id),
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                monto DECIMAL(10,2) NOT NULL,
                observaciones TEXT
            )
        """)
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
def listar_anticipos(fecha_desde: str = Query(...), fecha_hasta: str = Query(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Se asegura de crear la tabla si entran a mirar antes de registrar uno
        cur.execute("""
            CREATE TABLE IF NOT EXISTS anticipos_empleados (
                id SERIAL PRIMARY KEY,
                id_empleado INTEGER REFERENCES empleados(id),
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                monto DECIMAL(10,2) NOT NULL,
                observaciones TEXT
            )
        """)
        conn.commit()
        
        cur.execute("""
            SELECT a.id, a.fecha::text, a.monto, a.observaciones, e.nombre, e.apellido 
            FROM anticipos_empleados a
            JOIN empleados e ON a.id_empleado = e.id
            WHERE DATE(a.fecha) >= %s AND DATE(a.fecha) <= %s
            ORDER BY a.fecha DESC
        """, (fecha_desde, fecha_hasta))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  CAJAS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/caja/estado")
def estado_caja(id_sucursal: int = 1):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.monto_apertura, c.fecha_apertura::text, c.estado, e.nombre, e.apellido
            FROM cajas c JOIN empleados e ON c.id_empleado_apertura = e.id
            WHERE c.id_sucursal = %s AND c.estado = 'abierta'
            ORDER BY c.fecha_apertura DESC LIMIT 1
        """, (id_sucursal,))
        caja = fetchone_dict(cur)
        if not caja: return {"caja_abierta": False}
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta,
                   COALESCE(SUM(total),0) as total, COUNT(*) as tickets
            FROM ventas WHERE id_caja = %s
        """, (caja['id'],))
        resumen = fetchone_dict(cur)
        return {"caja_abierta": True, **caja, **resumen}
    finally:
        liberar_conexion(conn)

@app.post("/api/caja/abrir")
def abrir_caja(data: AperturaCaja):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM cajas WHERE id_sucursal=%s AND estado='abierta'", (data.id_sucursal,))
        if cur.fetchone(): raise HTTPException(status_code=400, detail="Ya hay una caja abierta")
        cur.execute("INSERT INTO cajas (id_sucursal, id_empleado_apertura, monto_apertura) VALUES (%s,%s,%s) RETURNING id",
                    (data.id_sucursal, data.id_empleado, data.monto_apertura))
        id_caja = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id_caja": id_caja}
    except HTTPException: raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.post("/api/caja/cerrar")
def cerrar_caja(id_caja: int = Query(...), data: CierreCaja = ...):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END),0) as efectivo,
                   COALESCE(SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END),0) as tarjeta
            FROM ventas WHERE id_caja = %s
        """, (id_caja,))
        totales = fetchone_dict(cur)
        cur.execute("""
            UPDATE cajas SET estado='cerrada', fecha_cierre=NOW(),
            id_empleado_cierre=%s, monto_cierre=%s, total_efectivo=%s, total_tarjeta=%s, observaciones=%s
            WHERE id=%s
        """, (data.id_empleado, data.monto_cierre, totales['efectivo'], totales['tarjeta'], data.observaciones, id_caja))
        conn.commit()
        return {"status": "ok", "total_efectivo": float(totales['efectivo']), "total_tarjeta": float(totales['tarjeta'])}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  PRODUCTOS Y PRESENTACIONES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/productos")
def obtener_productos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.sku, p.nombre, p.tipo, p.stock_actual as stock,
                   p.id_categoria, p.stock_alerta,
                   COALESCE(pr.precio_minorista, 0) as precio_minorista,
                   COALESCE(pr.precio_mayorista, 0) as precio_mayorista
            FROM productos p
            LEFT JOIN LATERAL (
                SELECT precio_minorista, precio_mayorista FROM presentaciones
                WHERE id_producto = p.id AND nombre = 'Unidad' LIMIT 1
            ) pr ON true
            WHERE p.activo=true ORDER BY p.nombre
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/productos/{id_producto}/presentaciones")
def obtener_presentaciones(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nombre, cantidad_unidades, precio_minorista, precio_mayorista, activo
            FROM presentaciones WHERE id_producto=%s AND activo=true ORDER BY cantidad_unidades
        """, (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/productos_nuevo")
def crear_producto(prod: NuevoProducto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO productos (sku, nombre, tipo, stock_actual) VALUES (%s,%s,%s,%s) RETURNING id",
                    (prod.sku, prod.nombre, prod.tipo, prod.stock_inicial))
        id_prod = cur.fetchone()[0]
        # Crear presentación Unidad por defecto
        cur.execute("INSERT INTO presentaciones (id_producto, nombre, cantidad_unidades, precio_minorista, precio_mayorista) VALUES (%s,'Unidad',1,0,0)",
                    (id_prod,))
        conn.commit()
        return {"status": "ok", "id_producto": id_prod}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.post("/api/productos/{id_producto}/presentaciones")
def crear_presentacion(id_producto: int, pres: Presentacion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO presentaciones (id_producto, nombre, cantidad_unidades, precio_minorista, precio_mayorista)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (id_producto, pres.nombre, pres.cantidad_unidades, pres.precio_minorista, pres.precio_mayorista))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/presentaciones/{id_pres}")
def actualizar_presentacion(id_pres: int, pres: Presentacion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE presentaciones SET nombre=%s, cantidad_unidades=%s,
            precio_minorista=%s, precio_mayorista=%s WHERE id=%s
        """, (pres.nombre, pres.cantidad_unidades, pres.precio_minorista, pres.precio_mayorista, id_pres))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/presentaciones/{id_pres}")
def eliminar_presentacion(id_pres: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE presentaciones SET activo=false WHERE id=%s", (id_pres,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/productos/{id_producto}/stock")
def actualizar_stock(id_producto: int, body: ActualizarStock):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET stock_actual=%s WHERE id=%s", (body.nuevo_stock, id_producto))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/productos/con_presentaciones")
def productos_con_presentaciones():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, sku, nombre, tipo, stock_actual as stock, id_categoria, stock_alerta, imagen_url FROM productos WHERE activo=true ORDER BY nombre")
        productos = fetchall_dict(cur)
        for p in productos:
            cur.execute("""
                SELECT id, nombre, cantidad_unidades, precio_minorista, precio_mayorista
                FROM presentaciones WHERE id_producto=%s AND activo=true ORDER BY cantidad_unidades
            """, (p['id'],))
            p['presentaciones'] = fetchall_dict(cur)
        return productos
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  RECETAS Y PRODUCCION
# ═══════════════════════════════════════════════════════════════

@app.get("/api/recetas/{id_producto}")
def obtener_receta(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT r.id, r.id_insumo, i.nombre as insumo, i.unidad_medida as unidad, r.cantidad_necesaria
            FROM recetas r JOIN insumos i ON r.id_insumo = i.id WHERE r.id_producto = %s
        """, (id_producto,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/recetas/guardar")
def guardar_receta(data: GuardarReceta):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM recetas WHERE id_producto=%s", (data.id_producto,))
        for item in data.items:
            cur.execute("INSERT INTO recetas (id_producto, id_insumo, cantidad_necesaria) VALUES (%s,%s,%s)",
                        (data.id_producto, item.id_insumo, item.cantidad_necesaria))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.post("/api/produccion/registrar")
def registrar_produccion(orden: OrdenProduccion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ordenes_produccion
            (id_producto, id_empleado, cantidad_producida, observaciones,
             fecha_vencimiento, costo_total, id_categoria)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (orden.id_producto, orden.id_empleado, orden.cantidad_producida,
              orden.observaciones, orden.fecha_vencimiento, orden.costo_total,
              orden.id_categoria))
        
        cur.execute("SELECT id_insumo, cantidad_necesaria FROM recetas WHERE id_producto=%s", (orden.id_producto,))
        for item in cur.fetchall():
            consumo = float(item[1]) * orden.cantidad_producida
            cur.execute("UPDATE insumos SET stock_actual = stock_actual - %s WHERE id=%s", (consumo, item[0]))
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
        cur = conn.cursor()
        cur.execute("""
            SELECT o.id, o.fecha::text, o.cantidad_producida, o.observaciones,
                   o.fecha_vencimiento::text, o.costo_total, o.id_categoria, o.id_empleado,
                   p.nombre as producto, p.sku, p.id_categoria,
                   COALESCE(pr.precio_minorista, 0) as precio_venta_unit,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM ordenes_produccion o
            JOIN productos p ON o.id_producto = p.id
            JOIN empleados e ON o.id_empleado = e.id
            LEFT JOIN LATERAL (
                SELECT precio_minorista FROM presentaciones
                WHERE id_producto = p.id AND nombre = 'Unidad'
                LIMIT 1
            ) pr ON true
            ORDER BY o.fecha DESC LIMIT 100
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  DISTRIBUIDORES
# ═══════════════════════════════════════════════════════════════

@app.post("/api/distribuidores_nuevo")
def crear_distribuidor(dist: NuevoDistribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO distribuidores (razon_social, cuit, limite_credito) VALUES (%s,%s,%s)",
                    (dist.razon_social, dist.cuit, dist.limite_credito))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/distribuidores/{id_dist}/credito")
def actualizar_credito(id_dist: int, body: ActualizarCredito):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE distribuidores SET limite_credito=%s WHERE id=%s", (body.nuevo_limite, id_dist))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/distribuidores/{id_dist}")
def eliminar_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE distribuidores SET activo=false WHERE id=%s", (id_dist,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  VENTAS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/ventas")
def registrar_venta(venta: NuevaVenta):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO ventas (id_sucursal, id_empleado, id_caja, es_fiscal, metodo_pago, total) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (venta.id_sucursal, venta.id_empleado, venta.id_caja, venta.es_fiscal, venta.metodo_pago, venta.total))
        id_venta = cur.fetchone()[0]
        for item in venta.detalle:
            cur.execute("INSERT INTO detalle_ventas (id_venta, id_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (id_venta, item.id_producto, item.cantidad, item.precio_unitario))
            unidades_reales = item.cantidad * item.unidades_por_presentacion
            cur.execute("UPDATE productos SET stock_actual = stock_actual - %s WHERE id=%s",
                        (unidades_reales, item.id_producto))
        conn.commit()
        return {"status": "ok", "id_venta": id_venta}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  PEDIDOS B2B
# ═══════════════════════════════════════════════════════════════

@app.post("/api/pedidos_b2b")
def crear_pedido_b2b(pedido: NuevoPedidoB2B):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO pedidos_b2b (id_distribuidor, total) VALUES (%s,%s) RETURNING id",
                    (pedido.id_distribuidor, pedido.total))
        id_pedido = cur.fetchone()[0]
        for item in pedido.detalle:
            cur.execute("INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (id_pedido, item.id_producto, item.cantidad, item.precio_unitario))
        conn.commit()
        return {"status": "ok", "id_pedido": id_pedido}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/historial")
def historial_pedidos_b2b(estado: Optional[str] = None, id_distribuidor: Optional[int] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        filtros, params = [], []
        if estado: filtros.append("p.estado = %s"); params.append(estado)
        if id_distribuidor: filtros.append("p.id_distribuidor = %s"); params.append(id_distribuidor)
        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        cur.execute(f"""
            SELECT p.id, p.fecha::text, p.total, p.estado, d.razon_social as distribuidor
            FROM pedidos_b2b p JOIN distribuidores d ON p.id_distribuidor = d.id
            {where} ORDER BY p.fecha DESC LIMIT 200
        """, params)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/pedidos_b2b/{id_pedido}/detalle")
def detalle_pedido_b2b(id_pedido: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT dp.id_producto, p.nombre as producto, p.sku,
                   dp.cantidad, dp.precio_unitario, (dp.cantidad * dp.precio_unitario) as subtotal
            FROM detalle_pedidos_b2b dp JOIN productos p ON dp.id_producto = p.id WHERE dp.id_pedido = %s
        """, (id_pedido,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.put("/api/pedidos/{id_pedido}/estado")
def cambiar_estado_pedido(id_pedido: int, estado: str = Query(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE pedidos_b2b SET estado=%s WHERE id=%s", (estado, id_pedido))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  ADMIN / REPORTES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/admin/resumen_hoy")
def resumen_hoy():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(total),0) as rec, COUNT(*) as tickets FROM ventas WHERE DATE(fecha)=CURRENT_DATE")
        r = fetchone_dict(cur)
        cur.execute("SELECT COUNT(*) as cant FROM pedidos_b2b WHERE estado='Pendiente'")
        p = fetchone_dict(cur)
        return {"recaudacion_hoy": float(r['rec']), "tickets_hoy": r['tickets'], "pedidos_pendientes": p['cant']}
    finally:
        liberar_conexion(conn)

@app.get("/api/admin/pedidos_pendientes")
def pedidos_pendientes():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id as id_pedido, d.razon_social as distribuidor, p.estado, p.total
            FROM pedidos_b2b p JOIN distribuidores d ON p.id_distribuidor = d.id
            WHERE p.estado NOT IN ('Despachado','Cancelado') ORDER BY p.fecha DESC LIMIT 20
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/ventas_por_dia")
def ventas_por_dia(dias: int = 30):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DATE(fecha)::text as dia, COUNT(*) as tickets, SUM(total) as total,
                   SUM(CASE WHEN metodo_pago='Efectivo' THEN total ELSE 0 END) as efectivo,
                   SUM(CASE WHEN metodo_pago='Tarjeta' THEN total ELSE 0 END) as tarjeta
            FROM ventas WHERE fecha >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(fecha) ORDER BY dia DESC
        """, (dias,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/productos_mas_vendidos")
def productos_mas_vendidos(dias: int = 30):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.nombre, p.sku, SUM(dv.cantidad) as unidades, SUM(dv.cantidad * dv.precio_unitario) as total
            FROM detalle_ventas dv JOIN productos p ON dv.id_producto = p.id JOIN ventas v ON dv.id_venta = v.id
            WHERE v.fecha >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY p.id, p.nombre, p.sku ORDER BY unidades DESC LIMIT 10
        """, (dias,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/reportes/ventas_por_sucursal")
def ventas_por_sucursal(dias: int = 30):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.nombre as sucursal,
                   COUNT(v.id) as tickets,
                   COALESCE(SUM(v.total), 0) as total,
                   COALESCE(SUM(CASE WHEN v.metodo_pago='Efectivo' THEN v.total ELSE 0 END), 0) as efectivo,
                   COALESCE(SUM(CASE WHEN v.metodo_pago='Tarjeta'  THEN v.total ELSE 0 END), 0) as tarjeta
            FROM sucursales s
            LEFT JOIN ventas v ON v.id_sucursal = s.id
                AND v.fecha >= CURRENT_DATE - INTERVAL '%s days'
            WHERE s.activo = true
            GROUP BY s.id, s.nombre ORDER BY total DESC
        """, (dias,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  PROVEEDORES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/proveedores")
def listar_proveedores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.razon_social, p.cuit, p.email, p.telefono, p.direccion, p.notas, p.activo,
                   COUNT(DISTINCT pi.id_insumo) as cant_insumos,
                   COUNT(DISTINCT oc.id) as cant_ordenes
            FROM proveedores p
            LEFT JOIN proveedor_insumos pi ON pi.id_proveedor = p.id
            LEFT JOIN ordenes_compra oc ON oc.id_proveedor = p.id
            WHERE p.activo = true GROUP BY p.id ORDER BY p.razon_social
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

@app.get("/api/proveedores/{id_prov}/insumos")
def insumos_proveedor(id_prov: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pi.id, pi.id_insumo, i.nombre, i.unidad_medida as unidad, i.stock_actual as stock, pi.precio_unitario
            FROM proveedor_insumos pi JOIN insumos i ON pi.id_insumo = i.id
            WHERE pi.id_proveedor = %s ORDER BY i.nombre
        """, (id_prov,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/{id_prov}/insumos")
def asociar_insumo(id_prov: int, data: PrecioInsumo):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO proveedor_insumos (id_proveedor, id_insumo, precio_unitario)
            VALUES (%s,%s,%s)
            ON CONFLICT (id_proveedor, id_insumo) DO UPDATE SET precio_unitario = EXCLUDED.precio_unitario
        """, (id_prov, data.id_insumo, data.precio_unitario))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/proveedores/{id_prov}/insumos/{id_insumo}")
def desasociar_insumo(id_prov: int, id_insumo: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM proveedor_insumos WHERE id_proveedor=%s AND id_insumo=%s", (id_prov, id_insumo))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/ordenes_compra")
def listar_ordenes_compra(id_proveedor: Optional[int] = None, estado: Optional[str] = None):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        filtros, params = [], []
        if id_proveedor: filtros.append("oc.id_proveedor=%s"); params.append(id_proveedor)
        if estado: filtros.append("oc.estado=%s"); params.append(estado)
        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        cur.execute(f"""
            SELECT oc.id, oc.fecha::text, oc.fecha_entrega_estimada::text, oc.estado, oc.total, oc.notas,
                   p.razon_social as proveedor, e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM ordenes_compra oc
            JOIN proveedores p ON oc.id_proveedor = p.id
            JOIN empleados e ON oc.id_empleado = e.id
            {where} ORDER BY oc.fecha DESC LIMIT 200
        """, params)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/ordenes_compra/{id_orden}/detalle")
def detalle_orden_compra(id_orden: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.id_insumo, i.nombre as insumo, i.unidad_medida as unidad,
                   d.cantidad, d.precio_unitario, (d.cantidad * d.precio_unitario) as subtotal
            FROM detalle_ordenes_compra d JOIN insumos i ON d.id_insumo = i.id WHERE d.id_orden = %s
        """, (id_orden,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/ordenes_compra/nueva")
def crear_orden_compra(orden: NuevaOrdenCompra):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        total = sum(i.cantidad * i.precio_unitario for i in orden.detalle)
        cur.execute("INSERT INTO ordenes_compra (id_proveedor, id_empleado, fecha_entrega_estimada, total, notas) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (orden.id_proveedor, orden.id_empleado, orden.fecha_entrega_estimada, total, orden.notas))
        id_orden = cur.fetchone()[0]
        for item in orden.detalle:
            cur.execute("INSERT INTO detalle_ordenes_compra (id_orden, id_insumo, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                        (id_orden, item.id_insumo, item.cantidad, item.precio_unitario))
        conn.commit()
        return {"status": "ok", "id_orden": id_orden}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.put("/api/ordenes_compra/{id_orden}/estado")
def cambiar_estado_orden(id_orden: int, estado: str = Query(...)):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ordenes_compra SET estado=%s WHERE id=%s", (estado, id_orden))
        if estado == "Recibida":
            cur.execute("SELECT id_insumo, cantidad FROM detalle_ordenes_compra WHERE id_orden=%s", (id_orden,))
            for item in cur.fetchall():
                cur.execute("UPDATE insumos SET stock_actual = stock_actual + %s WHERE id=%s", (item[1], item[0]))
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
        cur = conn.cursor()
        cur.execute("""
            SELECT pg.id, pg.fecha::text, pg.monto, pg.metodo, pg.referencia, pg.notas, pg.id_orden,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM pagos_proveedores pg JOIN empleados e ON pg.id_empleado = e.id
            WHERE pg.id_proveedor = %s ORDER BY pg.fecha DESC
        """, (id_prov,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/proveedores/pago")
def registrar_pago(pago: NuevoPago):
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


# ═══════════════════════════════════════════════════════════════
#  MODELOS NUEVOS
# ═══════════════════════════════════════════════════════════════

class NuevaTarea(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    prioridad: str = "media"
    id_empleado_asignado: Optional[int] = None

class NuevoCobroDistribuidor(BaseModel):
    id_distribuidor: int
    id_pedido: Optional[int] = None
    id_empleado: int
    monto: float
    metodo: str
    referencia: Optional[str] = None
    notas: Optional[str] = None

# ═══════════════════════════════════════════════════════════════
#  TAREAS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/tareas")
def listar_tareas():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, t.titulo, t.descripcion, t.fecha_vencimiento::text,
                   t.prioridad, t.estado, t.fecha_creacion::text,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM tareas t
            LEFT JOIN empleados e ON t.id_empleado_asignado = e.id
            WHERE t.estado = 'pendiente'
            ORDER BY
                CASE t.prioridad WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
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
        cur.execute(
            "INSERT INTO tareas (titulo, descripcion, fecha_vencimiento, prioridad, id_empleado_asignado) VALUES (%s,%s,%s,%s,%s)",
            (t.titulo, t.descripcion, t.fecha_vencimiento, t.prioridad, t.id_empleado_asignado)
        )
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

# ═══════════════════════════════════════════════════════════════
#  COBROS DISTRIBUIDORES
# ═══════════════════════════════════════════════════════════════

@app.post("/api/cobros_distribuidores/nuevo")
def registrar_cobro_distribuidor(cobro: NuevoCobroDistribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cobros_distribuidores (id_distribuidor, id_pedido, id_empleado, monto, metodo, referencia, notas) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cobro.id_distribuidor, cobro.id_pedido, cobro.id_empleado, cobro.monto, cobro.metodo, cobro.referencia, cobro.notas)
        )
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
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.fecha::text, c.monto, c.metodo, c.referencia, c.notas, c.id_pedido,
                   e.nombre as empleado_nombre, e.apellido as empleado_apellido
            FROM cobros_distribuidores c JOIN empleados e ON c.id_empleado = e.id
            WHERE c.id_distribuidor = %s ORDER BY c.fecha DESC
        """, (id_dist,))
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  ENDPOINTS TABLERO
# ═══════════════════════════════════════════════════════════════

@app.get("/api/tablero/stock_bajo_productos")
def stock_bajo_productos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, sku, nombre, stock_actual, stock_alerta
            FROM productos
            WHERE activo = true
              AND (stock_actual <= stock_alerta OR stock_actual <= 0)
            ORDER BY stock_actual ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/stock_bajo_insumos")
def stock_bajo_insumos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nombre, unidad_medida as unidad,
                   stock_actual as stock, stock_minimo as minimo, stock_alerta
            FROM insumos
            WHERE activo = true 
              AND (stock_actual <= stock_minimo OR stock_actual <= stock_alerta)
            ORDER BY stock_actual ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.get("/api/tablero/deudas_proveedores")
def deudas_proveedores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT oc.id as id_orden, oc.id_proveedor, p.razon_social as proveedor,
                   oc.total, oc.fecha::text,
                   EXTRACT(DAY FROM NOW() - oc.fecha)::int as dias_atraso
            FROM ordenes_compra oc
            JOIN proveedores p ON oc.id_proveedor = p.id
            WHERE oc.estado = 'Recibida'
              AND oc.id NOT IN (
                  SELECT DISTINCT pg.id_orden
                  FROM pagos_proveedores pg
                  WHERE pg.id_orden IS NOT NULL
              )
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
        cur = conn.cursor()
        cur.execute("""
            SELECT pb.id as id_pedido, pb.id_distribuidor, d.razon_social as distribuidor,
                   pb.total, pb.fecha::text,
                   EXTRACT(DAY FROM NOW() - pb.fecha)::int as dias_atraso
            FROM pedidos_b2b pb
            JOIN distribuidores d ON pb.id_distribuidor = d.id
            WHERE pb.estado = 'Despachado'
              AND pb.id NOT IN (
                  SELECT DISTINCT cd.id_pedido
                  FROM cobros_distribuidores cd
                  WHERE cd.id_pedido IS NOT NULL
              )
              AND pb.fecha <= NOW() - INTERVAL '15 days'
            ORDER BY pb.fecha ASC
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  CATEGORIAS
# ═══════════════════════════════════════════════════════════════

class NuevaCategoria(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

@app.get("/api/categorias")
def listar_categorias():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, descripcion FROM categorias WHERE activo=true ORDER BY nombre")
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/categorias/nueva")
def crear_categoria(cat: NuevaCategoria):
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

@app.delete("/api/categorias/{id_cat}")
def eliminar_categoria(id_cat: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE categorias SET activo=false WHERE id=%s", (id_cat,))
        cur.execute("UPDATE productos SET id_categoria=NULL WHERE id_categoria=%s", (id_cat,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ── ACTUALIZAR Y ELIMINAR PRODUCTOS ──────────────────────────

class ActualizarProducto(BaseModel):
    sku: str
    nombre: str
    tipo: str = "propio"
    id_categoria: Optional[int] = None
    stock_alerta: int = 20
    stock_inicial: int = 0

@app.put("/api/productos/{id_producto}")
def actualizar_producto(id_producto: int, prod: ActualizarProducto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE productos SET sku=%s, nombre=%s, tipo=%s, id_categoria=%s, stock_alerta=%s
            WHERE id=%s
        """, (prod.sku, prod.nombre, prod.tipo, prod.id_categoria, prod.stock_alerta, id_producto))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/productos/{id_producto}")
def eliminar_producto(id_producto: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET activo=false WHERE id=%s", (id_producto,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ── INSUMOS ACTUALIZADOS ─────────────────────────────────────

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

@app.get("/api/insumos")
def obtener_insumos():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nombre, unidad_medida as unidad,
                   stock_actual as stock, stock_minimo as minimo,
                   costo_unitario as costo, costo_por_bulto,
                   presentacion_compra, cantidad_por_presentacion,
                   id_proveedor
            FROM insumos WHERE activo=true ORDER BY nombre
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

@app.post("/api/insumos_nuevo")
def crear_insumo_v2(ins: InsumoCompleto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO insumos (nombre, unidad_medida, stock_minimo, costo_unitario,
                                 presentacion_compra, cantidad_por_presentacion,
                                 costo_por_bulto, id_proveedor)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (ins.nombre, ins.unidad_medida, ins.stock_minimo, ins.costo_unitario,
              ins.presentacion_compra, ins.cantidad_por_presentacion,
              ins.costo_por_bulto, ins.id_proveedor))
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
            UPDATE insumos SET nombre=%s, unidad_medida=%s, stock_minimo=%s,
                costo_unitario=%s, presentacion_compra=%s,
                cantidad_por_presentacion=%s, costo_por_bulto=%s, id_proveedor=%s
            WHERE id=%s
        """, (ins.nombre, ins.unidad_medida, ins.stock_minimo, ins.costo_unitario,
              ins.presentacion_compra, ins.cantidad_por_presentacion,
              ins.costo_por_bulto, ins.id_proveedor, id_insumo))
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
        cur.execute("UPDATE insumos SET stock_actual = stock_actual + %s WHERE id=%s",
                    (data.cantidad, id_insumo))
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

# ── EDITAR Y ELIMINAR PRODUCCIÓN ────────────────────────────

class EditarOrdenProduccion(BaseModel):
    cantidad_producida: int
    fecha_vencimiento: Optional[str] = None
    observaciones: Optional[str] = None

@app.put("/api/produccion/{id_orden}")
def editar_orden_produccion(id_orden: int, data: EditarOrdenProduccion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE ordenes_produccion
            SET cantidad_producida=%s, fecha_vencimiento=%s, observaciones=%s
            WHERE id=%s
        """, (data.cantidad_producida, data.fecha_vencimiento, data.observaciones, id_orden))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/produccion/{id_orden}")
def eliminar_orden_produccion(id_orden: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ordenes_produccion WHERE id=%s", (id_orden,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  EMPRESA
# ═══════════════════════════════════════════════════════════════

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

@app.get("/api/empresa")
def obtener_empresa():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM empresa LIMIT 1")
        row = fetchone_dict(cur)
        return row or {}
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

# ═══════════════════════════════════════════════════════════════
#  PEDIDOS B2B — ACTUALIZAR DETALLE Y ELIMINAR
# ═══════════════════════════════════════════════════════════════

class ActualizarPedidoB2B(BaseModel):
    detalle: List[DetallePedido]
    total: float

@app.put("/api/pedidos_b2b/{id_pedido}/actualizar")
def actualizar_pedido_b2b(id_pedido: int, data: ActualizarPedidoB2B):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido=%s", (id_pedido,))
        for item in data.detalle:
            if item.cantidad > 0:
                cur.execute("INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario) VALUES (%s,%s,%s,%s)",
                            (id_pedido, item.id_producto, item.cantidad, item.precio_unitario))
        cur.execute("UPDATE pedidos_b2b SET total=%s WHERE id=%s", (data.total, id_pedido))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.delete("/api/pedidos_b2b/{id_pedido}")
def eliminar_pedido_b2b(id_pedido: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido=%s", (id_pedido,))
        cur.execute("DELETE FROM pedidos_b2b WHERE id=%s", (id_pedido,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores_lista")
def listar_distribuidores():
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, razon_social, cuit, limite_credito,
                   direccion, localidad, provincia, cp, telefono, email, dni
            FROM distribuidores WHERE activo=true ORDER BY razon_social
        """)
        return fetchall_dict(cur)
    finally:
        liberar_conexion(conn)

# ═══════════════════════════════════════════════════════════════
#  RUTAS WEB
# ═══════════════════════════════════════════════════════════════

from fastapi.responses import HTMLResponse

def serve_html(filename: str):
    path = os.path.join(BASE_DIR, "pantallas", filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/")
def raiz():
    return serve_html("login.html")

@app.get("/login")
def abrir_login():
    return serve_html("login.html")

@app.get("/admin")
def abrir_admin():
    return serve_html("panel_admin.html")

@app.get("/catalogo")
def abrir_catalogo():
    return serve_html("catalogo_stock.html")

@app.get("/distribuidores")
def abrir_distribuidores():
    return serve_html("distribuidores.html")

@app.get("/insumos")
def abrir_insumos():
    return serve_html("insumos.html")

@app.get("/b2b")
def abrir_b2b():
    return serve_html("portal_distribuidores.html")

@app.get("/empleados")
def abrir_empleados():
    return serve_html("empleados.html")

@app.get("/produccion")
def abrir_produccion():
    return serve_html("produccion.html")

@app.get("/produccion-panel")
def abrir_portal_produccion():
    return serve_html("portal_produccion.html")

@app.get("/historial-b2b")
def abrir_historial_b2b():
    return serve_html("historial_b2b.html")

@app.get("/reportes")
def abrir_reportes():
    return serve_html("reportes.html")

@app.get("/configuracion")
def abrir_configuracion():
    return serve_html("configuracion.html")

@app.get("/proveedores")
def abrir_proveedores_html():
    return serve_html("proveedores.html")

@app.get("/fichajes")
def abrir_portal_fichaje():
    return serve_html("portal_fichaje.html")
@app.get("/qr")
def abrir_qr_fichaje():
    return serve_html("qr_fichaje.html")
