"""Aplicación Streamlit para análisis exploratorio automático de archivos tabulares."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Explorador automático de datos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

TIPOS_CATEGORICOS = {"Categórica", "Texto", "Booleana"}
PALABRAS_FECHA = ("fecha", "date")


@st.cache_data(show_spinner=False)
def leer_archivo(contenido: bytes, extension: str) -> pd.DataFrame:
    """Lee el archivo cargado desde memoria, sin usar rutas fijas ni persistirlo."""
    buffer = BytesIO(contenido)
    extension = extension.lower()
    if extension == ".csv":
        # sep=None permite detectar delimitadores frecuentes, como coma y punto y coma.
        try:
            return pd.read_csv(buffer, sep=None, engine="python")
        except UnicodeDecodeError:
            buffer.seek(0)
            return pd.read_csv(buffer, sep=None, engine="python", encoding="latin-1")
    if extension == ".xlsx":
        return pd.read_excel(buffer, engine="openpyxl")
    if extension == ".xls":
        return pd.read_excel(buffer, engine="xlrd")
    raise ValueError("Formato no admitido. Use CSV, XLSX o XLS.")


@st.cache_data(show_spinner=False)
def preparar_dataset(df_original: pd.DataFrame) -> pd.DataFrame:
    """Limpia encabezados e intenta convertir columnas de fecha identificables por nombre."""
    df = df_original.copy()
    df.columns = [str(col).strip() for col in df.columns]
    for columna in df.columns:
        nombre = columna.lower()
        if any(palabra in nombre for palabra in PALABRAS_FECHA):
            convertida = pd.to_datetime(df[columna], errors="coerce")
            originales_no_nulos = int(df[columna].notna().sum())
            conversiones = int(convertida.notna().sum())
            # Evita destruir una columna si la inferencia por nombre fue equivocada.
            if originales_no_nulos == 0 or conversiones / originales_no_nulos >= 0.6:
                df[columna] = convertida
    return df


def tipo_analitico(serie: pd.Series) -> str:
    """Interpreta el tipo analítico sin modificar los valores de la serie."""
    if pd.api.types.is_bool_dtype(serie):
        return "Booleana"
    if pd.api.types.is_datetime64_any_dtype(serie):
        return "Fecha/hora"
    if pd.api.types.is_numeric_dtype(serie):
        return "Numérica"
    if isinstance(serie.dtype, pd.CategoricalDtype):
        return "Categórica"

    no_nulos = serie.dropna()
    unicos = int(no_nulos.nunique())
    proporcion = unicos / max(len(no_nulos), 1)
    return "Categórica" if unicos <= 50 or proporcion <= 0.20 else "Texto"


def clasificar_columnas(df: pd.DataFrame) -> dict[str, list[str]]:
    grupos = {tipo: [] for tipo in ["Numérica", "Categórica", "Texto", "Booleana", "Fecha/hora"]}
    for columna in df.columns:
        grupos[tipo_analitico(df[columna])].append(columna)
    return grupos


def tabla_tipos(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Variable": df.columns,
            "Tipo Pandas": [str(df[c].dtype) for c in df.columns],
            "Tipo analítico": [tipo_analitico(df[c]) for c in df.columns],
            "Valores no nulos": [int(df[c].notna().sum()) for c in df.columns],
            "Valores únicos": [int(df[c].nunique(dropna=True)) for c in df.columns],
        }
    )


def convertir_csv(df: pd.DataFrame) -> bytes:
    """Genera CSV UTF-8 con BOM en memoria, compatible con Excel."""
    return df.to_csv(index=False).encode("utf-8-sig")


def aplicar_filtros(df: pd.DataFrame, grupos: dict[str, list[str]]) -> pd.DataFrame:
    """Construye filtros en la barra lateral y devuelve una copia filtrada."""
    filtrado = df.copy()
    st.sidebar.header("Filtros interactivos")
    st.sidebar.caption("Los valores faltantes se conservan en filtros de fecha y numéricos.")

    with st.sidebar.expander("Filtros por fecha", expanded=False):
        for columna in grupos["Fecha/hora"]:
            serie = pd.to_datetime(filtrado[columna], errors="coerce")
            validos = serie.dropna()
            if validos.empty:
                st.caption(f"{columna}: no contiene fechas válidas.")
                continue
            minimo, maximo = validos.min().date(), validos.max().date()
            inicio, fin = st.date_input(
                f"Rango de {columna}",
                value=(minimo, maximo),
                min_value=minimo,
                max_value=maximo,
                key=f"fecha_{columna}",
            )
            mascara = serie.isna() | serie.dt.date.between(inicio, fin)
            filtrado = filtrado.loc[mascara]

    columnas_cat = grupos["Categórica"] + grupos["Booleana"]
    with st.sidebar.expander("Filtros categóricos", expanded=False):
        elegidas = st.multiselect("Variables categóricas", columnas_cat, key="filtros_cat")
        for columna in elegidas:
            etiqueta = filtrado[columna].astype("string").fillna("(Faltante)")
            opciones = sorted(etiqueta.unique().tolist())
            seleccion = st.multiselect(
                f"Categorías de {columna}", opciones, default=opciones, key=f"cat_{columna}"
            )
            filtrado = filtrado.loc[etiqueta.isin(seleccion)]

    with st.sidebar.expander("Filtros numéricos", expanded=False):
        elegidas = st.multiselect("Variables numéricas", grupos["Numérica"], key="filtros_num")
        for columna in elegidas:
            serie = pd.to_numeric(filtrado[columna], errors="coerce")
            validos = serie.dropna()
            if validos.empty:
                st.caption(f"{columna}: no contiene valores numéricos válidos.")
                continue
            minimo, maximo = float(validos.min()), float(validos.max())
            if minimo == maximo:
                st.caption(f"{columna}: valor constante {minimo:g}.")
                continue
            rango = st.slider(
                f"Rango de {columna}",
                min_value=minimo,
                max_value=maximo,
                value=(minimo, maximo),
                key=f"num_{columna}",
            )
            filtrado = filtrado.loc[serie.isna() | serie.between(*rango)]

    st.sidebar.metric("Registros resultantes", len(filtrado))
    return filtrado


def detectar_atipicos(
    df: pd.DataFrame, columnas: Iterable[str], factor: float
) -> pd.DataFrame:
    """Devuelve una fila por cada detección de valor atípico mediante IQR."""
    resultados: list[pd.DataFrame] = []
    for columna in columnas:
        serie = pd.to_numeric(df[columna], errors="coerce")
        q1, q3 = serie.quantile([0.25, 0.75])
        if pd.isna(q1) or pd.isna(q3):
            continue
        iqr = q3 - q1
        inferior = q1 - factor * iqr
        superior = q3 + factor * iqr
        mascara = serie.notna() & ((serie < inferior) | (serie > superior))
        if mascara.any():
            bloque = df.loc[mascara].copy()
            bloque.insert(0, "Fila original", bloque.index)
            bloque.insert(1, "Variable con valor atípico", columna)
            bloque.insert(2, "Valor detectado", serie.loc[mascara].to_numpy())
            bloque.insert(3, "Límite inferior", inferior)
            bloque.insert(4, "Límite superior", superior)
            resultados.append(bloque)
    if not resultados:
        return pd.DataFrame()
    return pd.concat(resultados, ignore_index=True)


def mostrar_bienvenida() -> None:
    st.info("Cargue un archivo desde la barra lateral para comenzar. El análisis no usa datos ficticios.")
    c1, c2, c3 = st.columns(3)
    c1.markdown("### 1. Cargar\nSeleccione un archivo **CSV, XLSX o XLS**.")
    c2.markdown("### 2. Explorar\nAplique filtros y revise calidad, estadísticas y gráficos.")
    c3.markdown("### 3. Descargar\nExporte los datos filtrados y los valores atípicos.")
    st.markdown(
        """
        #### Análisis disponibles
        - Dimensiones, tipos de variables y vista general.
        - Duplicados, valores faltantes y estadísticas descriptivas.
        - Distribuciones, diagramas de caja y correlaciones.
        - Detección de valores atípicos mediante rango intercuartílico.
        - Filtros de fecha, categorías y rangos numéricos.
        """
    )
    st.stop()


st.title("📊 Explorador automático de datos")
st.write(
    "Cargue un conjunto de datos y obtenga un análisis exploratorio automático, interactivo y adaptable a distintas áreas del conocimiento."
)
st.sidebar.header("Carga del dataset")
archivo = st.sidebar.file_uploader(
    "Seleccione un archivo", type=["csv", "xlsx", "xls"], help="Formatos admitidos: CSV, XLSX y XLS."
)

if archivo is None:
    mostrar_bienvenida()

try:
    extension = Path(archivo.name).suffix.lower()
    df = preparar_dataset(leer_archivo(archivo.getvalue(), extension))
except Exception as error:
    st.error(f"No fue posible procesar el archivo. Verifique su formato y contenido. Detalle: {error}")
    st.stop()

if df.empty or df.shape[1] == 0:
    st.warning("El archivo está vacío o no contiene columnas utilizables.")
    st.stop()

st.sidebar.success(f"Archivo cargado: {archivo.name}")
grupos_originales = clasificar_columnas(df)
df_filtrado = aplicar_filtros(df, grupos_originales)

if df_filtrado.empty:
    st.warning("Los filtros no producen registros. Ajuste los filtros de la barra lateral para continuar.")
    st.stop()

grupos = clasificar_columnas(df_filtrado)

st.caption(
    "Los datos se procesan durante la sesión. Evite cargar información personal, confidencial o sensible. "
    "Este análisis exploratorio no reemplaza la interpretación experta. Correlación no implica causalidad y un valor atípico no necesariamente es un error."
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Filas", f"{df_filtrado.shape[0]:,}")
m2.metric("Columnas", f"{df_filtrado.shape[1]:,}")
m3.metric("Duplicados completos", f"{df_filtrado.duplicated().sum():,}")
m4.metric("Celdas faltantes", f"{df_filtrado.isna().sum().sum():,}")

st.subheader("Dimensiones del dataset")
d1, d2, d3 = st.columns(3)
d1.write(f"**Archivo:** {archivo.name}")
d2.write(f"**Cantidad de filas:** {df_filtrado.shape[0]:,}")
d3.write(f"**Cantidad de columnas:** {df_filtrado.shape[1]:,}")

pestanas = st.tabs(
    [
        "Resumen y tipos",
        "Calidad de datos",
        "Estadísticas",
        "Distribuciones",
        "Correlaciones",
        "Valores atípicos",
        "Tabla ordenable",
    ]
)

with pestanas[0]:
    st.subheader("Tipos de variables")
    st.dataframe(tabla_tipos(df_filtrado), use_container_width=True, hide_index=True)

with pestanas[1]:
    st.subheader("Registros duplicados")
    cantidad_duplicados = int(df_filtrado.duplicated().sum())
    st.metric("Filas duplicadas después de la primera aparición", cantidad_duplicados)
    involucrados = df_filtrado.loc[df_filtrado.duplicated(keep=False)]
    if involucrados.empty:
        st.success("No se encontraron registros completamente duplicados.")
    else:
        st.write("Todos los registros involucrados en duplicados:")
        st.dataframe(involucrados, use_container_width=True)

    st.subheader("Valores faltantes")
    faltantes = pd.DataFrame(
        {
            "Variable": df_filtrado.columns,
            "Valores faltantes": df_filtrado.isna().sum().to_numpy(),
            "Porcentaje faltante": (df_filtrado.isna().mean().mul(100)).to_numpy(),
        }
    ).sort_values("Valores faltantes", ascending=False)
    st.dataframe(
        faltantes.style.format({"Porcentaje faltante": "{:.2f}%"}),
        use_container_width=True,
        hide_index=True,
    )
    fig_faltantes = px.bar(
        faltantes,
        x="Variable",
        y="Porcentaje faltante",
        title="Porcentaje de valores faltantes por variable",
        labels={"Porcentaje faltante": "Porcentaje (%)"},
    )
    st.plotly_chart(fig_faltantes, use_container_width=True)

with pestanas[2]:
    st.subheader("Estadísticas descriptivas")
    opcion = st.radio(
        "Variables a resumir",
        ["Todas las variables", "Solo variables numéricas", "Solo variables categóricas"],
        horizontal=True,
    )
    try:
        if opcion == "Solo variables numéricas":
            columnas = grupos["Numérica"]
            if not columnas:
                raise ValueError("El dataset filtrado no contiene variables numéricas.")
            resumen = df_filtrado[columnas].describe().T
        elif opcion == "Solo variables categóricas":
            columnas = grupos["Categórica"] + grupos["Texto"] + grupos["Booleana"]
            if not columnas:
                raise ValueError("El dataset filtrado no contiene variables categóricas, de texto o booleanas.")
            resumen = df_filtrado[columnas].describe(include="all").T
        else:
            resumen = df_filtrado.describe(include="all", datetime_is_numeric=True).T
        traduccion = {
            "count": "Conteo", "mean": "Media", "std": "Desviación estándar",
            "min": "Mínimo", "25%": "Primer cuartil", "50%": "Mediana",
            "75%": "Tercer cuartil", "max": "Máximo", "unique": "Valores únicos",
            "top": "Categoría más frecuente", "freq": "Frecuencia dominante",
        }
        st.dataframe(resumen.rename(columns=traduccion), use_container_width=True)
    except (ValueError, TypeError) as error:
        st.warning(str(error))

with pestanas[3]:
    st.subheader("Distribuciones")
    variable = st.selectbox("Seleccione una variable", df_filtrado.columns)
    tipo = tipo_analitico(df_filtrado[variable])
    if tipo == "Numérica":
        intervalos = st.slider("Número de intervalos", 5, 100, 30)
        fig_hist = px.histogram(df_filtrado, x=variable, nbins=intervalos, title=f"Histograma de {variable}")
        st.plotly_chart(fig_hist, use_container_width=True)

        agrupadoras = ["Sin agrupación"] + grupos["Categórica"] + grupos["Booleana"]
        agrupar = st.selectbox("Agrupar diagrama de caja por", agrupadoras)
        fig_box = px.box(
            df_filtrado,
            x=None if agrupar == "Sin agrupación" else agrupar,
            y=variable,
            points="outliers",
            title=f"Diagrama de caja de {variable}",
        )
        st.plotly_chart(fig_box, use_container_width=True)
    elif tipo in TIPOS_CATEGORICOS:
        etiquetas = df_filtrado[variable].astype("string").fillna("(Faltante)")
        frecuencias = etiquetas.value_counts(dropna=False).head(30).rename_axis("Categoría").reset_index(name="Frecuencia")
        if etiquetas.nunique(dropna=False) > 30:
            st.info("Se muestran las 30 categorías más frecuentes.")
        fig_cat = px.bar(frecuencias, x="Categoría", y="Frecuencia", title=f"Frecuencias de {variable}")
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("Para variables de fecha/hora consulte los filtros de la barra lateral y la tabla ordenable.")

with pestanas[4]:
    st.subheader("Correlaciones")
    numericas = grupos["Numérica"]
    if len(numericas) < 2:
        st.info("Se requieren al menos dos variables numéricas para calcular correlaciones.")
    else:
        seleccionadas = st.multiselect("Variables incluidas", numericas, default=numericas)
        metodo_visible = st.selectbox("Método", ["Pearson", "Spearman", "Kendall"])
        if len(seleccionadas) < 2:
            st.warning("Seleccione al menos dos variables numéricas.")
        else:
            matriz = df_filtrado[seleccionadas].corr(method=metodo_visible.lower())
            texto = np.where(matriz.isna(), "", np.vectorize(lambda x: f"{x:.2f}")(matriz.fillna(0).to_numpy()))
            calor = go.Figure(
                go.Heatmap(
                    z=matriz.to_numpy(), x=matriz.columns, y=matriz.index,
                    zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
                    text=texto, texttemplate="%{text}", hoverongaps=False,
                    colorbar={"title": "Correlación"},
                )
            )
            calor.update_layout(title=f"Matriz de correlación: {metodo_visible}")
            st.plotly_chart(calor, use_container_width=True)
            st.dataframe(matriz.style.format("{:.3f}"), use_container_width=True)

with pestanas[5]:
    st.subheader("Valores atípicos mediante IQR")
    numericas = grupos["Numérica"]
    if not numericas:
        st.info("El dataset filtrado no contiene variables numéricas.")
        atipicos = pd.DataFrame()
    else:
        columnas_atipicos = st.multiselect("Variables numéricas", numericas, default=numericas)
        factor = st.slider("Factor IQR", 1.0, 3.0, 1.5, 0.1)
        atipicos = detectar_atipicos(df_filtrado, columnas_atipicos, factor)
        st.metric("Número de detecciones", len(atipicos))
        if atipicos.empty:
            st.success("No se detectaron valores atípicos con la configuración actual.")
        else:
            conteo = atipicos["Variable con valor atípico"].value_counts().rename_axis("Variable").reset_index(name="Atípicos")
            st.plotly_chart(
                px.bar(conteo, x="Variable", y="Atípicos", title="Cantidad de atípicos por variable"),
                use_container_width=True,
            )
            st.dataframe(atipicos, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar valores atípicos",
            data=convertir_csv(atipicos),
            file_name="valores_atipicos.csv",
            mime="text/csv",
            disabled=atipicos.empty,
        )

with pestanas[6]:
    st.subheader("Tabla interactiva y ordenable")
    visibles = st.multiselect("Columnas visibles", df_filtrado.columns, default=list(df_filtrado.columns))
    if not visibles:
        st.warning("Seleccione al menos una columna para mostrar la tabla.")
    else:
        st.dataframe(df_filtrado[visibles], use_container_width=True, hide_index=True, height=520)

st.divider()
st.download_button(
    "Descargar datos filtrados",
    data=convertir_csv(df_filtrado),
    file_name="datos_filtrados.csv",
    mime="text/csv",
)
