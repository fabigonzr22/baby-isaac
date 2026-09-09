"""Baby Isaac — Wishlist web app.

Arquitectura:
- Página pública: portada, wishlist con filtros, producto, "Quiero regalarlo",
  nombre, confirmación, datos de Binance, aviso de pendiente.
- Panel privado (admin): login, dashboard, estados available/reserved/paid,
  confirmar pago, CRUD de regalos.
- Base de datos SQLite: productos, reservas, regaladores, estados de pago.
"""
import os
import sqlite3
import secrets
from datetime import datetime, timezone

from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, flash, abort)
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

# Datos de pago Binance (se pueden editar desde el panel admin → Configuración).
DEFAULT_BINANCE_DATA = os.environ.get("BINANCE_DATA") or (
    "USDT · Red TRC20\n"
    "Dirección: TU_DIRECCION_DE_BINANCE_AQUI\n"
    "Nombre: TU_NOMBRE_EN_BINANCE\n"
    "Monto: el indicado en el regalo")

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
    db.executescript("""
    CREATE TABLE IF NOT EXISTS productos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre      TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        categoria   TEXT NOT NULL,
        precio      REAL NOT NULL,
        emoji       TEXT NOT NULL DEFAULT '🎁',
        estado      TEXT NOT NULL DEFAULT 'available'
            CHECK (estado IN ('available','reserved','paid')),
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
    """)
    db.commit()

    # Semillas iniciales si la tabla está vacía
    cur = db.execute("SELECT COUNT(*) FROM productos")
    if cur.fetchone()[0] == 0:
        seed = [
            ("Bodys de algodón", "Suaves y cómodos para el día a día de Isaac.", "Ropa", 5, "👕"),
            ("Pijamas", "Para que Isaac duerma calentito y cómodo.", "Ropa", 15, "🌙"),
            ("Medias", "Para mantener calentitos esos piececitos.", "Ropa", 10, "🧦"),
            ("Franelas", "Franelas suaves para el día a día.", "Ropa", 16, "👚"),
            ("Camisas", "Camisas bonitas para Isaac.", "Ropa", 5, "👔"),
            ("Pantalones", "Pantalones cómodos para el bebé.", "Ropa", 15, "👖"),
            ("Colchón para colecho", "Para que Isaac duerma cerca y seguro.", "Dormir", 35, "🛏️"),
            ("Sábanas de algodón", "Sábanas suaves de algodón para la cuna.", "Dormir", 28, "🧺"),
            ("Mantas", "Mantas abrigadas para Isaac.", "Dormir", 24, "🧸"),
            ("Swaddle", "Para envolver y calmar al bebé.", "Dormir", 25, "🦢"),
            ("Lámpara de noche", "Luz suave para las noches de Isaac.", "Dormir", 25, "💡"),
            ("Porta bebé", "Para llevar a Isaac cerca de ti.", "Paseo", 34, "👶"),
            ("Libro para bebé (0-3 meses)", "Primeras lecturas para estimular a Isaac.", "Aprendizaje", 25, "📖"),
            ("Pañalera", "Para salir de paseo con todo lo necesario.", "Paseo", 40, "🎒"),
            ("Pañales", "Los básicos de todo bebé.", "Cuidado", 0, "🧷"),
            ("Termómetro digital", "Para cuidar la temperatura de Isaac.", "Cuidado", 30, "🌡️"),
            ("Aspirador nasal eléctrico", "Para despejar la naricita de Isaac.", "Cuidado", 0, "🔌"),
            ("Aspirador nasal manual", "Alternativa manual y práctica.", "Cuidado", 20, "🤧"),
            ("Nebulizador", "Para cuidar las vías respiratorias de Isaac.", "Cuidado", 0, "🫧"),
            ("Teteros / limpiador de tetero", "Kit de teteros y limpiador.", "Alimentación", 65, "🍼"),
        ]
        now = datetime.now(timezone.utc).isoformat()
        db.executemany(
            "INSERT INTO productos (nombre, descripcion, categoria, precio, emoji, estado, creado_en) "
            "VALUES (?,?,?,?,?, 'available', ?)", [(*p, now) for p in seed])
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


CATEGORIES = ["Ropa", "Dormir", "Paseo", "Alimentación", "Cuidado", "Aprendizaje"]
CATEGORY_EMOJI = {
    "Ropa": "👕", "Dormir": "🛏️", "Paseo": "👶", "Alimentación": "🍼",
    "Cuidado": "🧷", "Aprendizaje": "📖",
}
STATUS_LABEL = {
    "available": "Disponible",
    "reserved": "Reservado",
    "paid": "Pagado",
}


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
    return f"${p:,.0f}"


# ---------------------------------------------------------------------------
# Página pública
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()
    categoria = request.args.get("categoria", "")
    if categoria and categoria in CATEGORIES:
        productos = db.execute(
            "SELECT * FROM productos WHERE categoria = ? ORDER BY id",
            (categoria,)).fetchall()
    else:
        productos = db.execute(
            "SELECT * FROM productos ORDER BY id").fetchall()
    return render_template("index.html",
                           productos=productos,
                           categorias=CATEGORIES,
                           categoria_actual=categoria,
                           STATUS_LABEL=STATUS_LABEL)


