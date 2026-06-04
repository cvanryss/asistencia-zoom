
from io import BytesIO
from datetime import datetime, time

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Asistencia Zoom", page_icon="✅", layout="wide")

st.title("✅ Procesador de asistencia Zoom")
st.write(
    "Sube un reporte CSV de Zoom. La app calcula la asistencia real usando hora de entrada "
    "y hora de salida, descontando los tiempos fuera de Zoom y el tiempo anterior al inicio oficial de clase."
)

st.sidebar.header("Configuración de la clase")

hora_inicio_clase = st.sidebar.time_input(
    "Hora oficial de inicio de clase",
    value=time(19, 0)
)

usar_hora_termino = st.sidebar.checkbox(
    "Definir hora oficial de término de clase",
    value=False
)

hora_termino_clase = None
if usar_hora_termino:
    hora_termino_clase = st.sidebar.time_input(
        "Hora oficial de término de clase",
        value=time(21, 30)
    )

minutos_minimos = st.sidebar.number_input(
    "Minutos mínimos para quedar Presente",
    min_value=1,
    value=75,
    step=5
)

criterio_apellido = st.sidebar.selectbox(
    "Criterio para ordenar por apellido",
    [
        "Primer apellido: penúltima palabra",
        "Segundo elemento del nombre",
        "Ordenar por nombre completo"
    ],
    index=0
)

archivo = st.file_uploader("Sube el archivo CSV exportado desde Zoom", type=["csv"])


def detectar_inicio_participantes(archivo):
    archivo.seek(0)
    contenido = archivo.read().decode("utf-8-sig", errors="replace")
    lineas = contenido.splitlines()

    for i, linea in enumerate(lineas):
        linea_lower = linea.lower()
        tiene_nombre = (
            "nombre de usuario" in linea_lower
            or "nombre (nombre original)" in linea_lower
            or linea_lower.startswith("nombre,")
        )
        tiene_entrada = "hora de entrada" in linea_lower
        tiene_salida = "hora de salida" in linea_lower

        if tiene_nombre and tiene_entrada and tiene_salida:
            return i

    return 0


def leer_csv_zoom(archivo):
    fila_inicio = detectar_inicio_participantes(archivo)
    archivo.seek(0)

    try:
        return pd.read_csv(archivo, encoding="utf-8-sig", skiprows=fila_inicio)
    except UnicodeDecodeError:
        archivo.seek(0)
        return pd.read_csv(archivo, encoding="latin1", skiprows=fila_inicio)


def encontrar_columna(df, opciones):
    columnas_limpias = {str(c).strip(): c for c in df.columns}

    for opcion in opciones:
        if opcion in columnas_limpias:
            return columnas_limpias[opcion]

    for columna_original in df.columns:
        columna = str(columna_original).strip().lower()
        for opcion in opciones:
            if opcion.lower() in columna:
                return columna_original

    return None


def parsear_fechas(serie):
    fechas = pd.to_datetime(serie, errors="coerce", dayfirst=True)

    if fechas.isna().mean() > 0.5:
        fechas = pd.to_datetime(serie, errors="coerce", dayfirst=False)

    return fechas


def detectar_fecha_clase(df, columna_entrada):
    entradas = parsear_fechas(df[columna_entrada]).dropna()

    if entradas.empty:
        return None

    fechas = entradas.dt.date
    return fechas.mode().iloc[0]


def obtener_apellido_para_ordenar(nombre, criterio):
    if pd.isna(nombre):
        return ""

    texto = " ".join(str(nombre).strip().split())

    if not texto:
        return ""

    if "," in texto:
        return texto.split(",")[0].strip().upper()

    partes = texto.split()

    if criterio == "Ordenar por nombre completo":
        return texto.upper()

    if criterio == "Segundo elemento del nombre":
        if len(partes) >= 2:
            return partes[1].upper()
        return partes[0].upper()

    if len(partes) >= 2:
        return partes[-2].upper()

    return partes[0].upper()


def unir_intervalos(intervalos):
    if not intervalos:
        return []

    intervalos = sorted(intervalos, key=lambda x: x[0])
    unidos = [intervalos[0]]

    for inicio, fin in intervalos[1:]:
        ultimo_inicio, ultimo_fin = unidos[-1]

        if inicio <= ultimo_fin:
            unidos[-1] = (ultimo_inicio, max(ultimo_fin, fin))
        else:
            unidos.append((inicio, fin))

    return unidos


def minutos_intervalos(intervalos):
    total = 0
    for inicio, fin in intervalos:
        total += max(0, (fin - inicio).total_seconds() / 60)
    return int(round(total))


