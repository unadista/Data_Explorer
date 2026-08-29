# Explorador automático de datos

Aplicación web desarrollada con Streamlit para cargar archivos tabulares y ejecutar automáticamente un análisis exploratorio de datos. No contiene datasets predeterminados, no usa rutas fijas y procesa el archivo cargado en memoria durante la sesión.

## Funcionalidades

- Carga de archivos CSV, XLSX y XLS.
- Normalización de espacios en encabezados e inferencia prudente de columnas de fecha.
- Filtros interactivos por fecha, categoría y rango numérico.
- Indicadores de filas, columnas, duplicados y valores faltantes.
- Clasificación de variables por tipo Pandas y tipo analítico.
- Revisión de registros duplicados y valores faltantes.
- Estadísticas descriptivas numéricas y categóricas.
- Histogramas, diagramas de caja y gráficos de frecuencia con Plotly.
- Correlaciones de Pearson, Spearman y Kendall.
- Detección de valores atípicos mediante el método IQR.
- Tabla interactiva, selección de columnas y descargas CSV en UTF-8 con BOM.

## Formatos admitidos

- `.csv`, leído con Pandas y detección automática de separador.
- `.xlsx`, leído con `openpyxl`.
- `.xls`, leído con `xlrd`.

## Estructura del repositorio

```text
explorador-automatico-datos/
├── app.py
├── requirements.txt
└── README.md
```

No se debe incluir ningún dataset en el repositorio.

## Instalación

Requisitos: Python 3.11 recomendado y Git opcional.

```bash
python -m venv .venv
```

Active el entorno virtual:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS o Linux
source .venv/bin/activate
```

Instale las dependencias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecución local

```bash
streamlit run app.py
```

Streamlit mostrará la dirección local, normalmente `http://localhost:8501`.

## Despliegue en Streamlit Community Cloud

1. Cree un repositorio público o privado en GitHub compatible con su cuenta de Streamlit.
2. Suba `app.py`, `requirements.txt` y `README.md` a la rama principal.
3. Inicie sesión en Streamlit Community Cloud.
4. Seleccione **Create app** y conecte el repositorio.
5. Elija la rama principal y establezca `app.py` como archivo de entrada.
6. Despliegue la aplicación. No se requieren secretos ni variables de entorno.

## Privacidad y tratamiento responsable

Los datos se procesan durante la sesión de la aplicación. Evite cargar información personal, confidencial o sensible. La aplicación realiza análisis exploratorio y no reemplaza la interpretación de una persona experta. Una correlación no implica causalidad y un valor atípico no necesariamente corresponde a un error.

## Limitaciones conocidas

- Los archivos muy grandes pueden superar la memoria o los límites de carga del entorno de despliegue.
- La detección automática de fechas depende del nombre de la columna y de la proporción de valores convertibles.
- La detección IQR es un criterio estadístico general y puede no ser adecuada para todos los dominios.
- Las variables de texto de alta cardinalidad no se ofrecen como filtros categóricos para evitar interfaces excesivamente pesadas.
- Los libros de Excel se leen desde la primera hoja de forma predeterminada.
- La detección de separador y codificación de CSV cubre casos frecuentes, pero archivos inusuales pueden necesitar normalización previa.
