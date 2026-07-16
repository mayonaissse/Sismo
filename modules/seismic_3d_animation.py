"""
Módulo 3: Generación de Animación 3D Sismológica
==================================================
Renderiza animaciones 3D mostrando:
1. Fuente: Plano de falla y cinemática de ruptura (mecanismo focal)
2. Ondas de cuerpo: Propagación 3D de ondas P (compresión) y S (cizalle)
3. Ondas de superficie: Efecto en terreno (Rayleigh elípticas, Love serpenteantes)
   usando datos reales de sismogramas (Z, N, E)

Bibliotecas soportadas: PyVista (principal), Plotly, Matplotlib
"""

from __future__ import annotations

import numpy as np
import warnings
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any, Union
from pathlib import Path
from datetime import datetime
import json

# Visualización 3D - PyVista (principal)
try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False
    pv = None

# Plotly (opcional)
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None

# Matplotlib (opcional)
try:
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from mpl_toolkits.mplot3d import Axes3D
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    FuncAnimation = None
    Axes3D = None

# Procesamiento de señales
try:
    from scipy import signal
    from scipy.interpolate import interp1d
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    signal = None
    interp1d = None

# Configuración
from config.params import SearchParams, DEFAULT_PARAMS

# Suprimir warnings
warnings.filterwarnings("ignore", category=UserWarning)


# ============================================================
# ESTRUCTURAS DE DATOS PARA ANIMACIÓN
# ============================================================

@dataclass
class FaultPlane:
    """Representación geométrica del plano de falla."""
    strike: float       # Rumbo (grados, desde Norte hacia Este)
    dip: float          # Buzamiento (grados, 0-90)
    rake: float         # Deslizamiento (grados, -180 a 180)
    length: float       # Longitud de falla (km)
    width: float        # Ancho de falla (km)
    centroid_lat: float
    centroid_lon: float
    centroid_depth: float  # km
    
    # Vectores calculados
    normal: np.ndarray = field(init=False)      # Normal al plano (ENU)
    slip: np.ndarray = field(init=False)        # Vector deslizamiento (ENU)
    strike_vec: np.ndarray = field(init=False)  # Vector rumbo (ENU)
    dip_vec: np.ndarray = field(init=False)     # Vector buzamiento (ENU)
    
    # Malla para visualización
    mesh: Any = field(init=False, default=None)
    vertices: np.ndarray = field(init=False, default=None)
    faces: np.ndarray = field(init=False, default=None)
    
    def __post_init__(self):
        self._calculate_vectors()
        self._create_mesh()
    
    def _calculate_vectors(self):
        """Calcula vectores del plano de falla en coordenadas ENU."""
        import math
        
        strike_rad = np.radians(self.strike)
        dip_rad = np.radians(self.dip)
        rake_rad = np.radians(self.rake)
        
        # Vector normal al plano (apunta al bloque colgante)
        self.normal = np.array([
            -np.sin(dip_rad) * np.sin(strike_rad),  # Este
            np.sin(dip_rad) * np.cos(strike_rad),   # Norte
            -np.cos(dip_rad)                        # Up (negativo = hacia abajo)
        ])
        
        # Vector de rumbo (horizontal, perpendicular a strike)
        self.strike_vec = np.array([
            np.cos(strike_rad),   # Este
            np.sin(strike_rad),   # Norte
            0.0                   # Up
        ])
        
        # Vector de buzamiento (en el plano, hacia abajo)
        self.dip_vec = np.array([
            -np.cos(dip_rad) * np.sin(strike_rad),  # Este
            np.cos(dip_rad) * np.cos(strike_rad),   # Norte
            -np.sin(dip_rad)                        # Up
        ])
        
        # Vector de deslizamiento (rake medido desde strike_vec hacia dip_vec)
        self.slip = (np.cos(rake_rad) * self.strike_vec + 
                     np.sin(rake_rad) * self.dip_vec)
        
        # Normalizar
        self.normal = self.normal / np.linalg.norm(self.normal)
        self.slip = self.slip / np.linalg.norm(self.slip)
        self.strike_vec = self.strike_vec / np.linalg.norm(self.strike_vec)
        self.dip_vec = self.dip_vec / np.linalg.norm(self.dip_vec)
    
    def _create_mesh(self):
        """Crea malla rectangular del plano de falla."""
        # Centro en (0,0,0) local, luego se transforma
        half_len = self.length / 2
        half_wid = self.width / 2
        
        # Vértices locales (en coordenadas del plano: strike, dip, normal)
        local_vertices = np.array([
            [-half_len, -half_wid, 0],  # 0
            [ half_len, -half_wid, 0],  # 1
            [ half_len,  half_wid, 0],  # 2
            [-half_len,  half_wid, 0],  # 3
        ])
        
        # Transformar a ENU
        # Base local: strike_vec (x), dip_vec (y), normal (z)
        R = np.column_stack([self.strike_vec, self.dip_vec, self.normal])
        
        self.vertices = local_vertices @ R.T
        
        # Caras (dos triángulos)
        self.faces = np.array([
            [3, 0, 1, 2],  # 3 vértices: 0,1,2
            [3, 0, 2, 3],  # 3 vértices: 0,2,3
        ])
        
        if PYVISTA_AVAILABLE:
            self.mesh = pv.PolyData(self.vertices, self.faces)
    
    def get_centroid_enu(self) -> np.ndarray:
        """Centroide en ENU relativo al epicentro (aproximado)."""
        # El hipocentro está en el plano, típicamente en el centro o en un extremo
        # Para simplificar: centroide en el plano
        return np.array([0.0, 0.0, -self.centroid_depth])  # Profundidad negativa = abajo
    
    def get_rupture_front(self, time: float, rupture_velocity: float = 3.0) -> np.ndarray:
        """
        Calcula el frente de ruptura en el plano a un tiempo dado.
        
        Args:
            time: Tiempo desde origen (s)
            rupture_velocity: Velocidad de ruptura (km/s), típica 2.5-3.5 km/s
            
        Returns:
            Distancia de ruptura desde hipocentro a lo largo del strike
        """
        return rupture_velocity * time  # km


