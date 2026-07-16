#!/usr/bin/env python3
"""
Seismic 3D Analysis - Streamlit Web Application
================================================
Interfaz web interactiva para análisis sismológico con:
- Búsqueda de eventos USGS
- Visualización 3D de mecanismo focal
- Descarga de formas de onda FDSN
- Animación de propagación de ondas
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
import sys
import time

# Agregar directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

# Configuración de página
st.set_page_config(
    page_title="🌍 Análisis Sismológico 3D",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #ff7f0e;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        font-weight: bold;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

@st.cache_data(ttl=3600)
def search_usgs_events(lat, lon, radius_km, min_mag, start_date, end_date, limit=20):
    """Busca eventos en USGS ComCat API."""
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        'format': 'geojson',
        'latitude': lat,
        'longitude': lon,
        'maxradiuskm': radius_km,
        'minmagnitude': min_mag,
        'starttime': start_date,
        'endtime': end_date,
        'limit': limit,
        'orderby': 'time'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        events = []
        for feature in data['features']:
            props = feature['properties']
            geom = feature['geometry']
            coords = geom['coordinates']
            
            events.append({
                'id': feature['id'],
                'time': datetime.fromtimestamp(props['time'] / 1000),
                'latitude': coords[1],
                'longitude': coords[0],
                'depth': coords[2],
                'magnitude': props.get('mag', 0),
                'mag_type': props.get('magType', 'Mw'),
                'place': props.get('place', ''),
                'url': props.get('url', ''),
                'significance': props.get('sig', 0),
                'alert': props.get('alert', ''),
                'tsunami': props.get('tsunami', 0),
            })
        
        return pd.DataFrame(events)
    except Exception as e:
        st.error(f"Error consultando USGS: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_event_focal_mechanism(event_id):
    """Obtiene mecanismo focal de un evento USGS."""
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {'eventid': event_id, 'format': 'geojson'}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data['features']:
            return None
            
        feature = data['features'][0]
        products = feature['properties'].get('products', {})
        
        # Buscar momento tensorial
        for prod_type in ['moment-tensor', 'focal-mechanism']:
            if prod_type in products:
                for product in products[prod_type]:
                    if product.get('code') in ['gcmt', 'us', 'ptwc']:
                        contents = product.get('contents', {})
                        for key, val in contents.items():
                            if 'moment' in key.lower() or key.endswith('.json'):
                                try:
                                    if isinstance(val, dict):
                                        mt_data = val
                                    else:
                                        # Necesitaría descargar
                                        continue
                                    
                                    mt = mt_data.get('moment-tensor', mt_data)
                                    return parse_moment_tensor(mt, product.get('code', ''))
                                except:
                                    continue
        return None
    except Exception as e:
        st.warning(f"No se pudo obtener mecanismo focal: {e}")
        return None


def parse_moment_tensor(mt_data, source):
    """Parsea datos de momento tensorial."""
    fm = {
        'source': source,
        'strike': 0, 'dip': 0, 'rake': 0,
        'strike2': 0, 'dip2': 0, 'rake2': 0,
        'magnitude': 0, 'moment': 0
    }
    
    if 'magnitude' in mt_data:
        fm['magnitude'] = float(mt_data['magnitude'])
    elif 'mw' in mt_data:
        fm['magnitude'] = float(mt_data['mw'])
    
    if 'moment' in mt_data:
        fm['moment'] = float(mt_data['moment'])
    
    if 'nodal-planes' in mt_data:
        np = mt_data['nodal-planes']
        if 'nodal-plane-1' in np:
            p1 = np['nodal-plane-1']
            fm['strike'] = float(p1.get('strike', 0))
            fm['dip'] = float(p1.get('dip', 0))
            fm['rake'] = float(p1.get('rake', 0))
        if 'nodal-plane-2' in np:
            p2 = np['nodal-plane-2']
            fm['strike2'] = float(p2.get('strike', 0))
            fm['dip2'] = float(p2.get('dip', 0))
            fm['rake2'] = float(p2.get('rake', 0))
    
    return fm


def create_fault_plane_mesh(strike, dip, rake, length, width, centroid_depth):
    """Crea malla 3D del plano de falla."""
    import math
    
    strike_rad = math.radians(strike)
    dip_rad = math.radians(dip)
    rake_rad = math.radians(rake)
    
    # Vectores base del plano de falla
    strike_vec = np.array([
        math.cos(strike_rad),
        math.sin(strike_rad),
        0
    ])
    
    dip_vec = np.array([
        -math.cos(dip_rad) * math.sin(strike_rad),
        math.cos(dip_rad) * math.cos(strike_rad),
        -math.sin(dip_rad)
    ])
    
    normal = np.array([
        -math.sin(dip_rad) * math.sin(strike_rad),
        math.sin(dip_rad) * math.cos(strike_rad),
        -math.cos(dip_rad)
    ])
    
    slip = math.cos(rake_rad) * strike_vec + math.sin(rake_rad) * dip_vec
    
    # Vértices del plano (centrado en origen local)
    half_l, half_w = length / 2, width / 2
    local_verts = np.array([
        [-half_l, -half_w, 0],
        [half_l, -half_w, 0],
        [half_l, half_w, 0],
        [-half_l, half_w, 0],
    ])
    
    # Transformar a ENU
    R = np.column_stack([strike_vec, dip_vec, normal])
    vertices = local_verts @ R.T
    
    # Centrar en hipocentro
    centroid = np.array([0, 0, -centroid_depth])
    vertices += centroid
    
    # Caras (dos triángulos)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    
    return vertices, faces, strike_vec, dip_vec, normal, slip


def create_wavefield_points(radius_km=200, resolution=30):
    """Crea puntos para visualización de campo de ondas."""
    x = np.linspace(-radius_km, radius_km, resolution)
    y = np.linspace(-radius_km, radius_km, resolution)
    z = np.linspace(-radius_km, radius_km, resolution)
    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
    points = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    r = np.linalg.norm(points, axis=1)
    mask = r <= radius_km
    return points[mask], r[mask]


def compute_wave_amplitudes(points, r, time, source_depth=10, vp=6.0, vs=3.5, freq=1.0):
    """Calcula amplitudes de ondas P y S."""
    source_pos = np.array([0.0, 0.0, -source_depth])
    r_vec = points - source_pos
    r_dist = np.linalg.norm(r_vec, axis=1)
    
    # Evitar división por cero
    r_dist = np.maximum(r_dist, 0.1)
    r_unit = r_vec / r_dist[:, None]
    
    # Wavelet de Ricker
    a = math.pi * freq
    tp = r_dist / vp - time
    ts = r_dist / vs - time
    
    p_wave = (1 - 2 * a**2 * tp**2) * np.exp(-a**2 * tp**2) / r_dist
    s_wave = (1 - 2 * a**2 * ts**2) * np.exp(-a**2 * ts**2) / r_dist
    
    return p_wave, s_wave, r_unit


def plot_fault_3d(vertices, faces, strike_vec, dip_vec, normal, slip, event_data):
    """Crea gráfico 3D interactivo del plano de falla con Plotly."""
    
    fig = go.Figure()
    
    # Plano de falla
    fig.add_trace(go.Mesh3d(
        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color='brown', opacity=0.6, name='Plano de Falla',
        showscale=False, showlegend=True, legendgroup='fault'
    ))
    
    # Centroide
    centroid = np.mean(vertices, axis=0)
    
    # Vectores de falla
    scale = np.max(np.linalg.norm(vertices - centroid, axis=1)) * 0.5
    
    vectors = [
        ('Rumbo (Strike)', strike_vec, 'blue'),
        ('Buzamiento (Dip)', dip_vec, 'green'),
        ('Deslizamiento (Slip)', slip, 'red'),
        ('Normal', normal, 'purple')
    ]
    
    for name, vec, color in vectors:
        end = centroid + vec * scale
        fig.add_trace(go.Scatter3d(
            x=[centroid[0], end[0]], y=[centroid[1], end[1]], z=[centroid[2], end[2]],
            mode='lines+markers', line=dict(color=color, width=6),
            marker=dict(size=[0, 8], color=color),
            name=name, showlegend=True, legendgroup='vectors'
        ))
    
    # Epicentro
    fig.add_trace(go.Scatter3d(
        x=[0], y=[0], z=[0],
        mode='markers+text', marker=dict(size=12, color='yellow', symbol='diamond'),
        text=['Epicentro'], textposition='top center',
        name='Epicentro', showlegend=True, legendgroup='source'
    ))
    
    # Hipocentro
    fig.add_trace(go.Scatter3d(
        x=[0], y=[0], z=[-event_data.get('depth', 10)],
        mode='markers+text', marker=dict(size=12, color='red', symbol='diamond'),
        text=[f"Hipocentro ({event_data.get('depth', 10):.1f} km)"],
        textposition='top center', name='Hipocentro', showlegend=True, legendgroup='source'
    ))
    
    # Calculate bounds for proper centering
    all_x = np.concatenate([vertices[:, 0], [0, 0]])
    all_y = np.concatenate([vertices[:, 1], [0, 0]])
    all_z = np.concatenate([vertices[:, 2], [0, -event_data.get('depth', 10)]])
    
    # Add vector endpoints
    for vec in [strike_vec, dip_vec, normal, slip]:
        all_x = np.concatenate([all_x, [centroid[0] + vec[0] * scale]])
        all_y = np.concatenate([all_y, [centroid[1] + vec[1] * scale]])
        all_z = np.concatenate([all_z, [centroid[2] + vec[2] * scale]])
    
    x_range = [np.min(all_x), np.max(all_x)]
    y_range = [np.min(all_y), np.max(all_y)]
    z_range = [np.min(all_z), np.max(all_z)]
    
    # Center ranges
    x_center = (x_range[0] + x_range[1]) / 2
    y_center = (y_range[0] + y_range[1]) / 2
    z_center = (z_range[0] + z_range[1]) / 2
    max_range = max(x_range[1] - x_range[0], y_range[1] - y_range[0], z_range[1] - z_range[0]) / 2
    
    fig.update_layout(
        title=dict(
            text=f"Mecanismo Focal 3D - M{event_data.get('magnitude', 0):.1f} | "
                 f"Strike={strike_vec[0]:.0f}° Dip={dip_vec[0]:.0f}° Rake={slip[0]:.0f}°",
            x=0.5, xanchor='center'
        ),
        scene=dict(
            xaxis_title='Este (km)', yaxis_title='Norte (km)', zaxis_title='Profundidad (km)',
            xaxis=dict(range=[x_center - max_range, x_center + max_range]),
            yaxis=dict(range=[y_center - max_range, y_center + max_range]),
            zaxis=dict(range=[z_center - max_range, z_center + max_range], autorange='reversed'),
            aspectmode='cube',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))
        ),
        width=None, height=700, 
        showlegend=True,
        legend=dict(
            x=1.02, y=0.98,
            xanchor='left', yanchor='top',
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='rgba(0,0,0,0.2)',
            borderwidth=1,
            font=dict(size=11)
        ),
        margin=dict(l=0, r=180, t=60, b=0)
    )
    
    return fig


def plot_wave_propagation_2d(event_data, fm_data, time_step=0):
    """Crea visualización 2D de propagación de ondas (corte transversal)."""
    
    # Generar puntos en corte E-O (y=0)
    radius = 200
    res = 100
    x = np.linspace(-radius, radius, res)
    z = np.linspace(-radius, radius, res)
    X, Z = np.meshgrid(x, z)
    points = np.column_stack([X.ravel(), np.zeros_like(X.ravel()), Z.ravel()])
    r = np.linalg.norm(points, axis=1)
    
    # Calcular ondas
    p_wave, s_wave, _ = compute_wave_amplitudes(
        points, r, time_step, 
        source_depth=event_data.get('depth', 10)
    )
    
    # Reshape para contour
    P = p_wave.reshape(res, res)
    S = s_wave.reshape(res, res)
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=['Onda P (Compresional)', 'Onda S (Cizalle)'],
        shared_yaxes=True
    )
    
    fig.add_trace(go.Contour(
        z=P, x=x, y=z, colorscale='RdBu', showscale=True,
        colorbar=dict(title='Amplitud', x=0.46)
    ), row=1, col=1)
    
    fig.add_trace(go.Contour(
        z=S, x=x, y=z, colorscale='RdBu', showscale=True,
        colorbar=dict(title='Amplitud', x=1.02)
    ), row=1, col=2)
    
    # Hipocentro
    for col in [1, 2]:
        fig.add_trace(go.Scatter(
            x=[0], y=[-event_data.get('depth', 10)],
            mode='markers', marker=dict(size=15, color='red', symbol='diamond'),
            showlegend=False
        ), row=1, col=col)
    
    fig.update_layout(
        title=f"Propagación de Ondas - t={time_step:.1f}s",
        height=500,
        yaxis=dict(title='Profundidad (km)', autorange='reversed'),
        yaxis2=dict(title='Profundidad (km)', autorange='reversed'),
        xaxis=dict(title='Este (km)'),
        xaxis2=dict(title='Este (km)')
    )
    
    return fig


# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

def main():
    # Header
    st.markdown('<h1 class="main-header">🌍 Análisis Sismológico 3D</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#666;">Búsqueda USGS • Mecanismo Focal • Propagación de Ondas • Animación 3D</p>', unsafe_allow_html=True)
    
    # Initialize session state for animation
    if 'anim_frame' not in st.session_state:
        st.session_state.anim_frame = 0
    if 'anim_playing' not in st.session_state:
        st.session_state.anim_playing = False
    
    # Sidebar - Configuración
    with st.sidebar:
        st.markdown("## ⚙️ Configuración de Búsqueda")
        
        # Presets
        preset = st.selectbox(
            "📍 Preset de ubicación",
            ["Personalizado", "Chile (Santiago)", "Turquía-Siria 2023", "Japón (Noto) 2024", "México 2017"],
            index=0
        )
        
        presets = {
            "Chile (Santiago)": {"lat": -33.45, "lon": -70.65, "radius": 500},
            "Turquía-Siria 2023": {"lat": 37.17, "lon": 37.03, "radius": 500},
            "Japón (Noto) 2024": {"lat": 37.5, "lon": 137.2, "radius": 300},
            "México 2017": {"lat": 18.41, "lon": -98.71, "radius": 400},
        }
        
        if preset != "Personalizado":
            p = presets[preset]
            lat = st.number_input("Latitud", value=p["lat"], format="%.4f")
            lon = st.number_input("Longitud", value=p["lon"], format="%.4f")
            radius = st.number_input("Radio (km)", value=p["radius"], min_value=10, max_value=2000)
        else:
            lat = st.number_input("Latitud", value=-33.45, format="%.4f", help="Ej: -33.45 para Santiago")
            lon = st.number_input("Longitud", value=-70.65, format="%.4f", help="Ej: -70.65 para Santiago")
            radius = st.number_input("Radio de búsqueda (km)", value=500, min_value=10, max_value=2000)
        
        st.divider()
        
        # Parámetros temporales
        st.markdown("### 📅 Período Temporal")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Fecha inicio", value=datetime(2024, 1, 1))
        with col2:
            end_date = st.date_input("Fecha fin", value=datetime(2024, 12, 31))
        
        # Magnitud
        min_mag = st.slider("Magnitud mínima", 3.0, 8.0, 5.0, 0.1)
        max_mag = st.slider("Magnitud máxima", 3.0, 9.0, 9.0, 0.1)
        
        # Animación
        st.divider()
        st.markdown("### 🎬 Parámetros de Animación")
        anim_duration = st.slider("Duración (s)", 10, 120, 60)
        anim_fps = st.slider("FPS", 10, 60, 30)
        
        # Botón buscar
        search_btn = st.button("🔍 Buscar Eventos", type="primary", width='stretch')
    
    # Estado de sesión
    if 'events_df' not in st.session_state:
        st.session_state.events_df = pd.DataFrame()
    if 'selected_event' not in st.session_state:
        st.session_state.selected_event = None
    if 'focal_mechanism' not in st.session_state:
        st.session_state.focal_mechanism = None
    
    # Búsqueda
    if search_btn:
        with st.spinner("Buscando eventos en USGS ComCat..."):
            df = search_usgs_events(
                lat, lon, radius, min_mag,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                limit=50
            )
            st.session_state.events_df = df
            st.session_state.selected_event = None
            st.session_state.focal_mechanism = None
            if len(df) > 0:
                st.success(f"✅ Encontrados {len(df)} eventos")
            else:
                st.warning("⚠️ No se encontraron eventos con esos criterios")
    
    # Mostrar resultados
    if not st.session_state.events_df.empty:
        df = st.session_state.events_df
        
        # Tabla de eventos
        st.markdown('<h2 class="sub-header">📋 Eventos Encontrados</h2>', unsafe_allow_html=True)
        
        # Formatear para mostrar
        display_df = df.copy()
        display_df['time'] = display_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['depth'] = display_df['depth'].round(1)
        display_df['magnitude'] = display_df['magnitude'].round(1)
        display_df['distance_km'] = np.sqrt(
            (display_df['latitude'] - lat)**2 + (display_df['longitude'] - lon)**2
        ) * 111  # aprox
        
        # Selector de evento
        event_options = [
            f"{row['time']} | M{row['magnitude']:.1f} | {row['depth']:.1f}km | {row['place'][:50]}"
            for _, row in display_df.iterrows()
        ]
        
        selected_idx = st.selectbox(
            "Seleccionar evento para análisis detallado:",
            range(len(event_options)),
            format_func=lambda i: event_options[i]
        )
        
        if st.button("📊 Analizar Evento Seleccionado", type="secondary"):
            event = df.iloc[selected_idx]
            st.session_state.selected_event = event
            
            # Obtener mecanismo focal
            with st.spinner("Obteniendo mecanismo focal..."):
                fm = get_event_focal_mechanism(event['id'])
                st.session_state.focal_mechanism = fm
            
            st.rerun()
        
        # Dataframe interactivo
        st.dataframe(
            display_df[['time', 'magnitude', 'mag_type', 'depth', 'latitude', 'longitude', 'place']],
            width='stretch',
            hide_index=True,
            column_config={
                "time": "Tiempo (UTC)",
                "magnitude": "Mag.",
                "mag_type": "Tipo",
                "depth": "Prof. (km)",
                "latitude": "Lat",
                "longitude": "Lon",
                "place": "Lugar"
            }
        )
    
    # Análisis detallado del evento seleccionado
    if st.session_state.selected_event is not None:
        event = st.session_state.selected_event
        fm = st.session_state.focal_mechanism
        
        st.divider()
        st.markdown('<h2 class="sub-header">🔬 Análisis Detallado del Evento</h2>', unsafe_allow_html=True)
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🕐 Tiempo", event['time'].strftime('%Y-%m-%d %H:%M:%S'))
        with col2:
            st.metric("📍 Magnitud", f"M{event['magnitude']:.1f} ({event['mag_type']})")
        with col3:
            st.metric("📏 Profundidad", f"{event['depth']:.1f} km")
        with col4:
            st.metric("📍 Ubicación", f"{event['latitude']:.3f}, {event['longitude']:.3f}")
        
        # Mecanismo focal
        if fm:
            st.markdown("### 📐 Mecanismo Focal (Momento Tensorial)")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Parámetros del mecanismo
                fm_cols = st.columns(3)
                with fm_cols[0]:
                    st.metric("Strike", f"{fm['strike']:.1f}°")
                    st.metric("Strike 2", f"{fm['strike2']:.1f}°")
                with fm_cols[1]:
                    st.metric("Dip", f"{fm['dip']:.1f}°")
                    st.metric("Dip 2", f"{fm['dip2']:.1f}°")
                with fm_cols[2]:
                    st.metric("Rake", f"{fm['rake']:.1f}°")
                    st.metric("Rake 2", f"{fm['rake2']:.1f}°")
                
                if fm['magnitude'] > 0:
                    st.metric("Mw (Momento)", f"{fm['magnitude']:.2f}")
                if fm['moment'] > 0:
                    st.metric("Momento Sísmico", f"{fm['moment']:.2e} N·m")
                
                st.info(f"Fuente: {fm['source'].upper()}")
            
            with col2:
                # Tipo de falla basado en rake
                rake = fm['rake']
                if -22.5 <= rake <= 22.5 or abs(rake) >= 157.5:
                    fault_type = "🟢 **Falla Normal** (Deslizamiento dip-slip normal)"
                elif 67.5 <= rake <= 112.5:
                    fault_type = "🔴 **Falla Inversa** (Deslizamiento dip-slip inverso)"
                elif -112.5 <= rake <= -67.5:
                    fault_type = "🔵 **Falla Normal** (Deslizamiento dip-slip normal)"
                else:
                    fault_type = "🟡 **Falla de Deslizamiento Lateral** (Strike-slip)"
                
                st.markdown(f"### Tipo de Falla:\n{fault_type}")
                
                # Planos de falla
                st.markdown("**Planos de Falla:**")
                st.markdown(f"- Plano 1: Strike={fm['strike']:.0f}° Dip={fm['dip']:.0f}° Rake={fm['rake']:.0f}°")
                st.markdown(f"- Plano 2: Strike={fm['strike2']:.0f}° Dip={fm['dip2']:.0f}° Rake={fm['rake2']:.0f}°")
        
        else:
            st.warning("⚠️ No se encontró mecanismo focal para este evento. Usando valores sintéticos para demostración.")
            # Valores sintéticos
            fm = {
                'strike': 15, 'dip': 25, 'rake': 110,
                'strike2': 195, 'dip2': 65, 'rake2': -70,
                'magnitude': event['magnitude'], 'source': 'synthetic'
            }
        
        # Visualización 3D del plano de falla
        st.markdown("### 🎯 Visualización 3D del Plano de Falla")
        
        # Estimar dimensiones de falla (Wells & Coppersmith 1994)
        Mw = fm.get('magnitude', event['magnitude'])
        length = 10 ** (-3.22 + 0.69 * Mw)
        width = 10 ** (-1.01 + 0.32 * Mw)
        
        vertices, faces, strike_vec, dip_vec, normal, slip = create_fault_plane_mesh(
            fm['strike'], fm['dip'], fm['rake'], length, width, event['depth']
        )
        
        fig_3d = plot_fault_3d(vertices, faces, strike_vec, dip_vec, normal, slip, event)
        st.plotly_chart(fig_3d, width='stretch')
        
        # Propagación de ondas 2D
        st.markdown("### 🌊 Propagación de Ondas (Corte Transversal)")
        
        # Animation controls with status
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            time_slider = st.slider(
                "Tiempo (s)", 0.0, float(anim_duration), st.session_state.anim_frame / anim_fps, 1.0 / anim_fps,
                key="time_slider"
            )
            # Update session state from slider (only when manually changed)
            new_frame = int(time_slider * anim_fps)
            if new_frame != st.session_state.anim_frame:
                st.session_state.anim_frame = new_frame
        with col2:
            play_disabled = st.session_state.anim_playing
            if st.button("▶️ Play", disabled=play_disabled, width='stretch'):
                st.session_state.anim_playing = True
                st.write("🎬 BUTTON DEBUG: Play button clicked, setting anim_playing=True")
                st.rerun()
        with col3:
            stop_disabled = not st.session_state.anim_playing
            if st.button("⏸️ Stop", disabled=stop_disabled, width='stretch'):
                st.session_state.anim_playing = False
                st.write("🎬 BUTTON DEBUG: Stop button clicked, setting anim_playing=False")
                st.rerun()
        
        # Status indicator
        if st.session_state.anim_playing:
            st.info(f"▶️ Reproduciendo... frame {st.session_state.anim_frame}/{int(anim_duration * anim_fps)}")
        else:
            st.caption(f"⏸️ Pausado en {st.session_state.anim_frame / anim_fps:.1f}s")
        
        # DEBUG: Show session state
        st.write(f"🎬 STATE DEBUG: anim_frame={st.session_state.anim_frame}, anim_playing={st.session_state.anim_playing}, anim_fps={anim_fps}, anim_duration={anim_duration}")
        
        # Auto-advance animation - NO time.sleep() which blocks Streamlit Cloud
        if st.session_state.anim_playing:
            st.write(f"🎬 ANIM DEBUG: playing=True, frame={st.session_state.anim_frame}/{int(anim_duration * anim_fps)}")
            if st.session_state.anim_frame < int(anim_duration * anim_fps):
                st.session_state.anim_frame += 1
                st.write(f"🎬 ANIM DEBUG: Incremented frame to {st.session_state.anim_frame}, calling rerun...")
                st.rerun()  # Immediate rerun - NO time.sleep()
            else:
                st.session_state.anim_playing = False
                st.write("🎬 ANIM DEBUG: Reached end, stopping")
                st.rerun()
        
        # Current time for plotting
        current_time = st.session_state.anim_frame / anim_fps
        st.write(f"🎬 ANIM DEBUG: plotting time={current_time:.2f}s, frame={st.session_state.anim_frame}, playing={st.session_state.anim_playing}")
        
        fig_waves = plot_wave_propagation_2d(event, fm, current_time)
        st.plotly_chart(fig_waves, width='stretch')
        
        # Mapa de ubicación
        st.markdown("### 🗺️ Mapa de Ubicación")
        
        try:
            import folium
            from streamlit_folium import st_folium
            
            m = folium.Map(
                location=[event['latitude'], event['longitude']],
                zoom_start=6,
                tiles='OpenStreetMap'
            )
            
            # Epicentro
            folium.Marker(
                [event['latitude'], event['longitude']],
                popup=f"M{event['magnitude']:.1f} - {event['place']}",
                icon=folium.Icon(color='red', icon='star')
            ).add_to(m)
            
            # Círculo de radio
            folium.Circle(
                [event['latitude'], event['longitude']],
                radius=radius * 1000,
                color='blue', fill=True, fill_opacity=0.1
            ).add_to(m)
            
            st_folium(m, width=700, height=400)
        except ImportError:
            st.info("Instala `folium` y `streamlit-folium` para ver el mapa interactivo")
            # Mapa estático con Plotly
            fig_map = go.Figure(go.Scattermap(
                lat=[event['latitude']], lon=[event['longitude']],
                mode='markers', marker=dict(size=20, color='red'),
                text=[f"M{event['magnitude']:.1f} - {event['place']}"]
            ))
            fig_map.update_layout(
                mapbox_style="open-street-map",
                mapbox=dict(center=dict(lat=event['latitude'], lon=event['longitude']), zoom=5),
                height=400, margin=dict(l=0, r=0, t=0, b=0)
            )
            st.plotly_chart(fig_map, width='stretch')
        
        # Exportar datos
        st.divider()
        st.markdown("### 💾 Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📥 Descargar Evento (JSON)"):
                event_json = event.to_json()
                st.download_button(
                    "Descargar",
                    event_json,
                    f"{event['id']}_event.json",
                    "application/json"
                )
        with col2:
            if fm and st.button("📥 Descargar Mecanismo Focal (JSON)"):
                fm_json = json.dumps(fm, indent=2)
                st.download_button(
                    "Descargar",
                    fm_json,
                    f"{event['id']}_focal_mechanism.json",
                    "application/json"
                )
        with col3:
            if st.button("📥 Descargar Parámetros Animación"):
                params = {
                    'event': event.to_dict(),
                    'focal_mechanism': fm,
                    'animation': {
                        'duration': anim_duration,
                        'fps': anim_fps,
                        'fault_length': length,
                        'fault_width': width
                    }
                }
                params_json = json.dumps(params, indent=2, default=str)
                st.download_button(
                    "Descargar",
                    params_json,
                    f"{event['id']}_animation_params.json",
                    "application/json"
                )

    # Footer
    st.divider()
    st.markdown("""
    <div style="text-align:center; color:#666; padding:1rem;">
        <p>🌍 <strong>Análisis Sismológico 3D</strong> - Basado en USGS ComCat API, ObsPy y Plotly</p>
        <p>Desarrollado para investigación y educación sismológica</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()