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
# URLs de los GeoJSON
# -------------------------------
REGION_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WPS&version=1.0.0&request=GetExecutionResult&executionId=861818a4-710f-4725-9b50-d9fd316fcc41&outputId=result.json&mimetype=application%2Fjson"
PROVINCE_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WPS&version=1.0.0&request=GetExecutionResult&executionId=f9035478-e790-46ee-93bb-61bc24a828b4&outputId=result.json&mimetype=application%2Fjson"
MUNICIPIO_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WPS&version=1.0.0&request=GetExecutionResult&executionId=b6016b9f-04b3-44b6-80fd-07021bc031e5&outputId=result.json&mimetype=application%2Fjson"
DISTRITO_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WPS&version=1.0.0&request=GetExecutionResult&executionId=48235a8e-b7e0-408b-96ed-9c4b83f1e63c&outputId=result.json&mimetype=application%2Fjson"
SECCION_GEOJSON_URL = "https://geoportal.iderd.gob.do/geoserver/ows?service=WPS&version=1.0.0&request=GetExecutionResult&executionId=dca0cc18-0474-49e7-b107-10f759a7eabb&outputId=result.json&mimetype=application%2Fjson"

# -------------------------------
# Funciones para cargar y parsear los GeoJSON
# -------------------------------
def load_geojson(url):
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"No se pudo cargar el GeoJSON desde {url}")
            return None
    except Exception as e:
        st.error(f"Error al cargar el GeoJSON: {e}")
        return None

def get_regiones():
    """
    Retorna la lista de nombres de las regiones, extraídas del GeoJSON correspondiente.
    """
    data = st.session_state.get("geojson_regiones", {})
    if not data or "features" not in data:
        return []
    # Ajustar según la estructura real del GeoJSON
    regiones = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        nombre = props.get("NOMBRE_REGION", None)
        if nombre:
            regiones.append(nombre)
    return sorted(list(set(regiones)))

def get_provincias_por_region(region):
    """
    Retorna la lista de provincias que pertenecen a la región especificada,
    utilizando el GeoJSON de provincias.
    """
    if not region:
        return []
    data = st.session_state.get("geojson_provincias", {})
    if not data or "features" not in data:
        return []
    provincias = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        nombre_prov = props.get("NOMBRE_PROVINCIA", None)
        nombre_region = props.get("NOMBRE_REGION", None)
        if nombre_prov and nombre_region == region:
            provincias.append(nombre_prov)
    return sorted(list(set(provincias)))

def get_municipios_por_provincia(provincia):
    """
    Retorna la lista de municipios que pertenecen a la provincia especificada,
    usando el GeoJSON de municipios.
    """
    if not provincia:
        return []
    data = st.session_state.get("geojson_municipios", {})
    if not data or "features" not in data:
        return []
    municipios = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        nombre_muni = props.get("NOMBRE_MUNICIPIO", None)
        nombre_prov = props.get("NOMBRE_PROVINCIA", None)
        if nombre_muni and nombre_prov == provincia:
            municipios.append(nombre_muni)
    return sorted(list(set(municipios)))

def get_distritos_por_municipio(municipio):
    """
    Retorna la lista de distritos municipales que pertenecen al municipio,
    usando el GeoJSON de distritos.
    """
    if not municipio:
        return []
    data = st.session_state.get("geojson_distritos", {})
    if not data or "features" not in data:
        return []
    distritos = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        nombre_dm = props.get("NOMBRE_DM", None)
        nombre_muni = props.get("NOMBRE_MUNICIPIO", None)
        if nombre_dm and nombre_muni == municipio:
            distritos.append(nombre_dm)
    return sorted(list(set(distritos)))

def get_secciones_por_distrito(distrito):
    """
    Retorna la lista de secciones que pertenecen al distrito municipal,
    usando el GeoJSON de secciones.
    """
    if not distrito:
        return []
    data = st.session_state.get("geojson_secciones", {})
    if not data or "features" not in data:
        return []
    secciones = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        nombre_seccion = props.get("NOMBRE_SECCION", None)
        nombre_dm = props.get("NOMBRE_DM", None)
        if nombre_seccion and nombre_dm == distrito:
            secciones.append(nombre_seccion)
    return sorted(list(set(secciones)))