@dataclass
class Wavefield3D:
    """Campo de ondas 3D para animación."""
    # Configuración de malla
    radius_km: float = 300.0
    resolution: int = 50
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # ENU (epicentro)
    
    # Malla 3D
    grid: Any = field(init=False, default=None)
    points: np.ndarray = field(init=False, default=None)
    
    # Campos de ondas
    p_wave_amplitude: np.ndarray = field(init=False, default=None)  # Compresional
    s_wave_amplitude: np.ndarray = field(init=False, default=None)  # Cisalla
    rayleigh_amplitude: np.ndarray = field(init=False, default=None)  # Superficie
    love_amplitude: np.ndarray = field(init=False, default=None)
    
    # Velocidades de onda (km/s)
    vp: float = 6.0   # Onda P
    vs: float = 3.5   # Onda S
    vr: float = 3.0   # Rayleigh (~0.92*Vs)
    vl: float = 3.2   # Love
    
    # Parámetros de fuente
    source_depth: float = 10.0
    dominant_freq: float = 1.0  # Hz
    
    def __post_init__(self):
        self._create_grid()
    
    def _create_grid(self):
        """Crea malla 3D regular."""
        # Malla esférica o cartesiana
        x = np.linspace(-self.radius_km, self.radius_km, self.resolution)
        y = np.linspace(-self.radius_km, self.radius_km, self.resolution)
        z = np.linspace(-self.radius_km, self.radius_km, self.resolution)
        
        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
        self.points = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
        
        # Distancia al centro (epicentro en superficie, z=0)
        cx, cy, cz = self.center
        self.points[:, 0] -= cx
        self.points[:, 1] -= cy
        self.points[:, 2] -= cz
        
        self.r = np.linalg.norm(self.points, axis=1)
        
        # Máscara para puntos dentro del radio
        self.mask = self.r <= self.radius_km
        self.valid_points = self.points[self.mask]
        self.valid_r = self.r[self.mask]
        
        if PYVISTA_AVAILABLE:
            self.grid = pv.ImageData()
            self.grid.dimensions = (self.resolution, self.resolution, self.resolution)
            self.grid.origin = (-self.radius_km, -self.radius_km, -self.radius_km)
            self.grid.spacing = (2*self.radius_km/self.resolution,)*3
    
    def update_wavefield(self, time: float, fault: FaultPlane):
        """
        Actualiza campos de ondas para tiempo dado.
        
        Args:
            time: Tiempo desde origen (s)
            fault: Plano de falla con mecanismo focal
        """
        # Usar todos los puntos de la malla completa
        points = self.points
        r_dist = self.r
        
        # Ángulos para directividad
        # Vector desde fuente a punto
        source_pos = np.array([0.0, 0.0, -self.source_depth])
        r_vec = points - source_pos
        r_dist = np.linalg.norm(r_vec, axis=1)
        r_unit = r_vec / (r_dist[:, None] + 1e-10)
        
        # === ONDA P (Compresional) ===
        # Esférica, polarización radial
        tp = r_dist / self.vp - time
        # Función de onda: pulso de Ricker
        f = self.dominant_freq
        p_wave = self._ricker_wavelet(tp, f) * (1.0 / (r_dist + 1))
        
        # Amplitud radial (array completo)
        self.p_wave_amplitude = p_wave
        
        # === ONDA S (Cisalla) ===
        # Dos polarizaciones: SV (vertical) y SH (horizontal)
        ts = r_dist / self.vs - time
        s_wave = self._ricker_wavelet(ts, f) * (1.0 / (r_dist + 1))
        
        # Proyectar deslizamiento en direcciones de polarización S
        # SV: en plano radial-vertical
        # SH: perpendicular al plano radial (azimutal)
        self.s_wave_amplitude = s_wave
        
        # === ONDAS DE SUPERFICIE (aproximación) ===
        # Solo cerca de la superficie (z ≈ 0)
        surface_mask = (np.abs(points[:, 2]) < 5.0)  # 5 km de profundidad
        h_dist = np.sqrt(points[:, 0]**2 + points[:, 1]**2)  # Distancia horizontal
        
        # Rayleigh: movimiento elíptico retrogrado (vertical-radial)
        tr = h_dist / self.vr - time
        rayleigh = self._ricker_wavelet(tr, f * 0.5) * (1.0 / np.sqrt(h_dist + 1))
        self.rayleigh_amplitude = np.zeros_like(r_dist)
        self.rayleigh_amplitude[surface_mask] = rayleigh[surface_mask]
        
        # Love: movimiento horizontal transverso (SH)
        tl = h_dist / self.vl - time
        love = self._ricker_wavelet(tl, f * 0.5) * (1.0 / np.sqrt(h_dist + 1))
        self.love_amplitude = np.zeros_like(r_dist)
        self.love_amplitude[surface_mask] = love[surface_mask]
    
    def _ricker_wavelet(self, t: np.ndarray, f: float) -> np.ndarray:
        """Wavelet de Ricker (segunda derivada de gaussiana)."""
        # f = frecuencia dominante (Hz)
        a = np.pi * f
        return (1 - 2 * a**2 * t**2) * np.exp(-a**2 * t**2)
    
    def get_displacement_vectors(self, time: float, fault: FaultPlane, 
                                  scale: float = 10000.0) -> Dict[str, np.ndarray]:
        """
        Calcula vectores de desplazamiento para visualización.
        
        Returns:
            Dict con claves: 'P_radial', 'S_SV', 'S_SH', 'Rayleigh', 'Love'
            Cada uno es array (N, 3) de desplazamientos en ENU
        """
        points = self.points[self.mask]
        r = self.r[self.mask]
        
        # Vector radial unitario
        r_vec = points - np.array([0.0, 0.0, -self.source_depth])
        r_dist = np.linalg.norm(r_vec, axis=1)
        r_unit = r_vec / (r_dist[:, None] + 1e-10)
        
        # Vector vertical
        z_unit = np.array([0.0, 0.0, 1.0])
        
        # Vector transversal (azimutal)
        t_unit = np.cross(z_unit, r_unit)
        t_norm = np.linalg.norm(t_unit, axis=1)
        t_unit = t_unit / (t_norm[:, None] + 1e-10)
        
        # Vector SV (en plano radial-vertical, perpendicular a radial)
        sv_unit = np.cross(t_unit, r_unit)
        
        results = {}
        
        # P-wave: desplazamiento radial
        p_amp = self.p_wave_amplitude[self.mask]
        results['P_radial'] = p_amp[:, None] * r_unit * scale
        
        # S-wave: SV (vertical-radial) + SH (transversal)
        s_amp = self.s_wave_amplitude[self.mask]
        results['S_SV'] = s_amp[:, None] * sv_unit * scale
        results['S_SH'] = s_amp[:, None] * t_unit * scale
        
        # Surface waves (solo superficie)
        surf_mask = np.abs(points[:, 2]) < 5.0
        
        # Rayleigh: elíptico retrogrado (vertical + radial)
        r_amp = self.rayleigh_amplitude[self.mask]
        # Componente vertical (arriba) y radial (hacia afuera)
        # Retrógrado: vertical y radial en oposición de fase
        ray_vert = r_amp * np.cos(2 * np.pi * self.dominant_freq * 0.5 * time)  # fase
        ray_rad = -r_amp * np.sin(2 * np.pi * self.dominant_freq * 0.5 * time)
        ray_disp = np.zeros((len(r_amp), 3))
        ray_disp[:, 2] = ray_vert  # Up
        ray_disp[:, 0] = ray_rad * r_unit[:, 0]  # Este
        ray_disp[:, 1] = ray_rad * r_unit[:, 1]  # Norte
        results['Rayleigh'] = ray_disp * scale
        
        # Love: horizontal transversal (SH puro)
        l_amp = self.love_amplitude[self.mask]
        love_disp = np.zeros((len(l_amp), 3))
        love_disp[:, 0] = l_amp * t_unit[:, 0] * scale
        love_disp[:, 1] = l_amp * t_unit[:, 1] * scale
        results['Love'] = love_disp
        
        return results


