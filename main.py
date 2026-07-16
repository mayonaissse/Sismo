#!/usr/bin/env python3
"""
Main Entry Point: Seismic 3D Analysis Pipeline
================================================

Script principal ejecutable que orquesta el flujo completo:
1. Búsqueda de evento en USGS (epicentro, profundidad, mecanismo focal)
2. Descarga de formas de onda desde FDSN/IRIS (3 estaciones cercanas, Z/N/E)
3. Generación de animación 3D (falla, ondas P/S, ondas de superficie)

Uso:
    python main.py                           # Usa parámetros CUSTOM de config/params.py
    python main.py --preset CHILE_2024       # Usa preset predefinido
    python main.py --event-id us7000abc      # Evento específico USGS
    python main.py --lat -33.45 --lon -70.65 --radius 300 --min-mag 5.5 --start 2024-01-01 --end 2024-12-31
    python main.py --latest --min-mag 6.0    # Evento más reciente M≥6.0
"""

import sys
import argparse
from pathlib import Path

# Añadir directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from config.params import SearchParams, DEFAULT_PARAMS, get_params, validate_params
from workflow import Seismic3DWorkflow, quick_analysis, analyze_specific_event


def create_parser() -> argparse.ArgumentParser:
    """Crea el parser de argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Análisis Sismológico 3D - USGS + FDSN + Animación 3D",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:

  # Configuración personalizada (edita config/params.py -> CUSTOM)
  python main.py

  # Presets predefinidos
  python main.py --preset CHILE_2024
  python main.py --preset TURKEY_2023
  python main.py --preset JAPAN_2024

  # Evento específico por ID USGS
  python main.py --event-id us7000mabc

  # Búsqueda por coordenadas y parámetros
  python main.py --lat -33.45 --lon -70.65 --radius 300 --min-mag 5.5 \\
                 --start 2024-01-01 --end 2024-12-31

  # Evento más reciente M≥6.0
  python main.py --latest --min-mag 6.0

  # Solo obtener evento (sin formas de onda ni animación)
  python main.py --step 1 --event-id us7000abc

  # Evento + formas de onda (sin animación)
  python main.py --step 2 --event-id us7000abc
        """
    )
    
    # Modo de operación
    parser.add_argument(
        '--preset', 
        choices=['CUSTOM', 'CHILE_2024', 'TURKEY_2023', 'JAPAN_2024', 'MEXICO_2017'],
        default='CUSTOM',
        help='Preset de parámetros predefinido (default: CUSTOM)'
    )
    
    parser.add_argument(
        '--event-id', 
        type=str,
        help='ID de evento USGS específico (ej: us7000mabc)'
    )
    
    parser.add_argument(
        '--latest',
        action='store_true',
        help='Usar el evento más reciente que cumpla criterios de magnitud'
    )
    
    parser.add_argument(
        '--step',
        type=int,
        choices=[1, 2, 3],
        default=3,
        help='Ejecutar hasta paso N: 1=USGS, 2=+FDSN, 3=+Animación (default: 3)'
    )
    
    # Parámetros de búsqueda (sobrescriben preset)
    parser.add_argument('--lat', type=float, help='Latitud epicentro')
    parser.add_argument('--lon', type=float, help='Longitud epicentro')
    parser.add_argument('--radius', type=float, help='Radio búsqueda (km)')
    parser.add_argument('--min-mag', type=float, dest='min_mag', help='Magnitud mínima')
    parser.add_argument('--max-mag', type=float, dest='max_mag', help='Magnitud máxima')
    parser.add_argument('--start', type=str, help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='Fecha fin (YYYY-MM-DD)')
    
    # Parámetros de estaciones
    parser.add_argument('--stations', type=int, default=3, help='Número de estaciones (default: 3)')
    parser.add_argument('--client', type=str, default='IRIS', help='Cliente FDSN (default: IRIS)')
    
    # Parámetros de filtrado
    parser.add_argument('--freqmin', type=float, default=0.05, help='Filtro paso-banda min (Hz)')
    parser.add_argument('--freqmax', type=float, default=2.0, help='Filtro paso-banda max (Hz)')
    
    # Parámetros de animación
    parser.add_argument('--duration', type=float, default=60.0, help='Duración animación (s)')
    parser.add_argument('--fps', type=int, default=30, help='Frames por segundo')
    parser.add_argument('--format', choices=['mp4', 'gif', 'html', 'png'], default='mp4',
                        help='Formato salida (default: mp4)')
    parser.add_argument('--output', type=str, help='Directorio de salida')
    parser.add_argument('--filename', type=str, help='Nombre base archivo salida')
    
    # Otros
    parser.add_argument('-v', '--verbose', action='store_true', help='Salida detallada')
    parser.add_argument('--no-validate', action='store_true', help='Saltar validación de parámetros')
    
    return parser


