"""
Módulo 2: Extracción de Formas de Onda desde FDSN (ObsPy/IRIS)
==============================================================
Conecta a clientes FDSN (IRIS, ORFEUS, etc.), identifica las estaciones 
más cercanas al evento y descarga sismogramas en 3 componentes (Z, N, E).
Incluye limpieza instrumental, filtrado y manejo de errores.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Union
from pathlib import Path
import warnings
import logging
import numpy as np
import json

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suprimir warnings de ObsPy no críticos
warnings.filterwarnings("ignore", category=UserWarning, module="obspy")

# Intentar importar ObsPy (opcional)
try:
    from obspy import UTCDateTime, Stream, Trace, read_inventory
    from obspy.clients.fdsn import Client as FDSNClient
    from obspy.clients.fdsn.header import FDSNNoDataException, FDSNException
    from obspy.geodetics import locations2degrees, gps2dist_azimuth
    from obspy.signal.invsim import cosine_taper
    from obspy.signal.filter import bandpass
    from obspy.core.inventory import Inventory, Network, Station, Channel
    OBSPY_AVAILABLE = True
except ImportError:
    OBSPY_AVAILABLE = False
    # Placeholders para type hints
    UTCDateTime = None
    Stream = None
    Trace = None
    read_inventory = None
    FDSNClient = None
    FDSNNoDataException = Exception
    FDSNException = Exception
    locations2degrees = None
    gps2dist_azimuth = None
    cosine_taper = None
    bandpass = None
    Inventory = None
    Network = None
    Station = None
    Channel = None
    logger.warning("ObsPy no disponible - funcionalidad FDSN deshabilitada")


# ============================================================
# ESTRUCTURAS DE DATOS
# ============================================================

@dataclass
class StationInfo:
    """Información de una estación sismológica."""
    network: str
    station: str
    location: str
    latitude: float
    longitude: float
    elevation: float  # metros
    distance_km: float  # distancia al epicentro
    azimuth: float      # azimut desde epicentro (grados)
    back_azimuth: float # back-azimut (grados)
    channels: List[str] = field(default_factory=list)
    
    def __str__(self):
        return (f"{self.network}.{self.station}.{self.location} "
                f"(lat={self.latitude:.4f}, lon={self.longitude:.4f}, "
                f"dist={self.distance_km:.1f}km, az={self.azimuth:.1f}°)")


@dataclass
class WaveformData:
    """Contenedor de datos de forma de onda para una estación."""
    station_info: StationInfo
    stream: Stream              # Stream de ObsPy con 3 componentes
    starttime: UTCDateTime
    endtime: UTCDateTime
    sampling_rate: float
    npts: int
    component_map: Dict[str, Trace]  # 'Z', 'N', 'E' -> Trace
    
    # Metadatos de procesamiento
    processed: bool = False
    instrument_corrected: bool = False
    filtered: bool = False
    filter_params: Tuple[float, float] = (0.05, 2.0)
    
    def __post_init__(self):
        self._build_component_map()
    
    def _build_component_map(self):
        """Mapea trazas a componentes Z, N, E."""
        self.component_map = {}
        for tr in self.stream:
            ch = tr.stats.channel.upper()
            if ch.endswith('Z') or ch.endswith('1'):
                self.component_map['Z'] = tr
            elif ch.endswith('N') or ch.endswith('2'):
                self.component_map['N'] = tr
            elif ch.endswith('E') or ch.endswith('3'):
                self.component_map['E'] = tr
    
    def get_component(self, comp: str) -> Optional[Trace]:
        """Obtiene traza por componente ('Z', 'N', 'E')."""
        return self.component_map.get(comp.upper())
    
    def has_all_components(self) -> bool:
        """Verifica si tiene las 3 componentes."""
        return all(c in self.component_map for c in ['Z', 'N', 'E'])
    
    def get_displacement_amplitude(self, comp: str = 'Z') -> float:
        """Amplitud máxima de desplazamiento (micras)."""
        tr = self.get_component(comp)
        if tr is not None:
            return np.max(np.abs(tr.data)) * 1e6  # m -> µm
        return 0.0


@dataclass
class EventWaveforms:
    """Contenedor de formas de onda para un evento completo."""
    event_id: str
    event_time: UTCDateTime
    event_lat: float
    event_lon: float
    event_depth: float
    event_magnitude: float
    
    stations: List[WaveformData] = field(default_factory=list)
    
    # Metadatos de búsqueda
    search_radius_km: float = 500.0
    client_used: str = "IRIS"
    download_time: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        n_sta = len(self.stations)
        n_comp = sum(1 for s in self.stations if s.has_all_components())
        return (f"EventWaveforms: {self.event_id} "
                f"({self.event_lat:.3f}, {self.event_lon:.3f}, "
                f"M{self.event_magnitude:.1f}) - "
                f"{n_sta} estaciones, {n_comp} con 3 componentes")


# ============================================================
# CLIENTE FDSN WRAPPER
# ============================================================

class FDSNWaveformClient:
    """
    Cliente wrapper para descarga de formas de onda FDSN con ObsPy.
    Maneja múltiples clientes, reintentos, y selección de estaciones.
    """
    
    # Clientes FDSN disponibles
    AVAILABLE_CLIENTS = {
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
    
    def __init__(self, client_name: str = "IRIS", timeout: int = 60, 
                 user_agent: str = "Seismo3D/1.0"):
        """
        Inicializa cliente FDSN.
        
        Args:
            client_name: Nombre del cliente FDSN (ver AVAILABLE_CLIENTS)
            timeout: Timeout en segundos
            user_agent: User-Agent para requests
        """
        if not OBSPY_AVAILABLE:
            raise ImportError("ObsPy no está disponible. Instala con: pip install obspy")
        
        if client_name not in self.AVAILABLE_CLIENTS:
            logger.warning(f"Cliente '{client_name}' no reconocido, usando IRIS")
            client_name = "IRIS"
        
        self.client_name = client_name
        self.client = FDSNClient(client_name, timeout=timeout)
        self.client._user_agent = user_agent
        
        logger.info(f"Cliente FDSN inicializado: {client_name}")
    
    def get_stations_near_event(self, 
                                 event_lat: float, 
                                 event_lon: float,
                                 event_time: UTCDateTime,
                                 radius_km: float = 500.0,
                                 min_lat: float = None,
                                 max_lat: float = None,
                                 min_lon: float = None,
                                 max_lon: float = None,
                                 channel: str = "BH?",
                                 level: str = "channel",
                                 include_availability: bool = True) -> Inventory:
        """
        Obtiene inventario de estaciones cercanas a un evento.
        
        Args:
            event_lat, event_lon: Coordenadas del epicentro
            event_time: Tiempo del evento (para disponibilidad)
            radius_km: Radio de búsqueda en km
            min_lat, etc.: Bounding box opcional (alternativa a radio)
            channel: Patrón de canal (ej: "BH?", "HH?")
            level: Nivel de detalle ("network", "station", "channel")
            include_availability: Incluir info de disponibilidad temporal
            
        Returns:
            Inventory de ObsPy con estaciones encontradas
        """
        try:
            if min_lat is not None:
                # Búsqueda por bounding box
                inv = self.client.get_stations(
                    latitude=event_lat,
                    longitude=event_lon,
                    minlatitude=min_lat,
                    maxlatitude=max_lat,
                    minlongitude=min_lon,
                    maxlongitude=max_lon,
                    starttime=event_time - 3600,
                    endtime=event_time + 3600,
                    channel=channel,
                    level=level,
                    includeavailability=include_availability
                )
            else:
                # Búsqueda por radio
                inv = self.client.get_stations(
                    latitude=event_lat,
                    longitude=event_lon,
                    maxradiuskm=radius_km,
                    starttime=event_time - 3600,
                    endtime=event_time + 3600,
                    channel=channel,
                    level=level,
                    includeavailability=include_availability
                )
            
            logger.info(f"Encontradas {len(inv.networks)} redes, "
                       f"{sum(len(n.stations) for n in inv.networks)} estaciones")
            return inv
            
        except FDSNNoDataException:
            logger.warning("No se encontraron estaciones en el área")
            return Inventory()
        except FDSNException as e:
            logger.error(f"Error FDSN obteniendo estaciones: {e}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado obteniendo estaciones: {e}")
            raise
    
    def get_waveforms(self, 
                      network: str, 
                      station: str, 
                      location: str, 
                      channel: str,
                      starttime: UTCDateTime,
                      endtime: UTCDateTime,
                      attach_response: bool = True) -> Stream:
        """
        Descarga formas de onda para una estación/canal específico.
        
        Args:
            network, station, location, channel: Códigos FDSN
            starttime, endtime: Ventana temporal
            attach_response: Adjuntar respuesta instrumental
            
        Returns:
            Stream de ObsPy
        """
        try:
            st = self.client.get_waveforms(
                network=network,
                station=station,
                location=location,
                channel=channel,
                starttime=starttime,
                endtime=endtime,
                attach_response=attach_response
            )
            return st
        except FDSNNoDataException:
            logger.warning(f"Sin datos: {network}.{station}.{location}.{channel}")
            return Stream()
        except FDSNException as e:
            logger.error(f"Error FDSN descargando {network}.{station}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error descargando {network}.{station}: {e}")
            raise
    
    def get_waveforms_bulk(self, 
                           bulk: List[Tuple[str, str, str, str, 
                                          UTCDateTime, UTCDateTime]],
                           attach_response: bool = True) -> Stream:
        """
        Descarga masiva de formas de onda (más eficiente).
        
        Args:
            bulk: Lista de tuplas (net, sta, loc, cha, start, end)
            attach_response: Adjuntar respuesta instrumental
            
        Returns:
            Stream combinado
        """
        try:
            st = self.client.get_waveforms_bulk(bulk, attach_response=attach_response)
            return st
        except Exception as e:
            logger.error(f"Error en descarga masiva: {e}")
            raise


# ============================================================
# PROCESAMIENTO DE SEÑALES
# ============================================================

class WaveformProcessor:
    """
    Procesamiento de sismogramas: corrección instrumental, filtrado,
    decimation, taper, etc.
    """
    
    def __init__(self, 
                 freqmin: float = 0.05,
                 freqmax: float = 2.0,
                 corners: int = 4,
                 zerophase: bool = True,
                 remove_response: bool = True,
                 output_units: str = "VEL",  # "DISP", "VEL", "ACC"
                 pre_filt: Tuple[float, float, float, float] = (0.005, 0.01, 10.0, 20.0),
                 taper_fraction: float = 0.05,
                 decimate_factor: Optional[int] = None,
                 target_sampling_rate: Optional[float] = None):
        """
        Inicializa procesador.
        
        Args:
            freqmin, freqmax: Frecuencias de filtro pasa-banda (Hz)
            corners: Orden del filtro
            zerophase: Filtro de fase cero
            remove_response: Remover respuesta instrumental
            output_units: Unidades de salida ("DISP", "VEL", "ACC")
            pre_filt: Pre-filtro para remoción de respuesta (f1,f2,f3,f4)
            taper_fraction: Fracción de taper coseno
            decimate_factor: Factor de decimación (opcional)
            target_sampling_rate: Frecuencia objetivo para resample (Hz)
        """
        self.freqmin = freqmin
        self.freqmax = freqmax
        self.corners = corners
        self.zerophase = zerophase
        self.remove_response = remove_response
        self.output_units = output_units.upper()
        self.pre_filt = pre_filt
        self.taper_fraction = taper_fraction
        self.decimate_factor = decimate_factor
        self.target_sampling_rate = target_sampling_rate
        
        logger.info(f"WaveformProcessor: {freqmin}-{freqmax} Hz, "
                   f"remove_resp={remove_response}, output={output_units}")
    
    def process_stream(self, st: Stream, inventory: Inventory = None) -> Stream:
        """
        Procesa un Stream completo.
        
        Args:
            st: Stream de ObsPy
            inventory: Inventory con respuesta instrumental (opcional)
            
        Returns:
            Stream procesado
        """
        if len(st) == 0:
            return st
        
        st_processed = st.copy()
        
        # 1. Merge traces if needed (manejar gaps)
        st_processed.merge(method=1, fill_value='interpolate')
        
        # 2. Detrend y taper
        st_processed.detrend('demean')
        st_processed.detrend('linear')
        st_processed.taper(max_percentage=self.taper_fraction, 
                          type='cosine', max_length=10.0)
        
        # 3. Remover respuesta instrumental
        if self.remove_response and inventory:
            try:
                st_processed.remove_response(
                    inventory=inventory,
                    output=self.output_units,
                    pre_filt=self.pre_filt,
                    water_level=60
                )
                logger.debug("Respuesta instrumental removida")
            except Exception as e:
                logger.warning(f"No se pudo remover respuesta: {e}")
        
        # 4. Filtro pasa-banda
        st_processed.filter('bandpass', 
                           freqmin=self.freqmin, 
                           freqmax=self.freqmax,
                           corners=self.corners,
                           zerophase=self.zerophase)
        
        # 5. Decimación / Resample si se solicita
        if self.decimate_factor and self.decimate_factor > 1:
            st_processed.decimate(self.decimate_factor, no_filter=True)
            logger.debug(f"Decimado factor {self.decimate_factor}")
        elif self.target_sampling_rate:
            st_processed.resample(self.target_sampling_rate)
            logger.debug(f"Resampleado a {self.target_sampling_rate} Hz")
        
        return st_processed
    
    def process_trace(self, tr: Trace, inventory: Inventory = None) -> Trace:
        """Procesa una traza individual."""
        st = Stream([tr])
        st_processed = self.process_stream(st, inventory)
        return st_processed[0] if len(st_processed) > 0 else tr


# ============================================================
# SELECTOR DE ESTACIONES
# ============================================================

class StationSelector:
    """
    Selecciona las mejores estaciones para un evento.
    Prioriza: distancia, calidad de datos, 3 componentes, ancho de banda.
    """
    
    def __init__(self, 
                 max_stations: int = 3,
                 preferred_band: str = "BH",  # BH=Broadband, HH=High-gain
                 min_channels: int = 3,
                 max_distance_km: float = 500.0):
        self.max_stations = max_stations
        self.preferred_band = preferred_band
        self.min_channels = min_channels
        self.max_distance_km = max_distance_km
    
    def select_best_stations(self, 
                             inventory: Inventory,
                             event_lat: float,
                             event_lon: float,
                             event_time: UTCDateTime) -> List[StationInfo]:
        """
        Selecciona las mejores estaciones del inventario.
        
        Returns:
            Lista de StationInfo ordenadas por calidad (mejores primero)
        """
        candidates = []
        
        for network in inventory:
            for station in network:
                # Verificar disponibilidad temporal
                if not self._is_station_available(station, event_time):
                    continue
                
                # Obtener canales de la banda preferida
                channels = self._get_preferred_channels(station)
                
                if len(channels) < self.min_channels:
                    continue
                
                # Calcular distancia y azimut
                dist_m, az, baz = gps2dist_azimuth(
                    event_lat, event_lon, 
                    station.latitude, station.longitude
                )
                dist_km = dist_m / 1000.0
                
                if dist_km > self.max_distance_km:
                    continue
                
                # Evaluar calidad de la estación
                quality_score = self._score_station(station, channels, dist_km)
                
                info = StationInfo(
                    network=network.code,
                    station=station.code,
                    location=channels[0].location_code if channels else "",
                    latitude=station.latitude,
                    longitude=station.longitude,
                    elevation=station.elevation,
                    distance_km=dist_km,
                    azimuth=az,
                    back_azimuth=baz,
                    channels=[f"{c.location_code}.{c.code}" for c in channels]
                )
                
                candidates.append((quality_score, info))
        
        # Ordenar por score (mayor = mejor) y tomar top N
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = [c[1] for c in candidates[:self.max_stations]]
        
        logger.info(f"Seleccionadas {len(selected)} estaciones de {len(candidates)} candidatas")
        for i, s in enumerate(selected, 1):
            logger.info(f"  {i}. {s}")
        
        return selected
    
    def _is_station_available(self, station: Station, event_time: UTCDateTime) -> bool:
        """Verifica si la estación estaba operativa en el tiempo del evento."""
        for ch in station:
            if ch.start_date and ch.end_date:
                if ch.start_date <= event_time <= ch.end_date:
                    return True
            elif ch.start_date and ch.start_date <= event_time:
                return True
        return False
    
    def _get_preferred_channels(self, station: Station) -> List[Channel]:
        """Obtiene canales de la banda preferida (BH, HH, etc.)."""
        channels = []
        for ch in station:
            if ch.code.startswith(self.preferred_band):
                channels.append(ch)
        # Ordenar: Z, N, E (o 1, 2, 3)
        channels.sort(key=lambda c: (c.code[-1] not in 'Z1', c.code[-1] not in 'N2', c.code[-1] not in 'E3'))
        return channels
    
    def _score_station(self, station: Station, channels: List[Channel], dist_km: float) -> float:
        """Calcula score de calidad (mayor = mejor)."""
        score = 0.0
        
        # Penalizar distancia (más cerca = mejor)
        score += max(0, 100 - dist_km / 5)
        
        # Bonificar 3 componentes
        comp_codes = set(c.code[-1] for c in channels)
        if 'Z' in comp_codes or '1' in comp_codes:
            score += 10
        if 'N' in comp_codes or '2' in comp_codes:
            score += 10
        if 'E' in comp_codes or '3' in comp_codes:
            score += 10
        
        # Bonificar banda ancha (BH) vs alta ganancia (HH)
        if self.preferred_band == "BH" and any(c.code.startswith("BH") for c in channels):
            score += 20
        elif self.preferred_band == "HH" and any(c.code.startswith("HH") for c in channels):
            score += 20
        
        # Bonificar elevación baja (menos ruido)
        if station.elevation < 500:
            score += 5
        
        return score


# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================

class WaveformExtractor:
    """
    Orquestador principal para extracción de formas de onda de un evento.
    Coordina cliente FDSN, selector de estaciones, y procesador.
    """
    
    def __init__(self, 
                 client_name: str = "IRIS",
                 max_stations: int = 3,
                 radius_km: float = 500.0,
                 preferred_band: str = "BH",
                 freqmin: float = 0.05,
                 freqmax: float = 2.0,
                 remove_response: bool = True,
                 output_units: str = "VEL",
                 pre_filt: Tuple[float, float, float, float] = (0.005, 0.01, 10.0, 20.0),
                 starttime_offset: float = -60.0,
                 endtime_offset: float = 300.0,
                 timeout: int = 120):
        """
        Inicializa extractor.
        
        Args:
            client_name: Cliente FDSN a usar
            max_stations: Máximo número de estaciones
            radius_km: Radio de búsqueda
            preferred_band: Banda preferida ("BH", "HH")
            freqmin, freqmax: Filtro pasa-banda (Hz)
            remove_response: Remover respuesta instrumental
            output_units: Unidades salida ("DISP", "VEL", "ACC")
            pre_filt: Pre-filtro para respuesta instrumental
            starttime_offset: Segundos antes del origen
            endtime_offset: Segundos después del origen
            timeout: Timeout de red (segundos)
        """
        self.client = FDSNWaveformClient(client_name, timeout=timeout)
        self.selector = StationSelector(
            max_stations=max_stations,
            preferred_band=preferred_band,
            max_distance_km=radius_km
        )
        self.processor = WaveformProcessor(
            freqmin=freqmin,
            freqmax=freqmax,
            remove_response=remove_response,
            output_units=output_units,
            pre_filt=pre_filt
        )
        self.starttime_offset = starttime_offset
        self.endtime_offset = endtime_offset
        self.radius_km = radius_km
    
    def extract_event_waveforms(self, 
                                 event_id: str,
                                 event_time: UTCDateTime,
                                 event_lat: float,
                                 event_lon: float,
                                 event_depth: float,
                                 event_magnitude: float,
                                 inventory: Inventory = None) -> EventWaveforms:
        """
        Extrae formas de onda completas para un evento.
        
        Args:
            event_id: ID del evento (USGS, GCMT, etc.)
            event_time: Tiempo de origen
            event_lat, event_lon: Epicentro
            event_depth: Profundidad (km)
            event_magnitude: Magnitud
            inventory: Inventory pre-cargado (opcional)
            
        Returns:
            EventWaveforms con datos de todas las estaciones
        """
        logger.info(f"Extrayendo formas de onda para evento {event_id}")
        logger.info(f"  Origen: {event_time} | {event_lat:.4f}, {event_lon:.4f} | "
                   f"Prof: {event_depth}km | Mw: {event_magnitude}")
        
        # 1. Obtener inventario de estaciones si no se proporciona
        if inventory is None:
            inventory = self.client.get_stations_near_event(
                event_lat, event_lon, event_time, 
                radius_km=self.radius_km,
                channel=f"{self.selector.preferred_band}?"
            )
        
        # 2. Seleccionar mejores estaciones
        stations = self.selector.select_best_stations(
            inventory, event_lat, event_lon, event_time
        )
        
        if not stations:
            logger.warning("No se encontraron estaciones adecuadas")
            return EventWaveforms(
                event_id=event_id,
                event_time=event_time,
                event_lat=event_lat,
                event_lon=event_lon,
                event_depth=event_depth,
                event_magnitude=event_magnitude,
                search_radius_km=self.radius_km,
                client_used=self.client.client_name
            )
        
        # 3. Definir ventana temporal
        starttime = event_time + self.starttime_offset
        endtime = event_time + self.endtime_offset
        
        # 4. Descargar formas de onda
        waveform_data_list = []
        
        for station_info in stations:
            try:
                wf_data = self._download_station_waveforms(
                    station_info, starttime, endtime, inventory
                )
                if wf_data and wf_data.has_all_components():
                    waveform_data_list.append(wf_data)
                    logger.info(f"  ✓ {station_info.station}: 3 componentes OK")
                elif wf_data:
                    logger.warning(f"  ⚠ {station_info.station}: componentes incompletas")
                else:
                    logger.warning(f"  ✗ {station_info.station}: sin datos")
            except Exception as e:
                logger.error(f"  ✗ {station_info.station}: error - {e}")
        
        # 5. Construir resultado
        result = EventWaveforms(
            event_id=event_id,
            event_time=event_time,
            event_lat=event_lat,
            event_lon=event_lon,
            event_depth=event_depth,
            event_magnitude=event_magnitude,
            stations=waveform_data_list,
            search_radius_km=self.radius_km,
            client_used=self.client.client_name
        )
        
        logger.info(f"Extracción completada: {len(waveform_data_list)} estaciones con 3 componentes")
        return result
    
    def _download_station_waveforms(self, 
                                    station_info: StationInfo,
                                    starttime: UTCDateTime,
                                    endtime: UTCDateTime,
                                    inventory: Inventory) -> Optional[WaveformData]:
        """Descarga y procesa formas de onda para una estación."""
        
        # Construir lista de canales a descargar
        channels = station_info.channels
        if not channels:
            # Usar patrón estándar
            loc = station_info.location or "*"
            channels = [f"{loc}.{self.selector.preferred_band}Z",
                       f"{loc}.{self.selector.preferred_band}N",
                       f"{loc}.{self.selector.preferred_band}E"]
        
        # Descargar en bulk
        bulk = []
        for ch in channels:
            parts = ch.split('.')
            if len(parts) >= 2:
                loc = parts[0] if len(parts) > 2 else ""
                cha = parts[-1]
                bulk.append((
                    station_info.network,
                    station_info.station,
                    loc,
                    cha,
                    starttime,
                    endtime
                ))
        
        try:
            st = self.client.get_waveforms_bulk(bulk, attach_response=True)
            
            if len(st) == 0:
                return None
            
            # Procesar
            st_processed = self.processor.process_stream(st, inventory)
            
            # Verificar componentes
            comp_map = {}
            for tr in st_processed:
                ch = tr.stats.channel.upper()
                if ch.endswith('Z') or ch.endswith('1'):
                    comp_map['Z'] = tr
                elif ch.endswith('N') or ch.endswith('2'):
                    comp_map['N'] = tr
                elif ch.endswith('E') or ch.endswith('3'):
                    comp_map['E'] = tr
            
            # Crear WaveformData
            wf_data = WaveformData(
                station_info=station_info,
                stream=st_processed,
                starttime=starttime,
                endtime=endtime,
                sampling_rate=st_processed[0].stats.sampling_rate if st_processed else 0,
                npts=st_processed[0].stats.npts if st_processed else 0,
                component_map=comp_map,
                processed=True,
                instrument_corrected=self.processor.remove_response,
                filtered=True,
                filter_params=(self.processor.freqmin, self.processor.freqmax)
            )
            
            return wf_data
            
        except Exception as e:
            logger.error(f"Error descargando {station_info.station}: {e}")
            return None
    
    def save_waveforms(self, event_waveforms: EventWaveforms, output_dir: Path):
        """Guarda formas de onda en disco (MiniSEED + metadatos JSON)."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar cada estación
        for wf in event_waveforms.stations:
            sta_dir = output_dir / f"{wf.station_info.network}.{wf.station_info.station}"
            sta_dir.mkdir(exist_ok=True)
            
            # MiniSEED
            mseed_file = sta_dir / f"{wf.station_info.network}.{wf.station_info.station}.mseed"
            wf.stream.write(str(mseed_file), format="MSEED")
            
            # Metadatos JSON
            meta = {
                "station": {
                    "network": wf.station_info.network,
                    "station": wf.station_info.station,
                    "location": wf.station_info.location,
                    "latitude": wf.station_info.latitude,
                    "longitude": wf.station_info.longitude,
                    "elevation": wf.station_info.elevation,
                    "distance_km": wf.station_info.distance_km,
                    "azimuth": wf.station_info.azimuth,
                    "back_azimuth": wf.station_info.back_azimuth,
                },
                "event": {
                    "id": event_waveforms.event_id,
                    "time": str(event_waveforms.event_time),
                    "latitude": event_waveforms.event_lat,
                    "longitude": event_waveforms.event_lon,
                    "depth_km": event_waveforms.event_depth,
                    "magnitude": event_waveforms.event_magnitude,
                },
                "processing": {
                    "instrument_corrected": wf.instrument_corrected,
                    "filtered": wf.filtered,
                    "filter_freqmin": wf.filter_params[0],
                    "filter_freqmax": wf.filter_params[1],
                    "output_units": self.processor.output_units,
                    "sampling_rate": wf.sampling_rate,
                    "npts": wf.npts,
                    "starttime": str(wf.starttime),
                    "endtime": str(wf.endtime),
                    "components": list(wf.component_map.keys()),
                }
            }
            
            meta_file = sta_dir / "metadata.json"
            with open(meta_file, 'w') as f:
                json.dump(meta, f, indent=2)
        
        # Resumen del evento
        summary = {
            "event_id": event_waveforms.event_id,
            "event_time": str(event_waveforms.event_time),
            "event_lat": event_waveforms.event_lat,
            "event_lon": event_waveforms.event_lon,
            "event_depth_km": event_waveforms.event_depth,
            "event_magnitude": event_waveforms.event_magnitude,
            "n_stations": len(event_waveforms.stations),
            "stations": [
                {
                    "network": wf.station_info.network,
                    "station": wf.station_info.station,
                    "distance_km": wf.station_info.distance_km,
                    "azimuth": wf.station_info.azimuth,
                    "has_3comp": wf.has_all_components(),
                    "sampling_rate": wf.sampling_rate,
                }
                for wf in event_waveforms.stations
            ],
            "download_time": str(event_waveforms.download_time),
            "client": event_waveforms.client_used,
        }
        
        summary_file = output_dir / "event_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Datos guardados en: {output_dir}")


