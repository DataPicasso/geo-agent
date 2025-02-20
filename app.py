import streamlit as st
import requests
import pandas as pd
import folium
import random
from streamlit_folium import st_folium
from shapely.geometry import MultiPoint, Polygon

# -------------------------------
# Funciones para obtener provincias y ciudades dinámicamente desde Overpass API
# -------------------------------

@st.cache_data
def get_provincias():
    """
    Consulta Overpass API para obtener todas las provincias (admin_level=4) de República Dominicana.
    """
    query = """
    [out:json];
    area["name"="República Dominicana"]->.country;
    rel(area.country)["admin_level"="4"]["boundary"="administrative"];
    out tags;
    """
    url = "http://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    if response.status_code != 200:
        st.error("Error al consultar las provincias en Overpass API")
        return []
    data = response.json()
    provincias = []
    for element in data.get("elements", []):
        name = element.get("tags", {}).get("name")
        if name:
            provincias.append(name)
    return sorted(list(set(provincias)))

@st.cache_data
def get_ciudades(provincia):
    """
    Consulta Overpass API para obtener las ciudades o poblados (tags: place=city o place=town) 
    dentro de la provincia seleccionada.
    """
    query = f"""
    [out:json];
    area["name"="{provincia}"]->.province;
    node(area.province)["place"~"^(city|town)$"];
    out;
    """
    url = "http://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    if response.status_code != 200:
        st.error("Error al consultar las ciudades en Overpass API")
        return []
    data = response.json()
    ciudades = []
    for element in data.get("elements", []):
        name = element.get("tags", {}).get("name")
        if name:
            ciudades.append(name)
    return sorted(list(set(ciudades)))

# -------------------------------
# Funciones ya existentes para el generador de calles y asignación
# -------------------------------

# Función para construir la consulta Overpass API de calles
def build_overpass_query(provincia, ciudad):
    # La consulta busca el área de la provincia y luego filtra la ciudad dentro de ella
    query = f"""
    [out:json][timeout:25];
    area["name"="{provincia}"]->.province;
    area["name"="{ciudad}"](area.province)->.city;
    (
      way(area.city)["highway"]["name"];
    );
    out geom;
    """
    return query

# Función para consultar Overpass API para obtener calles
def get_streets(provincia, ciudad):
    url = "http://overpass-api.de/api/interpreter"
    query = build_overpass_query(provincia, ciudad)
    response = requests.post(url, data={'data': query})
    if response.status_code != 200:
        st.error("Error al consultar Overpass API")
        return None
    data = response.json()
    if "elements" not in data or len(data["elements"]) == 0:
        st.error("No se encontraron calles en la región especificada.")
        return None
    return data["elements"]

# Función para calcular el centroide de una calle (lista de nodos)
def calculate_centroid(geometry):
    lats = [point["lat"] for point in geometry]
    lons = [point["lon"] for point in geometry]
    return sum(lats) / len(lats), sum(lons) / len(lons)

# Función para asignar calles a agentes de forma secuencial (round-robin)
def assign_streets(streets, num_agents):
    assignments = {}
    for agent in range(1, num_agents+1):
        assignments[agent] = []
    for i, street in enumerate(streets):
        agent = (i % num_agents) + 1
        assignments[agent].append(street)
    return assignments

# Función para generar colores aleatorios
def generate_agent_colors(num_agents):
    colors = {}
    for agent in range(1, num_agents+1):
        # Genera un color hexadecimal aleatorio
        colors[agent] = "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])
    return colors

