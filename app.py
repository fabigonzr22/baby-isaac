"""Baby Isaac — Wishlist web app.

Arquitectura:
- Página pública: portada, wishlist con filtros, producto, "Quiero regalarlo",
  nombre, confirmación, datos de Binance, aviso de pendiente + mensaje de
  contacto + "¿regalar algo más?".
- Panel privado (admin): login, dashboard, stock por regalo, confirmar pago,
  CRUD de regalos.
- Base de datos SQLite: productos (con cantidad/stock), regaladores, reservas.

Modelo de stock: cada producto tiene `cantidad` (unidades que se pueden regalar).
Cada reserva (reserved/paid) descuenta 1 unidad. Un producto queda "agotado"
cuando reservas activas == cantidad.
"""
import os
import sqlite3
import secrets
from datetime import datetime, timezone

from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, flash, abort, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "isaac.db")

# Cambia esta contraseña en producción (variable de entorno ADMIN_PASSWORD),
# o mejor: desde el panel admin → Configuración.
ADMIN_USER = os.environ.get("ADMIN_USER", "fabi")
DEFAULT_ADMIN_PASSWORD_HASH = generate_password_hash(
    os.environ.get("ADMIN_PASSWORD", "isaac2026"))

# Datos de pago Binance y mensaje de contacto (editables desde el panel admin).
DEFAULT_BINANCE_DATA = os.environ.get("BINANCE_DATA") or (
    "USDT · Red TRC20\n"
    "Dirección: TU_DIRECCION_DE_BINANCE_AQUI\n"
    "Nombre: TU_NOMBRE_EN_BINANCE\n"
    "Monto: el indicado en el regalo")

