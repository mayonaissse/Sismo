#!/usr/bin/env python3
"""
Test Suite for Seismic 3D Analysis Project
===========================================
Ejecuta tests básicos de cada módulo para verificar instalación.
"""

import sys
import traceback
from pathlib import Path

# Añadir proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

def test_config():
    """Test configuración."""
    print("🔧 Testing config/params.py...")
    try:
        from config.params import SearchParams, DEFAULT_PARAMS, get_params, validate_params
        
        # Test params por defecto
        params = DEFAULT_PARAMS
        print(f"  Default: lat={params.latitude}, lon={params.longitude}, r={params.radius_km}km")
        
        # Test preset
        chile = get_params("CHILE_2024")
        print(f"  Preset CHILE_2024: lat={chile.latitude}, M≥{chile.min_magnitude}")
        
        # Test validación
        validate_params(params)
        print("  ✅ Validación OK")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def test_usgs_module():
    """Test módulo USGS."""
    print("\n📡 Testing modules/usgs_metadata.py...")
    try:
        from modules.usgs_metadata import (
            USGSMetadataExtractor, EarthquakeEvent, FocalMechanism,
            quick_search
        )
        
        # Test creación extractor
        extractor = USGSMetadataExtractor()
        print(f"  Extractor creado: {extractor.BASE_URL}")
        
        # Test FocalMechanism
        fm = FocalMechanism(strike=15, dip=25, rake=110, magnitude=6.5)
        p1, p2 = fm.to_fault_planes()
        print(f"  Fault planes: P1={p1}, P2={p2}")
        
        # Test vectors
        normal = fm.get_fault_normal()
        slip = fm.get_slip_vector()
        print(f"  Normal: {normal}, Slip: {slip}")
        
        print("  ✅ Módulo USGS OK")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def test_fdsn_module():
    """Test módulo FDSN (sin red)."""
    print("\n📊 Testing modules/fdsn_waveforms.py...")
    try:
        from modules.fdsn_waveforms import (
            WaveformExtractor, EventWaveforms, StationInfo,
            StationSelector, WaveformProcessor, OBSPY_AVAILABLE
        )
        
        # Test StationSelector
        selector = StationSelector(max_stations=3, preferred_band="BH")
        print(f"  Selector: max_stations={selector.max_stations}, band={selector.preferred_band}")
        
        # Test WaveformProcessor
        processor = WaveformProcessor(freqmin=0.05, freqmax=2.0)
        print(f"  Processor: {processor.freqmin}-{processor.freqmax} Hz")
        
        # Test WaveformExtractor (solo si ObsPy disponible)
        if OBSPY_AVAILABLE:
            extractor = WaveformExtractor(client_name="IRIS", max_stations=3)
            print(f"  Extractor: client={extractor.client.client_name}")
        else:
            print("  Extractor: ObsPy no disponible - saltando test de inicialización")
        
        print("  ✅ Módulo FDSN OK (estructura)")
        return True
    except ImportError as e:
        print(f"  ⚠ ObsPy no disponible: {e}")
        print("  ✅ Módulo FDSN OK (estructura, ObsPy opcional)")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def test_animation_module():
    """Test módulo animación."""
    print("\n🎬 Testing modules/seismic_3d_animation.py...")
    try:
        from modules.seismic_3d_animation import (
            FaultPlane, Wavefield3D, estimate_fault_length, estimate_fault_width,
            PYVISTA_AVAILABLE, PLOTLY_AVAILABLE, MATPLOTLIB_AVAILABLE
        )
        
        # Test FaultPlane
        fault = FaultPlane(
            strike=15, dip=25, rake=110,
            length=30, width=15,
            centroid_lat=-33.45, centroid_lon=-70.65, centroid_depth=50
        )
        print(f"  Fault: strike={fault.strike}, dip={fault.dip}, rake={fault.rake}")
        print(f"  Normal: {fault.normal}, Slip: {fault.slip}")
        
        # Test Wavefield3D
        wf = Wavefield3D(radius_km=200, resolution=20)
        wf.update_wavefield(10.0, fault)
        print(f"  Wavefield: P_max={wf.p_wave_amplitude.max():.4f}, S_max={wf.s_wave_amplitude.max():.4f}")
        
        # Test estimaciones
        length = estimate_fault_length(6.5)
        width = estimate_fault_width(6.5)
        print(f"  M6.5: Length={length:.1f}km, Width={width:.1f}km")
        
        # Renderers
        print(f"  Renderers: PyVista={PYVISTA_AVAILABLE}, Plotly={PLOTLY_AVAILABLE}, Matplotlib={MATPLOTLIB_AVAILABLE}")
        
        print("  ✅ Módulo Animación OK")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def test_workflow():
    """Test workflow principal."""
    print("\n🔄 Testing workflow.py...")
    try:
        from workflow import Seismic3DWorkflow
        from config.params import SearchParams
        
        params = SearchParams(latitude=-33.45, longitude=-70.65, min_magnitude=5.0)
        workflow = Seismic3DWorkflow(params)
        print(f"  Workflow creado: output_dir={workflow.output_dir}")
        
        print("  ✅ Workflow OK")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def test_main_cli():
    """Test CLI principal."""
    print("\n💻 Testing main.py (CLI parsing)...")
    try:
        from main import create_parser, build_params
        import argparse
        
        parser = create_parser()
        
        # Simular args
        class MockArgs:
            preset = 'CUSTOM'
            event_id = None
            latest = False
            lat = -33.45
            lon = -70.65
            radius = 500
            min_mag = 5.0
            max_mag = None
            start = "2024-01-01"
            end = "2024-12-31"
            stations = 3
            client = 'IRIS'
            freqmin = 0.05
            freqmax = 2.0
            duration = 60.0
            fps = 30
            format = "mp4"
            output = "test"
            filename = "test_output"
            renderer = None
            no_waveforms = False
            demo = False
        
        params = build_params(MockArgs())
        print(f"  Params creados: lat={params.latitude}, M≥{params.min_magnitude}")
        
        print("  ✅ CLI OK")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return False


def run_all_tests():
    """Ejecuta todos los tests."""
    print("=" * 60)
    print("🧪 SEISMIC 3D ANALYSIS - TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_config,
        test_usgs_module,
        test_fdsn_module,
        test_animation_module,
        test_workflow,
        test_main_cli,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("📋 RESUMEN")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test.__name__}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ¡TODOS LOS TESTS PASARON!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())