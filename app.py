
import streamlit as st
import sqlite3
from pathlib import Path
from datetime import date, datetime
import pandas as pd
import shutil
import hashlib
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "Base_Datos" / "derosasol_finanzas.db"
FACTURAS_DIR = APP_DIR / "Facturas"
BACKUPS_DIR = APP_DIR / "Backups"

for folder in [APP_DIR / "Base_Datos", FACTURAS_DIR, BACKUPS_DIR]:
    folder.mkdir(exist_ok=True)

SOCIOS = [
    ("Alfredo Miguel De La Rosa Durán", 25),
    ("Yeury Aponte", 25),
    ("Keny De La Rosa", 25),
    ("César Fernández", 25),
]

USUARIOS_INICIALES = [
    ("alfredo", "admin123", "Gerente", "Alfredo Miguel De La Rosa Durán"),
    ("yeury", "yeury123", "Socio", "Yeury Aponte"),
    ("keny", "keny123", "Socio", "Keny De La Rosa"),
    ("cesar", "cesar123", "Socio", "César Fernández"),
]

CATEGORIAS_GASTOS = [
    "IA",
    "Publicidad",
    "Equipos de oficina",
    "Luz",
    "Internet",
    "Software",
    "Oficina",
    "Hosting / Dominios",
    "Transporte",
    "Otros gastos internos",
]

CATEGORIAS_INGRESOS = [
    "Ganancia general",
    "Promoción musical",
    "Servicio",
    "Pago recibido",
    "Reembolso",
    "Otro ingreso",
]

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def conectar():
    return sqlite3.connect(DB_PATH)

def inicializar_db():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS socios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            participacion REAL NOT NULL DEFAULT 25
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL,
            socio_nombre TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            socio TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            moneda TEXT NOT NULL,
            metodo_pago TEXT,
            notas TEXT,
            factura_path TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            creado_por TEXT,
            creado_en TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            socio_registro TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            moneda TEXT NOT NULL,
            fuente TEXT,
            notas TEXT,
            comprobante_path TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            creado_por TEXT,
            creado_en TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aprobaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_movimiento TEXT NOT NULL,
            movimiento_id INTEGER NOT NULL,
            accion TEXT NOT NULL,
            usuario_aprobador TEXT,
            comentario TEXT,
            fecha_accion TEXT NOT NULL
        )
    """)
    # Agregar columnas nuevas si la base de datos ya existía
    for tabla in ["gastos", "ingresos"]:
        cur.execute(f"PRAGMA table_info({tabla})")
        columnas = [c[1] for c in cur.fetchall()]
        if "creado_por" not in columnas:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN creado_por TEXT")

    for nombre, participacion in SOCIOS:
        cur.execute(
            "INSERT OR IGNORE INTO socios (nombre, participacion) VALUES (?, ?)",
            (nombre, participacion)
        )

    for usuario, password, rol, socio_nombre in USUARIOS_INICIALES:
        cur.execute("""
            INSERT OR IGNORE INTO usuarios
            (usuario, password_hash, rol, socio_nombre, activo, creado_en)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (usuario, hash_password(password), rol, socio_nombre, datetime.now().isoformat()))

    conn.commit()
    conn.close()