@dataclass
class StationVisualization:
    """Visualización de estación con sismogramas reales."""
    station_info: Any  # StationInfo from fdsn_waveforms
    waveforms: Any     # WaveformData from fdsn_waveforms
    position_enu: np.ndarray = field(init=False)  # (E, N, U) relativo a epicentro
    
    def __post_init__(self):
        # Convertir lat/lon a ENU relativo al epicentro
        # Aproximación local: 1° ≈ 111 km
        self.position_enu = np.array([
            (self.station_info.longitude) * 111.0 * np.cos(np.radians(self.station_info.latitude)),  # E
            (self.station_info.latitude) * 111.0,  # N (simplificado)
            self.station_info.elevation / 1000.0   # U en km
        ])
    
    def get_seismogram_data(self, comp: str = 'Z', max_points: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """Obtiene datos de sismograma para visualización."""
        tr = self.waveforms.get_component(comp)
        if tr is None:
            return np.array([]), np.array([])
        
        t = tr.times()
        d = tr.data
        
        # Submuestrear si es muy largo
        if len(t) > max_points:
            idx = np.linspace(0, len(t)-1, max_points, dtype=int)
            t = t[idx]
            d = d[idx]
        
        return t, d


# ============================================================
# RENDERIZADOR PRINCIPAL (PyVista)
# ============================================================

class Seismic3DRenderer:
    """
    Renderizador 3D principal usando PyVista.
    Genera animaciones de propagación de ondas sísmicas.
    """
    
    def __init__(self, 
                 params: SearchParams = None,
                 offscreen: bool = True):
        """
        Inicializa renderizador.
        
        Args:
            params: Parámetros de configuración
            offscreen: Renderizado sin pantalla (para servidores/headless)
        """
        if not PYVISTA_AVAILABLE:
            raise ImportError("PyVista no está instalado. Instala con: pip install pyvista")
        
        self.params = params or DEFAULT_PARAMS
        self.offscreen = offscreen
        
        # Configurar tema PyVista
        pv.set_plot_theme("document")
        pv.global_theme.background = "white"
        pv.global_theme.window_size = [1920, 1080]
        
        self.plotter = None
        self.fault = None
        self.wavefield = None
        self.stations_vis = []
        
        # Estado de animación
        self.current_time = 0.0
        self.frame = 0
        self.total_frames = 0
        
        print(f"Seismic3DRenderer inicializado (offscreen={offscreen})")
    
    def setup_scene(self, 
                    event_data: Dict,
                    fault: FaultPlane,
                    event_waveforms: Any = None):
        """
        Configura la escena 3D completa.
        
        Args:
            event_data: Dict con info del evento (lat, lon, depth, mag, time)
            fault: FaultPlane con mecanismo focal
            event_waveforms: EventWaveforms con datos de estaciones (opcional)
        """
        self.fault = fault
        
        # Crear wavefield
        self.wavefield = Wavefield3D(
            radius_km=self.params.wave_propagation_radius_km,
            resolution=self.params.grid_resolution,
            source_depth=event_data.get('depth', 10.0),
            dominant_freq=1.0 / max(0.1, self.params.filter_freqmax)  # aproximación
        )
        
        # Configurar plotter
        self.plotter = pv.Plotter(
            off_screen=self.offscreen,
            window_size=[1920, 1080]
        )
        
        # 1. Agregar plano de falla
        self._add_fault_plane()
        
        # 2. Agregar malla de ondas (volumétrica)
        self._add_wavefield_volume()
        
        # 3. Agregar estaciones si hay datos
        if event_waveforms and event_waveforms.stations:
            self._add_stations(event_waveforms)
        
        # 4. Agregar epicentro e hipocentro
        self._add_source_markers(event_data)
        
        # 5. Configurar cámara
        self._setup_camera()
        
        # 6. Agregar ejes y escala
        self._add_axes_and_scale()
        
        # Calcular frames totales
        self.total_frames = int(self.params.animation_duration * self.params.fps)
        print(f"Escena configurada: {self.total_frames} frames a {self.params.fps} FPS")
    
    def _add_fault_plane(self):
        """Agrega malla del plano de falla."""
        if self.fault.mesh:
            # Posicionar en profundidad correcta
            mesh = self.fault.mesh.copy()
            centroid = self.fault.get_centroid_enu()
            mesh.translate(centroid, inplace=True)
            
            self.plotter.add_mesh(
                mesh,
                color=self.params.fault_color,
                opacity=self.params.fault_plane_opacity,
                show_edges=True,
                edge_color='black',
                line_width=2,
                name='fault_plane'
            )
            
            # Agregar vectores de falla (flechas)
            self._add_fault_vectors(centroid)
    
    def _add_fault_vectors(self, centroid: np.ndarray):
        """Agrega flechas mostrando strike, dip, slip, normal."""
        scale = self.fault.length * 0.3
        
        vectors = {
            'Strike': (self.fault.strike_vec, 'blue'),
            'Dip': (self.fault.dip_vec, 'green'),
            'Slip': (self.fault.slip, 'red'),
            'Normal': (self.fault.normal, 'purple')
        }
        
        for name, (vec, color) in vectors.items():
            arrow = pv.Arrow(
                start=centroid,
                direction=vec,
                scale=scale,
                tip_length=0.2,
                tip_radius=0.1,
                shaft_radius=0.05
            )
            self.plotter.add_mesh(
                arrow, color=color, opacity=0.8, name=f'fault_{name.lower()}'
            )
    
    def _add_wavefield_volume(self):
        """Agrega visualización volumétrica del campo de ondas."""
        # Inicializar con datos vacíos
        if self.wavefield.grid:
            # Agregar como volumen con isosuperficies
            self.plotter.add_volume(
                self.wavefield.grid,
                scalars='p_wave',
                opacity='sigmoid_5',
                cmap='Reds',
                name='p_wave_volume'
            )
    
    def _add_stations(self, event_waveforms: Any):
        """Agrega marcadores de estaciones con sismogramas."""
        for wf_data in event_waveforms.stations:
            sta = wf_data.station_info
            
            # Posición ENU (aproximada desde lat/lon)
            enu = np.array([
                sta.distance_km * np.sin(np.radians(sta.azimuth)),  # Este
                sta.distance_km * np.cos(np.radians(sta.azimuth)),  # Norte
                sta.elevation / 1000.0  # Up en km
            ])
            
            # Marcador de estación
            sphere = pv.Sphere(radius=2.0, center=enu)
            self.plotter.add_mesh(
                sphere, color=self.params.station_color,
                name=f'station_{sta.network}_{sta.station}'
            )
            
            # Etiqueta
            self.plotter.add_point_labels(
                [enu], [f"{sta.network}.{sta.station}"],
                font_size=10, text_color='black', name=f'label_{sta.station}'
            )
            
            # Guardar para animación
            self.stations_vis.append({
                'info': sta,
                'waveforms': wf_data,
                'position': enu,
                'sphere': sphere
            })
    
    def _add_source_markers(self, event_data: Dict):
        """Agrega marcadores de epicentro e hipocentro."""
        # Epicentro (superficie)
        epicenter = pv.Sphere(radius=3.0, center=(0, 0, 0))
        self.plotter.add_mesh(epicenter, color='yellow', name='epicenter')
        self.plotter.add_point_labels(
            [[0, 0, 2]], ['Epicentro'], font_size=12, text_color='black'
        )
        
        # Hipocentro (profundidad)
        depth = event_data.get('depth', 10.0)
        hypocenter = pv.Sphere(radius=3.0, center=(0, 0, -depth))
        self.plotter.add_mesh(hypocenter, color='red', name='hypocenter')
        self.plotter.add_point_labels(
            [[0, 0, -depth-2]], [f'Hipocentro ({depth} km)'], 
            font_size=12, text_color='black'
        )
    
    def _setup_camera(self):
        """Configura cámara para vista óptima."""
        self.plotter.camera_position = 'iso'
        self.plotter.camera.zoom(1.5)
        
        # Distancia y ángulos desde config
        self.plotter.camera.distance = self.params.camera_distance
        self.plotter.camera.elevation = self.params.camera_elevation
        self.plotter.camera.azimuth = self.params.camera_azimuth
    
    def _add_axes_and_scale(self):
        """Agrega ejes coordenados y barra de escala."""
        # Ejes
        self.plotter.add_axes(
            line_width=2,
            labels_off=False,
            xlabel='Este (km)',
            ylabel='Norte (km)',
            zlabel='Profundidad (km)'
        )
        
        # Barra de escala
        self.plotter.add_scale_bar(
            color='black', 
            label='km',
            position='lower_left'
        )
        
        # Título
        self.plotter.add_text(
            "Simulación 3D de Propagación de Ondas Sísmicas",
            position='upper_edge',
            font_size=16,
            color='black'
        )
    
    def animate_frame(self, frame: int) -> bool:
        """
        Actualiza escena para un frame de animación.
        
        Returns:
            True si continuar, False si terminar
        """
        self.frame = frame
        self.current_time = frame / self.params.fps
        
        # Actualizar wavefield
        self.wavefield.update_wavefield(self.current_time, self.fault)
        
        # Actualizar visualización volumétrica
        if self.wavefield.grid and hasattr(self.wavefield.grid, 'point_data'):
            # Actualizar escalares
            p_data = self.wavefield.p_wave_amplitude.reshape(
                self.wavefield.grid.dimensions, order='F'
            )
            self.wavefield.grid.point_data['p_wave'] = p_data.ravel(order='F')
            
            s_data = self.wavefield.s_wave_amplitude.reshape(
                self.wavefield.grid.dimensions, order='F'
            )
            self.wavefield.grid.point_data['s_wave'] = s_data.ravel(order='F')
        
        # Actualizar frentes de onda (isosuperficies)
        self._update_wavefronts()
        
        # Actualizar estaciones (sismogramas en tiempo real)
        self._update_station_seismograms()
        
        # Actualizar frente de ruptura en falla
        self._update_rupture_front()
        
        # Texto de tiempo
        self.plotter.add_text(
            f"Tiempo: {self.current_time:.1f} s",
            position='lower_right',
            font_size=14,
            color='black',
            name='time_text'
        )
        
        return frame < self.total_frames - 1
    
    def _update_wavefronts(self):
        """Actualiza isosuperficies de frentes de onda."""
        # Remover frentes anteriores
        for name in ['p_front', 's_front', 'rayleigh_front', 'love_front']:
            self.plotter.remove_actor(name, render=False)
        
        # Crear nuevas isosuperficies si hay datos
        if self.wavefield.p_wave_amplitude is not None:
            # P-wave front
            try:
                p_iso = self.wavefield.grid.contour(
                    [np.max(self.wavefield.p_wave_amplitude) * 0.5],
                    scalars='p_wave'
                )
                if p_iso.n_points > 0:
                    self.plotter.add_mesh(
                        p_iso, color=self.params.p_wave_color,
                        opacity=self.params.wave_opacity,
                        name='p_front'
                    )
            except Exception:
                pass
            
            # S-wave front
            try:
                s_iso = self.wavefield.grid.contour(
                    [np.max(self.wavefield.s_wave_amplitude) * 0.5],
                    scalars='s_wave'
                )
                if s_iso.n_points > 0:
                    self.plotter.add_mesh(
                        s_iso, color=self.params.s_wave_color,
                        opacity=self.params.wave_opacity,
                        name='s_front'
                    )
            except Exception:
                pass
    
    def _update_station_seismograms(self):
        """Actualiza visualización de sismogramas en estaciones."""
        # En una implementación completa, esto mostraría
        # el sismograma en una ventana separada o como textura
        pass
    
    def _update_rupture_front(self):
        """Actualiza frente de ruptura en el plano de falla."""
        rupture_dist = self.fault.get_rupture_front(self.current_time)
        
        # Visualizar como línea en el plano de falla
        if rupture_dist < self.fault.length / 2:
            # Crear línea de ruptura
            pts = np.array([
                [-rupture_dist, -self.fault.width/2, 0],
                [rupture_dist, -self.fault.width/2, 0],
                [rupture_dist, self.fault.width/2, 0],
                [-rupture_dist, self.fault.width/2, 0],
            ])
            
            R = np.column_stack([self.fault.strike_vec, self.fault.dip_vec, self.fault.normal])
            pts_enu = pts @ R.T + self.fault.get_centroid_enu()
            
            line = pv.lines_from_points(pts_enu)
            self.plotter.add_mesh(
                line, color='orange', line_width=5,
                name='rupture_front', render=False
            )
    
    def render_frame(self, output_path: str = None):
        """Renderiza frame actual."""
        if output_path:
            self.plotter.screenshot(output_path)
        else:
            self.plotter.render()
    
    def generate_animation(self, output_file: str = None):
        """
        Genera animación completa.
        
        Args:
            output_file: Ruta del archivo de salida (mp4, gif)
        """
        if output_file is None:
            output_file = f"{self.params.output_dir}/{self.params.output_filename}.{self.params.output_format}"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"Generando animación: {output_path}")
        print(f"  Duración: {self.params.animation_duration}s, FPS: {self.params.fps}")
        print(f"  Frames totales: {self.total_frames}")
        
        # Abrir movie
        self.plotter.open_movie(str(output_path), framerate=self.params.fps)
        
        try:
            for frame in range(self.total_frames):
                continue_anim = self.animate_frame(frame)
                self.plotter.write_frame()
                
                if frame % 30 == 0:
                    print(f"  Frame {frame}/{self.total_frames} ({frame/self.total_frames*100:.0f}%)")
                
                if not continue_anim:
                    break
        
        finally:
            self.plotter.close()
        
        print(f"Animación guardada: {output_path}")
        return output_path
    
    def generate_interactive_html(self, output_file: str = None):
        """Genera visualización interactiva HTML (requiere pyvista + panel/trame)."""
        if output_file is None:
            output_file = f"{self.params.output_dir}/{self.params.output_filename}.html"
        
        # PyVista puede exportar a HTML con plotter.export_html()
        # Requiere pyvista[trame] o panel
        try:
            self.plotter.export_html(output_file)
            print(f"HTML interactivo guardado: {output_file}")
        except Exception as e:
            print(f"No se pudo exportar HTML: {e}")
            print("Instala pyvista[trame] o panel para exportar HTML interactivo")
    
    def close(self):
        """Cierra el plotter."""
        if self.plotter:
            self.plotter.close()


