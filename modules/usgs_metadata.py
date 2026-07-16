"""
Módulo 1: Extracción de metadatos de terremotos desde USGS ComCat API.

Este módulo consulta la API de USGS ComCat para obtener:
- Epicentro (latitud, longitud)
- Profundidad hipocentral
- Magnitud y tipo de magnitud
- Mecanismo focal (strike, dip, rake) - momento tensorial
- Tiempo de origen
- Información de la región

Uso:
    from modules.usgs_metadata import USGSMetadataExtractor
    
    extractor = USGSMetadataExtractor()
    event = extractor.get_event_by_id("us7000abcd")
    # o buscar por parámetros
    events = extractor.search_events(lat=19.4, lon=-99.1, radius_km=500, min_mag=6.0)
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
import time

# Configuración
from config.params import SearchParams as ConfigSearchParams, validate_params as validate_search_params, USGSConfig


@dataclass
class FocalMechanism:
    """Mecanismo focal (momento tensorial)."""
    strike: float = 0.0      # Rumbo del plano de falla (grados)
    dip: float = 0.0         # Buzamiento del plano de falla (grados)
    rake: float = 0.0        # Deslizamiento (rake) en grados
    strike2: float = 0.0     # Plano auxiliar (strike2)
    dip2: float = 0.0        # Buzamiento plano auxiliar
    rake2: float = 0.0       # Rake plano auxiliar
    magnitude: float = 0.0   # Magnitud del momento (Mw)
    moment: float = 0.0      # Momento sísmico (N·m)
    source: str = ""         # Fuente (GCMT, USGS, etc.)
    timestamp: str = ""      # Timestamp del mecanismo
    
    def __post_init__(self):
        # Normalizar ángulos a 0-360
        for attr in ['strike', 'strike2']:
            val = getattr(self, attr)
            setattr(self, attr, val % 360)
        for attr in ['dip', 'dip2']:
            val = getattr(self, attr)
            setattr(self, attr, max(0, min(90, val)))
        for attr in ['rake', 'rake2']:
            val = getattr(self, attr)
            setattr(self, attr, max(-180, min(180, val)))
    
    def to_fault_planes(self) -> tuple:
        """
        Devuelve los dos planos de falla posibles (plano principal y auxiliar).
        Retorna: (plano_principal, plano_auxiliar)
        Cada plano es dict con strike, dip, rake.
        """
        principal = {
            'strike': self.strike,
            'dip': self.dip,
            'rake': self.rake
        }
        auxiliar = {
            'strike': self.strike2,
            'dip': self.dip2,
            'rake': self.rake2
        }
        return principal, auxiliar
    
    def get_fault_normal(self, use_auxiliary: bool = False) -> tuple:
        """
        Calcula el vector normal al plano de falla.
        Returns: (nx, ny, nz) en coordenadas ENU (East, North, Up)
        """
        import math
        
        if use_auxiliary:
            strike, dip = math.radians(self.strike2), math.radians(self.dip2)
        else:
            strike, dip = math.radians(self.strike), math.radians(self.dip)
        
        # Normal al plano de falla (apunta hacia el lado del bloque colgante)
        # Strike medido desde Norte hacia Este
        nx = -math.sin(dip) * math.sin(strike)
        ny = math.sin(dip) * math.cos(strike)
        nz = -math.cos(dip)
        
        return (nx, ny, nz)
    
    def get_slip_vector(self, use_auxiliary: bool = False) -> tuple:
        """
        Calcula el vector de deslizamiento (slip vector).
        Returns: (sx, sy, sz) en coordenadas ENU
        """
        import math
        
        if use_auxiliary:
            strike, dip, rake = math.radians(self.strike2), math.radians(self.dip2), math.radians(self.rake2)
        else:
            strike, dip, rake = math.radians(self.strike), math.radians(self.dip), math.radians(self.rake)
        
        # Vector de deslizamiento
        sx = math.cos(rake) * math.cos(strike) + math.sin(rake) * math.cos(dip) * math.sin(strike)
        sy = math.cos(rake) * math.sin(strike) - math.sin(rake) * math.cos(dip) * math.cos(strike)
        sz = -math.sin(rake) * math.sin(dip)
        
        return (sx, sy, sz)


@dataclass
class EarthquakeEvent:
    """Evento sísmico completo con todos los metadatos."""
    # Identificación
    id: str = ""
    url: str = ""
    
    # Origen
    time: datetime = field(default_factory=datetime.now)
    latitude: float = 0.0
    longitude: float = 0.0
    depth: float = 0.0  # km
    
    # Magnitud
    magnitude: float = 0.0
    magnitude_type: str = "Mw"
    
    # Ubicación
    place: str = ""
    region: str = ""
    
    # Mecanismo focal
    focal_mechanism: Optional[FocalMechanism] = None
    
    # Metadatos adicionales
    significance: int = 0
    alert: str = ""
    tsunami: int = 0
    felt: int = 0
    cdi: float = 0.0
    mmi: float = 0.0
    
    # Calidad de la solución
    gap: float = 0.0
    rms: float = 0.0
    nstations: int = 0
    
    # Metadatos raw
    properties: Dict[str, Any] = field(default_factory=dict)
    products: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.time, str):
            self.time = datetime.fromisoformat(self.time.replace('Z', '+00:00'))
    
    @property
    def magnitude_mw(self) -> float:
        """Magnitud de momento Mw (preferida)."""
        if self.magnitude_type in ['Mw', 'Mwc', 'Mwb', 'Mwr']:
            return self.magnitude
        return self.magnitude
    
    @property
    def seismic_moment(self) -> float:
        """Momento sísmico en N·m (Mw = 2/3 * log10(M0) - 6.07)."""
        Mw = self.magnitude_mw
        return 10 ** (1.5 * Mw + 9.05)
    
    @property
    def has_focal_mechanism(self) -> bool:
        return self.focal_mechanism is not None and self.focal_mechanism.moment > 0
    
    def get_fault_planes(self) -> tuple:
        """Retorna los dos planos de falla posibles."""
        if self.focal_mechanism:
            return self.focal_mechanism.to_fault_planes()
        return None, None
    
    def to_dict(self) -> dict:
        """Convierte a diccionario serializable."""
        d = asdict(self)
        d['time'] = self.time.isoformat()
        if self.focal_mechanism:
            d['focal_mechanism'] = asdict(self.focal_mechanism)
        return d
    
    def to_json(self, indent: int = 2) -> str:
        """Serializa a JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def save_json(self, filepath: Union[str, Path]) -> None:
        """Guarda en archivo JSON."""
        Path(filepath).write_text(self.to_json(), encoding='utf-8')
    
    @classmethod
    def from_json(cls, filepath: Union[str, Path]) -> 'EarthquakeEvent':
        """Carga desde archivo JSON."""
        data = json.loads(Path(filepath).read_text(encoding='utf-8'))
        data['time'] = datetime.fromisoformat(data['time'])
        if data.get('focal_mechanism'):
            data['focal_mechanism'] = FocalMechanism(**data['focal_mechanism'])
        return cls(**data)
    
    def __str__(self) -> str:
        fm = ""
        if self.has_focal_mechanism:
            fm = f", Mw={self.focal_mechanism.magnitude:.1f}, Strike={self.focal_mechanism.strike:.0f}, Dip={self.focal_mechanism.dip:.0f}, Rake={self.focal_mechanism.rake:.0f}"
        return (f"Event({self.id}): {self.time.strftime('%Y-%m-%d %H:%M')} "
                f"Lat={self.latitude:.3f}, Lon={self.longitude:.3f}, Depth={self.depth:.1f}km, "
                f"M{self.magnitude_type}={self.magnitude:.1f}{fm}")


