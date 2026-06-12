/* ============================================================
   auth.js — Seguridad central del Portal del Viento
   - Pide login si no hay sesión
   - Controla permisos por rol (cada panel declara su "clave")
   - Cierra la sesión sola tras 1 hora de inactividad
   Uso en cada panel (en el <head>, antes del resto del script):
     <script>window.PANEL_ACTUAL = 'reportes';</script>
     <script src="/static/auth.js"></script>
   ============================================================ */
(function () {
  // ---- Configuración ----
  var INACTIVIDAD_MIN = 60; // minutos hasta cerrar sesión sola

  // Qué paneles puede ver cada rol. 'admin' ve todo (caso especial abajo).
  var PERMISOS = {
    administrativo: ['admin','reportes','distribuidores','historial_b2b','gastos','fichajes','b2b','mayoristas','catalogo_stock','locales','proveedores'],
    vendedor:       [],   // el vendedor usa el POS, que tiene su login propio
    produccion:     ['produccion','produccion_panel','insumos','proveedores','carga_stock'],
    deposito:       ['armado','carga_stock','produccion_panel'],
  };
  // Paneles MUY sensibles: solo el admin real (no administrativo).
  // (empleados/sueldos, configuración) — no se listan en ningún rol salvo admin.

  var panel = window.PANEL_ACTUAL || '';

  // ---- Leer sesión ----
  var raw = sessionStorage.getItem('usuario');
  if (!raw) { irAlLogin(); return; }
  var u;
  try { u = JSON.parse(raw); } catch (e) { irAlLogin(); return; }
  var rol = (u && u.rol ? String(u.rol).toLowerCase().trim() : '');

  // ---- Control de permisos ----
  var permitido = false;
  if (rol === 'admin') {
    permitido = true; // admin ve todo
  } else if (PERMISOS[rol] && panel && PERMISOS[rol].indexOf(panel) !== -1) {
    permitido = true;
  }

  if (!permitido) {
    bloquear();
    return;
  }

  // ---- Cierre por inactividad ----
  var timer = null;
  function reiniciarTimer() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(cerrarPorInactividad, INACTIVIDAD_MIN * 60 * 1000);
    // Guardar marca de última actividad (compartida entre pestañas)
    try { localStorage.setItem('ultima_actividad', String(Date.now())); } catch(e) {}
  }
  function cerrarPorInactividad() {
    try { sessionStorage.removeItem('usuario'); } catch(e) {}
    alert('Tu sesión se cerró por inactividad. Volvé a iniciar sesión.');
    irAlLogin();
  }
  // Si otra pestaña registró actividad hace poco, no cerrar; si pasó el tiempo, cerrar
  function chequeoPeriodico() {
    try {
      var ua = parseInt(localStorage.getItem('ultima_actividad') || '0', 10);
      if (ua && (Date.now() - ua) > INACTIVIDAD_MIN * 60 * 1000) {
        cerrarPorInactividad();
      }
    } catch(e) {}
  }
  ['click','keydown','mousemove','touchstart','scroll'].forEach(function (ev) {
    window.addEventListener(ev, reiniciarTimer, { passive: true });
  });
  reiniciarTimer();
  setInterval(chequeoPeriodico, 60 * 1000); // revisa cada minuto

  // ---- Helpers ----
  function irAlLogin() {
    window.location.replace('/');
  }
  function bloquear() {
    document.documentElement.innerHTML =
      '<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0a0a;color:#fff;font-family:sans-serif;text-align:center;padding:24px">' +
      '<div style="max-width:380px">' +
      '<div style="font-size:54px;margin-bottom:16px">🔒</div>' +
      '<h1 style="font-size:22px;font-weight:bold;margin-bottom:10px">Acceso restringido</h1>' +
      '<p style="color:#9ca3af;font-size:15px;line-height:1.5">Tu usuario no tiene permiso para entrar a esta sección. Si creés que es un error, hablá con el administrador.</p>' +
      '<a href="/" style="display:inline-block;margin-top:22px;background:#d4ff3f;color:#000;font-weight:bold;padding:12px 24px;border-radius:10px;text-decoration:none">Volver al inicio</a>' +
      '</div></div>';
    throw new Error('Acceso no autorizado: ' + panel);
  }

  // Exponer el usuario para que el panel lo use si quiere
  window.USUARIO = u;
})();