@app.route("/regalo/<int:producto_id>")
def producto(producto_id):
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    return render_template("producto.html", p=p, STATUS_LABEL=STATUS_LABEL)


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

    if p["estado"] != "available":
        flash("Este regalo ya fue reservado. ¡Elige otro!", "error")
        return redirect(url_for("producto", producto_id=producto_id))

    # Crear regalador y reserva en una transacción
    now = now_iso()
    cur = db.execute("INSERT INTO regaladores (nombre, creado_en) VALUES (?,?)",
                     (nombre, now))
    regalador_id = cur.lastrowid
    db.execute(
        "INSERT INTO reservas (producto_id, regalador_id, estado, creado_en) "
        "VALUES (?,?, 'reserved', ?)", (producto_id, regalador_id, now))
    db.execute("UPDATE productos SET estado = 'reserved' WHERE id = ?",
               (producto_id,))
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
                           binance=get_binance_data())


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
    productos = db.execute(
        "SELECT * FROM productos ORDER BY estado, id").fetchall()
    # reservas con nombre del regalador
    reservas = db.execute("""
        SELECT r.*, p.nombre AS producto_nombre, p.precio, p.emoji,
               rg.nombre AS regalador_nombre
        FROM reservas r
        JOIN productos p ON p.id = r.producto_id
        JOIN regaladores rg ON rg.id = r.regalador_id
        ORDER BY r.creado_en DESC
    """).fetchall()
    counts = {
        "available": db.execute("SELECT COUNT(*) c FROM productos WHERE estado='available'").fetchone()["c"],
        "reserved": db.execute("SELECT COUNT(*) c FROM productos WHERE estado='reserved'").fetchone()["c"],
        "paid": db.execute("SELECT COUNT(*) c FROM productos WHERE estado='paid'").fetchone()["c"],
    }
    return render_template("dashboard.html",
                           productos=productos, reservas=reservas,
                           counts=counts, STATUS_LABEL=STATUS_LABEL,
                           categorias=CATEGORIES,
                           binance=get_binance_data())


@app.route("/admin/config", methods=["POST"])
def guardar_config():
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    binance = request.form.get("binance", "").strip()
    if binance:
        set_config(db, "binance_data", binance)
        flash("Datos de pago actualizados ✅", "ok")

    nueva_pass = request.form.get("nueva_password", "")
    if nueva_pass:
        set_config(db, "admin_password_hash", generate_password_hash(nueva_pass))
        flash("Contraseña actualizada ✅", "ok")

    return redirect(url_for("dashboard"))


@app.route("/admin/regalo/<int:producto_id>/confirmar", methods=["POST"])
def confirmar_pago(producto_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    db.execute("UPDATE productos SET estado = 'paid' WHERE id = ?",
               (producto_id,))
    db.execute(
        "UPDATE reservas SET estado = 'paid', pagado_en = ? "
        "WHERE producto_id = ? AND estado = 'reserved'",
        (now_iso(), producto_id))
    db.commit()
    flash(f"'{p['nombre']}' marcado como PAGADO ✅", "ok")
    return redirect(url_for("dashboard"))


@app.route("/admin/regalo/<int:producto_id>/liberar", methods=["POST"])
def liberar_regalo(producto_id):
    """Devuelve un regalo a 'available' (si alguien se arrepintió o no pagó)."""
    if not is_admin():
        return redirect(url_for("admin_login"))
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ?",
                   (producto_id,)).fetchone()
    if p is None:
        abort(404)
    db.execute("UPDATE productos SET estado = 'available' WHERE id = ?",
               (producto_id,))
    db.execute("DELETE FROM reservas WHERE producto_id = ? AND estado = 'reserved'",
               (producto_id,))
    db.commit()
    flash(f"'{p['nombre']}' vuelto a Disponible.", "ok")
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

    if not nombre or not categoria:
        flash("Nombre y categoría son obligatorios.", "error")
        return redirect(url_for("dashboard"))

    try:
        precio_f = float(precio)
    except ValueError:
        precio_f = 0.0

    db = get_db()
    db.execute(
        "INSERT INTO productos (nombre, descripcion, categoria, precio, emoji, estado, creado_en) "
        "VALUES (?,?,?,?,?, 'available', ?)",
        (nombre, descripcion, categoria, precio_f, emoji, now_iso()))
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

    try:
        precio_f = float(precio)
    except ValueError:
        precio_f = 0.0

    db = get_db()
    db.execute(
        "UPDATE productos SET nombre=?, descripcion=?, categoria=?, precio=?, emoji=? WHERE id=?",
        (nombre, descripcion, categoria, precio_f, emoji, producto_id))
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
# Inicializa la base de datos al importar (necesario para gunicorn en Render,
# donde no se ejecuta el bloque `__main__`).
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
