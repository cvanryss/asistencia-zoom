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

def leer_csv_zoom(archivo):
    try:
        return pd.read_csv(archivo, encoding="utf-8-sig")
    except UnicodeDecodeError:
        archivo.seek(0)
        return pd.read_csv(archivo, encoding="latin1")

def procesar_asistencia(df, minutos_minimos):
    columnas_requeridas = ["Nombre de usuario", "Duración (minutos)"]

    for columna in columnas_requeridas:
        if columna not in df.columns:
            st.error(f"El archivo no tiene la columna requerida: {columna}")
            st.stop()

    if "E-mail de usuario" not in df.columns:
        df["E-mail de usuario"] = ""

    df["Duración (minutos)"] = pd.to_numeric(
        df["Duración (minutos)"],
        errors="coerce"
    ).fillna(0)

    resultado = (
        df.groupby(["Nombre de usuario", "E-mail de usuario"], dropna=False, as_index=False)
          .agg({"Duración (minutos)": "sum"})
    )

    resultado["Estado"] = resultado["Duración (minutos)"].apply(
        lambda x: "Presente" if x >= minutos_minimos else "Ausente"
    )

    resultado = resultado.rename(
        columns={
            "Nombre de usuario": "Nombre",
            "E-mail de usuario": "Email",
            "Duración (minutos)": "Tiempo total de conexión (minutos)"
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

    with st.expander("Vista previa del archivo original"):
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