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
from pyproj import Transformer

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
    
    /* Botones en la barra lateral y cuerpo principal */
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
# Funciones para obtener divisiones administrativas desde Overpass API
# (Para Municipio y Distrito)
# -------------------------------
def get_municipios(provincia):
    query = f"""
    [out:json];
    area["name"="República Dominicana"]->.country;
    area["name"="{provincia}"](area.country)->.provincia;
    rel(area.provincia)["admin_level"="8"]["boundary"="administrative"];
    out tags;
    """
    url = "http://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    data = response.json()
    municipios = [element.get("tags", {}).get("name") for element in data.get("elements", []) if element.get("tags", {}).get("name")]
    return sorted(list(set(municipios)))

def get_distritos(municipio):
    query = f"""
    [out:json];
    area["name"="República Dominicana"]->.country;
    rel(area.country)["name"="{municipio}"]["admin_level"="8"];
    out tags;
    area["name"="{municipio}"]->.municipio;
    rel(area.municipio)["admin_level"="9"]["boundary"="administrative"];
    out tags;
    """
    url = "http://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    data = response.json()
    distritos = [element.get("tags", {}).get("name") for element in data.get("elements", []) if element.get("tags", {}).get("name")]
    return sorted(list(set(distritos)))

# -------------------------------
# Constantes para GeoJSON y archivo Excel de división territorial
# -------------------------------
DIVISION_XLSX_URL = "https://raw.githubusercontent.com/DataPicasso/geo-agent/main/division_territorial.xlsx"

PROVINCE_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typename=geonode%3ARD_PROV&outputFormat=json&srs=EPSG%3A32619&srsName=EPSG%3A32619"
MUNICIPIO_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typename=geonode%3ARD_MUNICIPIOS&outputFormat=json&srs=EPSG%3A32619&srsName=EPSG%3A32619"
DISTRITO_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typename=geonode%3ARD_DM&outputFormat=json&srs=EPSG%3A32619&srsName=EPSG%3A32619"
SECCION_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typename=geonode%3ARD_SECCIONES&outputFormat=json&srs=EPSG%3A32619&srsName=EPSG%3A32619"
BARRIOS_PARAJES_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typename=geonode%3ARD_BPARAJES&outputFormat=json&srs=EPSG%3A32619&srsName=EPSG%3A32619"

