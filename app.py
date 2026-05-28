from flask import Flask, render_template, request, redirect, session
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "taqueria_secret_key_123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# CONEXIÓN POSTGRESQL
# =========================
def get_db():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        sslmode="require"
    )


# =========================
# FILTRO FECHA
# =========================
@app.template_filter("fecha_bonita")
def fecha_bonita(value):

    if not value:
        return ""

    if isinstance(value, str):
        try:
            value = datetime.strptime(
                value,
                "%Y-%m-%d %H:%M:%S"
            )
        except:
            return value

    return value.strftime("%d/%m/%Y - %I:%M %p")


# =========================
# ESTADÍSTICAS
# =========================
def obtener_estadisticas():

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        "SELECT COUNT(*) AS total_productos FROM productos"
    )
    total_productos = cursor.fetchone()["total_productos"]

    cursor.execute(
        """
        SELECT COUNT(*) AS pedidos_pendientes
        FROM pedidos
        WHERE estado='pendiente'
        """
    )

    pedidos_pendientes = cursor.fetchone()["pedidos_pendientes"]

    cursor.execute(
        "SELECT COUNT(*) AS total_ventas FROM ventas"
    )

    total_ventas = cursor.fetchone()["total_ventas"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(total),0) AS ingresos
        FROM ventas
        """
    )

    ingresos = cursor.fetchone()["ingresos"]

    cursor.close()
    db.close()

    return {
        "total_productos": total_productos,
        "pedidos_pendientes": pedidos_pendientes,
        "total_ventas": total_ventas,
        "ingresos": ingresos
    }


# =========================
# LOGIN
# =========================
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form["usuario"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT *
            FROM usuarios
            WHERE usuario=%s
            AND password=%s
            LIMIT 1
            """,
            (usuario, password)
        )

        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user:

            session["usuario"] = user["usuario"]
            session["rol"] = user["rol"]

            return redirect("/dashboard")

        return render_template(
            "login.html",
            error="❌ Usuario o contraseña incorrectos"
        )

    return render_template("login.html")


# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():

    if "usuario" not in session:
        return redirect("/")

    rol = session["rol"]
    usuario = session["usuario"]

    stats = obtener_estadisticas()

    if rol == "admin":

        return render_template(
            "dashboard_admin.html",
            usuario=usuario,
            rol=rol,
            stats=stats
        )

    elif rol == "mesero":

        return render_template(
            "dashboard_mesero.html",
            usuario=usuario,
            rol=rol,
            stats=stats
        )

    elif rol == "cajero":

        return render_template(
            "dashboard_cajero.html",
            usuario=usuario,
            rol=rol,
            stats=stats
        )

    return "❌ Rol no válido"


# =========================
# PRODUCTOS
# =========================
@app.route("/productos", methods=["GET", "POST"])
def productos():

    if "usuario" not in session:
        return redirect("/")

    if session["rol"] != "admin":
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":

        nombre = request.form["nombre"]
        precio = request.form["precio"]
        categoria = request.form["categoria"]

        imagen = request.files.get("imagen")
        nombre_imagen = None

        if imagen and imagen.filename != "":

            nombre_imagen = imagen.filename

            ruta = os.path.join(
                app.config["UPLOAD_FOLDER"],
                nombre_imagen
            )

            imagen.save(ruta)

        cursor.execute(
            """
            INSERT INTO productos
            (nombre, precio, categoria, imagen)
            VALUES (%s, %s, %s, %s)
            """,
            (
                nombre,
                precio,
                categoria,
                nombre_imagen
            )
        )

        db.commit()

        cursor.close()
        db.close()

        return redirect("/productos")

    cursor.execute(
        """
        SELECT *
        FROM productos
        ORDER BY id_producto DESC
        """
    )

    productos = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "productos.html",
        productos=productos,
        usuario=session["usuario"],
        rol=session["rol"]
    )


