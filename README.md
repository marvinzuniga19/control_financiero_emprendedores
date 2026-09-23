# Control Financiero Pro - Aplicación de escritorio

Aplicación local creada con Python, CustomTkinter, SQLite y Matplotlib. Trabaja en córdobas nicaragüenses (C$) y no necesita conexión a internet.

## Funciones

- Panel dinámico por mes y año.
- Ingresos, gastos, utilidad y saldo disponible.
- Metas de ingresos y límite de gastos.
- Alertas automáticas y análisis por categoría.
- Gráfico mensual de ingresos y gastos.
- Registro, edición, duplicado, búsqueda y eliminación de movimientos.
- Búsqueda avanzada: texto libre, rango de fechas y tipo (ingreso/gasto).
- Categorías y métodos de pago personalizables con protección contra borrado en uso.
- Exportación de movimientos a CSV (respeta los filtros activos).
- Montos guardados en centavos para evitar errores de redondeo.
- Base de datos SQLite local con migraciones automáticas y copia de seguridad.
- Tema claro, oscuro o según el sistema (persistente).

## Requisitos

- Python 3.10 o superior.
- Windows 10/11 o una distribución Linux con Tk instalado.

## Instalación en Windows

1. Instala Python desde https://www.python.org/downloads/ y marca `Add Python to PATH`.
2. Descomprime el proyecto.
3. Abre PowerShell dentro de la carpeta.
4. Ejecuta:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

También puedes ejecutar `iniciar_windows.bat`; el archivo crea el entorno, instala las dependencias y abre la aplicación.

## Instalación en Arch Linux

```bash
sudo pacman -S python tk
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Después de dar permiso con `chmod +x iniciar_linux.sh`, también puedes iniciarla con `./iniciar_linux.sh`.

## Instalación en Ubuntu o Linux Mint

```bash
sudo apt install python3 python3-venv python3-tk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

## Datos y copias de seguridad

La base de datos se crea automáticamente en:

```text
data/control_financiero.db
```

Al actualizar el programa, la base de datos existente se migra sola al guardar los montos en centavos. Antes de migrar se genera una copia de seguridad en `data/control_financiero.db.bak`. Si algo sale mal, cierra la aplicación y sustituye `control_financiero.db` por esa copia.

Para hacer una copia manual, cierra la aplicación y copia ese archivo a otra ubicación. Para restaurarla, reemplaza el archivo por la copia guardada.

## Ejecutar las pruebas

Instala las dependencias de desarrollo y ejecuta pytest:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Crear un ejecutable para Windows

Dentro del entorno virtual instala PyInstaller:

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name ControlFinancieroPro --collect-all customtkinter main.py
```

El ejecutable aparecerá en `dist/ControlFinancieroPro/`. Se recomienda distribuir la carpeta completa generada por PyInstaller.

## Uso básico

1. Abre Configuración y establece el saldo inicial, las metas y el año.
2. Registra cada operación en Movimientos.
3. Abre el Panel y selecciona el periodo que deseas analizar.
4. Exporta los registros a CSV cuando necesites una copia externa.