# ============================================================
# RENDERIZADOR ALTERNATIVO: PLOTLY
# ============================================================

if PLOTLY_AVAILABLE:
    class PlotlySeismicRenderer:
        """Renderizador alternativo usando Plotly (web interactivo)."""
        
        def __init__(self, params: SearchParams = None):
            self.params = params or DEFAULT_PARAMS
            self.fig = None
        
        def create_fault_visualization(self, fault: FaultPlane, event_data: Dict) -> go.Figure:
            """Crea visualización 3D interactiva del plano de falla."""
            
            # Vértices del plano
            vertices = fault.vertices + fault.get_centroid_enu()
            
            fig = go.Figure()
            
            # Plano de falla
            fig.add_trace(go.Mesh3d(
                x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                i=[0, 0], j=[1, 2], k=[2, 3],
                color=self.params.fault_color,
                opacity=self.params.fault_plane_opacity,
                name='Plano de Falla',
                showscale=False
            ))
            
            # Vectores
            centroid = fault.get_centroid_enu()
            vectors = {
                'Strike': (fault.strike_vec, 'blue'),
                'Dip': (fault.dip_vec, 'green'),
                'Slip': (fault.slip, 'red'),
                'Normal': (fault.normal, 'purple')
            }
            
            for name, (vec, color) in vectors.items():
                end = centroid + vec * fault.length * 0.3
                fig.add_trace(go.Cone(
                    x=[centroid[0]], y=[centroid[1]], z=[centroid[2]],
                    u=[vec[0]], v=[vec[1]], w=[vec[2]],
                    sizemode="absolute", sizeref=2.0,
                    colorscale=[[0, color], [1, color]],
                    showscale=False,
                    name=name
                ))
            
            # Epicentro e hipocentro
            fig.add_trace(go.Scatter3d(
                x=[0], y=[0], z=[0],
                mode='markers+text',
                marker=dict(size=10, color='yellow'),
                text=['Epicentro'],
                name='Epicentro'
            ))
            
            depth = event_data.get('depth', 10)
            fig.add_trace(go.Scatter3d(
                x=[0], y=[0], z=[-depth],
                mode='markers+text',
                marker=dict(size=10, color='red'),
                text=[f'Hipocentro ({depth} km)'],
                name='Hipocentro'
            ))
            
            # Layout
            fig.update_layout(
                title="Mecanismo Focal 3D - Visualización Interactiva",
                scene=dict(
                    xaxis_title='Este (km)',
                    yaxis_title='Norte (km)',
                    zaxis_title='Profundidad (km)',
                    aspectmode='data',
                    camera=dict(
                        eye=dict(x=1.5, y=1.5, z=1.2)
                    )
                ),
                width=1000, height=800
            )
            
            self.fig = fig
            return fig
        
        def save_html(self, filepath: str):
            """Guarda como HTML interactivo."""
            if self.fig:
                self.fig.write_html(filepath)
                print(f"Guardado: {filepath}")

