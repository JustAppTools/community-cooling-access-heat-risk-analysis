"""Initialize the ArcGIS Pro project geodatabase and starter map.

Run with the ArcGIS Pro Python interpreter:
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" scripts\\setup_project.py
"""

from __future__ import annotations

from pathlib import Path

import arcpy


ROOT = Path(__file__).resolve().parents[1]
APRX_PATH = ROOT / "Community_Cooling_Access_Heat_Risk.aprx"
PROCESSED_DIR = ROOT / "data_processed"
GDB_NAME = "Community_Cooling_Access_Heat_Risk.gdb"
GDB_PATH = PROCESSED_DIR / GDB_NAME


def ensure_file_geodatabase() -> None:
    PROCESSED_DIR.mkdir(exist_ok=True)
    if not GDB_PATH.exists():
        arcpy.management.CreateFileGDB(str(PROCESSED_DIR), GDB_NAME)
        print(f"Created {GDB_PATH}")
    else:
        print(f"Found {GDB_PATH}")


def configure_project() -> None:
    if not APRX_PATH.exists():
        raise FileNotFoundError(f"Missing ArcGIS Pro project: {APRX_PATH}")

    aprx = arcpy.mp.ArcGISProject(str(APRX_PATH))
    aprx.defaultGeodatabase = str(GDB_PATH)

    existing_names = {m.name for m in aprx.listMaps()}
    if "Heat Risk and Cooling Access" not in existing_names:
        new_map = aprx.createMap("Heat Risk and Cooling Access", "MAP")
        try:
            new_map.addBasemap("Light Gray Canvas")
        except Exception as exc:
            print(f"Basemap was not added: {exc}")

    aprx.save()
    print(f"Configured {APRX_PATH}")


def main() -> None:
    arcpy.env.overwriteOutput = True
    ensure_file_geodatabase()
    configure_project()


if __name__ == "__main__":
    main()
