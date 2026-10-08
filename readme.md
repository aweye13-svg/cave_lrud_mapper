# Cave LRUD 2D/3D Mapper (QGIS Plugin)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![QGIS Version](https://img.shields.io/badge/QGIS-3.22+-green.svg)](https://qgis.org)

**Cave LRUD 2D/3D Mapper** is an automated speleological spatial analysis plugin for QGIS. It parses tabular cave survey measurements (distance, azimuth, inclination, and Left-Right-Up-Down cross-sectional bounds) referenced from an entrance GPS datum.

The plugin resolves complex branching topologies and survey loops, dynamically generating:
1. **2D Passage Footprints (`Polygon`)**: Planimetric conduit polygons with fully populated WGS84 coordinates for all wall corners and stations.
2. **3D Centerlines (`LineStringZ`)**: Subsurface 3D spatial polylines storing tape distances, bearings, and inclinations.
3. **3D Station Profiles (`PointZ`)**: Profile nodes indicating ceiling, floor, left wall, and right wall boundaries.
4. **Native Shaded 3D Octagonal Conduit Mesh (`PolygonZ`)**: Continuous 8-sided passage volumes with 2-pass corner rounding ($\ge 20^\circ$) rendered natively in the QGIS 3D Canvas.
5. **Universal Global UTM Auto-Detection**: Automatically identifies the local UTM projection zone and hemisphere anywhere on Earth from the entrance coordinates.
6. **Wavefront OBJ 3D Model (`.obj`)**: Auto-exported 3D mesh ready for Blender, CloudCompare, or 3D web viewers.

---

## Installation

### Method A: From the Official QGIS Plugin Repository
1. In QGIS, navigate to **Plugins** > **Manage and Install Plugins...**
2. Search for **Cave LRUD 2D/3D Mapper**.
3. Click **Install Plugin**.

### Method B: Manual Installation (ZIP)
1. Download or clone this repository.
2. Ensure the root folder is named `cave_lrud_mapper`.
3. Copy the folder to your QGIS active profile python plugins directory:
   * **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   * **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   * **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
4. Restart QGIS or use **Plugin Reloader**, then enable the plugin under **Plugins** > **Installed**.

---

## CSV Data Schema & Required Units

You can generate a blank, annotated CSV template directly inside QGIS by selecting **Cave Survey** > **Save Sample Survey CSV Template...**.

### Units Specification

| Column | Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `from_station` | Text | — | Origin survey station name |
| `to_station` | Text | — | Destination survey station name |
| `length_m` | Numeric | Meters ($m$) | Shot distance along tape/disto |
| `bearing_deg` | Numeric | Decimal Degrees ($0.0^\circ - 360.0^\circ$) | Compass azimuth ($0^\circ$ = North, $90^\circ$ = East) |
| `inc_deg` | Numeric | Decimal Degrees ($-90.0^\circ$ to $+90.0^\circ$) | Clinometer angle ($0^\circ$ = level, negative = downward pitch) |
| `left_m` | Numeric | Meters ($m$) | Left passage wall clearance (Defaults to 2 ft / 0.61 m dia if blank) |
| `right_m` | Numeric | Meters ($m$) | Right passage wall clearance (Defaults to 2 ft / 0.61 m dia if blank) |
| `up_m` | Numeric | Meters ($m$) | Ceiling clearance above station (Defaults to 2 ft / 0.61 m dia if blank) |
| `down_m` | Numeric | Meters ($m$) | Floor depth below station (Defaults to 2 ft / 0.61 m dia if blank) |
| `lat_or_y` | Numeric | Degrees or Meters | **Entrance Station only (Row 1)**: WGS84 Latitude or Projected Northing |
| `lon_or_x` | Numeric | Degrees or Meters | **Entrance Station only (Row 1)**: WGS84 Longitude or Projected Easting |
| `alt_m` | Numeric | Meters (masl) | **Entrance Station only (Row 1)**: Altitude above sea level |
| `crs` | Text | EPSG Code | **Optional**: Coordinate system (e.g., `EPSG:4326`, `EPSG:32650`) |

### Example CSV (`survey.csv`)

```csv
from_station,to_station,length_m,bearing_deg,inc_deg,left_m,right_m,up_m,down_m,lat_or_y,lon_or_x,alt_m,crs
A0,A1,5.13,324.0,-45.0,1.72,2.11,9.64,1.00,10.08023333,118.8484167,94.0,EPSG:4326
A1,A2,8.08,342.5,-47.0,7.19,2.87,6.02,1.00,,,,
A2,A3,4.30,272.0,-22.0,2.93,1.90,12.23,1.00,,,,
A3,A4,2.67,255.0,13.0,2.56,4.93,11.57,1.00,,,,
# Branch shot off A2
A2,B1,3.52,282.0,-15.0,3.31,9.81,7.80,1.00,,,,
B1,B2,5.63,325.0,-10.0,2.05,4.71,12.82,1.00,,,,