from flask import Flask, render_template, request, redirect, session
import mysql.connector
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "taqueria_secret_key_123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="taqueria"
    )


@app.template_filter("fecha_bonita")
def fecha_bonita(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except:
            return value
    return value.strftime("%d/%m/%Y - %I:%M %p")


def obtener_estadisticas():
    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT COUNT(*) AS total_productos FROM productos")
    total_productos = cursor.fetchone()["total_productos"]

    cursor.execute("SELECT COUNT(*) AS pedidos_pendientes FROM pedidos WHERE estado='pendiente'")
    pedidos_pendientes = cursor.fetchone()["pedidos_pendientes"]

    cursor.execute("SELECT COUNT(*) AS total_ventas FROM ventas")
    total_ventas = cursor.fetchone()["total_ventas"]

    cursor.execute("SELECT COALESCE(SUM(total), 0) AS ingresos FROM ventas")
    ingresos = cursor.fetchone()["ingresos"]

    cursor.close()
    db.close()

    return {
        "total_productos": total_productos,
        "pedidos_pendientes": pedidos_pendientes,
        "total_ventas": total_ventas,
        "ingresos": ingresos
    }


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True, buffered=True)

        cursor.execute(
            "SELECT * FROM usuarios WHERE usuario=%s AND password=%s LIMIT 1",
            (usuario, password)
        )
        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user:
            session["usuario"] = user["usuario"]
            session["rol"] = user["rol"]
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="❌ Usuario o contraseña incorrectos")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    rol = session["rol"]
    usuario = session["usuario"]
    stats = obtener_estadisticas()

    if rol == "admin":
        return render_template("dashboard_admin.html", usuario=usuario, rol=rol, stats=stats)
    elif rol == "mesero":
        return render_template("dashboard_mesero.html", usuario=usuario, rol=rol, stats=stats)
    elif rol == "cajero":
        return render_template("dashboard_cajero.html", usuario=usuario, rol=rol, stats=stats)
    else:
        return "❌ Rol no válido"


@app.route("/productos", methods=["GET", "POST"])
def productos():
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] != "admin":
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    if request.method == "POST":
        nombre = request.form["nombre"]
        precio = request.form["precio"]
        categoria = request.form["categoria"]

        imagen = request.files.get("imagen")
        nombre_imagen = None  # ← SIEMPRE definida

        if imagen and imagen.filename != "":
            nombre_imagen = imagen.filename
            ruta = os.path.join(app.config["UPLOAD_FOLDER"], nombre_imagen)
            imagen.save(ruta)

        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria, imagen) VALUES (%s, %s, %s, %s)",
            (nombre, precio, categoria, nombre_imagen)
        )
        db.commit()

        cursor.close()
        db.close()
        return redirect("/productos")

    cursor.execute("SELECT * FROM productos")
    productos = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "productos.html",
        productos=productos,
        usuario=session["usuario"],
        rol=session["rol"]
    )


@app.route("/editar_producto/<int:id_producto>", methods=["GET", "POST"])
def editar_producto(id_producto):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] != "admin":
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    if request.method == "POST":
        nombre = request.form["nombre"]
        precio = request.form["precio"]
        categoria = request.form["categoria"]
        imagen = request.files.get("imagen")

        cursor.execute(
            "SELECT * FROM productos WHERE id_producto=%s",
            (id_producto,)
        )
        producto_actual = cursor.fetchone()

        nombre_imagen = producto_actual["imagen"]

        if imagen and imagen.filename:
            if producto_actual["imagen"]:
                ruta_vieja = os.path.join(app.config["UPLOAD_FOLDER"], producto_actual["imagen"])
                if os.path.exists(ruta_vieja):
                    os.remove(ruta_vieja)

            nombre_imagen = imagen.filename
            ruta_nueva = os.path.join(app.config["UPLOAD_FOLDER"], nombre_imagen)
            imagen.save(ruta_nueva)

        cursor.execute(
            """
            UPDATE productos
            SET nombre=%s, precio=%s, categoria=%s, imagen=%s
            WHERE id_producto=%s
            """,
            (nombre, precio, categoria, nombre_imagen, id_producto)
        )
        db.commit()

        cursor.close()
        db.close()
        return redirect("/productos")

    cursor.execute(
        "SELECT * FROM productos WHERE id_producto=%s",
        (id_producto,)
    )
    producto = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template(
        "editar_producto.html",
        producto=producto,
        usuario=session["usuario"],
        rol=session["rol"]
    )