DEFAULT_CONTACTO = (
    "Escríbeme por WhatsApp para confirmar tu pago: "
    "TU_NUMERO_DE_WHATSAPP_AQUI")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Migración de esquema antiguo (sin columna `cantidad` en productos)
    cols = [r[1] for r in db.execute("PRAGMA table_info(productos)").fetchall()]
    if cols and "cantidad" not in cols:
        db.execute("DROP TABLE IF EXISTS reservas")
        db.execute("DROP TABLE IF EXISTS regaladores")
        db.execute("DROP TABLE IF EXISTS productos")

    db.executescript("""
    CREATE TABLE IF NOT EXISTS productos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre      TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        categoria   TEXT NOT NULL,
        precio      REAL NOT NULL,
        emoji       TEXT NOT NULL DEFAULT '🎁',
        imagen      TEXT NOT NULL DEFAULT '',
        cantidad    INTEGER NOT NULL DEFAULT 1,
        creado_en   TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS regaladores (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre     TEXT NOT NULL,
        creado_en  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reservas (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id   INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        regalador_id  INTEGER NOT NULL REFERENCES regaladores(id) ON DELETE CASCADE,
        estado        TEXT NOT NULL DEFAULT 'reserved'
            CHECK (estado IN ('reserved','paid')),
        creado_en     TEXT NOT NULL,
        pagado_en     TEXT
    );

    CREATE TABLE IF NOT EXISTS config (
        clave  TEXT PRIMARY KEY,
        valor  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS aportes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        nombre      TEXT NOT NULL,
        monto       REAL NOT NULL,
        creado_en   TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS asistentes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre     TEXT NOT NULL,
        creado_en  TEXT NOT NULL
    );
    """)
    db.commit()

    # Migración: añadir columna `imagen` si no existe.
    cols = [r[1] for r in db.execute("PRAGMA table_info(productos)").fetchall()]
    if cols and "imagen" not in cols:
        db.execute("ALTER TABLE productos ADD COLUMN imagen TEXT NOT NULL DEFAULT ''")
        db.commit()

    # Semillas iniciales si la tabla está vacía.
    # cantidad: cuántas unidades se pueden regalar de cada cosa.
    cur = db.execute("SELECT COUNT(*) FROM productos")
    if cur.fetchone()[0] == 0:
        seed = [
            ("Pijamas", "Para que Isaac duerma calentito y cómodo.", "Ropa", 15, "🌙", "pijamas.jpg", 5),
            ("Pantaloncitos o shorts", "Pantaloncitos cómodos para el bebé.", "Ropa", 15, "🩳", "pantalones.jpg", 5),
            ("Colchón para colecho", "Para que Isaac duerma cerca y seguro.", "Dormir", 35, "🛏️", "colchon_colecho.jpg", 1),
            ("Sábanas para colchón de colecho", "Sábanas suaves de algodón para el colecho.", "Dormir", 28, "🧺", "sabanas.jpg", 1),
            ("Swaddle", "Para envolver y calmar al bebé.", "Dormir", 25, "🦢", "swaddle.jpg", 1),
            ("Lámpara de noche", "Luz suave para las noches de Isaac.", "Dormir", 25, "💡", "lampara.jpg", 1),
            ("Fular", "Para llevar a Isaac cerquita de ti.", "Paseo", 34, "👶", "porta_bebe.jpg", 1),
            ("Libros para bebé de 0 a 3 meses", "Primeras lecturas para estimular a Isaac.", "Aprendizaje", 25, "📖", "libro.jpg", 1),
            ("Baby swing", "Para mecer y calmar a Isaac.", "Dormir", 160, "🪑", "baby_swing.jpg", 1),
            ("Cesta de ropa sucia para bebé", "Para mantener la ropita de Isaac organizada.", "Cuidado", 14, "🧺", "cesta_ropa.jpg", 1),
            ("Cámara monitor", "Para vigilar a Isaac desde cualquier lugar.", "Cuidado", 59.99, "📷", "camara_monitor.jpg", 1),
            ("Termómetro digital", "Para cuidar la temperatura de Isaac.", "Cuidado", 30, "🌡️", "termometro.jpg", 1),
            ("Aspirador nasal manual", "Alternativa manual y práctica para despejar la naricita.", "Cuidado", 20, "🤧", "aspirador_manual.jpg", 1),
            ("Monitoreo de bebé", "Para monitorear la respiración y el sueño de Isaac.", "Cuidado", 179.99, "📟", "monitoreo_bebe.jpg", 1),
            ("Teteros / limpiador de teteros", "Kit de teteros y limpiador.", "Alimentación", 65, "🍼", "teteros.jpg", 1),
            ("Almohada de lactancia", "Para hacer más cómoda la hora de la lactancia.", "Alimentación", 59.99, "🤱", "almohada_lactancia.jpg", 1),
            ("Organizador de gavetas", "Para ordenar la ropita de Isaac en las gavetas.", "Dormir", 40, "🗂️", "organizador_gavetas.jpg", 1),
            ("Esterilizador de teteros", "Para esterilizar los teteros de Isaac.", "Alimentación", 59.99, "♨️", "esterilizador.jpg", 1),
            ("Calentador de leche", "Para calentar la leche a la temperatura ideal.", "Alimentación", 65.99, "🍶", "calentador_leche.jpg", 1),
        ]
        now = datetime.now(timezone.utc).isoformat()
        db.executemany(
            "INSERT INTO productos (nombre, descripcion, categoria, precio, emoji, imagen, cantidad, creado_en) "
            "VALUES (?,?,?,?,?,?,?,?)", [(*p, now) for p in seed])
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


CATEGORIES = ["Ropa", "Dormir", "Paseo", "Alimentación", "Cuidado", "Aprendizaje"]

# Productos con precio estrictamente mayor a este monto permiten "aporte compartido".
APORTE_MIN = 100.0


def is_admin():
    return session.get("admin") is True


def get_config(db, clave, default=None):
    row = db.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return row["valor"] if row else default


