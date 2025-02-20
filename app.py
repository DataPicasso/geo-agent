import streamlit as st
import requests
import pandas as pd
import folium
import random
from shapely.geometry import MultiPoint, Polygon
from io import BytesIO  # Para el manejo del Excel en memoria
from sklearn.cluster import KMeans
from geopy.distance import geodesic
import numpy as np

# -------------------------------
# Estilos personalizados (tema oscuro)
# -------------------------------
st.markdown(
    """
    <style>
    /* Fuente y fondo oscuro */
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
    body, .stApp {
        background: linear-gradient(135deg, #121212, #1e1e1e);
        font-family: 'Roboto', sans-serif;
        color: #e0e0e0;
    }
    
    /* Barra lateral con fondo oscuro */
    [data-testid="stSidebar"] {
        background: #1a1a1a;
        border: none;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.7);
    }
    
    /* Labels en la barra lateral en color claro */
    [data-testid="stSidebar"] label {
        color: #e0e0e0 !important;
        font-weight: 600 !important;
    }
    
    /* Encabezados en tonos claros */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff;
    }
    
    /* Botones en la barra lateral */
    [data-testid="stSidebar"] .stButton > button {
        background-color: #333333 !important;
        color: #e0e0e0 !important;
        border-radius: 8px !important;
        border: none !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        padding: 10px 20px !important;
        transition: background-color 0.3s ease;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #444444 !important;
    }
    
    /* Botones en el cuerpo principal */
    .stButton > button, .stDownloadButton > button {
        background-color: #333333 !important;
        color: #e0e0e0 !important;
        border-radius: 8px !important;
        border: none !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        padding: 10px 20px !important;
        transition: background-color 0.3s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background-color: #444444 !important;
    }
    
    /* Tablas y contenedores con fondo oscuro */
    .css-1lcbmhc {
        background-color: #2a2a2a;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.7);
    }
    
    /* Pie de página oscuro */
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #1e1e1e;
        text-align: center;
        padding: 10px 0;
        font-size: 14px;
        color: #e0e0e0;
        border-top: 1px solid #333333;
    }
    </style>
    """,
    unsafe_allow_html=True
)

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
    # Se asegura que la provincia esté dentro de la República Dominicana
    query = f"""
    [out:json];
    area["name"="República Dominicana"]->.country;
    area["name"="{provincia}"](area.country)->.province;
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
# Funciones para generar calles y asignación optimizada
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

def assign_streets_cluster(streets, num_agents):
    """
    Convierte la lista de calles en un conjunto de coordenadas (usando el centroide de cada calle)
    y aplica KMeans para agruparlas en num_agents clusters. Retorna un diccionario con cada cluster.
    """
    data = []
    indices = []
    for idx, street in enumerate(streets):
        if "geometry" in street and len(street["geometry"]) > 0:
            lat, lon = calculate_centroid(street["geometry"])
            data.append([lat, lon])
            indices.append(idx)
    if not data:
        return {}
    data = np.array(data)
    kmeans = KMeans(n_clusters=num_agents, n_init=10, random_state=42).fit(data)
    labels = kmeans.labels_
    assignments = { i: [] for i in range(num_agents) }
    for label, idx in zip(labels, indices):
        assignments[label].append(streets[idx])
    return assignments

def reorder_cluster(cluster_streets):
    """
    Reordena la lista de calles dentro de un cluster usando el algoritmo del vecino más cercano.
    """
    if len(cluster_streets) < 2:
        return cluster_streets
    ordered = [cluster_streets.pop(0)]
    while cluster_streets:
        last = ordered[-1]
        last_coord = calculate_centroid(last["geometry"]) if "geometry" in last and len(last["geometry"]) > 0 else None
        if not last_coord:
            break
        best = None
        best_dist = float('inf')
        best_index = None
        for i, street in enumerate(cluster_streets):
            if "geometry" in street and len(street["geometry"]) > 0:
                coord = calculate_centroid(street["geometry"])
                d = geodesic(last_coord, coord).km
                if d < best_dist:
                    best_dist = d
                    best = street
                    best_index = i
        if best is not None:
            ordered.append(best)
            cluster_streets.pop(best_index)
        else:
            break
    return ordered

def generate_agent_colors(num_agents):
    colors = {}
    for agent in range(1, num_agents+1):
        colors[agent-1] = "#" + ''.join([random.choice('0123456789ABCDEF') for _ in range(6)])
    return colors

def create_map(assignments, mode, provincia, ciudad, agent_colors):
    # Se inicia el mapa centrado en la República Dominicana con zoom_start=8.
    m = folium.Map(location=[19.0, -70.0], zoom_start=8, tiles="cartodbpositron")
    for agent, streets in assignments.items():
        streets_ordered = reorder_cluster(streets.copy())
        feature_group = folium.FeatureGroup(name=f"Agente {agent+1}")
        if mode == "Calles":
            for street in streets_ordered:
                if "geometry" in street:
                    coords = [(pt["lat"], pt["lon"]) for pt in street["geometry"]]
                    folium.PolyLine(
                        coords,
                        color=agent_colors.get(agent, "#000000"),
                        weight=4,
                        tooltip=street.get("tags", {}).get("name", "Sin nombre")
                    ).add_to(feature_group)
        elif mode == "Área":
            points = []
            for street in streets_ordered:
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
                            style_function=lambda x, col=agent_colors.get(agent, "#000000"): {
                                "fillColor": col,
                                "color": col,
                                "fillOpacity": 0.4
                            }
                        ).add_to(feature_group)
                except Exception as e:
                    st.error(f"Error al calcular el área para el Agente {agent+1}: {e}")
        feature_group.add_to(m)
    folium.LayerControl().add_to(m)
    return m

def generate_dataframe(assignments, provincia, ciudad):
    rows = []
    for agent, streets in assignments.items():
        streets_ordered = reorder_cluster(streets.copy())
        for street in streets_ordered:
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
                "Agente": agent + 1
            })
    return pd.DataFrame(rows)

def generate_schedule(df, num_weeks, working_days, start_date):
    """
    Genera un calendario de visitas para cada agente.
    Se asume una jornada laboral normal con los días seleccionados.
    Divide las calles asignadas (ordenadas) entre los días disponibles.
    """
    weekday_map = {"Monday":0, "Tuesday":1, "Wednesday":2, "Thursday":3, "Friday":4, "Saturday":5, "Sunday":6}
    working_day_numbers = [weekday_map[day] for day in working_days]
    
    working_dates = []
    current_date = pd.to_datetime(start_date)
    total_days = num_weeks * len(working_days)
    while len(working_dates) < total_days:
        if current_date.weekday() in working_day_numbers:
            working_dates.append(current_date)
        current_date += pd.Timedelta(days=1)
    
    schedule = {}
    for agent in sorted(df["Agente"].unique()):
        agent_df = df[df["Agente"] == agent].sort_values("Order") if "Order" in df.columns else df[df["Agente"] == agent]
        groups = np.array_split(agent_df, total_days)
        schedule[agent] = [{"Date": date.strftime("%Y-%m-%d"), "Calles": group["Calle"].tolist()} 
                           for date, group in zip(working_dates, groups)]
    return schedule

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

if st.sidebar.button("Generar asignación"):
    with st.spinner("Consultando Overpass API para obtener calles..."):
        streets = get_streets(provincia, ciudad)
    if streets:
        assignments = assign_streets_cluster(streets, num_agents)
        agent_colors = generate_agent_colors(num_agents)
        mapa = create_map(assignments, mode, provincia, ciudad, agent_colors)
        df = generate_dataframe(assignments, provincia, ciudad)
        order_list = []
        for agent, streets_assigned in assignments.items():
            streets_ordered = reorder_cluster(streets_assigned.copy())
            for i, street in enumerate(streets_ordered):
                order_list.append(i+1)
        if len(order_list) == len(df):
            df["Order"] = order_list
        st.session_state.resultado = {"mapa": mapa, "dataframe": df}
        st.session_state.assignments = assignments
        st.session_state.agent_colors = agent_colors
    else:
        st.session_state.resultado = None

if st.session_state.resultado:
    st.subheader("Filtro de Agente")
    assignments_dict = st.session_state.get("assignments", {})
    filtro_opciones = ["Todos"] + [str(i+1) for i in assignments_dict.keys()]
    agente_filtrar = st.sidebar.selectbox("Filtrar por agente:", options=filtro_opciones, key="agent_filter")
    
    if agente_filtrar != "Todos":
        agente_seleccionado = int(agente_filtrar) - 1
        assignments_filtradas = { agente_seleccionado: assignments_dict.get(agente_seleccionado, []) }
    else:
        assignments_filtradas = assignments_dict
    
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
        
        with st.expander("Calendario de Visitas"):
            st.write("Configura el calendario de visitas:")
            start_date = st.date_input("Fecha de inicio", value=pd.to_datetime("today"))
            num_weeks = st.number_input("Cantidad de semanas", min_value=1, value=2, step=1)
            working_days = st.multiselect(
                "Días laborables", 
                options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            )
            if working_days:
                schedule = generate_schedule(st.session_state.resultado["dataframe"], num_weeks, working_days, start_date)
                agente_calendario = st.selectbox("Selecciona el agente para ver su calendario:", options=sorted(schedule.keys()))
                st.write(f"### Calendario para el Agente {agente_calendario}")
                schedule_df = pd.DataFrame(schedule[agente_calendario])
                st.dataframe(schedule_df)
            else:
                st.warning("Selecciona al menos un día laboral.")
    else:
        st.warning("No se encontraron datos de calles para exportar.")
else:
    st.info("Realice la solicitud de asignación para ver resultados.")

footer = """
<style>
.footer {
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    background-color: #e3f2fd;
    text-align: center;
    padding: 10px 0;
    font-size: 14px;
    color: #333;
    border-top: 1px solid #ccc;
}
</style>
<div class="footer">
    Creado por Pedro Miguel Figueroa Domínguez
</div>
"""
st.markdown(footer, unsafe_allow_html=True)