# Función para crear un mapa Folium con la visualización
def create_map(assignments, mode, provincia, ciudad, agent_colors):
    # Centrar el mapa en la ciudad (usaremos el centroide de todas las calles)
    all_centroids = []
    for streets in assignments.values():
        for street in streets:
            if "geometry" in street and len(street["geometry"]) > 0:
                cent = calculate_centroid(street["geometry"])
                all_centroids.append(cent)
    if not all_centroids:
        st.error("No se pudieron calcular coordenadas para centrar el mapa.")
        return None
    avg_lat = sum([pt[0] for pt in all_centroids]) / len(all_centroids)
    avg_lon = sum([pt[1] for pt in all_centroids]) / len(all_centroids)
    
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)
    
    for agent, streets in assignments.items():
        # Crear una capa para cada agente
        feature_group = folium.FeatureGroup(name=f"Agente {agent}")
        if mode == "Calles":
            # Dibujar cada calle como polilínea
            for street in streets:
                if "geometry" in street:
                    coords = [(pt["lat"], pt["lon"]) for pt in street["geometry"]]
                    folium.PolyLine(coords, color=agent_colors[agent], weight=4,
                                    tooltip=street.get("tags", {}).get("name", "Sin nombre")).add_to(feature_group)
        elif mode == "Área":
            # Calcular el convex hull de todos los puntos de las calles asignadas
            points = []
            for street in streets:
                if "geometry" in street:
                    for pt in street["geometry"]:
                        points.append((pt["lon"], pt["lat"]))
            if points:
                try:
                    polygon = MultiPoint(points).convex_hull
                    # Asegurarse de que se trata de un polígono válido
                    if isinstance(polygon, Polygon):
                        folium.GeoJson(data={
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [list(polygon.exterior.coords)]
                            }
                        }, style_function=lambda x, col=agent_colors[agent]: {"fillColor": col, "color": col, "fillOpacity": 0.4}).add_to(feature_group)
                except Exception as e:
                    st.error(f"Error al calcular el área para el Agente {agent}: {e}")
        feature_group.add_to(m)
    
    folium.LayerControl().add_to(m)
    return m

# Función para generar DataFrame con la información de las calles
def generate_dataframe(assignments, provincia):
    rows = []
    for agent, streets in assignments.items():
        for street in streets:
            name = street.get("tags", {}).get("name", "Sin nombre")
            if "geometry" in street and len(street["geometry"]) > 0:
                lat, lon = calculate_centroid(street["geometry"])
            else:
                lat, lon = None, None
            rows.append({
                "Calle": name,
                "Provincia": provincia,
                "País": "República Dominicana",
                "Latitud": lat,
                "Longitud": lon,
                "Agente": agent
            })
    return pd.DataFrame(rows)

# -------------------------------
# Interfaz en Streamlit
# -------------------------------
st.title("Asignación de Calles a Agentes en República Dominicana")

# Entradas del usuario en la barra lateral: selección de provincia y ciudad
st.sidebar.header("Configuración")

# Obtiene la lista de provincias de forma dinámica
provincias = get_provincias()
if not provincias:
    st.error("No se pudo obtener la lista de provincias.")
else:
    provincia = st.sidebar.selectbox("Seleccione la provincia:", provincias)
    # Obtiene la lista de ciudades para la provincia seleccionada
    ciudades = get_ciudades(provincia)
    if not ciudades:
        st.error("No se pudo obtener la lista de ciudades para la provincia seleccionada.")
    else:
        ciudad = st.sidebar.selectbox("Seleccione la ciudad:", ciudades)

num_agents = st.sidebar.number_input("Número de agentes:", min_value=1, value=3, step=1)
mode = st.sidebar.radio("Visualización en el mapa:", options=["Calles", "Área"])

if st.sidebar.button("Generar asignación"):
    with st.spinner("Consultando Overpass API para obtener calles..."):
        streets = get_streets(provincia, ciudad)
    if streets:
        st.success("Datos de calles obtenidos correctamente.")
        # Asignar calles a agentes de forma secuencial
        assignments = assign_streets(streets, num_agents)
        agent_colors = generate_agent_colors(num_agents)
        
        # Crear el mapa interactivo
        folium_map = create_map(assignments, mode, provincia, ciudad, agent_colors)
        if folium_map:
            st.subheader("Mapa de asignaciones")
            st_folium(folium_map, width=700, height=500)
        
        # Generar DataFrame para exportar a Excel
        df = generate_dataframe(assignments, provincia)
        st.subheader("Datos asignados")
        st.dataframe(df)
        
        # Convertir DataFrame a Excel para descarga
        to_excel = df.to_excel(index=False, engine='openpyxl')
        st.download_button(label="Descargar Excel", data=to_excel,
                           file_name="asignacion_calles.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