else:
    # Placeholder when Plotly not available
    class PlotlySeismicRenderer:
        def __init__(self, params=None):
            raise ImportError("Plotly no está instalado. Instala con: pip install plotly")


# ============================================================
# RENDERIZADOR ALTERNATIVO: MATPLOTLIB
# ============================================================

class MatplotlibSeismicRenderer:
    """Renderizador alternativo usando Matplotlib (animación simple)."""
    
    def __init__(self, params: SearchParams = None):
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("Matplotlib no está instalado. Instala con: pip install matplotlib")
        
        self.params = params or DEFAULT_PARAMS
        self.fig = None
        self.ax = None
    
    def create_static_fault_plot(self, fault: FaultPlane, event_data: Dict, 
                                  output_file: str = None):
        """Crea gráfico estático 3D del plano de falla."""
        
        self.fig = plt.figure(figsize=(12, 10))
        self.ax = self.fig.add_subplot(111, projection='3d')
        
        # Plano de falla
        vertices = fault.vertices + fault.get_centroid_enu()
        
        # Triángulos
        tri1 = vertices[[0, 1, 2]]
        tri2 = vertices[[0, 2, 3]]
        
        self.ax.plot_trisurf(
            vertices[:, 0], vertices[:, 1], vertices[:, 2],
            triangles=[[0, 1, 2], [0, 2, 3]],
            color=self.params.fault_color, alpha=self.params.fault_plane_opacity,
            edgecolor='black', linewidth=0.5
        )
        
        # Vectores
        centroid = fault.get_centroid_enu()
        scale = fault.length * 0.3
        
        vectors = [
            ('Strike', fault.strike_vec, 'blue'),
            ('Dip', fault.dip_vec, 'green'),
            ('Slip', fault.slip, 'red'),
            ('Normal', fault.normal, 'purple')
        ]
        
        for name, vec, color in vectors:
            end = centroid + vec * scale
            self.ax.quiver(
                centroid[0], centroid[1], centroid[2],
                vec[0]*scale, vec[1]*scale, vec[2]*scale,
                color=color, arrow_length_ratio=0.1, linewidth=2,
                label=name
            )
        
        # Epicentro e hipocentro
        self.ax.scatter([0], [0], [0], c='yellow', s=100, marker='*', label='Epicentro')
        depth = event_data.get('depth', 10)
        self.ax.scatter([0], [0], [-depth], c='red', s=100, marker='*', label=f'Hipocentro ({depth} km)')
        
        # Configuración
        self.ax.set_xlabel('Este (km)')
        self.ax.set_ylabel('Norte (km)')
        self.ax.set_zlabel('Profundidad (km)')
        self.ax.set_title(f"Mecanismo Focal: Strike={fault.strike:.0f}°, Dip={fault.dip:.0f}°, Rake={fault.rake:.0f}°")
        self.ax.legend()
        self.ax.invert_zaxis()  # Profundidad positiva hacia abajo
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"Gráfico guardado: {output_file}")
        
        return self.fig
    
    def create_wave_propagation_animation(self, wavefield: Wavefield3D, fault: FaultPlane,
                                           output_file: str = None):
        """Crea animación 2D de propagación de ondas (corte transversal)."""
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()
        
        # Corte transversal vertical (E-O)
        y_idx = wavefield.resolution // 2  # Norte = 0
        
        def update(frame):
            time = frame / self.params.fps
            wavefield.update_wavefield(time, fault)
            
            for ax in axes:
                ax.clear()
            
            # Datos del corte
            shape = (wavefield.resolution, wavefield.resolution)
            p_slice = wavefield.p_wave_amplitude.reshape(shape, order='F')[:, y_idx]
            s_slice = wavefield.s_wave_amplitude.reshape(shape, order='F')[:, y_idx]
            
            x = np.linspace(-wavefield.radius_km, wavefield.radius_km, wavefield.resolution)
            z = np.linspace(-wavefield.radius_km, wavefield.radius_km, wavefield.resolution)
            X, Z = np.meshgrid(x, z)
            
            # P-wave
            im1 = axes[0].pcolormesh(X, Z, p_slice.T, cmap='RdBu_r', shading='auto', vmin=-1, vmax=1)
            axes[0].set_title(f'Onda P (Compresional) - t={time:.1f}s')
            axes[0].set_xlabel('Este (km)'); axes[0].set_ylabel('Profundidad (km)')
            axes[0].invert_yaxis()
            plt.colorbar(im1, ax=axes[0])
            
            # S-wave
            im2 = axes[1].pcolormesh(X, Z, s_slice.T, cmap='RdBu_r', shading='auto', vmin=-1, vmax=1)
            axes[1].set_title(f'Onda S (Cizalle) - t={time:.1f}s')
            axes[1].set_xlabel('Este (km)'); axes[1].set_ylabel('Profundidad (km)')
            axes[1].invert_yaxis()
            plt.colorbar(im2, ax=axes[1])
            
            # Superficie (Rayleigh)
            surf_z_idx = wavefield.resolution // 2  # z=0
            r_slice = wavefield.rayleigh_amplitude.reshape(shape, order='F')[surf_z_idx, :]
            l_slice = wavefield.love_amplitude.reshape(shape, order='F')[surf_z_idx, :]
            
            axes[2].plot(x, r_slice, 'g-', label='Rayleigh', linewidth=2)
            axes[2].plot(x, l_slice, 'orange', label='Love', linewidth=2)
            axes[2].set_title(f'Ondas de Superficie (z=0) - t={time:.1f}s')
            axes[2].set_xlabel('Este (km)'); axes[2].set_ylabel('Amplitud')
            axes[2].legend(); axes[2].grid(True)
            
            # Falla
            axes[3].set_title(f'Plano de Falla: Strike={fault.strike:.0f}°, Dip={fault.dip:.0f}°, Rake={fault.rake:.0f}°')
            axes[3].axis('off')
            
            plt.tight_layout()
        
        anim = FuncAnimation(fig, update, frames=self.params.animation_duration * self.params.fps,
                            interval=1000/self.params.fps, blit=False)
        
        if output_file:
            anim.save(output_file, writer='ffmpeg', fps=self.params.fps)
            print(f"Animación guardada: {output_file}")
        
        return anim