def set_config(db, clave, valor):
    db.execute(
        "INSERT INTO config (clave, valor) VALUES (?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (clave, valor))
    db.commit()


def get_binance_data():
    db = get_db()
    return get_config(db, "binance_data", DEFAULT_BINANCE_DATA)


def get_contacto():
    db = get_db()
    return get_config(db, "contacto", DEFAULT_CONTACTO)


def check_admin_password(password):
    db = get_db()
    stored_hash = get_config(db, "admin_password_hash")
    if stored_hash:
        return check_password_hash(stored_hash, password)
    return check_password_hash(DEFAULT_ADMIN_PASSWORD_HASH, password)


@app.template_filter("precio")
def precio_filter(precio):
    """Formatea el precio: 'Por definir' si es 0/None, si no $X."""
    try:
        p = float(precio)
    except (TypeError, ValueError):
        return "Por definir"
    if p <= 0:
        return "Por definir"
    if p == int(p):
        return f"${p:,.0f}"
    return f"${p:,.2f}"


def contar_reservas_por_producto():
    """Devuelve {producto_id: {'reserved': n, 'paid': n}}."""
    db = get_db()
    rows = db.execute(
        "SELECT producto_id, estado, COUNT(*) AS n FROM reservas "
        "GROUP BY producto_id, estado").fetchall()
    m = {}
    for r in rows:
        pid = r["producto_id"]
        m.setdefault(pid, {"reserved": 0, "paid": 0})
        m[pid][r["estado"]] = r["n"]
    return m


def enriquecer(rows):
    """Añade a cada producto: reservados, pagados, disponibles y etiqueta."""
    counts = contar_reservas_por_producto()
    out = []
    for p in rows:
        pid = p["id"]
        c = counts.get(pid, {"reserved": 0, "paid": 0})
        disp = max(0, p["cantidad"] - c["reserved"] - c["paid"])
        d = dict(p)
        d["reservados"] = c["reserved"]
        d["pagados"] = c["paid"]
        d["disponibles"] = disp
        d["agotado"] = disp <= 0
        out.append(d)
    return out


def total_aportado(db, producto_id):
    """Suma de todos los aportes de un producto."""
    row = db.execute(
        "SELECT COALESCE(SUM(monto), 0) AS total FROM aportes WHERE producto_id = ?",
        (producto_id,)).fetchone()
    return float(row["total"])


def aportes_de(producto_id):
    """Lista de aportes de un producto (más recientes primero)."""
    db = get_db()
    return db.execute(
        "SELECT * FROM aportes WHERE producto_id = ? ORDER BY creado_en DESC",
        (producto_id,)).fetchall()


# ---------------------------------------------------------------------------
# Página pública
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()
    categoria = request.args.get("categoria", "")
    if categoria and categoria in CATEGORIES:
        rows = db.execute(
            "SELECT * FROM productos WHERE categoria = ? ORDER BY id",
            (categoria,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM productos ORDER BY id").fetchall()
    productos = enriquecer(rows)
    return render_template("index.html",
                           productos=productos,
                           categorias=CATEGORIES,
                           categoria_actual=categoria)


@app.route("/regalo/<int:producto_id>")
def producto(producto_id):
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    (p,) = enriquecer([p])
    aportado = total_aportado(db, producto_id)
    permitir_aporte = p["precio"] > APORTE_MIN
    aportes = aportes_de(producto_id)
    return render_template("producto.html", p=p,
                           aportado=aportado,
                           permitir_aporte=permitir_aporte,
                           aportes=aportes)


@app.route("/regalo/<int:producto_id>/reservar", methods=["POST"])
def reservar(producto_id):
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)

    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("Por favor escribe tu nombre para continuar.", "error")
        return redirect(url_for("producto", producto_id=producto_id))

    (p,) = enriquecer([p])
    if p["agotado"]:
        flash("Este regalo ya no está disponible. ¡Elige otro!", "error")
        return redirect(url_for("producto", producto_id=producto_id))

    # Crear regalador y reserva en una transacción
    now = now_iso()
    cur = db.execute("INSERT INTO regaladores (nombre, creado_en) VALUES (?,?)",
                     (nombre, now))
    regalador_id = cur.lastrowid
    db.execute(
        "INSERT INTO reservas (producto_id, regalador_id, estado, creado_en) "
        "VALUES (?,?, 'reserved', ?)", (producto_id, regalador_id, now))
    db.commit()

    session["reserva_producto_id"] = producto_id
    session["reserva_nombre"] = nombre
    flash("¡Gracias por tu detalle con Isaac! Tu regalo quedó reservado.", "ok")
    return redirect(url_for("confirmacion", producto_id=producto_id))


@app.route("/regalo/<int:producto_id>/confirmacion")
def confirmacion(producto_id):
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    nombre = session.get("reserva_nombre", "")
    return render_template("confirmacion.html", p=p, nombre=nombre,
                           binance=get_binance_data(),
                           contacto=get_contacto())


@app.route("/regalo/<int:producto_id>/aportar", methods=["POST"])
def aportar(producto_id):
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    nombre = request.form.get("nombre", "").strip()
    monto_str = request.form.get("monto", "").strip()
    if not nombre:
        flash("Por favor escribe tu nombre para aportar.", "error")
        return redirect(url_for("producto", producto_id=producto_id))
    try:
        monto = float(monto_str)
    except ValueError:
        monto = 0.0
    if monto <= 0:
        flash("Escribe un monto válido para tu aporte.", "error")
        return redirect(url_for("producto", producto_id=producto_id))
    db.execute(
        "INSERT INTO aportes (producto_id, nombre, monto, creado_en) VALUES (?,?,?,?)",
        (producto_id, nombre, monto, now_iso()))
    db.commit()
    flash("¡Gracias por tu aporte! 🎉", "ok")
    return redirect(url_for("producto", producto_id=producto_id))


@app.route("/confirmar-asistencia", methods=["POST"])
def confirmar_asistencia():
    db = get_db()
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "Escribe tu nombre"}), 400
    db.execute("INSERT INTO asistentes (nombre, creado_en) VALUES (?,?)",
               (nombre, now_iso()))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Panel privado (admin)
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin_login():
    if is_admin():
        return redirect(url_for("dashboard"))
    return render_template("admin_login.html")


