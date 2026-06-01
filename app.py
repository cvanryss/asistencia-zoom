import pandas as pd
import streamlit as st
from io import BytesIO

st.set_page_config(
    page_title="Asistencia Zoom",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Procesador de asistencia Zoom")
st.write(
    "Sube un reporte CSV de Zoom y la app calculará el tiempo total de conexión "
    "por usuario, marcando Presente o Ausente según el mínimo definido."
)

st.sidebar.header("Configuración")

minutos_minimos = st.sidebar.number_input(
    "Minutos mínimos para quedar Presente",
    min_value=1,
    value=75,
    step=5
)

archivo = st.file_uploader(
    "Sube el archivo CSV exportado desde Zoom",
    type=["csv"]
)

def detectar_inicio_participantes(archivo):
    # Detecta la fila donde empieza la tabla real de participantes.
    # Algunos reportes de Zoom traen primero una tabla resumen de la sesión.
    archivo.seek(0)
    lineas = archivo.read().decode("utf-8-sig", errors="replace").splitlines()

    posibles_encabezados = [
        "Nombre de usuario",
        "Nombre (nombre original)",
        "Nombre",
    ]

    for i, linea in enumerate(lineas):
        if any(encabezado in linea for encabezado in posibles_encabezados) and "Duración (minutos)" in linea:
            return i

    return 0

def leer_csv_zoom(archivo):
    # Lee CSV de Zoom aunque tenga una tabla resumen antes del listado de participantes.
    fila_inicio = detectar_inicio_participantes(archivo)

    archivo.seek(0)
    try:
        return pd.read_csv(archivo, encoding="utf-8-sig", skiprows=fila_inicio)
    except UnicodeDecodeError:
        archivo.seek(0)
        return pd.read_csv(archivo, encoding="latin1", skiprows=fila_inicio)

def encontrar_columna(df, opciones):
    # Busca una columna entre varios nombres posibles.
    for opcion in opciones:
        if opcion in df.columns:
            return opcion
    return None

def procesar_asistencia(df, minutos_minimos):
    # Suma la duración por usuario y marca Presente/Ausente.

    columna_nombre = encontrar_columna(
        df,
        [
            "Nombre de usuario",
            "Nombre (nombre original)",
            "Nombre"
        ]
    )

    columna_email = encontrar_columna(
        df,
        [
            "E-mail de usuario",
            "Correo electrónico",
            "Email",
            "Correo"
        ]
    )

    columna_duracion = encontrar_columna(
        df,
        [
            "Duración (minutos)",
            "Duracion (minutos)"
        ]
    )

    if columna_nombre is None:
        st.error("No encontré la columna de nombre del participante.")
        st.write("Columnas detectadas:", list(df.columns))
        st.stop()

    if columna_duracion is None:
        st.error("No encontré la columna de duración en minutos.")
        st.write("Columnas detectadas:", list(df.columns))
        st.stop()

    if columna_email is None:
        df["Email"] = ""
        columna_email = "Email"

    df[columna_duracion] = pd.to_numeric(
        df[columna_duracion],
        errors="coerce"
    ).fillna(0)

    resultado = (
        df.groupby([columna_nombre, columna_email], dropna=False, as_index=False)
          .agg({columna_duracion: "sum"})
    )

    resultado["Estado"] = resultado[columna_duracion].apply(
        lambda x: "Presente" if x >= minutos_minimos else "Ausente"
    )

    resultado = resultado.rename(
        columns={
            columna_nombre: "Nombre",
            columna_email: "Email",
            columna_duracion: "Tiempo total de conexión (minutos)"
        }
    )

    resultado = resultado.sort_values(
        ["Estado", "Nombre"],
        ascending=[False, True]
    )

    return resultado

def convertir_a_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Asistencia")
        worksheet = writer.sheets["Asistencia"]

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                try:
                    max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass

            worksheet.column_dimensions[column_letter].width = max_length + 2

    return output.getvalue()

if archivo is not None:
    df = leer_csv_zoom(archivo)

    with st.expander("Vista previa del archivo leído"):
        st.dataframe(df.head(20), use_container_width=True)

    resultado = procesar_asistencia(df, minutos_minimos)

    total_personas = len(resultado)
    presentes = (resultado["Estado"] == "Presente").sum()
    ausentes = (resultado["Estado"] == "Ausente").sum()

    col1, col2, col3 = st.columns(3)

    col1.metric("Total usuarios", total_personas)
    col2.metric("Presentes", presentes)
    col3.metric("Ausentes", ausentes)

    st.subheader("Resultado de asistencia")
    st.dataframe(resultado, use_container_width=True)

    excel = convertir_a_excel(resultado)
    csv = resultado.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    col_descarga_1, col_descarga_2 = st.columns(2)

    with col_descarga_1:
        st.download_button(
            label="⬇️ Descargar Excel",
            data=excel,
            file_name="asistencia_zoom.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with col_descarga_2:
        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv,
            file_name="asistencia_zoom.csv",
            mime="text/csv"
        )

else:
    st.info("Sube un archivo CSV de Zoom para comenzar.")