# Análisis Sismológico 3D - Python Modular
==========================================

Sistema completo y modular para búsqueda de eventos sísmicos (USGS), descarga de formas de onda (FDSN/ObsPy) y generación de animaciones 3D de propagación de ondas sísmicas.

## 🎯 Características Principales

| Módulo | Funcionalidad | Tecnologías |
|--------|--------------|-------------|
| **Módulo 1** | Metadatos USGS (epicentro, profundidad, mecanismo focal: strike/dip/rake) | USGS ComCat API, requests |
| **Módulo 2** | Formas de onda FDSN (3 estaciones cercanas, componentes Z/N/E, filtrado) | ObsPy, IRIS/ORFEUS |
| **Módulo 3** | Animación 3D (plano de falla, ondas P/S, ondas Rayleigh/Love con datos reales) | PyVista/Plotly/Matplotlib |

## 📁 Estructura del Proyecto

```
seismo_3d/
├── main.py                    # Script principal ejecutable
├── workflow.py                # Orquestador del flujo completo
├── config/
│   └── params.py              # Parámetros centralizados (¡MODIFICA AQUÍ!)
├── modules/
│   ├── __init__.py
│   ├── usgs_metadata.py       # Módulo 1: USGS ComCat API
│   ├── fdsn_waveforms.py      # Módulo 2: ObsPy FDSN Client
│   └── seismic_3d_animation.py # Módulo 3: Animación 3D
├── requirements.txt           # Dependencias completas
├── requirements-minimal.txt   # Dependencias mínimas (Termux/Android)
└── output/                    # Resultados generados
    ├── waveforms/             # MiniSEED + metadatos
    ├── *.mp4/.gif/.html       # Animaciones
    └── workflow_results.json  # Resumen completo
```

## 🚀 Instalación Rápida

### Opción A: Entorno Estándar (Linux/macOS/Windows)
```bash
# Clonar o descargar el proyecto
cd seismo_3d

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### Opción B: Termux (Android)
```bash
# En Termux
pkg install python libffi openssl libxml2 libxslt clang make
pip install -r requirements.txt

# Si ObsPy falla, usa versión mínima:
pip install -r requirements-minimal.txt
# Nota: En Termux, ObsPy puede requerir compilación nativa (tarda ~10 min)
```

### Opción C: Conda (Recomendado para ObsPy)
```bash
conda create -n seismo3d python=3.10
conda activate seismo3d
conda install -c conda-forge obspy pyvista plotly matplotlib scipy numpy pandas requests
```

## ⚙️ Configuración: ¡Modifica Aquí Tus Parámetros!

Edita **`config/params.py`** en la sección `CUSTOM`:

```python
# config/params.py - SECCIÓN CUSTOM (línea ~180)
CUSTOM = SearchParams(
    # === TU UBICACIÓN ===
    latitude=-33.45,        # ← TU LATITUD
    longitude=-70.65,       # ← TU LONGITUD
    radius_km=500.0,        # ← TU RADIO (km)
    
    # === TUS FECHAS ===
    start_time="2024-01-01",   # ← FECHA INICIO
    end_time="2024-12-31",     # ← FECHA FIN
    
    # === TU MAGNITUD ===
    min_magnitude=5.0,    # ← MAGNITUD MÍNIMA
    
    # === OPCIONAL: PERSONALIZACIÓN ADICIONAL ===
    n_stations=3,              # Estaciones a descargar
    filter_freqmin=0.05,       # Filtro pasa-banda (Hz)
    filter_freqmax=2.0,
    animation_duration=60.0,   # Duración animación (seg)
    fps=30,                    # Frames por segundo
    output_format="mp4",       # mp4, gif, html, png
    output_filename="mi_terremoto_3d"
)
```

### Presets Predefinidos
```bash
python main.py --preset CHILE_2024     # Chile 2024
python main.py --preset TURKEY_2023    # Turquía-Siria 2023 (Mw 7.8)
python main.py --preset JAPAN_2024     # Japón Noto 2024 (Mw 7.6)
python main.py --preset MEXICO_2017    # México 2017 (Mw 7.1)
```

## 💻 Uso Básico

### 1. Flujo Completo (3 pasos)
```bash
# Usa tu configuración CUSTOM
python main.py