# ============================================================
# FUNCIÓN PRINCIPAL DE CREACIÓN DE ANIMACIÓN
# ============================================================

def create_seismic_3d_animation(event_data: Dict,
                                 focal_mechanism: Dict,
                                 event_waveforms: Any = None,
                                 params: SearchParams = None,
                                 renderer_type: str = "pyvista",
                                 output_file: str = None) -> str:
    """
    Función principal para crear animación 3D sismológica.
    
    Args:
        event_data: Dict con lat, lon, depth, magnitude, time, id
        focal_mechanism: Dict con strike, dip, rake, magnitude (Mw)
        event_waveforms: EventWaveforms de fdsn_waveforms (opcional)
        params: SearchParams de configuración
        renderer_type: 'pyvista', 'plotly', 'matplotlib'
        output_file: Archivo de salida
        
    Returns:
        Ruta del archivo generado
    """
    params = params or DEFAULT_PARAMS
    
    # Crear plano de falla
    fault = FaultPlane(
        strike=focal_mechanism['strike'],
        dip=focal_mechanism['dip'],
        rake=focal_mechanism['rake'],
        length=estimate_fault_length(focal_mechanism.get('magnitude', event_data['magnitude'])),
        width=estimate_fault_width(focal_mechanism.get('magnitude', event_data['magnitude'])),
        centroid_lat=event_data['lat'],
        centroid_lon=event_data['lon'],
        centroid_depth=event_data['depth']
    )
    
    print(f"Plano de falla creado: Strike={fault.strike:.1f}, Dip={fault.dip:.1f}, Rake={fault.rake:.1f}")
    print(f"  Longitud: {fault.length:.1f} km, Ancho: {fault.width:.1f} km")
    print(f"  Vector deslizamiento: {fault.slip}")
    print(f"  Normal: {fault.normal}")
    
    if renderer_type == "pyvista":
        if not PYVISTA_AVAILABLE:
            raise ImportError("PyVista no disponible. Instala: pip install pyvista")
        
        renderer = Seismic3DRenderer(params, offscreen=True)
        renderer.setup_scene(event_data, fault, event_waveforms)
        
        if output_file is None:
            output_file = f"{params.output_dir}/{params.output_filename}.{params.output_format}"
        
        renderer.generate_animation(output_file)
        renderer.close()
        
    elif renderer_type == "plotly":
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly no disponible. Instala: pip install plotly")
        
        renderer = PlotlySeismicRenderer(params)
        fig = renderer.create_fault_visualization(fault, event_data)
        
        if output_file is None:
            output_file = f"{params.output_dir}/{params.output_filename}.html"
        
        renderer.save_html(output_file)
        
    elif renderer_type == "matplotlib":
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("Matplotlib no disponible. Instala: pip install matplotlib")
        
        renderer = MatplotlibSeismicRenderer(params)
        
        # Gráfico estático
        static_file = output_file or f"{params.output_dir}/{params.output_filename}_static.png"
        renderer.create_static_fault_plot(fault, event_data, static_file)
        
        # Animación 2D
        wavefield = Wavefield3D(
            radius_km=params.wave_propagation_radius_km,
            resolution=params.grid_resolution,
            source_depth=event_data['depth']
        )
        
        anim_file = output_file or f"{params.output_dir}/{params.output_filename}_2d.mp4"
        renderer.create_wave_propagation_animation(wavefield, fault, anim_file)
        
    else:
        raise ValueError(f"Renderer desconocido: {renderer_type}")
    
    return output_file