# -------------------------------
# Funciones para cargar y filtrar GeoJSON
# -------------------------------
def load_geojson(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error al cargar GeoJSON desde: {url}")
    except Exception as e:
        st.error(f"Excepción al cargar GeoJSON desde: {url}\nError: {e}")
    return {}

def filter_feature(geojson_data, value):
    for feature in geojson_data.get("features", []):
        props = feature.get("properties", {})
        if "TOPONIMIA" in props and props["TOPONIMIA"].strip().upper() == value.strip().upper():
            return feature
    return None

def get_boundary(selected_prov, selected_muni, selected_dist, selected_secc, selected_barrio):
    boundary = None
    if selected_barrio and selected_barrio != "Todos":
        data = load_geojson(BARRIOS_PARAJES_URL)
        feature = filter_feature(data, selected_barrio)
        if feature:
            boundary = feature.get("geometry")
    if not boundary and selected_secc and selected_secc != "Todos":
        data = load_geojson(SECCION_GEOJSON_URL)
        feature = filter_feature(data, selected_secc)
        if feature:
            boundary = feature.get("geometry")
    if not boundary and selected_dist and selected_dist != "Todos":
        data = load_geojson(DISTRITO_GEOJSON_URL)
        feature = filter_feature(data, selected_dist)
        if feature:
            boundary = feature.get("geometry")
    if not boundary and selected_muni and selected_muni != "Todos":
        data = load_geojson(MUNICIPIO_GEOJSON_URL)
        feature = filter_feature(data, selected_muni)
        if feature:
            boundary = feature.get("geometry")
    if not boundary and selected_prov and selected_prov != "Todos":
        boundary = get_province_boundary(selected_prov)
    return boundary

def get_province_boundary(provincia):
    query = f"""
    [out:json][timeout:25];
    area["name"="🇩🇴 República Dominicana"]->.country;
    area["name"="{provincia}"](area.country)->.provincia;
    (
      relation(area.provincia)["boundary"="administrative"]["admin_level"="4"];
    );
    out geom;
    """
    url = "http://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    data = response.json()
    if data.get("elements"):
        element = data["elements"][0]
        if "geometry" in element:
            coords = [(pt["lon"], pt["lat"]) for pt in element["geometry"]]
            return {"type": "Polygon", "coordinates": [coords]}
    return None

def build_overpass_query_polygon(geometry):
    if geometry["type"] == "MultiPolygon":
        geometry = {"type": "Polygon", "coordinates": geometry["coordinates"][0]}
    if geometry["type"] != "Polygon":
        return ""
    transformer = Transformer.from_crs("EPSG:32619", "EPSG:4326", always_xy=True)
    coords = []
    for coord in geometry["coordinates"][0]:
        lon, lat = transformer.transform(coord[0], coord[1])
        coords.append(f"{lat} {lon}")
    poly_string = " ".join(coords)
    query = f"""
    [out:json][timeout:25];
    (
      way["highway"]["name"](poly:"{poly_string}");
    );
    out geom;
    """
    return query

def get_streets_by_polygon(boundary):
    url = "http://overpass-api.de/api/interpreter"
    query = build_overpass_query_polygon(boundary)
    if not query:
        return None
    try:
        response = requests.post(url, data={'data': query})
        data = response.json()
    except Exception as e:
        st.error(f"Error al decodificar la respuesta JSON: {e}\nRespuesta recibida: {response.text}")
        return None
    if data.get("elements"):
        return data["elements"]
    return None

# -------------------------------
# Funciones para asignación, clustering y mapeo
# -------------------------------
def calculate_centroid(geometry):
    lats = [point["lat"] for point in geometry]
    lons = [point["lon"] for point in geometry]
    return sum(lats) / len(lats), sum(lons) / len(lons)

def assign_streets_cluster(streets, num_agents):
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
    assignments = {i: [] for i in range(num_agents)}
    for label, idx in zip(labels, indices):
        assignments[label].append(streets[idx])
    return assignments

def reorder_cluster(cluster_streets):
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

def create_map(assignments, mode, boundary, agent_colors):
    if boundary and boundary["type"] == "Polygon":
        lats = [pt[1] for pt in boundary["coordinates"][0]]
        lons = [pt[0] for pt in boundary["coordinates"][0]]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
    else:
        center = [19.0, -70.0]
    m = folium.Map(location=center, zoom_start=13, tiles="cartodbpositron")
    for agent, streets in assignments.items():
        streets_ordered = reorder_cluster(streets.copy())
        feature_group = folium.FeatureGroup(name=f"Agente {agent+1}")
        if mode == "Calles":
            for street in streets_ordered:
                if "geometry" in street:
                    coords = [(pt["lat"], pt["lon"]) for pt in street["geometry"]]
                    folium.PolyLine(coords, color=agent_colors.get(agent, "#000000"), weight=4,
                                    tooltip=street.get("tags", {}).get("name", "Sin nombre")).add_to(feature_group)
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
                            data={"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [list(polygon.exterior.coords)]}},
                            style_function=lambda x, col=agent_colors.get(agent, "#000000"): {"fillColor": col, "color": col, "fillOpacity": 0.4}
                        ).add_to(feature_group)
                except Exception:
                    pass
        feature_group.add_to(m)
    folium.LayerControl().add_to(m)
    return m

def generate_dataframe(assignments, selected_prov, selected_muni, selected_dist, selected_secc, selected_barrio):
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
                "Provincia": selected_prov,
                "Municipio": selected_muni,
                "Distrito Municipal": selected_dist,
                "Sección": selected_secc,
                "Barrio": selected_barrio,
                "País": "🇩🇴 República Dominicana",
                "Latitud": lat,
                "Longitud": lon,
                "Agente": agent + 1
            })
    return pd.DataFrame(rows)

# Funciones de actualización para los filtros en cascada
def update_provincia():
    st.session_state.municipio = None
    st.session_state.distrito = None

def update_municipio():
    st.session_state.distrito = None

