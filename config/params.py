"""
Configuración centralizada de parámetros para el proyecto sismológico 3D.
Modifica estos parámetros para futuras búsquedas sismológicas.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class USGSConfig:
    """Configuración para el cliente USGS."""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_cache: bool = True
    cache_ttl: int = 300  # 5 minutos
    user_agent: str = "Seismo3D/1.0"


@dataclass
class SearchParams:
    """
    Parámetros configurables para la búsqueda sismológica.
    Modifica estos valores para futuras búsquedas.
    """
    # === PARÁMETROS DE UBICACIÓN ===
    # Opción A: Coordenadas directas (lat, lon)
    latitude: float = -33.45      # Latitud del epicentro (ej: Santiago, Chile: -33.45)
    longitude: float = -70.65     # Longitud del epicentro (ej: Santiago, Chile: -70.65)
    
    # Opción B: Lugar por nombre (se geocodifica automáticamente si lat/lon = 0)
    # location_name: str = "Santiago, Chile"
    
    # Radio de búsqueda en kilómetros
    radius_km: float = 500.0
    
    # === PARÁMETROS TEMPORALES ===
    # Formato: YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS
    start_time: str = "2024-01-01"
    end_time: str = "2024-12-31"
    
    # === PARÁMETROS DE MAGNITUD ===
    min_magnitude: float = 5.0    # Magnitud mínima (Mw)
    max_magnitude: Optional[float] = None  # None = sin límite superior
    
    # === PARÁMETROS DE ESTACIONES FDSN ===
    # Cliente FDSN a usar (IRIS, IRISPH5, IRISDMC, ORFEUS, BGR, etc.)
    fdsn_client: str = "IRIS"
    
    # Número de estaciones más cercanas a descargar
    n_stations: int = 3
    
    # Componentes a descargar (Z, N, E = Vertical, Norte, Este)
    components: tuple = ("BHZ", "BHN", "BHE")  # Banda ancha
    # components: tuple = ("HHZ", "HHN", "HHE")  # Alta ganancia (opcional)
    
    # Filtro de banda pasabanda (Hz)
    filter_freqmin: float = 0.05   # Frecuencia mínima (Hz)
    filter_freqmax: float = 2.0    # Frecuencia máxima (Hz)
    
    # Ventana de tiempo relativa al origen del evento (segundos)
    starttime_offset: float = -60   # Segundos antes del origen
    endtime_offset: float = 300     # Segundos después del origen
    
    # === PARÁMETROS DE ANIMACIÓN 3D ===
    # Duración de la animación (segundos)
    animation_duration: float = 60.0
    
    # FPS de la animación
    fps: int = 30
    
    # Resolución de la malla 3D para ondas
    grid_resolution: int = 50
    
    # Radio de propagación de ondas para animación (km)
    wave_propagation_radius_km: float = 300.0
    
    # Factor de escala para amplificación visual de desplazamientos
    displacement_scale: float = 10000.0
    
    # === PARÁMETROS DE SALIDA ===
    # Directorio de salida
    output_dir: str = "output"
    
    # Formato de video: 'mp4', 'gif', 'html'
    output_format: str = "mp4"
    
    # Nombre base del archivo de salida
    output_filename: str = "seismic_3d_animation"
    
    # Guardar frames individuales (para debugging)
    save_frames: bool = False
    
    # === CONFIGURACIÓN DE CLIENTES FDSN ===
    FDSN_CLIENTS = {
        "IRIS": "IRIS",
        "IRISPH5": "IRISPH5", 
        "IRISDMC": "IRISDMC",
        "ORFEUS": "ORFEUS",
        "BGR": "BGR",
        "ETH": "ETH",
        "KOERI": "KOERI",
        "KNMI": "KNMI",
        "LMU": "LMU",
        "NIEP": "NIEP",
        "NOA": "NOA",
        "ODC": "ODC",
        "RASPISHAKE": "RASPISHAKE",
        "RESIF": "RESIF",
        "SCEDC": "SCEDC",
        "TEXNET": "TEXNET",
        "UIB": "UIB",
    }
    
    # === PARÁMETROS DE FILTRO INSTRUMENTAL ===
    # Respuesta instrumental a remover (respuesta de instrumento)
    remove_instrument_response: bool = True
    output_units: str = "VEL"  # "VEL", "DISP", "ACC"
    
    # Pre-filtro para remoción de respuesta instrumental
    pre_filt: tuple = (0.005, 0.01, 10.0, 20.0)  # (f1, f2, f3, f4) en Hz
    
    # === CONFIGURACIÓN DE ANIMACIÓN 3D ===
    # Colores para ondas
    p_wave_color: str = "red"
    s_wave_color: str = "blue"
    rayleigh_color: str = "green"
    love_color: str = "orange"
    fault_color: str = "brown"
    station_color: str = "black"
    
    # Tamaños
    station_marker_size: float = 15.0
    fault_plane_opacity: float = 0.6
    wave_opacity: float = 0.7
    
    # Configuración de cámara
    camera_distance: float = 500.0
    camera_elevation: float = 30.0
    camera_azimuth: float = 45.0


# === PRESETS PARA PRUEBAS RÁPIDAS ===
# Descomenta uno de estos presets para pruebas rápidas

# PRESET 1: Terremoto de Chile 2024 (ejemplo del usuario)
CHILE_2024 = SearchParams(
    latitude=-33.45,
    longitude=-70.65,
    radius_km=500.0,
    start_time="2024-01-01",
    end_time="2024-12-31",
    min_magnitude=5.0,
    output_filename="chile_2024_seismic_3d"
)

# PRESET 2: Terremoto de Turquía-Siria 2023 (Mw 7.8)
TURKEY_2023 = SearchParams(
    latitude=37.17,
    longitude=37.03,
    radius_km=500.0,
    start_time="2023-02-01",
    end_time="2023-02-28",
    min_magnitude=7.0,
    output_filename="turkey_2023_m78_seismic_3d"
)

# PRESET 3: Terremoto de Japón 2024 (Noto, Mw 7.6)
JAPAN_2024 = SearchParams(
    latitude=37.5,
    longitude=137.2,
    radius_km=300.0,
    start_time="2024-01-01",
    end_time="2024-01-31",
    min_magnitude=7.0,
    output_filename="japan_2024_noto_seismic_3d"
)

# PRESET 4: Terremoto de México 2017 (Mw 7.1)
MEXICO_2017 = SearchParams(
    latitude=18.41,
    longitude=-98.71,
    radius_km=400.0,
    start_time="2017-09-19",
    end_time="2017-09-19",
    min_magnitude=7.0,
    output_filename="mexico_2017_seismic_3d"
)

# PRESET 5: Configuración personalizada del usuario (MODIFICA ESTOS VALORES)
CUSTOM = SearchParams(
    # === MODIFICA ESTOS PARÁMETROS PARA TU BÚSQUEDA ===
    latitude=-33.45,      # ← TU LATITUD AQUÍ
    longitude=-70.65,     # ← TU LONGITUD AQUÍ
    radius_km=500.0,      # ← TU RADIO EN KM AQUÍ
    start_time="2024-01-01",   # ← TU FECHA INICIO AQUÍ (YYYY-MM-DD)
    end_time="2024-12-31",     # ← TU FECHA FIN AQUÍ (YYYY-MM-DD)
    min_magnitude=5.0,    # ← TU MAGNITUD MÍNIMA AQUÍ
    # ================================================
    output_filename="custom_seismic_3d"
)


# Configuración por defecto (usa CUSTOM para tus parámetros)
DEFAULT_PARAMS = CUSTOM


def get_params(preset: str = "CUSTOM") -> SearchParams:
    """
    Obtiene parámetros predefinidos o personalizados.
    
    Args:
        preset: Uno de "CUSTOM", "CHILE_2024", "TURKEY_2023", "JAPAN_2024", "MEXICO_2017"
    
    Returns:
        SearchParams configurado
    """
    presets = {
        "CUSTOM": CUSTOM,
        "CHILE_2024": CHILE_2024,
        "TURKEY_2023": TURKEY_2023,
        "JAPAN_2024": JAPAN_2024,
        "MEXICO_2017": MEXICO_2017,
    }
    return presets.get(preset.upper(), CUSTOM)


def validate_params(params: SearchParams) -> bool:
    """Valida que los parámetros sean coherentes."""
    errors = []
    
    if not (-90 <= params.latitude <= 90):
        errors.append(f"Latitud inválida: {params.latitude} (debe ser -90 a 90)")
    
    if not (-180 <= params.longitude <= 180):
        errors.append(f"Longitud inválida: {params.longitude} (debe ser -180 a 180)")
    
    if params.radius_km <= 0:
        errors.append(f"Radio inválido: {params.radius_km} (debe ser > 0)")
    
    if params.min_magnitude < 0:
        errors.append(f"Magnitud mínima inválida: {params.min_magnitude}")
    
    if params.max_magnitude and params.max_magnitude < params.min_magnitude:
        errors.append("Magnitud máxima debe ser >= magnitud mínima")
    
    try:
        datetime.fromisoformat(params.start_time.replace('Z', '+00:00'))
        datetime.fromisoformat(params.end_time.replace('Z', '+00:00'))
    except ValueError:
        errors.append("Formato de fecha inválido. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS")
    
    if params.start_time >= params.end_time:
        errors.append("Fecha de inicio debe ser anterior a fecha de fin")
    
    if params.n_stations <= 0:
        errors.append("Número de estaciones debe ser > 0")
    
    if params.filter_freqmin >= params.filter_freqmax:
        errors.append("Frecuencia mínima debe ser < frecuencia máxima")
    
    if params.animation_duration <= 0:
        errors.append("Duración de animación debe ser > 0")
    
    if params.fps <= 0:
        errors.append("FPS debe ser > 0")
    
    if errors:
        raise ValueError("Errores de validación:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True


if __name__ == "__main__":
    # Test de validación
    params = DEFAULT_PARAMS
    print("=== Parámetros de configuración ===")
    print(f"Ubicación: {params.latitude}, {params.longitude}")
    print(f"Radio: {params.radius_km} km")
    print(f"Periodo: {params.start_time} a {params.end_time}")
    print(f"Magnitud mínima: {params.min_magnitude}")
    print(f"Estaciones: {params.n_stations}")
    print(f"Componentes: {params.components}")
    print(f"Filtro: {params.filter_freqmin}-{params.filter_freqmax} Hz")
    print(f"Animación: {params.animation_duration}s a {params.fps} FPS")
    print(f"Salida: {params.output_dir}/{params.output_filename}.{params.output_format}")
    
    try:
        validate_params(params)
        print("\n✓ Parámetros válidos")
    except ValueError as e:
        print(f"\n✗ {e}")