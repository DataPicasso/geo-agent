# Geo Agent 🇩🇴

Geo Agent es una aplicación web desarrollada con Streamlit que permite organizar y asignar rutas de calles de forma inteligente y dinámica en la República Dominicana.

## Despliegue

La aplicación está desplegada en Streamlit Cloud y puedes acceder a ella mediante el siguiente enlace:

[https://geoagent.streamlit.app/](https://geoagent.streamlit.app/)

## Descripción

Geo Agent utiliza:

- **Límites administrativos:** Se emplean los límites administrativos proporcionados por Geoportal del IDERD a través de GeoJSON para Municipio, Distrito Municipal, Sección y Barrio.
- **División territorial:** La estructura jerárquica de la división territorial se extrae de un archivo Excel (`division_territorial.xlsx`) alojado en el repositorio.
- **Extracción de calles:** Se usa Overpass API para extraer las calles de OpenStreetMap dentro del área delimitada.
- **Optimización de rutas:** Se utiliza el algoritmo KMeans para agrupar y ordenar las rutas asignadas a los agentes.
- **Visualización interactiva:** Los resultados se muestran en un mapa interactivo con Folium.

La ubicación geoespacial de la **Provincia** se obtiene desde OpenStreetMap (a través de Overpass API), mientras que para los niveles de Municipio, Distrito Municipal, Sección y Barrio se utilizan los GeoJSON correspondientes.

## Características

- Filtros dinámicos en cascada basados en el archivo Excel, permitiendo seleccionar de forma jerárquica:  
  **Provincia → Municipio → Distrito Municipal → Sección → Barrio**
- Extracción de calles dentro del perímetro definido por los límites administrativos.
- Optimización y asignación de rutas a múltiples agentes.
- Visualización interactiva en un mapa.
- Descarga de los resultados en formato Excel.
- Uso del emoji 🇩🇴 para destacar la República Dominicana en la interfaz.

## Requisitos

Consulta el archivo `requirements.txt` para conocer las dependencias necesarias:
streamlit requests pandas folium shapely scikit-learn geopy numpy pyproj openpyxl



## Instalación

1. Clona el repositorio:


   git clone https://github.com/DataPicasso/geo-agent.git

Navega al directorio del proyecto:


   Copiar
   cd geo-agent

Instala las dependencias:

   Copiar
   pip install -r requirements.txt
   
Ejecuta la aplicación:

   Copiar
   streamlit run app.py