def procesar_asistencia(
    df,
    minutos_minimos,
    hora_inicio_clase,
    hora_termino_clase,
    criterio_apellido
):
    columna_nombre = encontrar_columna(df, ["Nombre de usuario", "Nombre (nombre original)", "Nombre"])
    columna_email = encontrar_columna(df, ["E-mail de usuario", "Correo electrónico", "Email", "Correo"])
    columna_entrada = encontrar_columna(df, ["Hora de entrada", "Entrada"])
    columna_salida = encontrar_columna(df, ["Hora de salida", "Salida"])

    if columna_nombre is None:
        st.error("No encontré la columna de nombre del participante.")
        st.write("Columnas detectadas:", list(df.columns))
        st.stop()

    if columna_entrada is None or columna_salida is None:
        st.error("No encontré las columnas de hora de entrada y/o hora de salida.")
        st.write("Columnas detectadas:", list(df.columns))
        st.stop()

    if columna_email is None:
        df["Email interno"] = ""
        columna_email = "Email interno"

    df = df.copy()
    df["Entrada_dt"] = parsear_fechas(df[columna_entrada])
    df["Salida_dt"] = parsear_fechas(df[columna_salida])

    fecha_clase = detectar_fecha_clase(df, columna_entrada)

    if fecha_clase is None:
        st.error("No pude detectar la fecha de clase desde el archivo.")
        st.stop()

    df = df.dropna(subset=["Entrada_dt", "Salida_dt"])
    df = df[df["Salida_dt"] > df["Entrada_dt"]]

    registros = []

    for _, row in df.iterrows():
        fecha_base = row["Entrada_dt"].date()
        inicio_clase_dt = datetime.combine(fecha_base, hora_inicio_clase)

        if hora_termino_clase is not None:
            termino_clase_dt = datetime.combine(fecha_base, hora_termino_clase)
            if termino_clase_dt <= inicio_clase_dt:
                termino_clase_dt = termino_clase_dt + pd.Timedelta(days=1)
        else:
            termino_clase_dt = None

        inicio_real = max(row["Entrada_dt"], inicio_clase_dt)
        fin_real = row["Salida_dt"]

        if termino_clase_dt is not None:
            fin_real = min(fin_real, termino_clase_dt)

        if fin_real > inicio_real:
            registros.append({
                "Nombre": row[columna_nombre],
                "Email interno": row[columna_email],
                "Inicio considerado": inicio_real,
                "Fin considerado": fin_real
            })

    if len(registros) == 0:
        st.warning("No se encontraron conexiones válidas para calcular asistencia.")
        st.stop()

    conexiones = pd.DataFrame(registros)
    filas_resultado = []

    for (nombre, email), grupo in conexiones.groupby(["Nombre", "Email interno"], dropna=False):
        intervalos = list(zip(grupo["Inicio considerado"], grupo["Fin considerado"]))
        intervalos_unidos = unir_intervalos(intervalos)
        minutos = minutos_intervalos(intervalos_unidos)
        apellido = obtener_apellido_para_ordenar(nombre, criterio_apellido)

        filas_resultado.append({
            "Nombre": nombre,
            "Apellido": apellido,
            "Tiempo real de conexión (minutos)": minutos,
            "Estado": "Presente" if minutos >= minutos_minimos else "Ausente",
            "Fecha Clase": fecha_clase.strftime("%d-%m-%Y")
        })

    resultado = pd.DataFrame(filas_resultado)

    if criterio_apellido == "Ordenar por nombre completo":
        resultado = resultado.sort_values(["Nombre"], ascending=[True])
    else:
        resultado = resultado.sort_values(["Apellido", "Nombre"], ascending=[True, True])

    resultado = resultado[
        [
            "Nombre",
            "Apellido",
            "Tiempo real de conexión (minutos)",
            "Estado",
            "Fecha Clase"
        ]
    ]

    conexiones = conexiones.drop(columns=["Email interno"], errors="ignore")

    return resultado, conexiones, fecha_clase


def convertir_a_excel(resultado, fecha_clase):
    output = BytesIO()

    resumen = pd.DataFrame({
        "Campo": ["Fecha clase", "Total usuarios", "Presentes", "Ausentes"],
        "Valor": [
            fecha_clase.strftime("%d-%m-%Y"),
            len(resultado),
            int((resultado["Estado"] == "Presente").sum()),
            int((resultado["Estado"] == "Ausente").sum())
        ]
    })

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumen.to_excel(writer, index=False, sheet_name="Resumen general")
        resultado.to_excel(writer, index=False, sheet_name="Resumen asistencia")

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter
                for cell in column_cells:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except Exception:
                        pass
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 45)

    return output.getvalue()


if archivo is not None:
    df = leer_csv_zoom(archivo)

    with st.expander("Vista previa del archivo leído"):
        st.dataframe(df.head(30), use_container_width=True)

    resultado, conexiones, fecha_clase = procesar_asistencia(
        df=df,
        minutos_minimos=minutos_minimos,
        hora_inicio_clase=hora_inicio_clase,
        hora_termino_clase=hora_termino_clase,
        criterio_apellido=criterio_apellido
    )

    st.info(
        f"Fecha detectada: {fecha_clase.strftime('%d-%m-%Y')} | "
        f"Inicio oficial: {hora_inicio_clase.strftime('%H:%M')}"
    )

    total_personas = len(resultado)
    presentes = (resultado["Estado"] == "Presente").sum()
    ausentes = (resultado["Estado"] == "Ausente").sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total usuarios", total_personas)
    col2.metric("Presentes", presentes)
    col3.metric("Ausentes", ausentes)

    st.subheader("Resultado de asistencia")
    st.caption(
        "Criterio usado: se descuenta el tiempo anterior al inicio oficial de clase, "
        "se descuentan los tiempos fuera de Zoom y se unen tramos superpuestos. "
        "La fecha de clase se detecta automáticamente desde el archivo."
    )
    st.dataframe(resultado, use_container_width=True)

    excel = convertir_a_excel(resultado, fecha_clase)
    csv = resultado.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    fecha_archivo = fecha_clase.strftime("%Y-%m-%d")

    col_descarga_1, col_descarga_2 = st.columns(2)

    with col_descarga_1:
        st.download_button(
            label="⬇️ Descargar Excel",
            data=excel,
            file_name=f"asistencia_{fecha_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with col_descarga_2:
        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv,
            file_name=f"asistencia_{fecha_archivo}.csv",
            mime="text/csv"
        )

else:
    st.info("Sube un archivo CSV de Zoom para comenzar.")