# =========================
# PEDIDOS
# =========================
@app.route("/pedidos", methods=["GET", "POST"])
def pedidos():

    if "usuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT *
        FROM productos
        ORDER BY nombre
        """
    )

    productos = cursor.fetchall()

    # =========================
    # AGREGAR PRODUCTO
    # =========================
    if request.method == "POST":

        producto_id = request.form["producto"]
        cantidad = int(request.form["cantidad"])

        if "pedido_actual_id" not in session:

            cursor.execute(
                """
                INSERT INTO pedidos
                (mesa, estado)
                VALUES (%s, %s)
                RETURNING id_pedido
                """,
                (1, "en_armado")
            )

            pedido = cursor.fetchone()

            session["pedido_actual_id"] = pedido["id_pedido"]

            db.commit()

        pedido_actual_id = session["pedido_actual_id"]

        cursor.execute(
            """
            SELECT *
            FROM productos
            WHERE id_producto=%s
            """,
            (producto_id,)
        )

        producto = cursor.fetchone()

        subtotal = float(producto["precio"]) * cantidad

        cursor.execute(
            """
            INSERT INTO detalle_pedido
            (
                id_pedido,
                id_producto,
                cantidad,
                subtotal
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                pedido_actual_id,
                producto["id_producto"],
                cantidad,
                subtotal
            )
        )

        db.commit()

        cursor.close()
        db.close()

        return redirect("/pedidos")

    # =========================
    # PEDIDO ACTUAL
    # =========================
    pedido_actual_id = session.get("pedido_actual_id")

    detalles_actuales = []
    total_actual = 0

    if pedido_actual_id:

        cursor.execute(
            """
            SELECT
                d.id_detalle,
                pr.nombre AS producto,
                d.cantidad,
                d.subtotal
            FROM detalle_pedido d
            INNER JOIN productos pr
                ON d.id_producto = pr.id_producto
            WHERE d.id_pedido = %s
            """,
            (pedido_actual_id,)
        )

        detalles_actuales = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(subtotal),0) AS total
            FROM detalle_pedido
            WHERE id_pedido = %s
            """,
            (pedido_actual_id,)
        )

        total_actual = cursor.fetchone()["total"]

    # =========================
    # HISTORIAL PEDIDOS
    # =========================
    cursor.execute(
        """
        SELECT
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado,
            COALESCE(SUM(d.subtotal),0) AS total
        FROM pedidos p
        LEFT JOIN detalle_pedido d
            ON p.id_pedido = d.id_pedido
        GROUP BY
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado
        ORDER BY p.id_pedido DESC
        """
    )

    lista_pedidos = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "pedidos.html",
        productos=productos,
        detalles_actuales=detalles_actuales,
        total_actual=total_actual,
        pedido_actual_id=pedido_actual_id,
        pedidos=lista_pedidos,
        usuario=session["usuario"],
        rol=session["rol"]
    )


# =========================
# FINALIZAR PEDIDO
# =========================
@app.route("/finalizar_pedido", methods=["POST"])
def finalizar_pedido():

    if "pedido_actual_id" not in session:
        return redirect("/pedidos")

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE pedidos
        SET estado=%s
        WHERE id_pedido=%s
        """,
        (
            "pendiente",
            session["pedido_actual_id"]
        )
    )

    db.commit()

    cursor.close()
    db.close()

    session.pop("pedido_actual_id", None)

    return redirect("/pedidos")


# =========================
# CANCELAR PEDIDO
# =========================
@app.route("/cancelar_pedido/<int:id_pedido>", methods=["POST"])
def cancelar_pedido(id_pedido):

    if "usuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE pedidos
        SET estado='cancelado'
        WHERE id_pedido=%s
        """,
        (id_pedido,)
    )

    db.commit()

    cursor.close()
    db.close()

    return redirect("/pedidos")


# =========================
# VENTAS
# =========================
@app.route("/ventas")
def ventas():

    if "usuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado,
            COALESCE(SUM(d.subtotal),0) AS total
        FROM pedidos p
        LEFT JOIN detalle_pedido d
            ON p.id_pedido = d.id_pedido
        WHERE p.estado='pendiente'
        GROUP BY
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado
        ORDER BY p.id_pedido DESC
        """
    )

    pedidos = cursor.fetchall()

    cursor.execute(
        """
        SELECT *
        FROM ventas
        ORDER BY id_venta DESC
        """
    )

    historial_ventas = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "ventas.html",
        pedidos=pedidos,
        ventas=historial_ventas,
        usuario=session["usuario"],
        rol=session["rol"]
    )


# =========================
# COBRAR PEDIDO
# =========================
@app.route("/cobrar_pedido/<int:id_pedido>", methods=["POST"])
def cobrar_pedido(id_pedido):

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(subtotal),0) AS total
        FROM detalle_pedido
        WHERE id_pedido=%s
        """,
        (id_pedido,)
    )

    resultado = cursor.fetchone()

    total = resultado["total"]

    cursor.execute(
        """
        INSERT INTO ventas
        (id_pedido, total)
        VALUES (%s, %s)
        RETURNING id_venta
        """,
        (id_pedido, total)
    )

    id_venta = cursor.fetchone()["id_venta"]

    cursor.execute(
        """
        UPDATE pedidos
        SET estado='pagado'
        WHERE id_pedido=%s
        """,
        (id_pedido,)
    )

    db.commit()

    cursor.close()
    db.close()

    return redirect(f"/ticket/{id_venta}")


# =========================
# TICKET
# =========================
@app.route("/ticket/<int:id_venta>")
def ticket(id_venta):

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT
            v.id_venta,
            v.total,
            v.fecha,
            p.mesa,
            p.id_pedido
        FROM ventas v
        INNER JOIN pedidos p
            ON v.id_pedido = p.id_pedido
        WHERE v.id_venta=%s
        """,
        (id_venta,)
    )

    encabezado = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            pr.nombre AS producto,
            d.cantidad,
            d.subtotal
        FROM detalle_pedido d
        INNER JOIN productos pr
            ON d.id_producto = pr.id_producto
        WHERE d.id_pedido=%s
        """,
        (encabezado["id_pedido"],)
    )

    detalles = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "ticket.html",
        ticket=encabezado,
        detalles=detalles,
        usuario=session["usuario"]
    )


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    app.run(debug=True)