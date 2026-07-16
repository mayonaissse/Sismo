"""
Módulos de Análisis Sismológico 3D
===================================

Paquete principal con tres submódulos:

1. usgs_metadata - Extracción de metadatos desde USGS ComCat API
2. fdsn_waveforms - Descarga de formas de onda vía FDSN (ObsPy/IRIS) 
3. seismic_3d_animation - Generación de animaciones 3D sismológicas
"""

__version__ = "1.0.0"
__author__ = "Seismic 3D Analysis Team"

# Exports principales - USGS (siempre disponible)
from .usgs_metadata import (
    USGSMetadataExtractor,
    EarthquakeEvent,
    FocalMechanism,
    quick_search,
    get_latest_large_event,
)

from config.params import SearchParams

# FDSN - intentar importar (ObsPy opcional)
try:
    from .fdsn_waveforms import (
        WaveformExtractor,
        EventWaveforms,
        StationInfo,
        WaveformData,
        StationSelector,
        WaveformProcessor,
        FDSNWaveformClient,
        extract_waveforms_for_event,
        OBSPY_AVAILABLE,
    )
except ImportError:
    OBSPY_AVAILABLE = False
    WaveformExtractor = None
    EventWaveforms = None
    StationInfo = None
    WaveformData = None
    StationSelector = None
    WaveformProcessor = None
    FDSNWaveformClient = None
    extract_waveforms_for_event = None

# Animation - siempre disponible (con fallbacks)
from .seismic_3d_animation import (
    create_seismic_3d_animation,
    FaultPlane,
    Wavefield3D,
    Seismic3DRenderer,
    PlotlySeismicRenderer,
    MatplotlibSeismicRenderer,
    StationVisualization,
    estimate_fault_length,
    estimate_fault_width,
)

__all__ = [
    # USGS
    'USGSMetadataExtractor',
    'EarthquakeEvent', 
    'FocalMechanism',
    'quick_search',
    'get_latest_large_event',
    'SearchParams',
    # FDSN (pueden ser None si ObsPy no está disponible)
    'WaveformExtractor',
    'EventWaveforms',
    'StationInfo',
    'WaveformData',
    'StationSelector',
    'WaveformProcessor',
    'FDSNWaveformClient',
    'extract_waveforms_for_event',
    'OBSPY_AVAILABLE',
    # Animation
    'create_seismic_3d_animation',
    'FaultPlane',
    'Wavefield3D',
    'Seismic3DRenderer',
    'PlotlySeismicRenderer',
    'MatplotlibSeismicRenderer',
    'StationVisualization',
    'estimate_fault_length',
    'estimate_fault_width',
]