class USGSMetadataExtractor:
    """
    Extractor de metadatos sísmicos desde USGS ComCat API.
    
    API Documentation: https://earthquake.usgs.gov/fdsnws/event/1/
    """
    
    BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"
    
    def __init__(self, config: Optional[USGSConfig] = None):
        self.config = config or USGSConfig()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'application/json'
        })
        self._cache = {}
        self._cache_time = {}
    
    def _make_request(self, endpoint: str, params: dict) -> dict:
        """Realiza petición HTTP con reintentos y caché."""
        url = f"{self.BASE_URL}/{endpoint}"
        cache_key = f"{url}?{requests.utils.urlencode(params)}"
        
        # Verificar caché
        if self.config.enable_cache and cache_key in self._cache:
            if time.time() - self._cache_time[cache_key] < self.config.cache_ttl:
                return self._cache[cache_key]
        
        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.get(
                    url, 
                    params=params, 
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                # Cachear
                if self.config.enable_cache:
                    self._cache[cache_key] = data
                    self._cache_time[cache_key] = time.time()
                
                return data
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
        
        raise requests.exceptions.RequestException(
            f"Falló después de {self.config.max_retries} intentos: {last_exception}"
        )
    
    def _parse_event(self, feature: dict) -> EarthquakeEvent:
        """Convierte feature de GeoJSON a EarthquakeEvent."""
        props = feature['properties']
        geom = feature['geometry']
        coords = geom['coordinates']  # [lon, lat, depth]
        
        event = EarthquakeEvent(
            id=feature['id'],
            url=props.get('url', ''),
            time=datetime.fromtimestamp(props['time'] / 1000),
            latitude=coords[1],
            longitude=coords[0],
            depth=coords[2],
            magnitude=props.get('mag', 0.0),
            magnitude_type=props.get('magType', 'Mw'),
            place=props.get('place', ''),
            significance=props.get('sig', 0),
            alert=props.get('alert', ''),
            tsunami=props.get('tsunami', 0),
            felt=props.get('felt', 0),
            cdi=props.get('cdi', 0.0),
            mmi=props.get('mmi', 0.0),
            gap=props.get('gap', 0.0),
            rms=props.get('rms', 0.0),
            nstations=props.get('nst', 0),
            properties=props
        )
        
        # Extraer región del lugar
        if event.place:
            parts = event.place.split(', ')
            if len(parts) > 1:
                event.region = parts[-1]
            else:
                event.region = event.place
        
        # Extraer productos (mecanismo focal, etc.)
        event.products = props.get('products', {})
        event.focal_mechanism = self._extract_focal_mechanism(event.products)
        
        return event
    
    def _extract_focal_mechanism(self, products: dict) -> Optional[FocalMechanism]:
        """Extrae mecanismo focal de los productos USGS."""
        # Buscar en productos de momento tensorial
        for prod_type in ['moment-tensor', 'focal-mechanism', 'moment-tensor']:
            if prod_type in products:
                for product in products[prod_type]:
                    if product.get('code') in ['gcmt', 'us', 'ptwc']:
                        content = product.get('contents', {})
                        # Buscar archivo de momento tensorial
                        for key, val in content.items():
                            if key.endswith('.json') or 'moment' in key.lower():
                                try:
                                    if isinstance(val, dict):
                                        data = val
                                    else:
                                        # Necesitaría descargar el contenido
                                        continue
                                    
                                    # Parsear momento tensorial
                                    mt = data.get('moment-tensor', data)
                                    if 'moment' in mt or 'mw' in mt:
                                        return self._parse_moment_tensor(mt, product.get('code', ''))
                                except Exception:
                                    continue
        
        # Buscar en properties directamente (para eventos recientes de USGS)
        if 'moment-tensor' in products:
            for prod in products['moment-tensor']:
                if 'moment-tensor' in prod.get('contents', {}):
                    mt_data = prod['contents']['moment-tensor']
                    # mt_data sería un JSON descargado
                    pass
        
        return None
    
    def _parse_moment_tensor(self, mt_data: dict, source: str) -> FocalMechanism:
        """Parsea datos de momento tensorial a FocalMechanism."""
        # USGS/GCMT moment tensor format
        fm = FocalMechanism(source=source)
        
        # Intentar varios formatos
        if 'moment' in mt_data:
            fm.moment = float(mt_data['moment'])
            fm.magnitude = 2/3 * (fm.moment.log10() - 9.05) if fm.moment > 0 else 0
        
        if 'mw' in mt_data:
            fm.magnitude = float(mt_data['mw'])
        
        # Planos de falla (nodal planes)
        if 'nodal-planes' in mt_data:
            np = mt_data['nodal-planes']
            if 'nodal-plane-1' in np:
                p1 = np['nodal-plane-1']
                fm.strike = float(p1.get('strike', 0))
                fm.dip = float(p1.get('dip', 0))
                fm.rake = float(p1.get('rake', 0))
            if 'nodal-plane-2' in np:
                p2 = np['nodal-plane-2']
                fm.strike2 = float(p2.get('strike', 0))
                fm.dip2 = float(p2.get('dip', 0))
                fm.rake2 = float(p2.get('rake', 0))
        
        # Fallback: propiedades directas
        for attr in ['strike', 'dip', 'rake', 'strike2', 'dip2', 'rake2']:
            if attr in mt_data:
                setattr(fm, attr, float(mt_data[attr]))
        
        if 'timestamp' in mt_data:
            fm.timestamp = mt_data['timestamp']
        
        return fm
    
    def get_event_by_id(self, event_id: str) -> EarthquakeEvent:
        """Obtiene un evento específico por su ID USGS."""
        data = self._make_request("query", {
            'eventid': event_id,
            'format': 'geojson'
        })
        
        if not data['features']:
            raise ValueError(f"Evento no encontrado: {event_id}")
        
        return self._parse_event(data['features'][0])
    
    def search_events(self, params: ConfigSearchParams) -> List[EarthquakeEvent]:
        """
        Busca eventos según parámetros.
        
        Args:
            params: SearchParams con criterios de búsqueda
            
        Returns:
            Lista de EarthquakeEvent ordenados por tiempo (más reciente primero)
        """
        validate_search_params(params)
        
        api_params = {
            'format': 'geojson',
            'starttime': params.start_time,
            'endtime': params.end_time,
            'minmagnitude': params.min_magnitude,
            'maxmagnitude': params.max_magnitude,
            'mindepth': params.min_depth,
            'maxdepth': params.max_depth,
            'limit': params.limit,
            'orderby': params.order_by,
        }
        
        # Búsqueda por radio desde punto
        if params.latitude is not None and params.longitude is not None:
            api_params['latitude'] = params.latitude
            api_params['longitude'] = params.longitude
            api_params['maxradiuskm'] = params.radius_km
        
        # Búsqueda por bounding box
        if params.min_latitude is not None:
            api_params['minlatitude'] = params.min_latitude
            api_params['maxlatitude'] = params.max_latitude
            api_params['minlongitude'] = params.min_longitude
            api_params['maxlongitude'] = params.max_longitude
        
        data = self._make_request("query", api_params)
        
        events = [self._parse_event(f) for f in data['features']]
        return events
    
    def get_latest_event(self, 
                         min_magnitude: float = 5.0,
                         region: Optional[str] = None) -> Optional[EarthquakeEvent]:
        """Obtiene el evento más reciente que cumpla criterios."""
        params = ConfigSearchParams(
            start_time=(datetime.utcnow() - timedelta(days=30)).isoformat(),
            end_time=datetime.utcnow().isoformat(),
            min_magnitude=min_magnitude,
            limit=10,
            order_by='time'
        )
        
        events = self.search_events(params)
        
        if region:
            events = [e for e in events if region.lower() in e.region.lower()]
        
        return events[0] if events else None
    
    def get_focal_mechanism_detail(self, event_id: str) -> Optional[FocalMechanism]:
        """
        Obtiene detalle completo del mecanismo focal descargando productos.
        Requiere descargar archivos JSON de productos USGS.
        """
        event = self.get_event_by_id(event_id)
        
        if 'moment-tensor' not in event.products:
            return event.focal_mechanism
        
        # Descargar producto de momento tensorial
        for product in event.products['moment-tensor']:
            if product['code'] in ['gcmt', 'us']:
                content_url = product['contents'].get('moment-tensor.json', {}).get('url')
                if content_url:
                    try:
                        resp = self.session.get(content_url, timeout=30)
                        resp.raise_for_status()
                        mt_data = resp.json()
                        return self._parse_moment_tensor(mt_data, product['code'])
                    except Exception:
                        continue
        
        return event.focal_mechanism
    
    def search_by_region_and_magnitude(self,
                                        region_name: str,
                                        min_mag: float = 5.0,
                                        days_back: int = 30,
                                        max_results: int = 20) -> List[EarthquakeEvent]:
        """
        Búsqueda conveniente por nombre de región y magnitud mínima.
        """
        params = ConfigSearchParams(
            start_time=(datetime.utcnow() - timedelta(days=days_back)).isoformat(),
            end_time=datetime.utcnow().isoformat(),
            min_magnitude=min_mag,
            limit=max_results,
            order_by='time'
        )
        
        events = self.search_events(params)
        
        if region_name:
            events = [e for e in events if region_name.lower() in e.region.lower()]
        
        return events
    
    def get_event_with_focal_mechanism(self, event_id: str) -> EarthquakeEvent:
        """
        Obtiene evento completo con mecanismo focal detallado.
        Descarga productos adicionales si están disponibles.
        """
        event = self.get_event_by_id(event_id)
        
        # Si no tiene mecanismo focal, intentar descargar
        if not event.has_focal_mechanism:
            fm = self.get_focal_mechanism_detail(event_id)
            if fm:
                event.focal_mechanism = fm
        
        return event


# Funciones de conveniencia
def quick_search(lat: float, lon: float, radius_km: float = 500, 
                 min_mag: float = 5.0, days_back: int = 30) -> List[EarthquakeEvent]:
    """Búsqueda rápida por coordenadas."""
    extractor = USGSMetadataExtractor()
    params = SearchParams(
        latitude=lat,
        longitude=lon,
        radius_km=radius_km,
        min_magnitude=min_mag,
        start_time=(datetime.utcnow() - timedelta(days=days_back)).isoformat(),
        end_time=datetime.utcnow().isoformat(),
        limit=20,
        order_by='time'
    )
    return extractor.search_events(params)


def get_latest_large_event(min_mag: float = 6.0, region: str = None) -> Optional[EarthquakeEvent]:
    """Obtiene el último evento grande global o en región."""
    extractor = USGSMetadataExtractor()
    return extractor.get_latest_event(min_magnitude=min_mag, region=region)


if __name__ == "__main__":
    # Demo y pruebas
    print("=== USGS Metadata Extractor Demo ===\n")
    
    extractor = USGSMetadataExtractor()
    
    # 1. Buscar últimos eventos grandes en Chile
    print("1. Buscando últimos eventos M≥6.0 en Chile (últimos 30 días)...")
    events = extractor.search_by_region_and_magnitude("chile", min_mag=6.0, days_back=30, max_results=5)
    
    for i, ev in enumerate(events, 1):
        print(f"  {i}. {ev}")
        if ev.has_focal_mechanism:
            fm = ev.focal_mechanism
            p1, p2 = ev.get_fault_planes()
            print(f"     FM: Mw={fm.magnitude:.1f}, Strike={fm.strike:.0f}, Dip={fm.dip:.0f}, Rake={fm.rake:.0f}")
            print(f"     Planos: P1=({p1['strike']:.0f},{p1['dip']:.0f},{p1['rake']:.0f}) "
                  f"P2=({p2['strike']:.0f},{p2['dip']:.0f},{p2['rake']:.0f})")
    
    if events:
        # 2. Obtener detalle del primero con mecanismo focal completo
        print(f"\n2. Obteniendo detalle completo del primer evento: {events[0].id}")
        event_detail = extractor.get_event_with_focal_mechanism(events[0].id)
        print(f"   {event_detail}")
        
        if event_detail.has_focal_mechanism:
            fm = event_detail.focal_mechanism
            print(f"   Mecanismo focal completo:")
            print(f"     Strike: {fm.strike:.1f}°, Dip: {fm.dip:.1f}°, Rake: {fm.rake:.1f}°")
            print(f"     Strike2: {fm.strike2:.1f}°, Dip2: {fm.dip2:.1f}°, Rake2: {fm.rake2:.1f}°")
            print(f"     Mw: {fm.magnitude:.2f}, Moment: {fm.moment:.2e} N·m")
            print(f"     Fuente: {fm.source}")
            
            # Vectores de falla
            n = fm.get_fault_normal()
            s = fm.get_slip_vector()
            print(f"     Normal al plano: N=({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f})")
            print(f"     Vector deslizamiento: S=({s[0]:.3f}, {s[1]:.3f}, {s[2]:.3f})")
        
        # 3. Guardar evento completo
        output_path = Path("/data/data/com.termux/files/home/seismo_3d/output")
        output_path.mkdir(parents=True, exist_ok=True)
        event_detail.save_json(output_path / f"{event_detail.id}_detail.json")
        print(f"\n   Evento guardado en: {output_path}/{event_detail.id}_detail.json")
    
    # 4. Búsqueda por coordenadas (ej: Santiago, Chile)
    print("\n3. Búsqueda cerca de Santiago, Chile (radio 300km, M≥5.0)...")
    santiago_events = quick_search(-33.45, -70.67, radius_km=300, min_mag=5.0)
    for ev in santiago_events[:3]:
        print(f"   {ev}")
    
    print("\n=== Demo completado ===")