# -------------------------------
# Funciones para obtener calles desde Overpass API
# (Mantienen la lógica original)
# -------------------------------
def build_overpass_query(provincia, municipio, distrito):
    # Se construye la consulta utilizando la jerarquía: provincia > municipio > distrito
    query = f"""
    [out:json][timeout:25];
    area["name"="{provincia}"]->.provincia;
    area["name"="{municipio}"](area.provincia)->.municipio;
    area["name"="{distrito}"](area.municipio)->.distrito;
    (
      way(area.distrito)["highway"]["name"];
    );
    out geom;
    """
    return query

def get_streets(provincia, municipio, distrito):
    url = "http://overpass-api.de/api/interpreter"
    query = build_overpass_query(provincia, municipio, distrito)
    response = requests.post(url, data={'data': query})
    if response.status_code != 200:
        st.error("Error al consultar Overpass API")
        return None
    data = response.json()
    if "elements" not in data or len(data["elements"]) == 0:
        st.warning("No se encontraron calles en el área especificada.")
        return None
    return data["elements"]

# -------------------------------
# Funciones de asignación y mapeo
# (Sin cambios en la lógica principal)
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
    assignments = { i: [] for i in range(num_agents) }
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

def create_map(assignments, mode, provincia, municipio, distrito, agent_colors):
    # Se inicia el mapa centrado en República Dominicana con zoom_start=8.
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

def generate_dataframe(assignments, provincia, municipio, distrito):
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
                "Municipio": municipio,
                "Distrito Municipal": distrito,
                "País": "República Dominicana",
                "Latitud": lat,
                "Longitud": lon,
                "Agente": agent + 1
            })
    return pd.DataFrame(rows)

def generate_schedule(df, working_days, start_date, rutas_por_dia):
    schedule = {}
    for agent in sorted(df["Agente"].unique()):
        agent_df = df[df["Agente"] == agent].copy()
        if "Order" in agent_df.columns:
            agent_df = agent_df.sort_values("Order")
        else:
            agent_df = agent_df.reset_index(drop=True)
        total_routes = len(agent_df)
        required_days = int(np.ceil(total_routes / rutas_por_dia))
        working_dates = []
        current_date = pd.to_datetime(start_date)
        while len(working_dates) < required_days:
            if current_date.strftime("%A") in working_days:
                working_dates.append(current_date)
            current_date += pd.Timedelta(days=1)
        groups = [agent_df.iloc[i*rutas_por_dia:(i+1)*rutas_por_dia] for i in range(required_days)]
        schedule[agent] = [{"Date": date.strftime("%Y-%m-%d"), "Calles": group["Calle"].tolist()} 
                           for date, group in zip(working_dates, groups)]
    return schedule

# -------------------------------
# Funciones de actualización de sesión
# (Resetean niveles inferiores al cambiar uno superior)
# -------------------------------
def update_region():
    st.session_state.provincia = None
    st.session_state.municipio = None
    st.session_state.distrito = None
    st.session_state.seccion = None

def update_provincia():
    st.session_state.municipio = None
    st.session_state.distrito = None
    st.session_state.seccion = None

def update_municipio():
    st.session_state.distrito = None
    st.session_state.seccion = None

def update_distrito():
    st.session_state.seccion = None

# -------------------------------
# Interfaz en Streamlit
# -------------------------------
st.title("GEO AGENT: Organización Inteligente de Rutas en República Dominicana")
st.markdown("Esta aplicación utiliza **inteligencia artificial** para organizar y repartir las rutas de calles dentro de áreas delimitadas a nivel de región, provincia, municipio, distrito municipal y sección.")

# Cargar los GeoJSON en sesión (solo la primera vez)
if "geojson_regiones" not in st.session_state:
    st.session_state["geojson_regiones"] = load_geojson(REGION_GEOJSON_URL)
if "geojson_provincias" not in st.session_state:
    st.session_state["geojson_provincias"] = load_geojson(PROVINCE_GEOJSON_URL)
if "geojson_municipios" not in st.session_state:
    st.session_state["geojson_municipios"] = load_geojson(MUNICIPIO_GEOJSON_URL)
if "geojson_distritos" not in st.session_state:
    st.session_state["geojson_distritos"] = load_geojson(DISTRITO_GEOJSON_URL)
