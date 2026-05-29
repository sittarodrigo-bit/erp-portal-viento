from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from pydantic import BaseModel
from datetime import datetime

# ==========================================
# 1. INICIALIZACIÓN Y CONFIGURACIÓN
# ==========================================

app = FastAPI(title="API Portal del Viento")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "postgresql://neondb_owner:npg_atPC4hK8ivcb@ep-summer-dream-aqz9xefr-pooler.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def obtener_conexion():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error crítico de conexión: {e}")
        return None

# ==========================================
# 2. MODELOS DE DATOS (Pydantic)
# ==========================================

class DetalleVenta(BaseModel):
    id_producto: int
    cantidad: int
    precio_unitario: float

class NuevaVenta(BaseModel):
    id_sucursal: int
    id_empleado: int
    metodo_pago: str
    es_fiscal: bool
    total: float
    detalle: list[DetalleVenta]

class DetallePedidoB2B(BaseModel):
    id_producto: int
    cantidad: int
    precio_unitario: float

class NuevoPedidoB2B(BaseModel):
    id_distribuidor: int
    total: float
    detalle: list[DetallePedidoB2B]

class ActualizacionStock(BaseModel):
    nuevo_stock: int

class ActualizacionPrecio(BaseModel):
    precio_minorista: float
    precio_mayorista: float

class NuevoDistribuidor(BaseModel):
    razon_social: str
    cuit: str
    limite_credito: float

class EditarCredito(BaseModel):
    nuevo_limite: float

# Modelo para crear un producto desde cero
class NuevoProducto(BaseModel):
    sku: str
    nombre: str
    precio_minorista: float
    precio_mayorista: float
    stock_inicial: int

# ==========================================
# 3. ENDPOINTS DE DATOS (API)
# ==========================================