def build_params(args) -> SearchParams:
    """Construye SearchParams desde argumentos y preset."""
    
    # Base: preset
    params = get_params(args.preset)
    
    # Sobrescribir con argumentos CLI
    if args.lat is not None:
        params.latitude = args.lat
    if args.lon is not None:
        params.longitude = args.lon
    if args.radius is not None:
        params.radius_km = args.radius
    if args.min_mag is not None:
        params.min_magnitude = args.min_mag
    if args.max_mag is not None:
        params.max_magnitude = args.max_mag
    if args.start is not None:
        params.start_time = args.start
    if args.end is not None:
        params.end_time = args.end
    if args.stations is not None:
        params.n_stations = args.stations
    if args.client is not None:
        params.fdsn_client = args.client
    if args.freqmin is not None:
        params.filter_freqmin = args.freqmin
    if args.freqmax is not None:
        params.filter_freqmax = args.freqmax
    if args.duration is not None:
        params.animation_duration = args.duration
    if args.fps is not None:
        params.fps = args.fps
    if args.format is not None:
        params.output_format = args.format
    if args.output is not None:
        params.output_dir = args.output
    if args.filename is not None:
        params.output_filename = args.filename
    
    return params


def main():
    """Función principal."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Configurar logging
    import logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    logger = logging.getLogger(__name__)
    
    # Banner
    print("=" * 70)
    print("  🌍 ANÁLISIS SISMOLÓGICO 3D - USGS + FDSN + ANIMACIÓN")
    print("=" * 70)
    
    # Construir parámetros
    params = build_params(args)
    
    # Validar
    if not args.no_validate:
        try:
            validate_params(params)
            print("✓ Parámetros validados")
        except ValueError as e:
            logger.error(f"Parámetros inválidos: {e}")
            sys.exit(1)
    
    # Mostrar configuración
    print(f"\n📋 CONFIGURACIÓN:")
    print(f"   Preset: {args.preset}")
    print(f"   Ubicación: {params.latitude:.4f}, {params.longitude:.4f}")
    print(f"   Radio: {params.radius_km:.0f} km")
    print(f"   Periodo: {params.start_time} → {params.end_time}")
    print(f"   Magnitud: M≥{params.min_magnitude}" + (f", M≤{params.max_magnitude}" if params.max_magnitude else ""))
    print(f"   Estaciones: {params.n_stations} (cliente: {params.fdsn_client})")
    print(f"   Filtro: {params.filter_freqmin}-{params.filter_freqmax} Hz")
    print(f"   Animación: {params.animation_duration:.0f}s @ {params.fps} FPS → {params.output_format}")
    print(f"   Salida: {params.output_dir}/{params.output_filename}.{params.output_format}")
    
    # Crear workflow
    workflow = Seismic3DWorkflow(params)
    
    try:
        # Ejecutar según paso solicitado
        if args.step == 1:
            logger.info("Ejecutando solo Paso 1: Búsqueda USGS")
            result = workflow.run_step1_only(
                event_id=args.event_id,
                use_latest=args.latest
            )
        elif args.step == 2:
            logger.info("Ejecutando Pasos 1-2: USGS + FDSN")
            result = workflow.run_step1_2_only(event_id=args.event_id)
        else:
            logger.info("Ejecutando Flujo Completo (3 pasos)")
            result = workflow.run_full_workflow(
                event_id=args.event_id,
                use_latest=args.latest
            )
        
        # Resumen final
        print("\n" + "=" * 70)
        print("  ✅ PROCESO COMPLETADO")
        print("=" * 70)
        
        if result.get('event'):
            ev = result['event']
            print(f"\n📍 Evento: {ev.get('id', 'N/A')}")
            print(f"   Tiempo: {ev.get('time', 'N/A')}")
            print(f"   Ubicación: {ev.get('latitude', 0):.4f}, {ev.get('longitude', 0):.4f}")
            print(f"   Profundidad: {ev.get('depth_km', 0):.1f} km")
            print(f"   Magnitud: M{ev.get('magnitude', 0):.1f}")
            
            fm = ev.get('focal_mechanism')
            if fm:
                print(f"   Mecanismo Focal: Strike={fm.get('strike',0):.0f}°, "
                      f"Dip={fm.get('dip',0):.0f}°, Rake={fm.get('rake',0):.0f}°")
        
        if result.get('waveforms'):
            wf = result['waveforms']
            print(f"\n📡 Formas de onda: {wf.get('n_stations', 0)} estaciones")
            for sta in wf.get('stations', []):
                print(f"   {sta['network']}.{sta['station']}: "
                      f"{sta['distance_km']:.1f}km, comp={sta['components']}")
        
        if result.get('animation'):
            print(f"\n🎬 Animación: {result['animation']}")
        
        if result.get('files'):
            print(f"\n📁 Archivos generados:")
            for f in result['files']:
                print(f"   {f}")
        
        if result.get('errors'):
            print(f"\n⚠ Advertencias/Errores:")
            for err in result['errors']:
                print(f"   - {err}")
        
        print("\n" + "=" * 70)
        
    except KeyboardInterrupt:
        logger.warning("\n⚠ Proceso interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Error fatal: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()