if "geojson_secciones" not in st.session_state:
    st.session_state["geojson_secciones"] = load_geojson(SECCION_GEOJSON_URL)

st.sidebar.header("Configuración de GEO AGENT")

# 1. Selección de Región
regiones = get_regiones()
region = None  # Aseguramos que 'region' exista siempre
if not regiones:
    st.error("No se pudo obtener la lista de regiones.")
else:
    if "region" not in st.session_state:
        st.session_state.region = regiones[0]
    region = st.sidebar.selectbox(
        "Seleccione la región:",
        regiones,
        index=regiones.index(st.session_state.region),
        key="region",
        on_change=update_region
    )

# 2. Selección de Provincia
provincias = get_provincias_por_region(region) if region else []
provincia = None
if provincias:
    if "provincia" not in st.session_state or st.session_state.provincia not in provincias:
        st.session_state.provincia = provincias[0]
    provincia = st.sidebar.selectbox(
        "Seleccione la provincia:",
        provincias,
        index=provincias.index(st.session_state.provincia),
        key="provincia",
        on_change=update_provincia
    )
else:
    st.warning("No se encontraron provincias para la región seleccionada.")

# 3. Selección de Municipio
municipios = get_municipios_por_provincia(provincia) if provincia else []
municipio = None
if municipios:
    if "municipio" not in st.session_state or st.session_state.municipio not in municipios:
        st.session_state.municipio = municipios[0]
    municipio = st.sidebar.selectbox(
        "Seleccione el municipio:",
        municipios,
        index=municipios.index(st.session_state.municipio),
        key="municipio",
        on_change=update_municipio
    )
else:
    st.warning("No se encontraron municipios para la provincia seleccionada.")

# 4. Selección de Distrito Municipal
distritos = get_distritos_por_municipio(municipio) if municipio else []
distrito = None
if distritos:
    if "distrito" not in st.session_state or st.session_state.distrito not in distritos:
        st.session_state.distrito = distritos[0]
    distrito = st.sidebar.selectbox(
        "Seleccione el Distrito Municipal:",
        distritos,
        index=distritos.index(st.session_state.distrito),
        key="distrito",
        on_change=update_distrito
    )
else:
    st.warning("No se encontraron distritos municipales para el municipio seleccionado.")

# 5. Selección de Sección
secciones = get_secciones_por_distrito(distrito) if distrito else []
seccion = None
if secciones:
    if "seccion" not in st.session_state or st.session_state.seccion not in secciones:
        st.session_state.seccion = secciones[0]
    seccion = st.sidebar.selectbox(
        "Seleccione la Sección:",
        secciones,
        index=secciones.index(st.session_state.seccion),
        key="seccion"
    )
else:
    st.warning("No se encontraron secciones para el distrito seleccionado.")

# Número de agentes y modo de visualización
num_agents = st.sidebar.number_input("Número de agentes:", min_value=1, value=3, step=1)
mode = st.sidebar.radio("Modo de visualización del mapa:", options=["Calles", "Área"])

if "resultado" not in st.session_state:
    st.session_state.resultado = None

# Botón para generar asignación de calles
if st.sidebar.button("Generar asignación"):
    with st.spinner("Consultando Overpass API para obtener calles..."):
        # Se usa la provincia, municipio y distrito seleccionados.
        streets = get_streets(provincia, municipio, distrito) if (provincia and municipio and distrito) else None
    if streets:
        assignments = assign_streets_cluster(streets, num_agents)
        agent_colors = generate_agent_colors(num_agents)
        mapa = create_map(assignments, mode, provincia, municipio, distrito, agent_colors)
        df = generate_dataframe(assignments, provincia, municipio, distrito)
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

# Mostrar resultados
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
    
    mapa_filtrado = create_map(
        assignments_filtradas, 
        mode, 
        provincia, 
        municipio, 
        distrito, 
        st.session_state.get("agent_colors", {})
    )
    
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
            rutas_por_dia = st.number_input("Cantidad de rutas por día", min_value=1, value=3, step=1)
            working_days = st.multiselect(
                "Días laborables", 
                options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            )
            if working_days:
                schedule = generate_schedule(st.session_state.resultado["dataframe"], working_days, start_date, rutas_por_dia)
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
"""
st.markdown(footer, unsafe_allow_html=True)
