from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI(title="API Portal del Viento - Alfajores")

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# CONFIGURACIÓN DE BASE DE DATOS
# ==============================================================================
DB_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_jqkxN4SRzP5o@ep-still-firefly-apwc5fuw-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require")

def obtener_conexion():
    try:
        return psycopg2.connect(DB_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la BD: {e}")

def liberar_conexion(conn):
    if conn:
        conn.close()

def fetchall_dict(cursor):
    return [dict(row) for row in cursor.fetchall()]

# ==============================================================================
# MODELOS DE DATOS (Pydantic)
# ==============================================================================
class Categoria(BaseModel):
    nombre: str

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
    costo_total: float
    id_categoria: Optional[int] = None

class ProduccionUpdate(BaseModel):
    cantidad_producida: int
    fecha_vencimiento: Optional[str] = None
    observaciones: Optional[str] = None

class PedidoUpdate(BaseModel):
    detalle: List[DetallePedido]
    total: float

# ==============================================================================
# ENDPOINTS BÁSICOS / EMPRESA
# ==============================================================================
@app.get("/api/empresa")
def get_empresa():
    return {
        "nombre": "Portal del Viento",
        "razon_social": "Portal del Viento S.A.",
        "cuit": "30-12345678-9",
        "direccion": "Mendoza, Argentina",
        "telefono": "261 123 4567"
    }

# ==============================================================================
# ENDPOINTS CATEGORÍAS
# ==============================================================================
@app.get("/api/categorias")
def get_categorias():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM categorias ORDER BY nombre ASC")
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.post("/api/categorias/nueva")
def crear_categoria(cat: Categoria):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO categorias (nombre) VALUES (%s)", (cat.nombre,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/categorias/{id}")
def eliminar_categoria(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM categorias WHERE id = %s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ENDPOINTS PRODUCTOS Y PRESENTACIONES
# ==============================================================================
@app.get("/api/productos")
def get_productos():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.get("/api/productos/con_presentaciones")
def get_productos_presentaciones():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
        productos = fetchall_dict(cur)
        
        for p in productos:
            cur.execute("SELECT * FROM presentaciones WHERE id_producto = %s ORDER BY cantidad_unidades ASC", (p['id'],))
            p['presentaciones'] = fetchall_dict(cur)
        return productos
    finally:
        liberar_conexion(conn)

@app.post("/api/productos_nuevo")
def crear_producto(prod: Producto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos (sku, nombre, tipo, stock, id_categoria, stock_alerta)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (prod.sku, prod.nombre, prod.tipo, prod.stock_inicial, prod.id_categoria, prod.stock_alerta))
        id_prod = cur.fetchone()[0]
        
        # Crear presentación base automática (Unidad)
        cur.execute("""
            INSERT INTO presentaciones (id_producto, nombre, cantidad_unidades, precio_minorista, precio_mayorista)
            VALUES (%s, 'Unidad', 1, 0, 0)
        """, (id_prod,))
        
        conn.commit()
        return {"id": id_prod}
    finally:
        liberar_conexion(conn)

@app.put("/api/productos/{id}")
def actualizar_producto(id: int, prod: Producto):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE productos 
            SET sku=%s, nombre=%s, id_categoria=%s, stock_alerta=%s
            WHERE id=%s
        """, (prod.sku, prod.nombre, prod.id_categoria, prod.stock_alerta, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/productos/{id}")
def eliminar_producto(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM productos WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/productos/{id}/stock")
def actualizar_stock_directo(id: int, stock: StockUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET stock=%s WHERE id=%s", (stock.nuevo_stock, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/productos/{id}/presentaciones")
def get_presentaciones(id: int):
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM presentaciones WHERE id_producto = %s ORDER BY cantidad_unidades ASC", (id,))
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.post("/api/productos/{id}/presentaciones")
def crear_presentacion(id: int, pres: Presentacion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO presentaciones (id_producto, nombre, cantidad_unidades, precio_minorista, precio_mayorista)
            VALUES (%s, %s, %s, %s, %s)
        """, (id, pres.nombre, pres.cantidad_unidades, pres.precio_minorista, pres.precio_mayorista))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.put("/api/presentaciones/{id}")
