import streamlit as st
import requests
import pandas as pd
import folium
import random
from shapely.geometry import MultiPoint, Polygon
from io import BytesIO  # Para el manejo del Excel en memoria

# -------------------------------
# Funciones para obtener provincias y ciudades dinámicamente desde Overpass API
# -------------------------------

def get_provincias():
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

def get_ciudades(provincia):
    query = f"""
    [out:json];
    area["name"="{provincia}"]->.province;
    node(area.province)["place"~"^(city|town|village)$"];
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
# Funciones para generar calles y asignación
# -------------------------------

def build_overpass_query(provincia, ciudad):
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

def get_streets(provincia, ciudad):
    url = "http://overpass-api.de/api/interpreter"
    query = build_overpass_query(provincia, ciudad)
    response = requests.post(url, data={'data': query})
    if response.status_code != 200:
        st.error("Error al consultar Overpass API")
        return None
    data = response.json()
    if "elements" not in data or len(data["elements"]) == 0:
        st.warning("No se encontraron calles en la región especificada.")
        return None
    return data["elements"]

def calculate_centroid(geometry):
    lats = [point["lat"] for point in geometry]
    lons = [point["lon"] for point in geometry]
    return sum(lats) / len(lats), sum(lons) / len(lons)

def assign_streets(streets, num_agents):
    assignments = {}
    for agent in range(1, num_agents+1):
        assignments[agent] = []
    for i, street in enumerate(streets):
        agent = (i % num_agents) + 1
        assignments[agent].append(street)
    return assignments

def generate_agent_colors(num_agents):
    colors = {}
    for agent in range(1, num_agents+1):
        colors[agent] = "#" + ''.join([random.choice('0123456789ABCDEF') for _ in range(6)])
    return colors

def create_map(assignments, mode, provincia, ciudad, agent_colors):
    all_centroids = []
    for streets in assignments.values():
        for street in streets:
            if "geometry" in street and len(street["geometry"]) > 0:
                cent = calculate_centroid(street["geometry"])
                all_centroids.append(cent)
    if not all_centroids:
        st.warning("No se encontraron coordenadas de calles. Mostrando mapa base de RD.")
        default_lat, default_lon = 19.0, -70.0
        m = folium.Map(location=[default_lat, default_lon], zoom_start=8, tiles="cartodbpositron")
        return m
    avg_lat = sum(pt[0] for pt in all_centroids) / len(all_centroids)
    avg_lon = sum(pt[1] for pt in all_centroids) / len(all_centroids)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles="cartodbpositron")
    for agent, streets in assignments.items():
        feature_group = folium.FeatureGroup(name=f"Agente {agent}")
        if mode == "Calles":
            for street in streets:
                if "geometry" in street:
                    coords = [(pt["lat"], pt["lon"]) for pt in street["geometry"]]
                    folium.PolyLine(
                        coords,
                        color=agent_colors[agent],
                        weight=4,
                        tooltip=street.get("tags", {}).get("name", "Sin nombre")
                    ).add_to(feature_group)
        elif mode == "Área":
            points = []
            for street in streets:
                if "geometry" in street:
                    for pt in street["geometry"]:
                        points.append((pt["lon"], pt["lat"]))
            if points:
                try:
                    polygon = MultiPoint(points).convex_hull
                    if isinstance(polygon, Polygon):
                        folium.GeoJson(
                            data={
                                "type": "Feature",
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [list(polygon.exterior.coords)]
                                }
                            },
                            style_function=lambda x, col=agent_colors[agent]: {
                                "fillColor": col,
                                "color": col,
                                "fillOpacity": 0.4
                            }
                        ).add_to(feature_group)
                except Exception as e:
                    st.error(f"Error al calcular el área para el Agente {agent}: {e}")
        feature_group.add_to(m)
    folium.LayerControl().add_to(m)
    return m

def generate_dataframe(assignments, provincia, ciudad):
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
                "Ciudad": ciudad,
                "País": "República Dominicana",
                "Latitud": lat,
                "Longitud": lon,
                "Agente": agent
            })
    return pd.DataFrame(rows)

# -------------------------------
# Callbacks para mantener la selección en session_state
# -------------------------------
def update_provincia():
    st.session_state.ciudad = None

# -------------------------------
# Interfaz en Streamlit
# -------------------------------

st.title("Asignación de Calles a Agentes en República Dominicana")
st.sidebar.header("Configuración")

provincias = get_provincias()
if not provincias:
    st.error("No se pudo obtener la lista de provincias.")
else:
    if "provincia" not in st.session_state:
        st.session_state.provincia = provincias[0]
    provincia = st.sidebar.selectbox("Seleccione la provincia:", provincias,
                                     index=provincias.index(st.session_state.provincia),
                                     key="provincia", on_change=update_provincia)

    ciudades = get_ciudades(provincia)
    if ciudades:
        if "ciudad" not in st.session_state or st.session_state.ciudad not in ciudades:
            st.session_state.ciudad = ciudades[0]
        ciudad = st.sidebar.selectbox("Seleccione la ciudad:", ciudades,
                                      index=ciudades.index(st.session_state.ciudad),
                                      key="ciudad")
    else:
        st.warning("No se encontraron ciudades para la provincia seleccionada.")

num_agents = st.sidebar.number_input("Número de agentes:", min_value=1, value=3, step=1)
mode = st.sidebar.radio("Visualización en el mapa:", options=["Calles", "Área"])

if "resultado" not in st.session_state:
    st.session_state.resultado = None

# Al generar la asignación se guardan también 'assignments' y 'agent_colors' en session_state
if st.sidebar.button("Generar asignación"):
    with st.spinner("Consultando Overpass API para obtener calles..."):
        streets = get_streets(provincia, ciudad)
    if streets:
        assignments = assign_streets(streets, num_agents)
        agent_colors = generate_agent_colors(num_agents)
        folium_map = create_map(assignments, mode, provincia, ciudad, agent_colors)
        df = generate_dataframe(assignments, provincia, ciudad)
        st.session_state.resultado = {"mapa": folium_map, "dataframe": df}
        st.session_state.assignments = assignments
        st.session_state.agent_colors = agent_colors
    else:
        st.session_state.resultado = None

if st.session_state.resultado:
    st.subheader("Filtro de Agente")
    # Opciones: "Todos" o agentes 1 a num_agents
    filtro_opciones = ["Todos"] + [str(i) for i in range(1, num_agents+1)]
    agente_filtrar = st.sidebar.selectbox("Filtrar por agente:", options=filtro_opciones, key="agent_filter")
    
    # Filtrado seguro usando get() en session_state
    if agente_filtrar != "Todos":
        agente_seleccionado = int(agente_filtrar)
        assignments_filtradas = { agente_seleccionado: st.session_state.get("assignments", {}).get(agente_seleccionado, []) }
    else:
        assignments_filtradas = st.session_state.get("assignments", {})
    
    # Regenera el mapa según el filtro
    mapa_filtrado = create_map(assignments_filtradas, mode, provincia, ciudad, st.session_state.get("agent_colors", {}))
    
    st.subheader("Mapa de asignaciones")
    mapa_html = mapa_filtrado._repr_html_()
    st.components.v1.html(mapa_html, width=700, height=500, scrolling=True)
    
    if not st.session_state.resultado["dataframe"].empty:
        st.subheader("Datos asignados")
        st.dataframe(st.session_state.resultado["dataframe"])
        output = BytesIO()
        st.session_state.resultado["dataframe"].to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        st.download_button(
            label="Descargar Excel",
            data=output,
            file_name="asignacion_calles.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No se encontraron datos de calles para exportar.")
else:
    st.info("Realice la solicitud de asignación para ver resultados.")