@app.route("/eliminar_producto/<int:id_producto>", methods=["POST"])
def eliminar_producto(id_producto):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] != "admin":
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        "SELECT imagen FROM productos WHERE id_producto=%s",
        (id_producto,)
    )
    producto = cursor.fetchone()

    if producto and producto["imagen"]:
        ruta_imagen = os.path.join(app.config["UPLOAD_FOLDER"], producto["imagen"])
        if os.path.exists(ruta_imagen):
            os.remove(ruta_imagen)

    cursor.execute(
        "DELETE FROM productos WHERE id_producto=%s",
        (id_producto,)
    )
    db.commit()

    cursor.close()
    db.close()

    return redirect("/productos")


@app.route("/pedidos", methods=["GET", "POST"])
def pedidos():
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "mesero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT * FROM productos ORDER BY nombre")
    productos = cursor.fetchall()

    # AGREGAR PRODUCTO AL PEDIDO ACTUAL
    if request.method == "POST":
        producto_id = request.form["producto"]
        cantidad = int(request.form["cantidad"])

        # si no existe pedido actual en sesión, lo crea
        if "pedido_actual_id" not in session:
            cursor.execute(
                "INSERT INTO pedidos (mesa, estado) VALUES (%s, %s)",
                (1, "en_armado")
            )
            db.commit()
            session["pedido_actual_id"] = cursor.lastrowid

        pedido_actual_id = session["pedido_actual_id"]

        cursor.execute(
            "SELECT * FROM productos WHERE id_producto=%s",
            (producto_id,)
        )
        producto = cursor.fetchone()

        if not producto:
            cursor.close()
            db.close()
            return "❌ Producto no encontrado"

        subtotal = float(producto["precio"]) * cantidad

        cursor.execute(
            """
            INSERT INTO detalle_pedido (id_pedido, id_producto, cantidad, subtotal)
            VALUES (%s, %s, %s, %s)
            """,
            (pedido_actual_id, producto["id_producto"], cantidad, subtotal)
        )
        db.commit()

        cursor.close()
        db.close()
        return redirect("/pedidos")

    # CARGAR PEDIDO ACTUAL
    pedido_actual_id = session.get("pedido_actual_id")
    detalles_actuales = []
    total_actual = 0

    if pedido_actual_id:
        cursor.execute("""
            SELECT
                d.id_detalle,
                d.id_pedido,
                pr.nombre AS producto,
                d.cantidad,
                d.subtotal
            FROM detalle_pedido d
            INNER JOIN productos pr ON d.id_producto = pr.id_producto
            WHERE d.id_pedido = %s
        """, (pedido_actual_id,))
        detalles_actuales = cursor.fetchall()

        cursor.execute("""
            SELECT COALESCE(SUM(subtotal), 0) AS total
            FROM detalle_pedido
            WHERE id_pedido = %s
        """, (pedido_actual_id,))
        total_actual = cursor.fetchone()["total"]

    # LISTA DE PEDIDOS YA GUARDADOS
    cursor.execute("""
        SELECT
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado,
            COALESCE(SUM(d.subtotal), 0) AS total
        FROM pedidos p
        LEFT JOIN detalle_pedido d ON p.id_pedido = d.id_pedido
        WHERE p.estado IN ('pendiente', 'cancelado', 'pagado')
        GROUP BY p.id_pedido, p.fecha, p.mesa, p.estado
        ORDER BY p.id_pedido DESC
    """)
    lista_pedidos = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "pedidos.html",
        productos=productos,
        pedido_actual_id=pedido_actual_id,
        detalles_actuales=detalles_actuales,
        total_actual=total_actual,
        pedidos=lista_pedidos,
        usuario=session["usuario"],
        rol=session["rol"]
    )


@app.route("/quitar_detalle/<int:id_detalle>", methods=["POST"])
def quitar_detalle(id_detalle):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "mesero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        "DELETE FROM detalle_pedido WHERE id_detalle=%s",
        (id_detalle,)
    )
    db.commit()

    pedido_actual_id = session.get("pedido_actual_id")
    if pedido_actual_id:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM detalle_pedido WHERE id_pedido=%s",
            (pedido_actual_id,)
        )
        total_detalles = cursor.fetchone()["total"]

        if total_detalles == 0:
            cursor.execute(
                "DELETE FROM pedidos WHERE id_pedido=%s AND estado='en_armado'",
                (pedido_actual_id,)
            )
            db.commit()
            session.pop("pedido_actual_id", None)

    cursor.close()
    db.close()

    return redirect("/pedidos")