def actualizar_presentacion(id: int, pres: Presentacion):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE presentaciones 
            SET nombre=%s, cantidad_unidades=%s, precio_minorista=%s, precio_mayorista=%s
            WHERE id=%s
        """, (pres.nombre, pres.cantidad_unidades, pres.precio_minorista, pres.precio_mayorista, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/presentaciones/{id}")
def eliminar_presentacion(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM presentaciones WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ENDPOINTS DISTRIBUIDORES
# ==============================================================================
@app.get("/api/distribuidores_lista")
def get_distribuidores():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM distribuidores ORDER BY razon_social ASC")
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.post("/api/distribuidores_nuevo")
def crear_distribuidor(dist: Distribuidor):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO distribuidores (razon_social, dni, cuit, telefono, email, direccion, localidad, provincia, cp, limite_credito, notas, aprobado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
        """, (dist.razon_social, dist.dni, dist.cuit, dist.telefono, dist.email, dist.direccion, dist.localidad, dist.provincia, dist.cp, dist.limite_credito, dist.notas))
        conn.commit()
        return {"status": "ok"}
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
        """, (dist.razon_social, dist.dni, dist.cuit, dist.telefono, dist.email, dist.direccion, dist.localidad, dist.provincia, dist.cp, dist.limite_credito, dist.notas, id))
        conn.commit()
        return {"status": "ok"}
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
    finally:
        liberar_conexion(conn)

@app.delete("/api/distribuidores/{id}")
def eliminar_distribuidor(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM distribuidores WHERE id=%s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.get("/api/distribuidores/{id_dist}/estado_cuenta")
def estado_cuenta_distribuidor(id_dist: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, fecha::text, total, estado FROM pedidos_b2b WHERE id_distribuidor = %s AND estado != 'Cancelado'", (id_dist,))
        pedidos = fetchall_dict(cur)
        
        cur.execute("SELECT id, fecha::text, monto, metodo, referencia FROM cobros_distribuidores WHERE id_distribuidor = %s", (id_dist,))
        cobros = fetchall_dict(cur)
        
        total_pedidos = sum(float(p['total']) for p in pedidos)
        total_cobrado = sum(float(c['monto']) for c in cobros)
        
        return {
            "total_pedidos": total_pedidos,
            "total_cobrado": total_cobrado,
            "saldo_pendiente": total_pedidos - total_cobrado,
            "pedidos": pedidos,
            "cobros": cobros
        }
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ENDPOINTS PEDIDOS B2B
# ==============================================================================
@app.post("/api/pedidos_b2b")
def crear_pedido_b2b(pedido: PedidoB2B):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # 1. Insertar el pedido principal
        cur.execute("""
            INSERT INTO pedidos_b2b (id_distribuidor, total, estado)
            VALUES (%s, %s, 'Pendiente') RETURNING id
        """, (pedido.id_distribuidor, pedido.total))
        id_pedido = cur.fetchone()[0]

        # 2. Insertar los detalles y descontar stock
        for item in pedido.detalle:
            subtotal = item.cantidad * item.precio_unitario
            cur.execute("""
                INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario, subtotal)
                VALUES (%s, %s, %s, %s, %s)
            """, (id_pedido, item.id_producto, item.cantidad, item.precio_unitario, subtotal))
            
            # Obtener multiplicador si usó presentación
            multiplicador = 1
            if item.id_presentacion:
                cur.execute("SELECT cantidad_unidades FROM presentaciones WHERE id = %s", (item.id_presentacion,))
                res_pres = cur.fetchone()
                if res_pres:
                    multiplicador = res_pres[0]

            cantidad_descontar = item.cantidad * multiplicador
            cur.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (cantidad_descontar, item.id_producto))

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
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT p.id, p.fecha::text, p.total, p.estado, p.id_distribuidor, d.razon_social as distribuidor 
        FROM pedidos_b2b p
        LEFT JOIN distribuidores d ON p.id_distribuidor = d.id
        WHERE 1=1
    """
    params = []
    if estado:
        query += " AND p.estado = %s"
        params.append(estado)
    if id_distribuidor:
        query += " AND p.id_distribuidor = %s"
        params.append(id_distribuidor)
    
    query += " ORDER BY p.fecha DESC"
    cur.execute(query, tuple(params))
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.get("/api/pedidos_b2b/{id}/detalle")
def detalle_pedido_b2b(id: int):
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT dp.*, pr.nombre as producto, pr.sku 
        FROM detalle_pedidos_b2b dp
        JOIN productos pr ON dp.id_producto = pr.id
        WHERE dp.id_pedido = %s
    """, (id,))
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.put("/api/pedidos_b2b/{id}/actualizar")
def actualizar_pedido(id: int, payload: PedidoUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Eliminar detalle anterior y reponer stock
        cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        viejos = cur.fetchall()
        for v in viejos:
            cur.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (v[1], v[0]))
            
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        cur.execute("UPDATE pedidos_b2b SET total = %s WHERE id = %s", (payload.total, id))
        
        # Insertar nuevo detalle y descontar stock
        for item in payload.detalle:
            subtotal = item.cantidad * item.precio_unitario
            cur.execute("""
                INSERT INTO detalle_pedidos_b2b (id_pedido, id_producto, cantidad, precio_unitario, subtotal)
                VALUES (%s, %s, %s, %s, %s)
            """, (id, item.id_producto, item.cantidad, item.precio_unitario, subtotal))
            cur.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (item.cantidad, item.id_producto))

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
        # Si se cancela, devolvemos el stock
        if estado == 'Cancelado':
            cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
            items = cur.fetchall()
            for item in items:
                cur.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (item[1], item[0]))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/pedidos_b2b/{id}")
def eliminar_pedido(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Devolver stock
        cur.execute("SELECT id_producto, cantidad FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        items = cur.fetchall()
        for item in items:
            cur.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (item[1], item[0]))
        
        cur.execute("DELETE FROM detalle_pedidos_b2b WHERE id_pedido = %s", (id,))
        cur.execute("DELETE FROM pedidos_b2b WHERE id = %s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ENDPOINTS EMPLEADOS / INSUMOS / RECETAS
# ==============================================================================
@app.get("/api/empleados")
def get_empleados():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM empleados ORDER BY apellido ASC")
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.get("/api/insumos")
def get_insumos():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM insumos ORDER BY nombre ASC")
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.get("/api/recetas/{id_producto}")
def get_receta(id_producto: int):
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT r.*, i.nombre as insumo, i.unidad, i.costo 
        FROM recetas r
        JOIN insumos i ON r.id_insumo = i.id
        WHERE r.id_producto = %s
    """, (id_producto,))
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.post("/api/recetas/guardar")
def guardar_receta(receta: RecetaUpdate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM recetas WHERE id_producto = %s", (receta.id_producto,))
        for item in receta.items:
            cur.execute("""
                INSERT INTO recetas (id_producto, id_insumo, cantidad_necesaria)
                VALUES (%s, %s, %s)
            """, (receta.id_producto, item.id_insumo, item.cantidad_necesaria))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

# ==============================================================================
# ENDPOINTS PRODUCCIÓN (Actualizado sin vínculos minoristas)
# ==============================================================================
@app.get("/api/produccion/historial")
def historial_produccion():
    conn = obtener_conexion()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT pr.*, p.nombre as producto, e.nombre as empleado_nombre, e.apellido as empleado_apellido
        FROM produccion pr
        JOIN productos p ON pr.id_producto = p.id
        JOIN empleados e ON pr.id_empleado = e.id
        ORDER BY pr.fecha DESC
    """)
    res = fetchall_dict(cur)
    liberar_conexion(conn)
    return res

@app.post("/api/produccion/registrar")
def registrar_produccion(prod: ProduccionCreate):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        # Registrar el lote fabricado
        cur.execute("""
            INSERT INTO produccion (id_producto, id_empleado, cantidad_producida, fecha_vencimiento, observaciones, costo_total, id_categoria)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (prod.id_producto, prod.id_empleado, prod.cantidad_producida, prod.fecha_vencimiento, prod.observaciones, prod.costo_total, prod.id_categoria))
        
        # Aumentar stock del producto terminado
        cur.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (prod.cantidad_producida, prod.id_producto))

        # Descontar stock de insumos según receta
        cur.execute("SELECT id_insumo, cantidad_necesaria FROM recetas WHERE id_producto = %s", (prod.id_producto,))
        receta = cur.fetchall()
        for item in receta:
            id_insumo = item[0]
            cant_descontar = item[1] * prod.cantidad_producida
            cur.execute("UPDATE insumos SET stock = stock - %s WHERE id = %s", (cant_descontar, id_insumo))

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
        # Ajustar diferencia de stock
        cur.execute("SELECT id_producto, cantidad_producida FROM produccion WHERE id = %s", (id,))
        old = cur.fetchone()
        diff = payload.cantidad_producida - old[1]
        
        cur.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (diff, old[0]))
        cur.execute("""
            UPDATE produccion SET cantidad_producida=%s, fecha_vencimiento=%s, observaciones=%s
            WHERE id=%s
        """, (payload.cantidad_producida, payload.fecha_vencimiento, payload.observaciones, id))
        conn.commit()
        return {"status": "ok"}
    finally:
        liberar_conexion(conn)

@app.delete("/api/produccion/{id}")
def eliminar_produccion(id: int):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_producto, cantidad_producida FROM produccion WHERE id = %s", (id,))
        old = cur.fetchone()
        cur.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (old[1], old[0]))
        cur.execute("DELETE FROM produccion WHERE id=%s", (id,))
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
        return HTMLResponse(content=f.read())

@app.get("/")
def index():
    return HTMLResponse(content="<h1>API Portal del Viento B2B Funcionando</h1>")

@app.get("/admin")
def route_admin():
    return serve_html("dashboard.html")

@app.get("/catalogo")
def route_catalogo():
    return serve_html("catalogo_stock.html")

@app.get("/insumos")
def route_insumos():
    return serve_html("insumos.html")

@app.get("/produccion")
def route_produccion():
    return serve_html("produccion.html")

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

@app.get("/carga-stock")
def route_carga_stock():
    return serve_html("carga_stock.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