def login(usuario, password):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT usuario, rol, socio_nombre
        FROM usuarios
        WHERE usuario = ? AND password_hash = ? AND activo = 1
    """, (usuario.lower().strip(), hash_password(password)))
    row = cur.fetchone()
    conn.close()
    return row

def guardar_archivo(uploaded_file, tipo, socio, fecha_registro):
    if uploaded_file is None:
        return ""
    safe_socio = (
        socio.replace(" ", "_")
        .replace("é", "e").replace("á", "a").replace("í", "i")
        .replace("ó", "o").replace("ú", "u")
        .replace("É", "E").replace("Á", "A").replace("Í", "I")
        .replace("Ó", "O").replace("Ú", "U")
    )
    carpeta = FACTURAS_DIR / tipo / safe_socio
    carpeta.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"{fecha_registro}_{timestamp}_{uploaded_file.name}"
    ruta = carpeta / nombre
    with open(ruta, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(ruta)

def cargar_df(tabla, usuario_actual=None, rol=None, socio_nombre=None):
    conn = conectar()

    if tabla == "socios":
        query = "SELECT * FROM socios ORDER BY id ASC"
        df = pd.read_sql_query(query, conn)

    elif tabla == "gastos":
        if rol == "Socio":
            df = pd.read_sql_query(
                "SELECT * FROM gastos WHERE socio = ? ORDER BY fecha DESC, id DESC",
                conn,
                params=(socio_nombre,)
            )
        else:
            df = pd.read_sql_query("SELECT * FROM gastos ORDER BY fecha DESC, id DESC", conn)

    elif tabla == "ingresos":
        if rol == "Socio":
            df = pd.read_sql_query(
                "SELECT * FROM ingresos WHERE socio_registro = ? ORDER BY fecha DESC, id DESC",
                conn,
                params=(socio_nombre,)
            )
        else:
            df = pd.read_sql_query("SELECT * FROM ingresos ORDER BY fecha DESC, id DESC", conn)

    elif tabla == "usuarios":
        df = pd.read_sql_query("SELECT id, usuario, rol, socio_nombre, activo, creado_en FROM usuarios ORDER BY id ASC", conn)

    else:
        df = pd.read_sql_query(f"SELECT * FROM {tabla}", conn)

    conn.close()
    return df

def actualizar_estado(tabla, registro_id, estado):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(f"UPDATE {tabla} SET estado = ? WHERE id = ?", (estado, registro_id))
    conn.commit()
    conn.close()

def cambiar_password(usuario, nueva_password):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "UPDATE usuarios SET password_hash = ? WHERE usuario = ?",
        (hash_password(nueva_password), usuario)
    )
    conn.commit()
    conn.close()

def crear_backup():
    BACKUPS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUPS_DIR / f"backup_derosasol_finanzas_{timestamp}.db"
    shutil.copy2(DB_PATH, destino)
    return destino

def resumen_dashboard(rol=None, socio_nombre=None):
    gastos = cargar_df("gastos", rol=rol, socio_nombre=socio_nombre)
    ingresos = cargar_df("ingresos", rol=rol, socio_nombre=socio_nombre)

    gastos_aprobados = gastos[gastos["estado"] == "Aprobado"] if not gastos.empty else gastos
    ingresos_aprobados = ingresos[ingresos["estado"] == "Aprobado"] if not ingresos.empty else ingresos

    total_gastos = float(gastos_aprobados["monto"].sum()) if not gastos_aprobados.empty else 0
    total_ingresos = float(ingresos_aprobados["monto"].sum()) if not ingresos_aprobados.empty else 0
    balance = total_ingresos - total_gastos

    return gastos, ingresos, total_gastos, total_ingresos, balance



def preparar_texto_moneda(df, columna_monto="monto"):
    if df is None or df.empty or columna_monto not in df.columns:
        return "$0.00"
    return f"${float(df[columna_monto].sum()):,.2f}"


def analizar_finanzas_local(gastos, ingresos):
    """IA financiera local V2 basada en reglas. No usa internet ni API."""
    lineas = []
    recomendaciones = []
    alertas = []

    gastos = gastos.copy() if gastos is not None else pd.DataFrame()
    ingresos = ingresos.copy() if ingresos is not None else pd.DataFrame()

    if not gastos.empty and "monto" in gastos.columns:
        gastos["monto"] = pd.to_numeric(gastos["monto"], errors="coerce").fillna(0)
    if not ingresos.empty and "monto" in ingresos.columns:
        ingresos["monto"] = pd.to_numeric(ingresos["monto"], errors="coerce").fillna(0)

    gastos_ap = gastos[gastos["estado"] == "Aprobado"].copy() if not gastos.empty and "estado" in gastos.columns else gastos.copy()
    ingresos_ap = ingresos[ingresos["estado"] == "Aprobado"].copy() if not ingresos.empty and "estado" in ingresos.columns else ingresos.copy()
    gastos_pend = gastos[gastos["estado"] == "Pendiente"].copy() if not gastos.empty and "estado" in gastos.columns else pd.DataFrame()
    ingresos_pend = ingresos[ingresos["estado"] == "Pendiente"].copy() if not ingresos.empty and "estado" in ingresos.columns else pd.DataFrame()

    total_gastos = float(gastos_ap["monto"].sum()) if not gastos_ap.empty and "monto" in gastos_ap.columns else 0
    total_ingresos = float(ingresos_ap["monto"].sum()) if not ingresos_ap.empty and "monto" in ingresos_ap.columns else 0
    balance = total_ingresos - total_gastos
    total_pend_g = float(gastos_pend["monto"].sum()) if not gastos_pend.empty and "monto" in gastos_pend.columns else 0
    total_pend_i = float(ingresos_pend["monto"].sum()) if not ingresos_pend.empty and "monto" in ingresos_pend.columns else 0

    pendientes_g = len(gastos_pend)
    pendientes_i = len(ingresos_pend)
    rechazados_g = len(gastos[gastos["estado"] == "Rechazado"]) if not gastos.empty and "estado" in gastos.columns else 0

    lineas.append("REPORTE IA FINANCIERA LOCAL V2 - DEROSASOL LLC")
    lineas.append(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lineas.append("")
    lineas.append("RESUMEN EJECUTIVO")
    lineas.append(f"Ingresos aprobados: ${total_ingresos:,.2f}")
    lineas.append(f"Gastos aprobados: ${total_gastos:,.2f}")
    lineas.append(f"Balance aprobado: ${balance:,.2f}")
    lineas.append(f"Gastos pendientes: {pendientes_g} (${total_pend_g:,.2f})")
    lineas.append(f"Ingresos pendientes: {pendientes_i} (${total_pend_i:,.2f})")
    lineas.append(f"Gastos rechazados: {rechazados_g}")

    if balance < 0:
        alertas.append("El balance aprobado está negativo. Antes de aprobar más gastos, conviene revisar ingresos próximos o aportes de socios.")
    elif balance == 0 and total_gastos > 0:
        alertas.append("El balance aprobado está en cero. La empresa no tiene margen disponible con los registros aprobados actuales.")
    else:
        recomendaciones.append("El balance aprobado no está en negativo. Mantén el control de aprobación antes de asumir nuevos gastos.")

    if pendientes_g > 0:
        alertas.append(f"Hay {pendientes_g} gasto(s) pendiente(s) por ${total_pend_g:,.2f}. Alfredo debe revisarlos antes de cerrar el reporte.")
    if pendientes_i > 0:
        alertas.append(f"Hay {pendientes_i} ingreso(s) pendiente(s) por ${total_pend_i:,.2f}. Si son correctos, pueden mejorar el balance.")

    if not gastos_ap.empty and "monto" in gastos_ap.columns:
        lineas.append("")
        lineas.append("GASTOS POR CATEGORÍA")
        cat = gastos_ap.groupby("categoria")["monto"].sum().sort_values(ascending=False) if "categoria" in gastos_ap.columns else pd.Series(dtype=float)
        for categoria, monto in cat.items():
            porc = (float(monto) / total_gastos * 100) if total_gastos else 0
            lineas.append(f"- {categoria}: ${float(monto):,.2f} ({porc:.1f}%)")
        if not cat.empty:
            categoria_top = cat.index[0]
            monto_top = float(cat.iloc[0])
            lineas.append(f"Categoría más costosa: {categoria_top} (${monto_top:,.2f})")
            if total_gastos and (monto_top / total_gastos) >= 0.35:
                recomendaciones.append(f"La categoría '{categoria_top}' concentra más del 35% del gasto aprobado. Revisa si hay suscripciones, publicidad o compras que se puedan consolidar.")

        lineas.append("")
        lineas.append("GASTOS POR SOCIO")
        socio_sum = gastos_ap.groupby("socio")["monto"].sum().sort_values(ascending=False) if "socio" in gastos_ap.columns else pd.Series(dtype=float)
        for socio, monto in socio_sum.items():
            porc = (float(monto) / total_gastos * 100) if total_gastos else 0
            lineas.append(f"- {socio}: ${float(monto):,.2f} ({porc:.1f}%)")
        if not socio_sum.empty:
            mayor_socio = socio_sum.index[0]
            mayor_monto = float(socio_sum.iloc[0])
            menor_socio = socio_sum.index[-1]
            menor_monto = float(socio_sum.iloc[-1])
            lineas.append(f"Socio que más ha invertido/aportado en gastos aprobados: {mayor_socio} (${mayor_monto:,.2f})")
            lineas.append(f"Socio con menor gasto aprobado registrado: {menor_socio} (${menor_monto:,.2f})")
            promedio = total_gastos / max(len(socio_sum), 1)
            if mayor_monto > promedio * 1.5 and len(socio_sum) > 1:
                recomendaciones.append(f"{mayor_socio} tiene una carga de gasto aprobada por encima del promedio. Conviene revisar si los demás socios deben compensar o aportar proporcionalmente.")

        limite_alto = max(250, total_gastos * 0.30)
        altos = gastos_ap[gastos_ap["monto"] >= limite_alto].sort_values("monto", ascending=False)
        if not altos.empty:
            alertas.append(f"Hay {len(altos)} gasto(s) alto(s) que merecen revisión individual.")
            lineas.append("")
            lineas.append("GASTOS ALTOS DETECTADOS")
            for _, r in altos.head(5).iterrows():
                lineas.append(f"- #{r.get('id','')} | {r.get('fecha','')} | {r.get('socio','')} | {r.get('categoria','')} | ${float(r.get('monto',0)):,.2f} | {r.get('descripcion','')}")

        cols_dup = [c for c in ["socio", "descripcion", "monto"] if c in gastos_ap.columns]
        if len(cols_dup) == 3:
            duplicados = gastos_ap[gastos_ap.duplicated(cols_dup, keep=False)].sort_values(cols_dup)
            if not duplicados.empty:
                alertas.append(f"Se detectaron {len(duplicados)} registro(s) con posible duplicidad por socio, descripción y monto.")
                lineas.append("")
                lineas.append("POSIBLES DUPLICADOS")
                for _, r in duplicados.head(8).iterrows():
                    lineas.append(f"- #{r.get('id','')} | {r.get('fecha','')} | {r.get('socio','')} | ${float(r.get('monto',0)):,.2f} | {r.get('descripcion','')}")
    else:
        recomendaciones.append("Todavía no hay gastos aprobados suficientes para evaluar socios, categorías o gastos altos.")

    if not ingresos_ap.empty and "monto" in ingresos_ap.columns:
        lineas.append("")
        lineas.append("INGRESOS POR CATEGORÍA")
        incat = ingresos_ap.groupby("categoria")["monto"].sum().sort_values(ascending=False) if "categoria" in ingresos_ap.columns else pd.Series(dtype=float)
        for categoria, monto in incat.items():
            porc = (float(monto) / total_ingresos * 100) if total_ingresos else 0
            lineas.append(f"- {categoria}: ${float(monto):,.2f} ({porc:.1f}%)")

    if total_gastos > total_ingresos and total_ingresos > 0:
        recomendaciones.append("Los gastos aprobados superan los ingresos aprobados. Antes de aprobar nuevos gastos, confirma de dónde saldrá el capital.")
    if total_gastos == 0 and total_ingresos == 0:
        recomendaciones.append("Todavía no hay suficiente información aprobada para un análisis fuerte. Aprueba algunos registros y vuelve a generar el reporte.")

    lineas.append("")
    lineas.append("ALERTAS")
    if alertas:
        for a in alertas:
            lineas.append(f"- {a}")
    else:
        lineas.append("- No se detectaron alertas fuertes con los datos actuales.")

    lineas.append("")
    lineas.append("RECOMENDACIONES")
    for r in recomendaciones:
        lineas.append(f"- {r}")

    lineas.append("")
    lineas.append("MENSAJE CORTO PARA SOCIOS")
    lineas.append(f"Resumen DEROSASOL: ingresos aprobados ${total_ingresos:,.2f}, gastos aprobados ${total_gastos:,.2f}, balance ${balance:,.2f}. Pendientes: {pendientes_g} gastos (${total_pend_g:,.2f}) y {pendientes_i} ingresos (${total_pend_i:,.2f}) por revisión.")

    return "\n".join(lineas)


def obtener_metricas_ia(gastos, ingresos):
    gastos = gastos.copy() if gastos is not None else pd.DataFrame()
    ingresos = ingresos.copy() if ingresos is not None else pd.DataFrame()
    if not gastos.empty and "monto" in gastos.columns:
        gastos["monto"] = pd.to_numeric(gastos["monto"], errors="coerce").fillna(0)
    if not ingresos.empty and "monto" in ingresos.columns:
        ingresos["monto"] = pd.to_numeric(ingresos["monto"], errors="coerce").fillna(0)
    gastos_ap = gastos[gastos["estado"] == "Aprobado"].copy() if not gastos.empty and "estado" in gastos.columns else gastos.copy()
    ingresos_ap = ingresos[ingresos["estado"] == "Aprobado"].copy() if not ingresos.empty and "estado" in ingresos.columns else ingresos.copy()
    gastos_pend = gastos[gastos["estado"] == "Pendiente"].copy() if not gastos.empty and "estado" in gastos.columns else pd.DataFrame()
    ingresos_pend = ingresos[ingresos["estado"] == "Pendiente"].copy() if not ingresos.empty and "estado" in ingresos.columns else pd.DataFrame()

    total_gastos = float(gastos_ap["monto"].sum()) if not gastos_ap.empty else 0
    total_ingresos = float(ingresos_ap["monto"].sum()) if not ingresos_ap.empty else 0
    balance = total_ingresos - total_gastos
    total_pend_g = float(gastos_pend["monto"].sum()) if not gastos_pend.empty else 0
    total_pend_i = float(ingresos_pend["monto"].sum()) if not ingresos_pend.empty else 0

    socio_top = "Sin datos"
    socio_top_monto = 0
    socio_menor = "Sin datos"
    socio_menor_monto = 0
    categoria_top = "Sin datos"
    categoria_top_monto = 0
    gasto_top_desc = "Sin datos"
    gasto_top_monto = 0

    if not gastos_ap.empty:
        if "socio" in gastos_ap.columns:
            socio_sum = gastos_ap.groupby("socio")["monto"].sum().sort_values(ascending=False)
            if not socio_sum.empty:
                socio_top = str(socio_sum.index[0]); socio_top_monto = float(socio_sum.iloc[0])
                socio_menor = str(socio_sum.index[-1]); socio_menor_monto = float(socio_sum.iloc[-1])
        if "categoria" in gastos_ap.columns:
            cat_sum = gastos_ap.groupby("categoria")["monto"].sum().sort_values(ascending=False)
            if not cat_sum.empty:
                categoria_top = str(cat_sum.index[0]); categoria_top_monto = float(cat_sum.iloc[0])
        top_row = gastos_ap.sort_values("monto", ascending=False).head(1)
        if not top_row.empty:
            r = top_row.iloc[0]
            gasto_top_desc = f"#{r.get('id','')} | {r.get('categoria','')} | {r.get('descripcion','')}"
            gasto_top_monto = float(r.get("monto", 0))

    return {
        "total_gastos": total_gastos,
        "total_ingresos": total_ingresos,
        "balance": balance,
        "pend_g_count": len(gastos_pend),
        "pend_i_count": len(ingresos_pend),
        "total_pend_g": total_pend_g,
        "total_pend_i": total_pend_i,
        "socio_top": socio_top,
        "socio_top_monto": socio_top_monto,
        "socio_menor": socio_menor,
        "socio_menor_monto": socio_menor_monto,
        "categoria_top": categoria_top,
        "categoria_top_monto": categoria_top_monto,
        "gasto_top_desc": gasto_top_desc,
        "gasto_top_monto": gasto_top_monto,
    }

st.set_page_config(page_title="DEROSASOL LLC Finanzas Internas", layout="wide")
inicializar_db()

if "logueado" not in st.session_state:
    st.session_state.logueado = False
    st.session_state.usuario = None
    st.session_state.rol = None
    st.session_state.socio_nombre = None

if not st.session_state.logueado:
    st.title("DEROSASOL LLC Finanzas Internas")
    st.subheader("Inicio de sesión")

    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        resultado = login(usuario, password)
        if resultado:
            st.session_state.logueado = True
            st.session_state.usuario = resultado[0]
            st.session_state.rol = resultado[1]
            st.session_state.socio_nombre = resultado[2]
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

    st.info("Usuarios temporales: alfredo/admin123, yeury/yeury123, keny/keny123, cesar/cesar123")
    st.stop()

usuario_actual = st.session_state.usuario
rol_actual = st.session_state.rol
socio_actual = st.session_state.socio_nombre

st.sidebar.success(f"{socio_actual} | {rol_actual}")

if st.sidebar.button("Cerrar sesión"):
    st.session_state.logueado = False
    st.session_state.usuario = None
    st.session_state.rol = None
    st.session_state.socio_nombre = None
    st.rerun()

st.title("DEROSASOL LLC Finanzas Internas")
st.caption("Control interno de inversión, gastos, ingresos y validación gerencial.")

if rol_actual == "Gerente":
    opciones_menu = [
        "Dashboard",
        "Registrar gasto",
        "Registrar ingreso",
        "Revisión gerencial",
        "Socios",
        "Reportes",
        "Usuarios",
        "Backups",
        "IA Financiera",
    ]
else:
    opciones_menu = [
        "Dashboard",
        "Registrar gasto",
        "Registrar ingreso",
        "Mis registros",
    ]

menu = st.sidebar.radio("Menú", opciones_menu)

socios = [s[0] for s in SOCIOS]

if menu == "Dashboard":
    gastos, ingresos, total_gastos, total_ingresos, balance = resumen_dashboard(rol=rol_actual, socio_nombre=socio_actual)

    col1, col2, col3 = st.columns(3)
    col1.metric("Gastos aprobados", f"${total_gastos:,.2f}")
    col2.metric("Ingresos aprobados", f"${total_ingresos:,.2f}")
    col3.metric("Balance aprobado", f"${balance:,.2f}")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Gastos por socio" if rol_actual == "Gerente" else "Tus gastos")
        if not gastos.empty:
            df = gastos[gastos["estado"] == "Aprobado"]
            if not df.empty:
                if rol_actual == "Gerente":
                    st.dataframe(df.groupby(["socio", "moneda"])["monto"].sum().reset_index(), use_container_width=True)
                else:
                    st.dataframe(df[["fecha", "categoria", "descripcion", "monto", "moneda", "estado", "notas"]], use_container_width=True)
            else:
                st.info("Todavía no hay gastos aprobados.")
        else:
            st.info("Todavía no hay gastos registrados.")

    with col_b:
        st.subheader("Pendientes de revisión")
        pendientes_g = len(gastos[gastos["estado"] == "Pendiente"]) if not gastos.empty else 0
        pendientes_i = len(ingresos[ingresos["estado"] == "Pendiente"]) if not ingresos.empty else 0
        st.metric("Gastos pendientes", pendientes_g)
        st.metric("Ingresos pendientes", pendientes_i)

elif menu == "Registrar gasto":
    st.header("Registrar gasto interno")

    with st.form("form_gasto"):
        col1, col2 = st.columns(2)
        fecha = col1.date_input("Fecha", value=date.today())

        if rol_actual == "Gerente":
            socio = col2.selectbox("Socio que pagó", socios)
        else:
            socio = socio_actual
            col2.text_input("Socio que pagó", value=socio_actual, disabled=True)

        col3, col4 = st.columns(2)
        categoria = col3.selectbox("Categoría", CATEGORIAS_GASTOS)
        moneda = col4.selectbox("Moneda", ["USD", "DOP"])

        descripcion = st.text_input("Descripción del gasto")
        monto = st.number_input("Monto", min_value=0.0, step=1.0, format="%.2f")
        metodo_pago = st.text_input("Método de pago", placeholder="Ej: tarjeta, efectivo, PayPal, transferencia")
        notas = st.text_area("Notas", placeholder="Detalles adicionales: por qué se hizo el gasto, para qué oficina, qué cubre, etc.")
        factura = st.file_uploader("Subir factura / recibo / comprobante", type=["pdf", "png", "jpg", "jpeg"])

        enviado = st.form_submit_button("Guardar gasto")

    if enviado:
        if not descripcion or monto <= 0:
            st.error("Debes agregar una descripción y un monto mayor que cero.")
        else:
            ruta = guardar_archivo(factura, "Gastos", socio, str(fecha))
            conn = conectar()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO gastos
                (fecha, socio, categoria, descripcion, monto, moneda, metodo_pago, notas, factura_path, estado, creado_por, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)
            """, (str(fecha), socio, categoria, descripcion, monto, moneda, metodo_pago, notas, ruta, usuario_actual, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.success("Gasto guardado como Pendiente de revisión.")

elif menu == "Registrar ingreso":
    st.header("Registrar ingreso / ganancia")

    with st.form("form_ingreso"):
        col1, col2 = st.columns(2)
        fecha = col1.date_input("Fecha", value=date.today())

        if rol_actual == "Gerente":
            socio_registro = col2.selectbox("Socio que registra", socios)
        else:
            socio_registro = socio_actual
            col2.text_input("Socio que registra", value=socio_actual, disabled=True)

        col3, col4 = st.columns(2)
        categoria = col3.selectbox("Categoría", CATEGORIAS_INGRESOS)
        moneda = col4.selectbox("Moneda", ["USD", "DOP"])

        descripcion = st.text_input("Descripción del ingreso")
        monto = st.number_input("Monto", min_value=0.0, step=1.0, format="%.2f")
        fuente = st.text_input("Fuente", placeholder="Ej: PayPal, transferencia, efectivo, cliente")
        notas = st.text_area("Notas", placeholder="Detalles adicionales del ingreso.")
        comprobante = st.file_uploader("Subir comprobante", type=["pdf", "png", "jpg", "jpeg"])

        enviado = st.form_submit_button("Guardar ingreso")

    if enviado:
        if not descripcion or monto <= 0:
            st.error("Debes agregar una descripción y un monto mayor que cero.")
        else:
            ruta = guardar_archivo(comprobante, "Ingresos", socio_registro, str(fecha))
            conn = conectar()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ingresos
                (fecha, socio_registro, categoria, descripcion, monto, moneda, fuente, notas, comprobante_path, estado, creado_por, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)
            """, (str(fecha), socio_registro, categoria, descripcion, monto, moneda, fuente, notas, ruta, usuario_actual, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.success("Ingreso guardado como Pendiente de revisión.")

elif menu == "Revisión gerencial" and rol_actual == "Gerente":
    st.header("Revisión gerencial")
    st.caption("Aquí Alfredo puede aprobar, rechazar o dejar pendiente lo registrado por cada socio.")

    pestaña_gastos, pestaña_ingresos = st.tabs(["Gastos pendientes", "Ingresos pendientes"])

    with pestaña_gastos:
        gastos = cargar_df("gastos")
        pendientes = gastos[gastos["estado"] == "Pendiente"] if not gastos.empty else gastos
        if pendientes.empty:
            st.info("No hay gastos pendientes.")
        else:
            for _, row in pendientes.iterrows():
                with st.expander(f"#{row['id']} | {row['fecha']} | {row['socio']} | {row['descripcion']} | {row['moneda']} {row['monto']:,.2f}"):
                    st.write("Categoría:", row["categoria"])
                    st.write("Método de pago:", row["metodo_pago"])
                    st.write("Notas:", row["notas"] if row["notas"] else "Sin notas")
                    st.write("Factura:", row["factura_path"] if row["factura_path"] else "Sin archivo")
                    st.write("Creado por:", row["creado_por"] if "creado_por" in row else "")
                    c1, c2, c3 = st.columns(3)
                    if c1.button("Aprobar", key=f"ag{row['id']}"):
                        actualizar_estado("gastos", int(row["id"]), "Aprobado")
                        st.rerun()
                    if c2.button("Rechazar", key=f"rg{row['id']}"):
                        actualizar_estado("gastos", int(row["id"]), "Rechazado")
                        st.rerun()
                    if c3.button("Mantener pendiente", key=f"pg{row['id']}"):
                        actualizar_estado("gastos", int(row["id"]), "Pendiente")
                        st.rerun()

    with pestaña_ingresos:
        ingresos = cargar_df("ingresos")
        pendientes = ingresos[ingresos["estado"] == "Pendiente"] if not ingresos.empty else ingresos
        if pendientes.empty:
            st.info("No hay ingresos pendientes.")
        else:
            for _, row in pendientes.iterrows():
                with st.expander(f"#{row['id']} | {row['fecha']} | {row['socio_registro']} | {row['descripcion']} | {row['moneda']} {row['monto']:,.2f}"):
                    st.write("Categoría:", row["categoria"])
                    st.write("Fuente:", row["fuente"])
                    st.write("Notas:", row["notas"] if row["notas"] else "Sin notas")
                    st.write("Comprobante:", row["comprobante_path"] if row["comprobante_path"] else "Sin archivo")
                    st.write("Creado por:", row["creado_por"] if "creado_por" in row else "")
                    c1, c2, c3 = st.columns(3)
                    if c1.button("Aprobar", key=f"ai{row['id']}"):
                        actualizar_estado("ingresos", int(row["id"]), "Aprobado")
                        st.rerun()
                    if c2.button("Rechazar", key=f"ri{row['id']}"):
                        actualizar_estado("ingresos", int(row["id"]), "Rechazado")
                        st.rerun()
                    if c3.button("Mantener pendiente", key=f"pi{row['id']}"):
                        actualizar_estado("ingresos", int(row["id"]), "Pendiente")
                        st.rerun()

elif menu == "Socios" and rol_actual == "Gerente":
    st.header("Socios")
    df = cargar_df("socios")
    st.dataframe(df, use_container_width=True)

    gastos = cargar_df("gastos")
    if not gastos.empty:
        aprobados = gastos[gastos["estado"] == "Aprobado"]
        if not aprobados.empty:
            st.subheader("Inversión aprobada por socio")
            resumen = aprobados.groupby(["socio", "moneda"])["monto"].sum().reset_index()
            st.dataframe(resumen, use_container_width=True)
        else:
            st.info("Todavía no hay gastos aprobados.")

elif menu == "Reportes" and rol_actual == "Gerente":
    st.header("Reportes")
    gastos = cargar_df("gastos")
    ingresos = cargar_df("ingresos")

    st.subheader("Gastos")
    st.dataframe(gastos, use_container_width=True)

    st.subheader("Ingresos")
    st.dataframe(ingresos, use_container_width=True)

    col1, col2 = st.columns(2)
    if col1.button("Exportar gastos a CSV"):
        ruta = APP_DIR / "gastos_exportados.csv"
        gastos.to_csv(ruta, index=False)
        st.success(f"Exportado: {ruta}")

    if col2.button("Exportar ingresos a CSV"):
        ruta = APP_DIR / "ingresos_exportados.csv"
        ingresos.to_csv(ruta, index=False)
        st.success(f"Exportado: {ruta}")


elif menu == "IA Financiera" and rol_actual == "Gerente":
    st.header("IA Financiera Local V2")
    st.caption("Análisis automático sin internet, sin Gemini y sin costo. Solo usa los datos guardados en esta aplicación.")

    gastos = cargar_df("gastos")
    ingresos = cargar_df("ingresos")
    metricas = obtener_metricas_ia(gastos, ingresos)

    col1, col2, col3 = st.columns(3)
    col1.metric("Gastos aprobados", f"${metricas['total_gastos']:,.2f}")
    col2.metric("Ingresos aprobados", f"${metricas['total_ingresos']:,.2f}")
    col3.metric("Balance", f"${metricas['balance']:,.2f}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Gastos pendientes", f"{metricas['pend_g_count']} | ${metricas['total_pend_g']:,.2f}")
    col5.metric("Ingresos pendientes", f"{metricas['pend_i_count']} | ${metricas['total_pend_i']:,.2f}")
    col6.metric("Mayor gasto", f"${metricas['gasto_top_monto']:,.2f}")

    st.divider()

    st.subheader("Lectura rápida de la IA")
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"Socio que más ha invertido/aportado en gastos aprobados: **{metricas['socio_top']}** | ${metricas['socio_top_monto']:,.2f}")
        st.info(f"Categoría más costosa: **{metricas['categoria_top']}** | ${metricas['categoria_top_monto']:,.2f}")
    with c2:
        st.warning(f"Socio con menor gasto aprobado registrado: **{metricas['socio_menor']}** | ${metricas['socio_menor_monto']:,.2f}")
        st.warning(f"Gasto individual más alto: **{metricas['gasto_top_desc']}** | ${metricas['gasto_top_monto']:,.2f}")

    reporte_ia = analizar_finanzas_local(gastos, ingresos)
    st.subheader("Reporte inteligente para Alfredo")
    st.text_area("Reporte generado", value=reporte_ia, height=560)

    st.download_button(
        "Descargar reporte IA V2 en TXT",
        data=reporte_ia,
        file_name=f"reporte_ia_derosasol_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain"
    )

    st.subheader("Tablas rápidas")
    tab1, tab2, tab3, tab4 = st.tabs(["Gastos por socio", "Gastos por categoría", "Pendientes", "Gasto más alto"])

    with tab1:
        if not gastos.empty:
            aprobados = gastos[gastos["estado"] == "Aprobado"]
            if not aprobados.empty:
                st.dataframe(aprobados.groupby(["socio", "moneda"])["monto"].sum().reset_index().sort_values("monto", ascending=False), use_container_width=True)
            else:
                st.info("No hay gastos aprobados.")
        else:
            st.info("No hay gastos registrados.")

    with tab2:
        if not gastos.empty:
            aprobados = gastos[gastos["estado"] == "Aprobado"]
            if not aprobados.empty:
                st.dataframe(aprobados.groupby(["categoria", "moneda"])["monto"].sum().reset_index().sort_values("monto", ascending=False), use_container_width=True)
            else:
                st.info("No hay gastos aprobados.")
        else:
            st.info("No hay gastos registrados.")

    with tab3:
        pendientes_g = gastos[gastos["estado"] == "Pendiente"] if not gastos.empty else gastos
        pendientes_i = ingresos[ingresos["estado"] == "Pendiente"] if not ingresos.empty else ingresos
        st.write("Gastos pendientes")
        st.dataframe(pendientes_g, use_container_width=True)
        st.write("Ingresos pendientes")
        st.dataframe(pendientes_i, use_container_width=True)

    with tab4:
        if not gastos.empty:
            aprobados = gastos[gastos["estado"] == "Aprobado"]
            if not aprobados.empty:
                st.dataframe(aprobados.sort_values("monto", ascending=False).head(10), use_container_width=True)
            else:
                st.info("No hay gastos aprobados.")
        else:
            st.info("No hay gastos registrados.")

elif menu == "Usuarios" and rol_actual == "Gerente":
    st.header("Usuarios")
    usuarios = cargar_df("usuarios")
    st.dataframe(usuarios, use_container_width=True)

    st.subheader("Cambiar contraseña")
    with st.form("cambiar_password"):
        usuario_sel = st.selectbox("Usuario", usuarios["usuario"].tolist())
        nueva = st.text_input("Nueva contraseña", type="password")
        confirmar = st.text_input("Confirmar contraseña", type="password")
        guardar = st.form_submit_button("Guardar nueva contraseña")

    if guardar:
        if len(nueva) < 6:
            st.error("La contraseña debe tener al menos 6 caracteres.")
        elif nueva != confirmar:
            st.error("Las contraseñas no coinciden.")
        else:
            cambiar_password(usuario_sel, nueva)
            st.success(f"Contraseña actualizada para {usuario_sel}.")

elif menu == "Backups" and rol_actual == "Gerente":
    st.header("Backups")
    st.write("Crea una copia de seguridad de la base de datos local.")
    if st.button("Crear backup ahora"):
        destino = crear_backup()
        st.success(f"Backup creado: {destino}")
    st.divider()
    st.subheader("Sincronización con Supabase")

    if st.button("Sincronizar socios con Supabase"):
        try:
            for nombre, participacion in SOCIOS:
                supabase.table("socios").insert({
                    "nombre_completo": nombre,
                    "porcentaje_participacion": participacion,
                    "activo": True,
                    "notas": "Socio inicial DEROSASOL LLC"
                }).execute()

            st.success("Socios sincronizados correctamente con Supabase.")

        except Exception as e:
            st.error(f"Error sincronizando socios: {e}")
    
if st.button("Sincronizar usuarios con Supabase"):
    try:
        for usuario, password, rol, socio_nombre in USUARIOS_INICIALES:
            supabase.table("usuarios").insert({
                "usuario": usuario,
                "password_hash": hashlib.sha256(password.encode()).hexdigest(),
                "rol": rol,
                "socio_nombre": socio_nombre,
                "activo": True
            }).execute()

        st.success("Usuarios sincronizados correctamente con Supabase.")

    except Exception as e:
        st.error(f"Error sincronizando usuarios: {e}")
if st.button("Sincronizar gastos con Supabase"):
    try:
        gastos_df = cargar_df("gastos")

        if gastos_df.empty:
            st.warning("No hay gastos para sincronizar.")
        else:
            for _, row in gastos_df.iterrows():
                supabase.table("gastos").insert({
                    "socio_nombre": row["socio"],
                    "categoria": row["categoria"],
                    "descripcion": row["descripcion"],
                    "monto": float(row["monto"]),
                    "fecha_gasto": row["fecha"],
                    "estado": row["estado"],
                    "factura_pdf": row["factura_path"],
                    "notas": row["notas"],
                    "aprobado_por": "",
                    "fecha_aprobacion": None
                }).execute()

            st.success("Gastos sincronizados correctamente con Supabase.")

    except Exception as e:
        st.error(f"Error sincronizando gastos: {e}")
if st.button("Sincronizar ingresos con Supabase"):
    try:
        ingresos_df = cargar_df("ingresos")

        if ingresos_df.empty:
            st.warning("No hay ingresos para sincronizar.")
        else:
            for _, row in ingresos_df.iterrows():
                supabase.table("ingresos").insert({
                    "socio_nombre": row["socio_registro"],
                    "fuente": row["fuente"],
                    "descripcion": row["descripcion"],
                    "monto": float(row["monto"]),
                    "fecha_ingreso": row["fecha"],
                    "estado": row["estado"],
                    "notas": row["notas"],
                    "aprobado_por": "",
                    "fecha_aprobacion": None
                }).execute()

            st.success("Ingresos sincronizados correctamente con Supabase.")

    except Exception as e:
        st.error(f"Error sincronizando ingresos: {e}") 
if st.button("Sincronizar aprobaciones con Supabase"):
    try:
        aprobaciones_df = cargar_df("aprobaciones")

        if aprobaciones_df.empty:
            st.warning("No hay aprobaciones para sincronizar.")
        else:
            for _, row in aprobaciones_df.iterrows():
                supabase.table("aprobaciones").insert({
                    "tipo_movimiento": row["tipo_movimiento"],
                    "movimiento_id": int(row["movimiento_id"]),
                    "accion": row["accion"],
                    "usuario_aprobador": row["usuario_aprobador"],
                    "comentario": row["comentario"],
                    "fecha_accion": row["fecha_accion"]
                }).execute()

            st.success("Aprobaciones sincronizadas correctamente con Supabase.")

    except Exception as e:
        st.error(f"Error sincronizando aprobaciones: {e}")                       
    if menu == "Mis registros":
     st.header("Mis registros")
    gastos = cargar_df("gastos", rol=rol_actual, socio_nombre=socio_actual)
    ingresos = cargar_df("ingresos", rol=rol_actual, socio_nombre=socio_actual)

    st.subheader("Mis gastos")
    st.dataframe(gastos, use_container_width=True)

    st.subheader("Mis ingresos")
    st.dataframe(ingresos, use_container_width=True)
