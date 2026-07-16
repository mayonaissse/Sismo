"""
Seismic 3D Analysis - Package Entry Point
==========================================
Permite ejecutar: python -m seismo_3d
"""

import sys
from pathlib import Path

# Añadir directorio del paquete al path
package_dir = Path(__file__).parent
sys.path.insert(0, str(package_dir))

# Importar y ejecutar main
from main import main

if __name__ == "__main__":
    sys.exit(main())