@app.route("/finalizar_pedido", methods=["POST"])
def finalizar_pedido():
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "mesero"]:
        return "⛔ Acceso denegado"

    pedido_actual_id = session.get("pedido_actual_id")
    if not pedido_actual_id:
        return redirect("/pedidos")

    db = get_db()
    cursor = db.cursor(buffered=True)

    cursor.execute(
        "UPDATE pedidos SET estado=%s WHERE id_pedido=%s",
        ("pendiente", pedido_actual_id)
    )
    db.commit()

    cursor.close()
    db.close()

    session.pop("pedido_actual_id", None)
    return redirect("/pedidos")


@app.route("/cancelar_pedido/<int:id_pedido>", methods=["POST"])
def cancelar_pedido(id_pedido):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "mesero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(buffered=True)

    cursor.execute(
        "UPDATE pedidos SET estado=%s WHERE id_pedido=%s",
        ("cancelado", id_pedido)
    )
    db.commit()

    cursor.close()
    db.close()

    return redirect("/pedidos")


@app.route("/ventas")
def ventas():
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "cajero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    # pedidos pendientes listos para cobrar
    cursor.execute("""
        SELECT
            p.id_pedido,
            p.fecha,
            p.mesa,
            p.estado,
            COALESCE(SUM(d.subtotal), 0) AS total
        FROM pedidos p
        LEFT JOIN detalle_pedido d ON p.id_pedido = d.id_pedido
        WHERE p.estado = 'pendiente'
        GROUP BY p.id_pedido, p.fecha, p.mesa, p.estado
        ORDER BY p.id_pedido DESC
    """)
    pedidos_pendientes = cursor.fetchall()

    # historial de ventas
    cursor.execute("""
        SELECT
            v.id_venta,
            v.id_pedido,
            v.total,
            v.fecha
        FROM ventas v
        ORDER BY v.id_venta DESC
    """)
    historial_ventas = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "ventas.html",
        pedidos=pedidos_pendientes,
        ventas=historial_ventas,
        usuario=session["usuario"],
        rol=session["rol"]
    )


@app.route("/cobrar_pedido/<int:id_pedido>", methods=["POST"])
def cobrar_pedido(id_pedido):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "cajero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT COALESCE(SUM(subtotal), 0) AS total
        FROM detalle_pedido
        WHERE id_pedido=%s
    """, (id_pedido,))
    resultado = cursor.fetchone()

    total = resultado["total"] if resultado["total"] else 0

    cursor.execute(
        "INSERT INTO ventas (id_pedido, total) VALUES (%s, %s)",
        (id_pedido, total)
    )
    db.commit()

    id_venta = cursor.lastrowid

    cursor.execute(
        "UPDATE pedidos SET estado=%s WHERE id_pedido=%s",
        ("pagado", id_pedido)
    )
    db.commit()

    cursor.close()
    db.close()

    return redirect(f"/ticket/{id_venta}")


@app.route("/ticket/<int:id_venta>")
def ticket(id_venta):
    if "usuario" not in session or "rol" not in session:
        return redirect("/")

    if session["rol"] not in ["admin", "cajero"]:
        return "⛔ Acceso denegado"

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT
            v.id_venta,
            v.id_pedido,
            v.total,
            v.fecha,
            p.mesa
        FROM ventas v
        INNER JOIN pedidos p ON v.id_pedido = p.id_pedido
        WHERE v.id_venta = %s
    """, (id_venta,))
    encabezado = cursor.fetchone()

    cursor.execute("""
        SELECT
            pr.nombre AS producto,
            d.cantidad,
            d.subtotal
        FROM detalle_pedido d
        INNER JOIN productos pr ON d.id_producto = pr.id_producto
        WHERE d.id_pedido = %s
    """, (encabezado["id_pedido"],))
    detalles = cursor.fetchall()

    cursor.close()
    db.close()

    if not encabezado:
        return "❌ Ticket no encontrado"

    return render_template(
        "ticket.html",
        ticket=encabezado,
        detalles=detalles,
        usuario=session["usuario"]
    )


if __name__ == "__main__":
    app.run(debug=True)