# O con parámetros inline
python main.py --lat -33.45 --lon -70.65 --radius 300 --min-mag 5.5 \
               --start 2024-01-01 --end 2024-12-31
```

### 2. Evento Específico por ID USGS
```bash
python main.py --event-id us7000mabc
```

### 3. Evento Más Reciente M≥6.0
```bash
python main.py --latest --min-mag 6.0
```

### 4. Pasos Individuales
```bash
# Solo búsqueda USGS (Paso 1)
python main.py --step 1 --event-id us7000mabc

# USGS + Formas de onda FDSN (Pasos 1-2)
python main.py --step 2 --event-id us7000mabc

# Completo (Pasos 1-2-3) - default
python main.py --step 3
```

## 🔬 Uso Programático (API)

### Módulo 1: USGS Metadata
```python
from modules.usgs_metadata import USGSMetadataExtractor, quick_search

extractor = USGSMetadataExtractor()

# Búsqueda rápida por coordenadas
events = quick_search(-33.45, -70.67, radius_km=300, min_mag=5.0)
for ev in events:
    print(f"{ev.time}: M{ev.magnitude} @ {ev.latitude:.3f},{ev.longitude:.3f}")
    if ev.has_focal_mechanism:
        fm = ev.focal_mechanism
        print(f"  FM: Strike={fm.strike:.0f}, Dip={fm.dip:.0f}, Rake={fm.rake:.0f}")

# Evento específico con mecanismo focal completo
event = extractor.get_event_with_focal_mechanism("us7000mabc")
```

### Módulo 2: FDSN Waveforms (ObsPy)
```python
from modules.fdsn_waveforms import extract_waveforms_for_event
from obspy import UTCDateTime

waveforms = extract_waveforms_for_event(
    event_id="us7000mabc",
    event_time=UTCDateTime("2024-01-15T12:34:56"),
    event_lat=-33.45,
    event_lon=-70.65,
    event_depth=50.0,
    event_magnitude=6.2,
    client="IRIS",
    max_stations=3,
    radius_km=300,
    freqmin=0.05,
    freqmax=2.0,
    output_dir="./output/waveforms"
)

print(f"Estaciones: {len(waveforms.stations)}")
for wf in waveforms.stations:
    sta = wf.station_info
    print(f"  {sta.network}.{sta.station}: {sta.distance_km:.1f}km, comps={list(wf.component_map.keys())}")
    # Acceder a componentes: wf.get_component('Z'), 'N', 'E'
```

### Módulo 3: Animación 3D
```python
from modules.seismic_3d_animation import create_seismic_3d_animation, FaultPlane

# Datos del evento
event_data = {
    'id': 'us7000mabc',
    'time': '2024-01-15T12:34:56',
    'lat': -33.45,
    'lon': -70.65,
    'depth': 50.0,
    'magnitude': 6.2
}

# Mecanismo focal
focal_mechanism = {
    'strike': 15.0,
    'dip': 25.0,
    'rake': 110.0,
    'magnitude': 6.2
}