# ============================================================
# FUNCIONES DE CONVENIENCIA
# ============================================================

def extract_waveforms_for_event(event_id: str,
                                 event_time: Union[str, UTCDateTime],
                                 event_lat: float,
                                 event_lon: float,
                                 event_depth: float,
                                 event_magnitude: float,
                                 client: str = "IRIS",
                                 max_stations: int = 3,
                                 radius_km: float = 500.0,
                                 freqmin: float = 0.05,
                                 freqmax: float = 2.0,
                                 output_dir: Optional[str] = None) -> EventWaveforms:
    """
    Función de conveniencia: extrae formas de onda para un evento.
    
    Args:
        event_id: ID del evento
        event_time: Tiempo origen (string ISO o UTCDateTime)
        event_lat, event_lon: Epicentro
        event_depth: Profundidad (km)
        event_magnitude: Magnitud
        client: Cliente FDSN
        max_stations: Máximo estaciones
        radius_km: Radio búsqueda
        freqmin, freqmax: Filtro (Hz)
        output_dir: Directorio salida (opcional)
        
    Returns:
        EventWaveforms con datos
    """
    if isinstance(event_time, str):
        event_time = UTCDateTime(event_time)
    
    extractor = WaveformExtractor(
        client_name=client,
        max_stations=max_stations,
        radius_km=radius_km,
        freqmin=freqmin,
        freqmax=freqmax
    )
    
    result = extractor.extract_event_waveforms(
        event_id=event_id,
        event_time=event_time,
        event_lat=event_lat,
        event_lon=event_lon,
        event_depth=event_depth,
        event_magnitude=event_magnitude
    )
    
    if output_dir:
        extractor.save_waveforms(result, Path(output_dir))
    
    return result


