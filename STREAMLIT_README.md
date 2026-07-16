# 🌍 Seismic 3D Analysis - Streamlit Web App

Interfaz web interactiva para análisis sismológico con visualización 3D.

## 🚀 Despliegue Rápido en Streamlit Community Cloud

### 1. Push a GitHub
```bash
cd seismo_3d
git add .
git commit -m "Add Streamlit web app"
git push origin main
```

### 2. Deploy en Streamlit Cloud
1. Ve a [share.streamlit.io](https://share.streamlit.io)
2. Conecta tu cuenta GitHub
3. Selecciona repositorio: `mayonaissse/Sismo`
4. Branch: `main`
5. Main file path: `streamlit_app.py`
6. ¡Deploy!

### 3. Configuración automática
Streamlit Cloud instalará automáticamente las dependencias desde `requirements-streamlit.txt`

## 🏃 Ejecución Local

```bash
# Instalar dependencias
pip install -r requirements-streamlit.txt

# Ejecutar
streamlit run streamlit_app.py
```

La app estará disponible en `http://localhost:8501`

## 🎯 Funcionalidades Web

| Pestaña | Descripción |
|---------|-------------|
| **🔍 Buscar Eventos** | Buscar terremotos en USGS por ubicación, radio, fechas y magnitud |
| **📐 Mecanismo Focal** | Visualización 3D interactiva del plano de falla (Plotly) |
| **🌊 Propagación Ondas** | Animación 2D de ondas P/S y ondas de superficie |
| **📡 Formas de Onda** | Descarga de sismogramas FDSN (requiere ObsPy) |

## 🔧 Configuración Avanzada

### Variables de entorno (Streamlit Secrets)
En Streamlit Cloud > Settings > Secrets:
```toml
# Opcional: Configuración personalizada
USGS_TIMEOUT = 30
MAX_EVENTS = 50
DEFAULT_RADIUS_KM = 500
```

### Personalización
Edita `.streamlit/config.toml` para:
- Cambiar tema/colores
- Configurar puerto
- Deshabilitar CORS si necesario

## 📱 Características UI

- **Responsive**: Funciona en móvil y desktop
- **Interactiva**: Gráficos 3D con zoom, rotación, hover
- **Cache inteligente**: Consultas USGS cacheadas por 1 hora
- **Feedback visual**: Spinners, métricas, alertas
- **Exportación**: Descarga de parámetros JSON

## 🛠️ Estructura de Archivos

```
seismo_3d/
├── streamlit_app.py          # App principal
├── requirements-streamlit.txt # Dependencias web
├── .streamlit/
│   └── config.toml           # Configuración Streamlit
├── modules/                  # Backend Python (reutilizado)
│   ├── usgs_metadata.py
│   ├── fdsn_waveforms.py
│   └── seismic_3d_animation.py
└── config/params.py          # Parámetros compartidos
```

## 🔗 Integración con Backend Python

La web app reutiliza directamente los módulos:
- `USGSMetadataExtractor` para búsqueda de eventos
- `FaultPlane` / `Wavefield3D` para visualización 3D
- `extract_waveforms_for_event` para FDSN (si ObsPy disponible)

## ⚠️ Limitaciones Conocidas

1. **ObsPy en Streamlit Cloud**: Requiere compilación nativa, puede fallar. La funcionalidad FDSN se desactiva graciosamente.
2. **Animaciones pesadas**: Renderizado 3D en navegador puede ser lento en móviles.
3. **Límites USGS**: API tiene rate limiting (100 req/min).

## 📄 Licencia

MIT License - Ver LICENSE en el repo principal.