@app.route("/admin/login", methods=["POST"])
def admin_login_post():
    user = request.form.get("usuario", "").strip()
    password = request.form.get("password", "")
    if user == ADMIN_USER and check_admin_password(password):
        session["admin"] = True
        flash("Bienvenida, Fabi 👽", "ok")
        return redirect(url_for("dashboard"))
    flash("Usuario o contraseña incorrectos.", "error")
    return redirect(url_for("admin_login"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))


@app.route("/admin/dashboard")
def dashboard():
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY id").fetchall()
    productos = enriquecer(rows)

    reservas = db.execute("""
        SELECT r.*, p.nombre AS producto_nombre, p.precio, p.emoji,
               rg.nombre AS regalador_nombre
        FROM reservas r
        JOIN productos p ON p.id = r.producto_id
        JOIN regaladores rg ON rg.id = r.regalador_id
        ORDER BY r.creado_en DESC
    """).fetchall()

    aportes = db.execute("""
        SELECT a.*, p.nombre AS producto_nombre
        FROM aportes a
        JOIN productos p ON p.id = a.producto_id
        ORDER BY a.creado_en DESC
    """).fetchall()

    asistentes = db.execute(
        "SELECT * FROM asistentes ORDER BY creado_en DESC").fetchall()

    total_disponibles = sum(p["disponibles"] for p in productos)
    total_reservados = sum(p["reservados"] for p in productos)
    total_pagados = sum(p["pagados"] for p in productos)
    counts = {
        "available": total_disponibles,
        "reserved": total_reservados,
        "paid": total_pagados,
    }
    return render_template("dashboard.html",
                           productos=productos, reservas=reservas,
                           aportes=aportes, asistentes=asistentes,
                           counts=counts,
                           categorias=CATEGORIES,
                           binance=get_binance_data(),
                           contacto=get_contacto())


@app.route("/admin/config", methods=["POST"])
def guardar_config():
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    binance = request.form.get("binance", "").strip()
    if binance:
        set_config(db, "binance_data", binance)
        flash("Datos de pago actualizados ✅", "ok")

    contacto = request.form.get("contacto", "").strip()
    if contacto:
        set_config(db, "contacto", contacto)
        flash("Mensaje de contacto actualizado ✅", "ok")

    nueva_pass = request.form.get("nueva_password", "")
    if nueva_pass:
        set_config(db, "admin_password_hash", generate_password_hash(nueva_pass))
        flash("Contraseña actualizada ✅", "ok")

    return redirect(url_for("dashboard"))