@app.get("/api/productos")
def obtener_productos():
    conn = obtener_conexion()
    if not conn: raise HTTPException(status_code=500, detail="BD no disponible")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id_producto, p.sku, p.nombre, p.precio_mayorista, p.precio_minorista, i.stock_actual
        FROM productos p LEFT JOIN inventario_sucursales i ON p.id_producto = i.id_producto
        WHERE p.estado = TRUE ORDER BY p.id_producto ASC
    """)
    productos = cursor.fetchall()
    conn.close()
    return [{"id": p[0], "sku": p[1], "nombre": p[2], "precio_mayorista": p[3], "precio_minorista": p[4], "stock": p[5]} for p in productos]

# --- NUEVA RUTA: CREAR PRODUCTO ---
@app.post("/api/productos_nuevo")
def crear_producto(prod: NuevoProducto):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        # 1. Crear el producto en el catálogo general
        cursor.execute("""
            INSERT INTO productos (sku, nombre, categoria, precio_mayorista, precio_minorista, estado)
            VALUES (%s, %s, 'General', %s, %s, TRUE) RETURNING id_producto
        """, (prod.sku, prod.nombre, prod.precio_mayorista, prod.precio_minorista))
        id_nuevo_prod = cursor.fetchone()[0]
        
        # 2. Asignarle el stock físico a la fábrica (Sucursal 1)
        cursor.execute("""
            INSERT INTO inventario_sucursales (id_sucursal, id_producto, stock_actual)
            VALUES (1, %s, %s)
        """, (id_nuevo_prod, prod.stock_inicial))
        
        conn.commit()
        return {"mensaje": "Producto creado exitosamente"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.post("/api/ventas")
def registrar_venta(venta: NuevaVenta):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO ventas_pos (id_sucursal, id_empleado, total, metodo_pago, es_fiscal, tipo_comprobante) VALUES (%s, %s, %s, %s, %s, 'Remito Interno') RETURNING id_venta", (venta.id_sucursal, venta.id_empleado, venta.total, venta.metodo_pago, venta.es_fiscal))
        id_venta = cursor.fetchone()[0]
        for item in venta.detalle:
            cursor.execute("INSERT INTO detalle_ventas_pos (id_venta, id_producto, cantidad, precio_unitario, subtotal) VALUES (%s, %s, %s, %s, %s)", (id_venta, item.id_producto, item.cantidad, item.precio_unitario, item.cantidad * item.precio_unitario))
            cursor.execute("UPDATE inventario_sucursales SET stock_actual = stock_actual - %s WHERE id_producto = %s AND id_sucursal = %s", (item.cantidad, item.id_producto, venta.id_sucursal))
        conn.commit()
        return {"mensaje": "Venta registrada"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@app.post("/api/pedidos_b2b")
def registrar_pedido_b2b(pedido: NuevoPedidoB2B):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO pedidos_b2b (id_distribuidor, estado, total_neto) VALUES (%s, 'Pendiente', %s) RETURNING id_pedido", (pedido.id_distribuidor, pedido.total))
        id_pedido = cursor.fetchone()[0]
        for item in pedido.detalle:
            cursor.execute("INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_congelado, subtotal) VALUES (%s, %s, %s, %s, %s)", (id_pedido, item.id_producto, item.cantidad, item.precio_unitario, item.cantidad * item.precio_unitario))
        conn.commit()
        return {"mensaje": "Pedido registrado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@app.get("/api/admin/resumen_hoy")
def obtener_resumen_hoy():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(total), 0), COUNT(id_venta) FROM ventas_pos WHERE DATE(fecha) = CURRENT_DATE")
    ventas = cursor.fetchone()
    cursor.execute("SELECT COUNT(id_pedido) FROM pedidos_b2b WHERE estado = 'Pendiente'")
    pedidos = cursor.fetchone()[0]
    conn.close()
    return {"recaudacion_hoy": ventas[0], "tickets_hoy": ventas[1], "pedidos_pendientes": pedidos}

@app.get("/api/admin/pedidos_pendientes")
def obtener_pedidos_pendientes():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT p.id_pedido, d.razon_social, p.fecha_creacion, p.total_neto, p.estado FROM pedidos_b2b p JOIN distribuidores d ON p.id_distribuidor = d.id_distribuidor WHERE p.estado IN ('Pendiente', 'Para Preparar') ORDER BY p.fecha_creacion DESC")
    pedidos = cursor.fetchall()
    conn.close()
    return [{"id_pedido": p[0], "distribuidor": p[1], "fecha": p[2].strftime("%Y-%m-%d %H:%M"), "total": p[3], "estado": p[4]} for p in pedidos]

@app.put("/api/productos/{id_producto}/stock")
def actualizar_stock(id_producto: int, datos: ActualizacionStock):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE inventario_sucursales SET stock_actual = %s WHERE id_producto = %s AND id_sucursal = 1", (datos.nuevo_stock, id_producto))
        conn.commit()
        return {"mensaje": "Stock actualizado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@app.put("/api/productos/{id_producto}/precio")
def actualizar_precio(id_producto: int, datos: ActualizacionPrecio):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE productos SET precio_minorista = %s, precio_mayorista = %s WHERE id_producto = %s", (datos.precio_minorista, datos.precio_mayorista, id_producto))
        conn.commit()
        return {"mensaje": "Precios actualizados"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@app.get("/api/distribuidores_lista")
def obtener_distribuidores():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id_distribuidor, razon_social, cuit, limite_credito FROM distribuidores ORDER BY id_distribuidor ASC")
    filas = cursor.fetchall()
    conn.close()
    return [{"id": f[0], "razon_social": f[1], "cuit": f[2], "limite_credito": f[3]} for f in filas]

@app.post("/api/distribuidores_nuevo")
def crear_distribuidor(dist: NuevoDistribuidor):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO distribuidores (razon_social, cuit, limite_credito) VALUES (%s, %s, %s)", (dist.razon_social, dist.cuit, dist.limite_credito))
        conn.commit()
        return {"mensaje": "Distribuidor creado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@app.put("/api/distribuidores/{id_dist}/credito")
def actualizar_credito_distribuidor(id_dist: int, datos: EditarCredito):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE distribuidores SET limite_credito = %s WHERE id_distribuidor = %s", (datos.nuevo_limite, id_dist))
        conn.commit()
        return {"mensaje": "Límite actualizado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

# ==========================================
# 4. RUTAS PARA NAVEGACIÓN WEB
# ==========================================

@app.get("/admin")
def abrir_panel_control(): return FileResponse("pantallas/panel_admin.html")
@app.get("/catalogo")
def abrir_catalogo_stock(): return FileResponse("pantallas/catalogo_stock.html")
@app.get("/distribuidores")
def abrir_distribuidores(): return FileResponse("pantallas/distribuidores.html")
@app.get("/caja")
def abrir_caja_mostrador(): return FileResponse("pantallas/punto_de_venta.html")
@app.get("/b2b")
def abrir_portal_mayorista(): return FileResponse("pantallas/portal_distribuidores.html")
# ... (mantené todo lo anterior igual, solo agregá esta nueva ruta antes de la sección 4)

@app.put("/api/pedidos/{id_pedido}/estado")
def actualizar_estado_pedido(id_pedido: int, estado: str):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE pedidos_b2b SET estado = %s WHERE id_pedido = %s", (estado, id_pedido))
        conn.commit()
        return {"mensaje": "Estado actualizado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

# ... (seguido de tu sección 4 de RUTAS WEB)