# -------------------------------
# Cargar el archivo Excel con la división territorial
# -------------------------------
@st.cache_data
def load_division_excel():
    try:
        return pd.read_excel(DIVISION_XLSX_URL)
    except Exception:
        return pd.DataFrame()

df_division = load_division_excel()

# Crear listas dinámicas para cada nivel (cascada) a partir del Excel
provincias_all = sorted(df_division["Provincia"].dropna().unique().tolist()) if "Provincia" in df_division.columns else []
selected_prov = st.sidebar.selectbox("Seleccione la Provincia:", ["Todos"] + provincias_all, index=0, key="provincia", on_change=update_provincia)

df_prov = df_division[df_division["Provincia"] == selected_prov] if selected_prov != "Todos" else df_division
municipios_all = sorted(df_prov["Municipio"].dropna().unique().tolist()) if "Municipio" in df_prov.columns else []
selected_muni = st.sidebar.selectbox("Seleccione el Municipio:", ["Todos"] + municipios_all, index=0, key="municipio", on_change=update_municipio)

df_muni = df_prov[df_prov["Municipio"] == selected_muni] if selected_prov != "Todos" and selected_muni != "Todos" else df_prov
distritos_all = sorted(df_muni["Distrito Municipal"].dropna().unique().tolist()) if "Distrito Municipal" in df_muni.columns else []
selected_dist = st.sidebar.selectbox("Seleccione el Distrito Municipal:", ["Todos"] + distritos_all, index=0, key="distrito")

df_dist = df_muni[df_muni["Distrito Municipal"] == selected_dist] if selected_prov != "Todos" and selected_muni != "Todos" and selected_dist != "Todos" else df_muni
secciones_all = sorted(df_dist["Sección"].dropna().unique().tolist()) if "Sección" in df_dist.columns else []
selected_secc = st.sidebar.selectbox("Seleccione la Sección:", ["Todos"] + secciones_all, index=0, key="seccion")

df_secc = df_dist[df_dist["Sección"] == selected_secc] if selected_prov != "Todos" and selected_muni != "Todos" and selected_dist != "Todos" and selected_secc != "Todos" else df_dist
barrios_all = sorted(df_secc["Barrio"].dropna().unique().tolist()) if "Barrio" in df_secc.columns else []
selected_barrio = st.sidebar.selectbox("Seleccione el Barrio:", ["Todos"] + barrios_all, index=0, key="barrio")

num_agents = st.sidebar.number_input("Número de agentes:", min_value=1, value=3, step=1)
mode = st.sidebar.radio("Modo de visualización del mapa:", options=["Calles", "Área"])

st.title("GEO AGENT 🇩🇴: Organización Inteligente de Rutas en República Dominicana")
st.markdown("Esta aplicación utiliza los límites administrativos definidos en GeoJSON (para Municipio, Distrito, Sección y Barrio) y la ubicación geoespacial de la Provincia obtenida de OpenStreetMap para filtrar dinámicamente el área en 🇩🇴 República Dominicana. Se extraen las calles desde OpenStreetMap dentro del perímetro seleccionado.")

if "resultado" not in st.session_state:
    st.session_state.resultado = None

if st.sidebar.button("Generar asignación"):
    boundary = get_boundary(selected_prov, selected_muni, selected_dist, selected_secc, selected_barrio)
    st.session_state.boundary = boundary  # Almacena el boundary en el estado de sesión
    if boundary:
        with st.spinner("Consultando Overpass API para obtener calles dentro del perímetro..."):
            streets = get_streets_by_polygon(boundary)
        if streets:
            assignments = assign_streets_cluster(streets, num_agents)
            agent_colors = generate_agent_colors(num_agents)
            mapa = create_map(assignments, mode, boundary, agent_colors)
            df = generate_dataframe(assignments, selected_prov, selected_muni, selected_dist, selected_secc, selected_barrio)
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
    
    mapa_filtrado = create_map(assignments_filtradas, mode, st.session_state.boundary, st.session_state.get("agent_colors", {}))
    
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

st.markdown(
    """
    <style>
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
    <div class="footer">
        Creado por Pedro Miguel Figueroa Domínguez
    </div>
    """,
    unsafe_allow_html=True
)