def estimate_fault_length(magnitude: float) -> float:
    """Estima longitud de falla (km) desde magnitud (Wells & Coppersmith 1994)."""
    # Log10(L) = -2.44 + 0.59*Mw (strike-slip)
    # Para todo tipo: Log10(L) = -3.22 + 0.69*Mw
    return 10 ** (-3.22 + 0.69 * magnitude)


def estimate_fault_width(magnitude: float) -> float:
    """Estima ancho de falla (km) desde magnitud."""
    # Log10(W) = -1.01 + 0.32*Mw
    return 10 ** (-1.01 + 0.32 * magnitude)


# ============================================================
# DEMO / TESTING
# ============================================================

if __name__ == "__main__":
    print("=== Seismic 3D Animation Demo ===\n")
    
    # Datos de prueba (evento ejemplo Chile)
    test_event = {
        'id': 'test_chile_2024',
        'time': '2024-01-15T12:34:56',
        'lat': -33.45,
        'lon': -70.65,
        'depth': 50.0,
        'magnitude': 6.5
    }
    
    test_focal = {
        'strike': 15.0,    # grados
        'dip': 25.0,       # grados
        'rake': 110.0,     # grados (reverse faulting)
        'magnitude': 6.5   # Mw
    }
    
    # Crear plano de falla
    fault = FaultPlane(
        strike=test_focal['strike'],
        dip=test_focal['dip'],
        rake=test_focal['rake'],
        length=estimate_fault_length(test_focal['magnitude']),
        width=estimate_fault_width(test_focal['magnitude']),
        centroid_lat=test_event['lat'],
        centroid_lon=test_event['lon'],
        centroid_depth=test_event['depth']
    )
    
    print(f"Plano de falla de prueba:")
    print(f"  Strike: {fault.strike:.1f}°, Dip: {fault.dip:.1f}°, Rake: {fault.rake:.1f}°")
    print(f"  Length: {fault.length:.1f} km, Width: {fault.width:.1f} km")
    print(f"  Normal: {fault.normal}")
    print(f"  Slip: {fault.slip}")
    print(f"  Strike vec: {fault.strike_vec}")
    print(f"  Dip vec: {fault.dip_vec}")
    
    # Test wavefield
    print("\nCreando wavefield...")
    wavefield = Wavefield3D(radius_km=200, resolution=30, source_depth=50)
    wavefield.update_wavefield(10.0, fault)
    print(f"  P-wave max amp: {np.max(wavefield.p_wave_amplitude):.4f}")
    print(f"  S-wave max amp: {np.max(wavefield.s_wave_amplitude):.4f}")
    print(f"  Rayleigh max: {np.max(wavefield.rayleigh_amplitude):.4f}")
    print(f"  Love max: {np.max(wavefield.love_amplitude):.4f}")
    
    # Test renderers
    print("\nProbando renderizadores disponibles:")
    print(f"  PyVista: {'✓' if PYVISTA_AVAILABLE else '✗'}")
    print(f"  Plotly: {'✓' if PLOTLY_AVAILABLE else '✗'}")
    print(f"  Matplotlib: {'✓' if MATPLOTLIB_AVAILABLE else '✗'}")
    print(f"  SciPy: {'✓' if SCIPY_AVAILABLE else '✗'}")
    
    if MATPLOTLIB_AVAILABLE:
        print("\nGenerando gráfico estático con Matplotlib...")
        renderer = MatplotlibSeismicRenderer()
        renderer.create_static_fault_plot(fault, test_event, 
                                          "/data/data/com.termux/files/home/seismo_3d/output/test_fault.png")
        print("Gráfico guardado en output/test_fault.png")
    
    print("\n=== Demo completado ===")