# Crear animación
output = create_seismic_3d_animation(
    event_data=event_data,
    focal_mechanism=focal_mechanism,
    event_waveforms=waveforms,  # opcional: datos reales
    renderer_type="pyvista",    # "pyvista", "plotly", "matplotlib"
    output_file="./output/mi_animacion.mp4"
)
```

## 🎬 Renderizadores Disponibles

| Renderer | Formato | Interactivo | Requisitos | Uso Recomendado |
|----------|---------|-------------|------------|-----------------|
| **PyVista** | mp4, gif | No (offscreen) | VTK, PyVista | Animaciones video producción |
| **Plotly** | html | ✅ Sí | plotly | Exploración web interactiva |
| **Matplotlib** | mp4, png | No | matplotlib | Fallback, gráficos estáticos |

## 📊 Salidas Generadas

```
output/
├── mi_terremoto_3d.mp4           # Animación principal
├── mi_terremoto_3d.html          # Versión interactiva (Plotly)
├── mi_terremoto_3d_static.png    # Gráfico estático (Matplotlib)
├── waveforms/
│   ├── IU.ANMO/                  # Estación 1
│   │   ├── IU.ANMO.mseed         # MiniSEED 3 componentes
│   │   └── metadata.json         # Metadatos estación
│   ├── IU.COLA/                  # Estación 2
│   └── event_summary.json        # Resumen evento
└── workflow_results.json         # Resultados completos JSON
```

## 🔧 Parámetros Avanzados (config/params.py)

```python
# Filtro instrumental
remove_instrument_response=True  # Remover respuesta instrumento
output_units="VEL"               # "VEL", "DISP", "ACC"
pre_filt=(0.005, 0.01, 10.0, 20.0)  # Pre-filtro para remoción respuesta

# Ventana temporal relativa al origen
starttime_offset=-60   # 60s antes del origen
endtime_offset=300     # 300s después del origen

# Animación 3D
grid_resolution=50           # Resolución malla 3D
wave_propagation_radius_km=300  # Radio propagación ondas
displacement_scale=10000.0   # Escala amplificación visual

# Cámara
camera_distance=500.0
camera_elevation=30.0
camera_azimuth=45.0
```

## 🧪 Testing y Desarrollo

```bash
# Ejecutar tests de cada módulo
python -m modules.usgs_metadata
python -m modules.fdsn_waveforms
python -m modules.seismic_3d_animation

# Verificar dependencias
python -c "import pyvista, plotly, obspy; print('✅ Todo OK')"
```

## 🐛 Solución de Problemas

### ObsPy no instala en Termux
```bash
# Usar conda o compilar desde fuente
pkg install libffi openssl libxml2 libxslt clang make
pip install --no-binary=obspy obspy
# O usar requirements-minimal.txt (sin ObsPy)
```

### PyVista/VTK no disponible
```bash
# El sistema hará fallback automático a Plotly/Matplotlib
# Para PyVista en Linux:
pip install pyvista vtk
# En headless servers: xvfb-run python script.py
```

### Memoria insuficiente en animación 3D
```python
# Reducir en config/params.py:
grid_resolution=30      # Era 50
wave_propagation_radius_km=200  # Era 300
animation_duration=30.0  # Era 60s
```

## 📚 Referencias Científicas

- **USGS ComCat API**: https://earthquake.usgs.gov/fdsnws/event/1/
- **FDSN Web Services**: https://www.fdsn.org/webservices/
- **ObsPy Documentation**: https://docs.obspy.org/
- **Mecanismo Focal (Aki & Richards, 2002)**: Quantitative Seismology
- **Escalas Falla (Wells & Coppersmith, 1994)**: BSSA
- **PyVista**: https://docs.pyvista.org/
- **Wavefield Simulation**: Shearer (2009) Introduction to Seismology

## 📄 Licencia

MIT License - Libre uso académico y comercial.

## 🤝 Contribuciones

1. Fork del proyecto
2. Crea feature branch (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Add nueva funcionalidad'`)
4. Push (`git push origin feature/nueva-funcionalidad`)
5. Pull Request

## 📞 Soporte

- Issues: GitHub Issues
- Documentación: Ver docstrings en cada módulo
- Ejemplos: `python -m modules.<modulo>` para demos

---

**Desarrollado para investigación sismológica y educación** 🌍📊
*Compatible con Python 3.9+*