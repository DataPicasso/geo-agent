# geo-agent

# Asignación de Calles a Agentes en República Dominicana

Esta aplicación en Streamlit permite:
- Obtener un listado de calles de una región en República Dominicana utilizando Overpass API.
- Asignar las calles de forma secuencial y justa entre un número determinado de agentes.
- Visualizar la asignación en un mapa interactivo mediante Folium, con la posibilidad de filtrar por agente y ver la visualización ya sea como líneas (calles) o como áreas (convex hull).
- Exportar la información a un archivo Excel (.xlsx) con columnas: Calle, Provincia, País, Latitud, Longitud y Agente.

## Acceso a la Aplicación
Puedes acceder a la aplicación desplegada en Streamlit en el siguiente enlace:
[GeoAgent RD](https://geoagent.streamlit.app/#b21eb022)

## Requisitos

- Python 3.7 o superior.
- Las dependencias están especificadas en el archivo `requirements.txt`.

## Instalación y Ejecución en Local

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/tu_usuario/tu_repositorio.git
   cd tu_repositorio