# --- Reservas: confirmar pago / liberar (por reserva individual) ---
@app.route("/admin/reserva/<int:reserva_id>/confirmar", methods=["POST"])
def confirmar_pago(reserva_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    r = db.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if r is None:
        abort(404)
    db.execute("UPDATE reservas SET estado = 'paid', pagado_en = ? WHERE id = ?",
               (now_iso(), reserva_id))
    db.commit()
    flash("Pago confirmado ✅", "ok")
    return redirect(url_for("dashboard"))


@app.route("/admin/reserva/<int:reserva_id>/liberar", methods=["POST"])
def liberar_reserva(reserva_id):
    """Libera una reserva (si alguien se arrepintió o no pagó)."""
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    db.execute("DELETE FROM reservas WHERE id = ?", (reserva_id,))
    db.commit()
    flash("Reserva liberada (unidad disponible de nuevo).", "ok")
    return redirect(url_for("dashboard"))


# --- CRUD de regalos ---
@app.route("/admin/regalo/nuevo", methods=["POST"])
def nuevo_regalo():
    if not is_admin():
        return redirect(url_for("admin_login"))
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    categoria = request.form.get("categoria", "").strip()
    precio = request.form.get("precio", "0").strip()
    emoji = request.form.get("emoji", "🎁").strip()
    imagen = request.form.get("imagen", "").strip()
    cantidad = request.form.get("cantidad", "1").strip()

    if not nombre or not categoria:
        flash("Nombre y categoría son obligatorios.", "error")
        return redirect(url_for("dashboard"))

    try:
        precio_f = float(precio)
    except ValueError:
        precio_f = 0.0
    try:
        cantidad_i = max(1, int(cantidad))
    except ValueError:
        cantidad_i = 1

    db = get_db()
    db.execute(
        "INSERT INTO productos (nombre, descripcion, categoria, precio, emoji, imagen, cantidad, creado_en) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (nombre, descripcion, categoria, precio_f, emoji, imagen, cantidad_i, now_iso()))
    db.commit()
    flash(f"Regalo '{nombre}' agregado ✅", "ok")
    return redirect(url_for("dashboard"))


@app.route("/admin/regalo/<int:producto_id>/editar", methods=["POST"])
def editar_regalo(producto_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    categoria = request.form.get("categoria", "").strip()
    precio = request.form.get("precio", "0").strip()
    emoji = request.form.get("emoji", "🎁").strip()
    cantidad = request.form.get("cantidad", "1").strip()

    try:
        precio_f = float(precio)
    except ValueError:
        precio_f = 0.0
    try:
        cantidad_i = max(1, int(cantidad))
    except ValueError:
        cantidad_i = 1

    db = get_db()
    imagen = request.form.get("imagen", "").strip()
    if not imagen:
        # Conservar la imagen actual si el formulario no la trae.
        actual = db.execute(
            "SELECT imagen FROM productos WHERE id = ?", (producto_id,)).fetchone()
        imagen = actual["imagen"] if actual else ""
    db.execute(
        "UPDATE productos SET nombre=?, descripcion=?, categoria=?, precio=?, emoji=?, imagen=?, cantidad=? WHERE id=?",
        (nombre, descripcion, categoria, precio_f, emoji, imagen, cantidad_i, producto_id))
    db.commit()
    flash(f"Regalo '{nombre}' actualizado ✅", "ok")
    return redirect(url_for("dashboard"))


@app.route("/admin/regalo/<int:producto_id>/eliminar", methods=["POST"])
def eliminar_regalo(producto_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    db.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    db.commit()
    flash(f"Regalo '{p['nombre']}' eliminado 🗑️", "ok")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
# Inicializa la base de datos al importar (necesario para gunicorn en Render).
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