def load_waveforms_from_dir(waveform_dir: Union[str, Path]) -> EventWaveforms:
    """Carga formas de onda guardadas desde directorio."""
    waveform_dir = Path(waveform_dir)
    summary_file = waveform_dir / "event_summary.json"
    
    if not summary_file.exists():
        raise FileNotFoundError(f"No se encuentra {summary_file}")
    
    with open(summary_file) as f:
        summary = json.load(f)
    
    event_wf = EventWaveforms(
        event_id=summary["event_id"],
        event_time=UTCDateTime(summary["event_time"]),
        event_lat=summary["event_lat"],
        event_lon=summary["event_lon"],
        event_depth=summary["event_depth_km"],
        event_magnitude=summary["event_magnitude"],
    )
    
    # Cargar cada estación
    for sta_summary in summary["stations"]:
        sta_dir = waveform_dir / f"{sta_summary['network']}.{sta_summary['station']}"
        mseed_file = sta_dir / f"{sta_summary['network']}.{sta_summary['station']}.mseed"
        
        if mseed_file.exists():
            st = read(str(mseed_file))
            # Reconstruir StationInfo y WaveformData...
            # (Implementación simplificada)
    
    return event_wf


# ============================================================
# DEMO / TESTING
# ============================================================

if __name__ == "__main__":
    print("=== FDSN Waveform Extractor Demo ===\n")
    
    print(f"ObsPy disponible: {OBSPY_AVAILABLE}")
    
    # Ejemplo: Terremoto Chile 2024 (ajustar fechas)
    # Usar un evento real conocido para testing
    test_event = {
        "id": "us7000mabc",  # Placeholder - usar ID real de USGS
        "time": "2024-01-15T12:34:56",
        "lat": -33.45,
        "lon": -70.65,
        "depth": 50.0,
        "mag": 6.2
    }
    
    print(f"Evento de prueba: {test_event}")
    print("\n⚠ NOTA: Para prueba real, usar ID de evento real de USGS")
    print("   y ajustar fechas. Ver módulo usgs_metadata.py para buscar eventos.\n")
    
    # Demo de inicialización
    print("Inicializando extractor...")
    extractor = WaveformExtractor(
        client_name="IRIS",
        max_stations=3,
        radius_km=300.0,
        freqmin=0.05,
        freqmax=2.0
    )
    print(f"Cliente: {extractor.client.client_name}")
    print(f"Estaciones máx: {extractor.selector.max_stations}")
    print(f"Radio: {extractor.radius_km} km")
    print(f"Filtro: {extractor.processor.freqmin}-{extractor.processor.freqmax} Hz")
    print("\n=== Demo completado ===")