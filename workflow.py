"""
Workflow de orquestación principal: Seismic3DWorkflow
======================================================
Coordina los 3 módulos:
1. USGS Metadata Extractor - Obtiene evento y mecanismo focal
2. FDSN Waveform Extractor - Descarga sismogramas de 3 estaciones cercanas
3. Seismic 3D Animation - Genera animación 3D completa
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Agregar directorio del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.params import SearchParams, DEFAULT_PARAMS, validate_params, get_params

# Importar módulos
try:
    from modules.usgs_metadata import (
        USGSMetadataExtractor, EarthquakeEvent, FocalMechanism,
        quick_search, get_latest_large_event
    )
    USGS_AVAILABLE = True
except ImportError as e:
    print(f"⚠ Módulo USGS no disponible: {e}")
    USGS_AVAILABLE = False

try:
    from modules.fdsn_waveforms import (
        WaveformExtractor, EventWaveforms, StationInfo, WaveformData,
        extract_waveforms_for_event
    )
    FDSN_AVAILABLE = True
except ImportError as e:
    print(f"⚠ Módulo FDSN no disponible: {e}")
    FDSN_AVAILABLE = False

try:
    from modules.seismic_3d_animation import (
        create_seismic_3d_animation, FaultPlane, Wavefield3D,
        estimate_fault_length, estimate_fault_width,
        PYVISTA_AVAILABLE, PLOTLY_AVAILABLE, MATPLOTLIB_AVAILABLE
    )
    ANIMATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠ Módulo de animación no disponible: {e}")
    ANIMATION_AVAILABLE = False


class Seismic3DWorkflow:
    """
    Orquestador principal del pipeline sismológico 3D.
    """
    
    def __init__(self, params: SearchParams = None):
        self.params = params or DEFAULT_PARAMS
        self.output_dir = Path(self.params.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Resultados
        self.event = None
        self.waveforms = None
        self.animation_file = None
        self.errors = []
        self.generated_files = []
        
        print(f"Seismic3DWorkflow inicializado")
        print(f"  Directorio salida: {self.output_dir}")
    
    def run_full_workflow(self,
                          event_id: str = None,
                          use_latest: bool = False,
                          preset: str = None) -> Dict[str, Any]:
        """
        Ejecuta el workflow completo.
        
        Args:
            event_id: ID específico de evento USGS
            use_latest: Usar el evento más reciente que cumpla criterios
            preset: Preset de parámetros a usar
            
        Returns:
            Dict con resultados de cada etapa
        """
        print("\n" + "=" * 60)
        print("🚀 INICIANDO WORKFLOW SISMOLÓGICO 3D")
        print("=" * 60)
        
        # Validar módulos
        self._check_dependencies()
        
        try:
            # === PASO 1: OBTENER EVENTO Y METADATOS USGS ===
            self.event = self._step1_get_event(event_id, use_latest, preset)
            
            if not self.event:
                raise RuntimeError("No se pudo obtener evento sísmico")
            
            # === PASO 2: EXTRAER FORMAS DE ONDA FDSN ===
            self.waveforms = self._step2_extract_waveforms()
            
            # === PASO 3: GENERAR ANIMACIÓN 3D ===
            self.animation_file = self._step3_generate_animation()
            
            # === RESUMEN ===
            return self._compile_results()
            
        except Exception as e:
            self.errors.append(f"Error fatal en workflow: {e}")
            raise
    
    def _check_dependencies(self):
        """Verifica dependencias críticas."""
        missing = []
        
        if not USGS_AVAILABLE:
            missing.append("usgs_metadata (requests)")
        if not FDSN_AVAILABLE:
            missing.append("fdsn_waveforms (obspy)")
        if not ANIMATION_AVAILABLE:
            missing.append("seismic_3d_animation (pyvista/plotly/matplotlib)")
        
        if missing:
            print(f"\n⚠ Módulos no disponibles: {', '.join(missing)}")
            print("   Instala dependencias con: pip install -r requirements.txt")
        
        # Al menos USGS + uno de animación
        if not USGS_AVAILABLE:
            raise RuntimeError("Módulo USGS es obligatorio. Instala requests.")
        
        if not (PYVISTA_AVAILABLE or PLOTLY_AVAILABLE or MATPLOTLIB_AVAILABLE):
            raise RuntimeError("Ningún renderizador 3D disponible. Instala pyvista, plotly o matplotlib.")
    
    def _step1_get_event(self, 
                         event_id: str = None, 
                         use_latest: bool = False,
                         preset: str = None) -> Optional[Dict]:
        """
        Paso 1: Obtener evento sísmico desde USGS.
        """
        print("\n" + "-" * 60)
        print("📡 PASO 1: Consultando catálogo USGS ComCat")
        print("-" * 60)
        
        extractor = USGSMetadataExtractor()
        
        if event_id:
            # Buscar evento específico
            print(f"  Buscando evento específico: {event_id}")
            event = extractor.get_event_by_id(event_id)
            # Intentar obtener mecanismo focal completo
            event = extractor.get_event_with_focal_mechanism(event_id)
            
        elif use_latest:
            # Buscar el más reciente
            print(f"  Buscando evento más reciente M≥{self.params.min_magnitude}...")
            event = extractor.get_latest_event(
                min_magnitude=self.params.min_magnitude
            )
            
        else:
            # Buscar por parámetros geográficos
            print(f"  Buscando eventos cerca de ({self.params.latitude}, {self.params.longitude})")
            print(f"    Radio: {self.params.radius_km} km, M≥{self.params.min_magnitude}")
            print(f"    Periodo: {self.params.start_time} a {self.params.end_time}")
            
            events = extractor.search_by_region_and_magnitude(
                region_name="",  # Búsqueda por coordenadas
                min_mag=self.params.min_magnitude,
                days_back=365,
                max_results=10
            )
            
            if events:
                # Filtrar por distancia al punto de referencia
                events = extractor.search_events(SearchParams(
                    latitude=self.params.latitude,
                    longitude=self.params.longitude,
                    radius_km=self.params.radius_km,
                    start_time=self.params.start_time,
                    end_time=self.params.end_time,
                    min_magnitude=self.params.min_magnitude,
                    max_magnitude=self.params.max_magnitude,
                    limit=10,
                    order_by='time'
                ))
                
                if events:
                    event = events[0]  # El más reciente
                else:
                    event = None
            else:
                event = None
        
        if not event:
            print("  ❌ No se encontraron eventos")
            self.errors.append("No se encontraron eventos con los criterios especificados")
            return None
        
        # Obtener mecanismo focal detallado si no lo tiene
        if not event.has_focal_mechanism:
            print("  ⚠ Evento sin mecanismo focal, intentando obtener productos USGS...")
            event = extractor.get_event_with_focal_mechanism(event.id)
        
        # Mostrar información
        print(f"  ✅ Evento encontrado: {event}")
        
        if event.has_focal_mechanism:
            fm = event.focal_mechanism
            print(f"  📐 Mecanismo focal: Mw={fm.magnitude:.1f}, "
                  f"Strike={fm.strike:.0f}°, Dip={fm.dip:.0f}°, Rake={fm.rake:.0f}°")
            print(f"     Fuente: {fm.source}")
        else:
            print("  ⚠ Sin mecanismo focal disponible")
            self.errors.append("Evento sin mecanismo focal - se usarán valores por defecto")
        
        # Guardar metadatos del evento
        event_file = self.output_dir / f"{event.id}_event.json"
        event.save_json(event_file)
        self.generated_files.append(str(event_file))
        
        return event.to_dict()
    
    def _step2_extract_waveforms(self) -> Optional[Dict]:
        """
        Paso 2: Descargar formas de onda desde FDSN.
        """
        print("\n" + "-" * 60)
        print("📊 PASO 2: Extrayendo formas de onda FDSN (ObsPy/IRIS)")
        print("-" * 60)
        
        if not FDSN_AVAILABLE:
            print("  ❌ Módulo FDSN no disponible - saltando extracción")
            self.errors.append("Módulo FDSN no disponible")
            return None
        
        if not self.event:
            print("  ❌ No hay evento para extraer formas de onda")
            return None
        
        # Verificar mecanismo focal
        fm = self.event.get('focal_mechanism')
        if not fm:
            print("  ⚠ Sin mecanismo focal - usando valores por defecto para animación")
        
        try:
            print(f"  Cliente FDSN: {self.params.fdsn_client}")
            print(f"  Estaciones objetivo: {self.params.n_stations}")
            print(f"  Componentes: {self.params.components}")
            print(f"  Filtro: {self.params.filter_freqmin}-{self.params.filter_freqmax} Hz")
            print(f"  Ventana: {self.params.starttime_offset}s a {self.params.endtime_offset}s relativo al origen")
            
            # Extraer formas de onda
            event_waveforms = extract_waveforms_for_event(
                event_id=self.event['id'],
                event_time=self.event['time'],
                event_lat=self.event['latitude'],
                event_lon=self.event['longitude'],
                event_depth=self.event['depth'],
                event_magnitude=self.event['magnitude'],
                client=self.params.fdsn_client,
                max_stations=self.params.n_stations,
                radius_km=self.params.radius_km,
                freqmin=self.params.filter_freqmin,
                freqmax=self.params.filter_freqmax,
                output_dir=str(self.output_dir / "waveforms")
            )
            
            if event_waveforms and event_waveforms.stations:
                print(f"  ✅ {len(event_waveforms.stations)} estaciones descargadas con 3 componentes")
                
                for wf in event_waveforms.stations:
                    sta = wf.station_info
                    comps = list(wf.component_map.keys())
                    print(f"    {sta.network}.{sta.station}: dist={sta.distance_km:.1f}km, "
                          f"comp={comps}, fs={wf.sampling_rate:.0f}Hz")
                
                # Guardar resumen
                summary_file = self.output_dir / "waveforms_summary.json"
                self.generated_files.append(str(summary_file))
                
                return {
                    'n_stations': len(event_waveforms.stations),
                    'stations': [
                        {
                            'network': wf.station_info.network,
                            'station': wf.station_info.station,
                            'distance_km': wf.station_info.distance_km,
                            'azimuth': wf.station_info.azimuth,
                            'components': list(wf.component_map.keys()),
                            'sampling_rate': wf.sampling_rate,
                            'npts': wf.npts
                        }
                        for wf in event_waveforms.stations
                    ]
                }
            else:
                print("  ⚠ No se pudieron descargar formas de onda válidas")
                self.errors.append("Sin datos de formas de onda - animación usará modelo teórico")
                return None
                
        except Exception as e:
            print(f"  ❌ Error extrayendo formas de onda: {e}")
            self.errors.append(f"Error FDSN: {e}")
            return None
    
    def _step3_generate_animation(self) -> Optional[str]:
        """
        Paso 3: Generar animación 3D.
        """
        print("\n" + "-" * 60)
        print("🎬 PASO 3: Generando animación 3D")
        print("-" * 60)
        
        if not ANIMATION_AVAILABLE:
            print("  ❌ Módulo de animación no disponible")
            self.errors.append("Módulo de animación no disponible")
            return None
        
        if not self.event:
            print("  ❌ No hay evento para animar")
            return None
        
        # Preparar datos del evento
        event_data = {
            'id': self.event['id'],
            'time': self.event['time'],
            'lat': self.event['latitude'],
            'lon': self.event['longitude'],
            'depth': self.event['depth'],
            'magnitude': self.event['magnitude']
        }
        
        # Preparar mecanismo focal
        fm = self.event.get('focal_mechanism', {})
        if fm:
            focal_mechanism = {
                'strike': fm['strike'],
                'dip': fm['dip'],
                'rake': fm['rake'],
                'magnitude': fm.get('magnitude', event_data['magnitude'])
            }
        else:
            # Valores por defecto (falla inversa típica de subducción)
            focal_mechanism = {
                'strike': 15.0,
                'dip': 25.0,
                'rake': 110.0,
                'magnitude': event_data['magnitude']
            }
            print("  ⚠ Usando mecanismo focal por defecto (subducción)")
        
        print(f"  Renderizador: {self._get_best_renderer()}")
        print(f"  Mecanismo: Strike={focal_mechanism['strike']:.0f}°, "
              f"Dip={focal_mechanism['dip']:.0f}°, Rake={focal_mechanism['rake']:.0f}°")
        
        # Crear animación
        try:
            output_file = create_seismic_3d_animation(
                event_data=event_data,
                focal_mechanism=focal_mechanism,
                event_waveforms=self.waveforms,
                params=self.params,
                renderer_type=self._get_best_renderer(),
                output_file=str(self.output_dir / f"{self.params.output_filename}.{self.params.output_format}")
            )
            
            print(f"  ✅ Animación generada: {output_file}")
            self.generated_files.append(output_file)
            return output_file
            
        except Exception as e:
            print(f"  ❌ Error generando animación: {e}")
            self.errors.append(f"Error animación: {e}")
            
            # Intentar fallback con matplotlib
            if MATPLOTLIB_AVAILABLE:
                print("  🔄 Intentando fallback con Matplotlib...")
                try:
                    output_file = create_seismic_3d_animation(
                        event_data=event_data,
                        focal_mechanism=focal_mechanism,
                        event_waveforms=None,
                        params=self.params,
                        renderer_type="matplotlib",
                        output_file=str(self.output_dir / f"{self.params.output_filename}_2d.mp4")
                    )
                    print(f"  ✅ Animación 2D generada: {output_file}")
                    self.generated_files.append(output_file)
                    return output_file
                except Exception as e2:
                    print(f"  ❌ Fallback también falló: {e2}")
                    self.errors.append(f"Fallback falló: {e2}")
            
            return None
    
    def _get_best_renderer(self) -> str:
        """Determina el mejor renderizador disponible."""
        if PYVISTA_AVAILABLE:
            return "pyvista"
        elif PLOTLY_AVAILABLE:
            return "plotly"
        elif MATPLOTLIB_AVAILABLE:
            return "matplotlib"
        return "matplotlib"  # fallback
    
    def _compile_results(self) -> Dict[str, Any]:
        """Compila resultados finales."""
        return {
            'event': self.event,
            'waveforms': self.waveforms,
            'animation': self.animation_file,
            'files': self.generated_files,
            'errors': self.errors,
            'timestamp': datetime.now().isoformat(),
            'params': {
                'lat': self.params.latitude,
                'lon': self.params.longitude,
                'radius_km': self.params.radius_km,
                'min_magnitude': self.params.min_magnitude,
                'start_time': self.params.start_time,
                'end_time': self.params.end_time
            }
        }
    
    def run_step1_only(self, event_id: str = None, use_latest: bool = False) -> Dict:
        """Ejecuta solo el paso 1 (obtener evento USGS)."""
        self.event = self._step1_get_event(event_id, use_latest)
        return {'event': self.event, 'files': self.generated_files, 'errors': self.errors}
    
    def run_step1_2_only(self, event_id: str = None) -> Dict:
        """Ejecuta pasos 1 y 2 (evento + formas de onda)."""
        self.event = self._step1_get_event(event_id)
        if self.event:
            self.waveforms = self._step2_extract_waveforms()
        return {
            'event': self.event, 
            'waveforms': self.waveforms, 
            'files': self.generated_files, 
            'errors': self.errors
        }


# Funciones de conveniencia
def quick_analysis(lat: float, lon: float, radius_km: float = 500, 
                   min_mag: float = 5.0, days_back: int = 30,
                   output_dir: str = None) -> Dict:
    """
    Análisis rápido: busca evento reciente y genera animación.
    """
    params = SearchParams(
        latitude=lat,
        longitude=lon,
        radius_km=radius_km,
        min_magnitude=min_mag,
        start_time=(datetime.utcnow() - timedelta(days=days_back)).isoformat(),
        end_time=datetime.utcnow().isoformat(),
        output_dir=output_dir or "output"
    )
    
    workflow = Seismic3DWorkflow(params)
    return workflow.run_full_workflow(use_latest=True)


def analyze_specific_event(event_id: str, output_dir: str = None) -> Dict:
    """
    Analiza un evento específico por ID USGS.
    """
    params = SearchParams(output_dir=output_dir or "output")
    workflow = Seismic3DWorkflow(params)
    return workflow.run_full_workflow(event_id=event_id)


if __name__ == "__main__":
    # Test rápido
    print("=== Seismic3DWorkflow Test ===")
    
    # Verificar módulos
    print(f"USGS: {'✓' if USGS_AVAILABLE else '✗'}")
    print(f"FDSN: {'✓' if FDSN_AVAILABLE else '✗'}")
    print(f"Animation: {'✓' if ANIMATION_AVAILABLE else '✗'}")
    print(f"  PyVista: {'✓' if PYVISTA_AVAILABLE else '✗'}")
    print(f"  Plotly: {'✓' if PLOTLY_AVAILABLE else '✗'}")
    print(f"  Matplotlib: {'✓' if MATPLOTLIB_AVAILABLE else '✗'}")
    
    # Test workflow creation
    params = SearchParams(latitude=-33.45, longitude=-70.65, min_magnitude=6.0)
    workflow = Seismic3DWorkflow(params)
    print(f"\nWorkflow creado: {workflow.output_dir}")