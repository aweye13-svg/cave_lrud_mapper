import csv
import math
import os
import shutil
import tempfile

from qgis.PyQt.QtWidgets import (
    QAction,
    QFileDialog,
    QMessageBox,
    QDialog,
    QMenu,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QPushButton,
    QScrollArea,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QListWidget,
    QListWidgetItem
)
from qgis.PyQt.QtGui import (
    QIcon,
    QColor,
    QFont,
    QImage,
    QPixmap,
    QPainter,
    QPen,
    QBrush,
    QPolygonF,
    QFontDatabase,
    QFontMetrics
)
from qgis.PyQt.QtCore import QMetaType, QRectF, Qt, QPointF

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsPluginLayer,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsLineString,
    QgsPolygon,
    QgsField,
    QgsVectorFileWriter,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMessageLog,
    Qgis,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLabel,
    QgsLayoutItemScaleBar,
    QgsLayoutItemPicture,
    QgsLayoutExporter,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings
)

try:
    from qgis._3d import (
        QgsVectorLayer3DRenderer,
        QgsLine3DSymbol,
        QgsPoint3DSymbol,
        QgsPolygon3DSymbol
    )
    HAS_3D = True
except ImportError:
    HAS_3D = False


NUM_SECTORS = 8
DEFAULT_RADIUS_M = (2.0 * 0.3048) / 2.0
CORNER_THRESHOLD_DEG = 20.0
CORNER_THRESHOLD_RAD = math.radians(CORNER_THRESHOLD_DEG)

SAMPLE_CSV_CONTENT = """# ==============================================================================================
# CAVE SURVEY DATA TEMPLATE (LRUD)
# ==============================================================================================
# COLUMN SPECIFICATIONS & UNITS:
#   from_station : Survey station name (Text)
#   to_station   : Target station name (Text)
#   length_m     : Shot tape distance in METERS (m)
#   bearing_deg  : Compass azimuth in DECIMAL DEGREES (0.0 to 360.0, 0 = North, 90 = East)
#   inc_deg      : Clinometer inclination in DECIMAL DEGREES (-90.0 down to +90.0 up, 0 = level)
#   left_m       : Left passage wall distance in METERS (m) [leave blank for default 2ft dia]
#   right_m      : Right passage wall distance in METERS (m) [leave blank for default 2ft dia]
#   up_m         : Roof clearance in METERS (m) [leave blank for default 2ft dia]
#   down_m       : Floor depth in METERS (m) [leave blank for default 2ft dia]
#   lat_or_y     : Entrance Y coordinate (WGS84 Latitude or Projected Northing) [Row 1 only]
#   lon_or_x     : Entrance X coordinate (WGS84 Longitude or Projected Easting) [Row 1 only]
#   alt_m        : Entrance elevation in METERS ABOVE SEA LEVEL (masl) [Row 1 only]
#   crs          : EPSG Code [Optional: auto-detected to local UTM zone if omitted]
# ==============================================================================================
from_station,to_station,length_m,bearing_deg,inc_deg,left_m,right_m,up_m,down_m,lat_or_y,lon_or_x,alt_m,crs
1,2,5.2,55.0,-80.0,0.0,0.7,8.0,2.0,10.897178,119.618872,5.0,EPSG:4326
2,3,3.3,55.0,-85.0,0.0,0.7,9.0,2.2,,,,
3,4,9.6,127.0,0.0,2.7,0.0,8.8,0.0,,,,
4,5,8.8,180.0,0.0,7.6,0.0,10.4,0.0,,,,
5,6,7.3,90.0,0.0,3.5,0.0,11.1,0.0,,,,
6,7,4.7,240.0,0.0,0.0,3.1,20.0,0.0,,,,
7,8,5.8,180.0,5.0,1.8,0.0,16.2,0.0,,,,
6,A,4.6,215.0,0.0,3.2,0.0,9.1,0.0,,,,
6,B,11.0,350.0,0.0,0.0,2.5,10.1,0.0,,,,
B,C,2.7,310.0,0.0,2.1,0.0,15.5,0.0,,,,
"""


class PlanStyleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select 2D Passage Style")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout_choice = QHBoxLayout()
        layout_choice.addWidget(QLabel("2D Plan View Type:"))
        self.combo_style = QComboBox()
        self.combo_style.addItems([
            "polygons",
            "filled polygons",
            "3d polygons",
            "shaded cylinders",
            "open spline curves",
            "filled spline curves",
            "artistic cave passage (experimental)"
        ])
        layout_choice.addWidget(self.combo_style)
        layout.addLayout(layout_choice)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_style(self):
        return self.combo_style.currentText()


class UnitExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Survey CSV - Select Units")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        layout_dist = QHBoxLayout()
        layout_dist.addWidget(QLabel("Distance / Passage Units:"))
        self.combo_dist = QComboBox()
        self.combo_dist.addItems(["Meters (m)", "Feet (ft)", "Inches (in)"])
        layout_dist.addWidget(self.combo_dist)
        layout.addLayout(layout_dist)

        layout_angle = QHBoxLayout()
        layout_angle.addWidget(QLabel("Bearing / Inclination Units:"))
        self.combo_angle = QComboBox()
        self.combo_angle.addItems(["Degrees (°)", "Gradians (grad / gon)"])
        layout_angle.addWidget(self.combo_angle)
        layout.addLayout(layout_angle)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_units(self):
        dist_map = {"Meters (m)": "m", "Feet (ft)": "ft", "Inches (in)": "in"}
        angle_map = {"Degrees (°)": "deg", "Gradians (grad / gon)": "grad"}
        return dist_map[self.combo_dist.currentText()], angle_map[self.combo_angle.currentText()]


class VectorizeRasterDialog(QDialog):
    def __init__(self, raster_layers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extract Passage from Georeferenced Sketch")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        layout_raster = QHBoxLayout()
        layout_raster.addWidget(QLabel("Select Georeferenced Layer:"))
        self.combo_raster = QComboBox()
        self.raster_layers = raster_layers
        for name in sorted(raster_layers.keys()):
            self.combo_raster.addItem(name)
        layout_raster.addWidget(self.combo_raster)
        layout.addLayout(layout_raster)

        layout_thresh = QHBoxLayout()
        layout_thresh.addWidget(QLabel("Background Darkness Threshold:"))
        self.spin_thresh = QSpinBox()
        self.spin_thresh.setRange(50, 254)
        self.spin_thresh.setValue(240)
        self.spin_thresh.setToolTip("Pixels with RGB values below this number are treated as cave wall strokes.")
        layout_thresh.addWidget(self.spin_thresh)
        layout.addLayout(layout_thresh)

        layout_simpl = QHBoxLayout()
        layout_simpl.addWidget(QLabel("Smoothing Tolerance (meters):"))
        self.spin_simpl = QDoubleSpinBox()
        self.spin_simpl.setRange(0.01, 5.0)
        self.spin_simpl.setSingleStep(0.05)
        self.spin_simpl.setValue(0.15)
        self.spin_simpl.setToolTip("Simplifies pixel stair-stepping using Douglas-Peucker algorithm.")
        layout_simpl.addWidget(self.spin_simpl)
        layout.addLayout(layout_simpl)

        layout_buff = QHBoxLayout()
        layout_buff.addWidget(QLabel("Survey Buffer Margin (meters):"))
        self.spin_buff = QDoubleSpinBox()
        self.spin_buff.setRange(1.0, 100.0)
        self.spin_buff.setValue(20.0)
        self.spin_buff.setToolTip("Clips out stray legend notes or border markings beyond this distance from centerline.")
        layout_buff.addWidget(self.spin_buff)
        layout.addLayout(layout_buff)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        selected_name = self.combo_raster.currentText()
        layer = self.raster_layers.get(selected_name)
        return (
            layer,
            self.spin_thresh.value(),
            self.spin_simpl.value(),
            self.spin_buff.value()
        )


class MapExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Cave Map to Image")
        self.setMinimumWidth(520)

        main_layout = QVBoxLayout(self)

        layout_name = QHBoxLayout()
        layout_name.addWidget(QLabel("Cave Name:"))
        self.txt_cave_name = QLineEdit("Elephant Cave")
        layout_name.addWidget(self.txt_cave_name)
        main_layout.addLayout(layout_name)

        layout_area = QHBoxLayout()
        layout_area.addWidget(QLabel("Area / Location:"))
        self.txt_area = QLineEdit("")
        self.txt_area.setPlaceholderText("e.g. Brgy. Cabayugan, Puerto Princesa City, Palawan")
        layout_area.addWidget(self.txt_area)
        main_layout.addLayout(layout_area)

        layout_surveyors = QHBoxLayout()
        layout_surveyors.addWidget(QLabel("Primary Surveyor:"))
        self.txt_surveyors = QLineEdit("PCSD Cave Assessment Team")
        layout_surveyors.addWidget(self.txt_surveyors)
        main_layout.addLayout(layout_surveyors)

        surveyor_header = QHBoxLayout()
        surveyor_header.addWidget(QLabel("<b>Additional Surveyors:</b>"))
        self.btn_add_surveyor = QPushButton("+")
        self.btn_add_surveyor.setToolTip("Add another surveyor")
        self.btn_add_surveyor.setFixedWidth(32)
        self.btn_add_surveyor.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_add_surveyor.clicked.connect(lambda: self.add_surveyor_row())
        surveyor_header.addWidget(self.btn_add_surveyor)
        surveyor_header.addStretch()
        main_layout.addLayout(surveyor_header)

        self.surveyors_container = QVBoxLayout()
        main_layout.addLayout(self.surveyors_container)
        self.surveyor_rows = []

        layout_view = QHBoxLayout()
        layout_view.addWidget(QLabel("View Mode:"))
        self.combo_view = QComboBox()
        self.combo_view.addItems(["Plan View (Top-Down)", "Profile View (Extended Elevation)"])
        layout_view.addWidget(self.combo_view)
        main_layout.addLayout(layout_view)

        main_layout.addWidget(QLabel("Select Layers to Underlay (beneath cave map):"))
        self.list_underlays = QListWidget()
        self.underlay_layers = {}

        internal_names = {"Cave Octagon Passage 3D", "Cave Centerline 3D", "Cave Stations"}
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() not in internal_names and not layer.name().startswith("Cave Passage 2D"):
                item = QListWidgetItem(
                    f"[{'Vector' if isinstance(layer, QgsVectorLayer) else 'Raster'}] {layer.name()}"
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.list_underlays.addItem(item)
                self.underlay_layers[item.text()] = layer

        if not self.underlay_layers:
            no_item = QListWidgetItem("No external vector/raster layers in project")
            no_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_underlays.addItem(no_item)

        main_layout.addWidget(self.list_underlays)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def add_surveyor_row(self, initial_text=""):
        if not isinstance(initial_text, str):
            initial_text = ""

        row_layout = QHBoxLayout()
        txt = QLineEdit(initial_text)
        txt.setPlaceholderText(f"Surveyor {len(self.surveyor_rows) + 2} name")
        row_layout.addWidget(txt)

        btn_remove = QPushButton("−")
        btn_remove.setToolTip("Remove this surveyor")
        btn_remove.setFixedWidth(30)
        btn_remove.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

        row_item = {"layout": row_layout, "widget": txt, "btn": btn_remove}
        self.surveyor_rows.append(row_item)

        btn_remove.clicked.connect(lambda: self.remove_surveyor_row(row_item))
        row_layout.addWidget(btn_remove)
        self.surveyors_container.addLayout(row_layout)

    def remove_surveyor_row(self, row_item):
        if row_item in self.surveyor_rows:
            self.surveyor_rows.remove(row_item)
            while row_item["layout"].count():
                child = row_item["layout"].takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.surveyors_container.removeItem(row_item["layout"])

    def get_data(self):
        selected_underlays = []
        for i in range(self.list_underlays.count()):
            item = self.list_underlays.item(i)
            if item.checkState() == Qt.CheckState.Checked and item.text() in self.underlay_layers:
                selected_underlays.append(self.underlay_layers[item.text()])

        all_surveyors = []
        primary = self.txt_surveyors.text().strip()
        if primary:
            all_surveyors.append(primary)

        for row in self.surveyor_rows:
            val = row["widget"].text().strip()
            if val:
                all_surveyors.append(val)

        return (
            self.txt_cave_name.text().strip(),
            self.txt_area.text().strip(),
            all_surveyors,
            self.combo_view.currentText(),
            selected_underlays
        )


class ImagePreviewDialog(QDialog):
    def __init__(self, render_callback, layer_items, title_desc="Map Preview", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview — {title_desc}")
        self.resize(1200, 760)

        self.render_callback = render_callback
        self.layer_items = layer_items
        self.scale_factor = 1.0

        self.export_settings = {
            "font_family": "Arial",
            "font_size": 11
        }

        main_layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_fit = QPushButton("Fit Window")
        self.lbl_zoom = QLabel("100%")

        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_fit.clicked.connect(self.fit_to_window)

        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.lbl_zoom)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        body_layout = QHBoxLayout()

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setStyleSheet("background-color: #2b2b2b;")
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.lbl_image)
        body_layout.addWidget(self.scroll_area, stretch=4)

        side_panel = QVBoxLayout()

        side_panel.addWidget(QLabel("<b>Layer Visibility:</b>"))
        self.layer_checkboxes = {}
        for lid, info in self.layer_items.items():
            chk = QCheckBox(info["name"])
            chk.setChecked(info["visible"])
            chk.toggled.connect(
                lambda checked, layer_id=lid: self.on_layer_toggled(layer_id, checked)
            )
            side_panel.addWidget(chk)
            self.layer_checkboxes[lid] = chk

        side_panel.addSpacing(14)
        side_panel.addWidget(QLabel("<b>Exported Image Font:</b>"))

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Style:"))
        self.combo_font = QComboBox()
        fonts = sorted(QFontDatabase().families())
        preferred = ["Arial", "Calibri", "Times New Roman", "Helvetica", "DejaVu Sans"]
        ordered_fonts = [f for f in preferred if f in fonts]
        ordered_fonts += [f for f in fonts if f not in ordered_fonts]
        self.combo_font.addItems(ordered_fonts or ["Arial"])
        if "Arial" in ordered_fonts:
            self.combo_font.setCurrentText("Arial")
        self.combo_font.currentTextChanged.connect(self.on_font_changed)
        font_row.addWidget(self.combo_font, stretch=1)
        side_panel.addLayout(font_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Size:"))
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 48)
        self.spin_font_size.setValue(11)
        self.spin_font_size.setSuffix(" pt")
        self.spin_font_size.valueChanged.connect(self.on_font_size_changed)
        size_row.addWidget(self.spin_font_size)
        side_panel.addLayout(size_row)

        font_note = QLabel(
            "Controls apply to the exported map title, area, surveyor information, "
            "and profile labels. Station labels retain their map-label styling."
        )
        font_note.setWordWrap(True)
        font_note.setStyleSheet("color: #666; font-style: italic;")
        side_panel.addWidget(font_note)

        side_panel.addStretch()
        body_layout.addLayout(side_panel, stretch=1)
        main_layout.addLayout(body_layout)

        bottom_bar = QHBoxLayout()
        info_lbl = QLabel(
            "ℹ Map boundaries are enclosed with a strict 0.25-inch outer margin."
        )
        info_lbl.setStyleSheet("color: #777; font-style: italic;")
        bottom_bar.addWidget(info_lbl)
        bottom_bar.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("Export & Save Image...")
        self.btn_export.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_export.clicked.connect(self.accept)
        bottom_bar.addWidget(self.btn_export)

        main_layout.addLayout(bottom_bar)

        self.current_preview_path = ""
        self.refresh_preview()

    def on_layer_toggled(self, layer_id, checked):
        if layer_id in self.layer_items:
            self.layer_items[layer_id]["visible"] = checked
            self.refresh_preview()

    def on_font_changed(self, family):
        self.export_settings["font_family"] = family
        self.refresh_preview()

    def on_font_size_changed(self, size):
        self.export_settings["font_size"] = int(size)
        self.refresh_preview()

    def refresh_preview(self):
        temp_dir = tempfile.gettempdir()
        self.current_preview_path = os.path.join(temp_dir, "live_preview_map.png")
        visible_layers = [
            info["layer"] for info in self.layer_items.values()
            if info["visible"]
        ]

        self.render_callback(
            self.current_preview_path,
            visible_layers,
            self.export_settings
        )
        self.original_pixmap = QPixmap(self.current_preview_path)
        self.update_zoom()

    def update_zoom(self):
        if not hasattr(self, "original_pixmap") or self.original_pixmap.isNull():
            return
        new_size = self.original_pixmap.size() * self.scale_factor
        scaled = self.original_pixmap.scaled(
            new_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_image.setPixmap(scaled)
        self.lbl_image.adjustSize()
        self.lbl_zoom.setText(f"{int(self.scale_factor * 100)}%")

    def zoom_in(self):
        self.scale_factor = min(self.scale_factor * 1.25, 4.0)
        self.update_zoom()

    def zoom_out(self):
        self.scale_factor = max(self.scale_factor / 1.25, 0.15)
        self.update_zoom()

    def fit_to_window(self):
        if not hasattr(self, "original_pixmap") or self.original_pixmap.isNull():
            return
        area_w = self.scroll_area.viewport().width() - 25
        area_h = self.scroll_area.viewport().height() - 25
        pix_w = self.original_pixmap.width()
        pix_h = self.original_pixmap.height()

        if pix_w > 0 and pix_h > 0:
            scale_w = area_w / pix_w
            scale_h = area_h / pix_h
            self.scale_factor = min(scale_w, scale_h, 1.0)
            self.update_zoom()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()


class CaveLRUDPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.menu = None
        self.action_import = None
        self.action_sample = None
        self.action_export_csv = None
        self.action_export_image = None
        self.action_vectorize = None
        self.active_centerline_layer = None
        self.active_passage_layer = None
        self.active_stations_layer = None
        self.active_tube_layer = None
        self.stations = {}
        self.traverse_order = []
        self._is_updating = False

    def _get_action_icon(self, filename, fallback_theme_name=""):
        plugin_dir = os.path.dirname(__file__)
        path = os.path.join(plugin_dir, filename)
        if os.path.exists(path):
            return QIcon(path)
        if fallback_theme_name and hasattr(QgsApplication, "getThemeIcon"):
            return QgsApplication.getThemeIcon(fallback_theme_name)
        return QIcon()

    def initGui(self):
        plugin_dir = os.path.dirname(__file__)
        main_icon_path = os.path.join(plugin_dir, "icon.svg")
        main_icon = QIcon(main_icon_path) if os.path.exists(main_icon_path) else QIcon()

        self.menu = QMenu("&Cave Survey", self.iface.mainWindow())
        self.menu.setIcon(main_icon)

        # 1. Import Cave Survey
        icon_import = self._get_action_icon("icon.svg", "mActionAddOgrLayer.svg")
        self.action_import = QAction(icon_import, "Import Cave Survey (LRUD)", self.iface.mainWindow())
        self.action_import.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action_import)
        self.menu.addAction(self.action_import)

        # 2. Extract Passage from Georeferenced Sketch
        icon_vectorize = self._get_action_icon("icon_extract.svg", "mActionPolygon.svg")
        self.action_vectorize = QAction(icon_vectorize, "Extract Passage from Georeferenced Sketch...", self.iface.mainWindow())
        self.action_vectorize.triggered.connect(self.run_vectorize_sketch)
        self.iface.addToolBarIcon(self.action_vectorize)
        self.menu.addAction(self.action_vectorize)

        # 3. Save Sample Survey CSV Template
        icon_sample = self._get_action_icon("icon_template.svg", "mActionFileSave.svg")
        self.action_sample = QAction(icon_sample, "Save Sample Survey CSV Template...", self.iface.mainWindow())
        self.action_sample.triggered.connect(self.save_sample_csv)
        self.menu.addAction(self.action_sample)

        # 4. Export Edited Layers to CSV
        icon_csv = self._get_action_icon("icon_export_csv.svg", "mActionSaveEdits.svg")
        self.action_export_csv = QAction(icon_csv, "Export Edited Layers to CSV...", self.iface.mainWindow())
        self.action_export_csv.triggered.connect(self.export_edited_csv)
        self.menu.addAction(self.action_export_csv)

        # 5. Export Map as Image
        icon_image = self._get_action_icon("icon_export_map.svg", "mActionSaveMapAsImage.svg")
        self.action_export_image = QAction(icon_image, "Export Map as Image (Plan/Profile)...", self.iface.mainWindow())
        self.action_export_image.triggered.connect(self.export_map_image)
        self.iface.addToolBarIcon(self.action_export_image)
        self.menu.addAction(self.action_export_image)

        self.iface.pluginMenu().addMenu(self.menu)

    def unload(self):
        self.iface.removePluginMenu("&Cave Survey", self.action_import)
        self.iface.removePluginMenu("&Cave Survey", self.action_vectorize)
        self.iface.removePluginMenu("&Cave Survey", self.action_sample)
        self.iface.removePluginMenu("&Cave Survey", self.action_export_csv)
        self.iface.removePluginMenu("&Cave Survey", self.action_export_image)

        self.iface.removeToolBarIcon(self.action_import)
        self.iface.removeToolBarIcon(self.action_vectorize)
        self.iface.removeToolBarIcon(self.action_export_image)

        if self.menu:
            self.iface.pluginMenu().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

    def save_sample_csv(self):
        default_path = os.path.join(os.path.expanduser("~"), "cave_survey_template.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Annotated Survey CSV Template", default_path, "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_CSV_CONTENT)
            QMessageBox.information(None, "Template Saved", f"Template saved to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to save template:\n{str(e)}")

    def run(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select Cave Survey CSV", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        csv_dir = os.path.dirname(os.path.abspath(file_path))
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_folder = os.path.join(csv_dir, base_name)

        if os.path.exists(output_folder) and os.listdir(output_folder):
            reply = QMessageBox.question(
                None,
                "Overwrite Existing Files?",
                f"Output directory already exists:\n{output_folder}\n\n"
                f"Existing cave layers and 3D OBJ will be replaced. Do you want to overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        os.makedirs(output_folder, exist_ok=True)

        style_dlg = PlanStyleDialog(self.iface.mainWindow())
        if style_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen_style = style_dlg.get_style()

        try:
            obj_path, v_count, f_count = self.process_cave_data(file_path, chosen_style, output_folder)
            QMessageBox.information(
                None, "Complete",
                f"Survey Processed & Saved Permanently!\n\n"
                f"• Output Folder: {output_folder}\n"
                f"• 2D Plan Style: {chosen_style}\n"
                f"• 4 Permanent Layers: Saved as GeoPackages\n"
                f"• OBJ Mesh exported: {obj_path}\n"
                f"Vertices: {v_count} | Faces: {f_count}"
            )
        except Exception as e:
            QMessageBox.critical(None, "Processing Error", f"Failed to parse survey:\n{str(e)}")

    def run_vectorize_sketch(self):
        rasters = {}
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsRasterLayer) and lyr.isValid():
                rasters[lyr.name()] = lyr

        if not rasters:
            QMessageBox.warning(
                None, "No Raster Layer",
                "Please georeference and load your manual sketch raster (TIFF/PNG/PDF/SVG) into QGIS first."
            )
            return

        dlg = VectorizeRasterDialog(rasters, self.iface.mainWindow())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        layer, threshold_val, simpl_tol, buff_margin = dlg.get_data()
        if not layer:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            None, "Save Vectorized Cave Passage (.gpkg)",
            os.path.join(os.path.dirname(layer.source()), f"{layer.name()}_vector_passage.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not save_path:
            return

        try:
            out_layer = self.vectorize_georeferenced_sketch(
                raster_layer=layer,
                output_path=save_path,
                threshold=threshold_val,
                simplify_tolerance=simpl_tol,
                buffer_dist=buff_margin
            )
            QMessageBox.information(
                None, "Extraction Complete",
                f"Cave passage outline successfully extracted and saved:\n{save_path}\n\n"
                f"Features Created: {out_layer.featureCount()}"
            )
        except Exception as e:
            QMessageBox.critical(None, "Extraction Error", f"Failed to vectorize raster sketch:\n{str(e)}")

    def vectorize_georeferenced_sketch(self, raster_layer, output_path, threshold=240, simplify_tolerance=0.15, buffer_dist=20.0, fill_passage_interior=True):
        from osgeo import gdal, ogr, osr
        import numpy as np
        from collections import deque

        if not raster_layer or not raster_layer.isValid():
            raise ValueError("Invalid raster layer selected.")

        source_path = raster_layer.source()
        ds = gdal.Open(source_path)
        if not ds:
            raise RuntimeError(f"GDAL could not open raster source: {source_path}")

        cols = ds.RasterXSize
        rows = ds.RasterYSize
        num_bands = ds.RasterCount

        red = ds.GetRasterBand(1).ReadAsArray()
        green = ds.GetRasterBand(2).ReadAsArray() if num_bands >= 2 else red
        blue = ds.GetRasterBand(3).ReadAsArray() if num_bands >= 3 else red
        alpha = ds.GetRasterBand(4).ReadAsArray() if num_bands >= 4 else None

        is_ink = (red < threshold) | (green < threshold) | (blue < threshold)
        if alpha is not None:
            is_ink = is_ink & (alpha > 10)

        binary_grid = np.zeros((rows, cols), dtype=np.uint8)

        if fill_passage_interior:
            h, w = is_ink.shape
            visited = np.zeros((h, w), dtype=bool)
            q = deque()

            for c in range(w):
                if not is_ink[0, c]:
                    q.append((0, c))
                    visited[0, c] = True
                if not is_ink[h - 1, c]:
                    q.append((h - 1, c))
                    visited[h - 1, c] = True
            for r in range(h):
                if not is_ink[r, 0]:
                    q.append((r, 0))
                    visited[r, 0] = True
                if not is_ink[r, w - 1]:
                    q.append((r, w - 1))
                    visited[r, w - 1] = True

            while q:
                cr, cc = q.popleft()
                for nr, nc in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
                    if 0 <= nr < h and 0 <= nc < w:
                        if not visited[nr, nc] and not is_ink[nr, nc]:
                            visited[nr, nc] = True
                            q.append((nr, nc))

            binary_grid = np.where(~visited, 1, 0).astype(np.uint8)
        else:
            binary_grid = np.where(is_ink, 1, 0).astype(np.uint8)

        driver_mem = gdal.GetDriverByName('MEM')
        mem_ds = driver_mem.Create('', cols, rows, 1, gdal.GDT_Byte)
        mem_ds.SetGeoTransform(ds.GetGeoTransform())
        mem_ds.SetProjection(ds.GetProjection())
        mem_band = mem_ds.GetRasterBand(1)
        mem_band.WriteArray(binary_grid)

        ogr_driver = ogr.GetDriverByName('Memory')
        ogr_ds = ogr_driver.CreateDataSource('mem_cave_outline')
        srs = osr.SpatialReference()
        srs.ImportFromWkt(ds.GetProjection())
        out_layer = ogr_ds.CreateLayer('passage_raw', srs, ogr.wkbPolygon)

        fd = ogr.FieldDefn('val', ogr.OFTInteger)
        out_layer.CreateField(fd)
        gdal.Polygonize(mem_band, None, out_layer, 0, [], callback=None)

        raster_crs = QgsCoordinateReferenceSystem(raster_layer.crs().authid())
        centerline_geom = None

        if self.active_centerline_layer and self.active_centerline_layer.isValid():
            cl_crs = self.active_centerline_layer.crs()
            transform_to_raster = QgsCoordinateTransform(cl_crs, raster_crs, QgsProject.instance())

            cl_feats = list(self.active_centerline_layer.getFeatures())
            if cl_feats:
                buffered_geoms = []
                for f in cl_feats:
                    g = f.geometry()
                    if cl_crs != raster_crs:
                        g.transform(transform_to_raster)
                    buf_val = buffer_dist if not raster_crs.isGeographic() else (buffer_dist / 111320.0)
                    buffered_geoms.append(g.buffer(buf_val, 6))

                centerline_geom = QgsGeometry.unaryUnion(buffered_geoms)

        cleaned_layer = QgsVectorLayer(f"Polygon?crs={raster_crs.authid()}", "Extracted Cave Outline", "memory")
        pr = cleaned_layer.dataProvider()

        new_features = []
        for i in range(out_layer.GetFeatureCount()):
            feat = out_layer.GetFeature(i)
            if feat.GetField('val') == 1:
                geom_wkt = feat.GetGeometryRef().ExportToWkt()
                qgs_geom = QgsGeometry.fromWkt(geom_wkt)

                if qgs_geom.isEmpty():
                    continue

                if centerline_geom and not qgs_geom.intersects(centerline_geom):
                    continue

                if simplify_tolerance > 0.0:
                    tol = simplify_tolerance if not raster_crs.isGeographic() else (simplify_tolerance / 111320.0)
                    qgs_geom = qgs_geom.simplify(tol)

                new_feat = QgsFeature()
                new_feat.setGeometry(qgs_geom)
                new_features.append(new_feat)

        if not new_features:
            raise RuntimeError(
                "No passage geometry could be detected.\n\n"
                "Possible reasons:\n"
                "1. Threshold is too strict (try adjusting the darkness threshold).\n"
                "2. The survey buffer margin is too narrow.\n"
                "3. The raster layer does not overlap with the survey stations."
            )

        pr.addFeatures(new_features)

        final_disk_layer = self._save_memory_layer_to_disk(
            cleaned_layer, output_path, "Extracted Manual Passage"
        )
        self._apply_2d_style(final_disk_layer, "filled polygons")
        QgsProject.instance().addMapLayer(final_disk_layer)

        return final_disk_layer

    def _get_val(self, row, aliases, default=None):
        for a in aliases:
            if a in row and row[a] != '':
                return row[a]
        return default

    def _safe_dim(self, raw_val):
        try:
            val = float(raw_val)
            return val if val > 0.0 else DEFAULT_RADIUS_M
        except (ValueError, TypeError):
            return DEFAULT_RADIUS_M

    def _get_local_utm_crs(self, lon, lat):
        zone = int(math.floor((lon + 180.0) / 6.0)) + 1
        epsg_code = 32600 + zone if lat >= 0 else 32700 + zone
        return QgsCoordinateReferenceSystem(f"EPSG:{epsg_code}")

    def process_cave_data(self, file_path, plan_style="polygons", output_folder=None):
        shots = []
        entrance_coords = None
        entrance_crs_str = None
        root_station = None

        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for raw_row in reader:
                if not raw_row or not any(raw_row.values()):
                    continue
                row = {k.strip(): (v.strip() if v else '') for k, v in raw_row.items() if k}
                from_st = self._get_val(row, ['from_station', 'from', 'station_from'])
                to_st = self._get_val(row, ['to_station', 'to', 'station_to'])

                if not from_st or from_st.startswith('#') or not to_st:
                    continue

                shots.append(row)

                lat_y = self._get_val(row, ['lat_or_y', 'lat', 'y', 'latitude', 'northing'])
                lon_x = self._get_val(row, ['lon_or_x', 'lon', 'long', 'x', 'longitude', 'easting'])
                alt = self._get_val(row, ['alt_m', 'alt', 'elevation', 'z'], 0.0)
                crs_col = self._get_val(row, ['crs', 'epsg', 'srs'])

                if entrance_coords is None and lat_y and lon_x:
                    entrance_coords = (float(lon_x), float(lat_y), float(alt) if alt != '' else 0.0)
                    entrance_crs_str = crs_col
                    root_station = from_st

        if not entrance_coords:
            raise ValueError("Entrance station must specify coordinates (lat_or_y and lon_or_x).")

        if not output_folder:
            csv_dir = os.path.dirname(os.path.abspath(file_path))
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_folder = os.path.join(csv_dir, base_name)
            os.makedirs(output_folder, exist_ok=True)

        project_crs = QgsProject.instance().crs()
        is_geographic_input = (abs(entrance_coords[0]) <= 180.0 and abs(entrance_coords[1]) <= 90.0)

        if not project_crs.isValid() or project_crs.isGeographic():
            if is_geographic_input:
                project_crs = self._get_local_utm_crs(entrance_coords[0], entrance_coords[1])
            else:
                project_crs = QgsCoordinateReferenceSystem(entrance_crs_str.upper()) if entrance_crs_str else project_crs
            QgsProject.instance().setCrs(project_crs)

        if entrance_crs_str:
            src_crs = QgsCoordinateReferenceSystem(entrance_crs_str.upper())
        else:
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326") if is_geographic_input else project_crs

        transform_to_proj = QgsCoordinateTransform(src_crs, project_crs, QgsProject.instance())
        start_pt = transform_to_proj.transform(QgsPointXY(entrance_coords[0], entrance_coords[1]))

        self.stations = {}
        self.traverse_order = [root_station]

        first_shot = shots[0]
        f_left = self._safe_dim(self._get_val(first_shot, ['left_m', 'left', 'l']))
        f_right = self._safe_dim(self._get_val(first_shot, ['right_m', 'right', 'r']))
        f_up = self._safe_dim(self._get_val(first_shot, ['up_m', 'up', 'u']))
        f_down = self._safe_dim(self._get_val(first_shot, ['down_m', 'down', 'd']))

        raw_az = self._get_val(first_shot, ['bearing_deg', 'bearing', 'azimuth', 'az'])
        raw_cl = self._get_val(first_shot, ['inc_deg', 'inc', 'clino', 'inclination'])
        init_az = math.radians(float(raw_az)) if raw_az else 0.0
        init_cl = math.radians(float(raw_cl)) if raw_cl else 0.0

        self.stations[root_station] = (start_pt.x(), start_pt.y(), entrance_coords[2], f_left, f_right, f_up, f_down, init_az, init_cl)

        unresolved = list(shots)
        max_loops = len(shots) * 6
        loop_counter = 0

        while unresolved and loop_counter < max_loops:
            loop_counter += 1
            shot = unresolved.pop(0)
            u = self._get_val(shot, ['from_station', 'from', 'station_from'])
            v = self._get_val(shot, ['to_station', 'to', 'station_to'])

            if u in self.stations:
                fx, fy, fz, _, _, _, _, _, _ = self.stations[u]

                raw_len = self._get_val(shot, ['length_m', 'length', 'dist'])
                raw_az = self._get_val(shot, ['bearing_deg', 'bearing', 'azimuth', 'az'])
                raw_cl = self._get_val(shot, ['inc_deg', 'inc', 'clino', 'inclination'])

                if raw_len in (None, '', '0', 0):
                    raise ValueError(f"Shot '{u} -> {v}' is missing surveyed tape length (length_m).")

                length = float(raw_len)
                az_deg = float(raw_az) if raw_az not in (None, '') else 0.0
                cl_deg = float(raw_cl) if raw_cl not in (None, '') else 0.0

                az_rad = math.radians(az_deg)
                cl_rad = math.radians(cl_deg)

                dx = length * math.cos(cl_rad) * math.sin(az_rad)
                dy = length * math.cos(cl_rad) * math.cos(az_rad)
                dz = length * math.sin(cl_rad)

                left = self._safe_dim(self._get_val(shot, ['left_m', 'left', 'l']))
                right = self._safe_dim(self._get_val(shot, ['right_m', 'right', 'r']))
                up = self._safe_dim(self._get_val(shot, ['up_m', 'up', 'u']))
                down = self._safe_dim(self._get_val(shot, ['down_m', 'down', 'd']))

                if v not in self.stations:
                    self.stations[v] = (fx + dx, fy + dy, fz + dz, left, right, up, down, az_rad, cl_rad)
                    self.traverse_order.append(v)
            else:
                unresolved.append(shot)

        incoming_shot = {}
        for s in shots:
            incoming_shot[s['to_station']] = s

        layers = self._create_layers(shots, self.stations, incoming_shot, project_crs, plan_style, output_folder)
        self.active_tube_layer = layers[0]
        self.active_centerline_layer = layers[1]
        self.active_passage_layer = layers[2]
        self.active_stations_layer = layers[3]

        self.active_centerline_layer.geometryChanged.connect(self._on_centerline_geometry_changed)

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        obj_file_path = os.path.join(output_folder, f"{base_name}_octagon_conduit.obj")

        v_count, f_count = self._export_3d_obj(shots, self.stations, incoming_shot, obj_file_path)
        self._launch_3d_view(layers)

        return obj_file_path, v_count, f_count

    def _catmull_rom_spline(self, pts, num_points_per_seg=10):
        if len(pts) < 2:
            return pts

        extended = [pts[0]] + list(pts) + [pts[-1]]
        result = []

        for i in range(1, len(extended) - 2):
            p0 = extended[i - 1]
            p1 = extended[i]
            p2 = extended[i + 1]
            p3 = extended[i + 2]

            for step in range(num_points_per_seg):
                t = float(step) / float(num_points_per_seg)
                t2 = t * t
                t3 = t2 * t

                x = 0.5 * (
                    (2.0 * p1.x()) +
                    (-p0.x() + p2.x()) * t +
                    (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2 +
                    (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
                )
                y = 0.5 * (
                    (2.0 * p1.y()) +
                    (-p0.y() + p2.y()) * t +
                    (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2 +
                    (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
                )
                result.append(QgsPointXY(x, y))

        result.append(pts[-1])
        return result

    def _build_artistic_passage_envelope(self, fl_pt, tl_pt, tr_pt, fr_pt, seed_val=42):
        def fract_edge(p_start, p_end, sub_segs=8, max_scallop=0.35, edge_id=0):
            edge_pts = [p_start]
            vx = p_end.x() - p_start.x()
            vy = p_end.y() - p_start.y()
            length = math.hypot(vx, vy)
            if length == 0:
                return edge_pts

            ux = -vy / length
            uy = vx / length

            for s in range(1, sub_segs):
                t = float(s) / float(sub_segs)
                base_x = p_start.x() + vx * t
                base_y = p_start.y() + vy * t
                pseudo_jitter = (math.sin(t * 13.0 * math.pi + seed_val + edge_id) * 0.15) * max_scallop
                offset = math.sin(t * math.pi * 3.0) * (max_scallop * 0.7) + pseudo_jitter
                edge_pts.append(QgsPointXY(base_x + ux * offset, base_y + uy * offset))

            edge_pts.append(p_end)
            return edge_pts

        wall_left = fract_edge(fl_pt, tl_pt, edge_id=1)
        wall_front = [tr_pt]
        wall_right = fract_edge(tr_pt, fr_pt, edge_id=2)
        wall_back = [fl_pt]

        return wall_left + wall_front + wall_right + wall_back

    def _generate_octagon_ring(self, cx, cy, cz, left, right, up, down, az):
        ring = []
        for i in range(NUM_SECTORS):
            angle = (2.0 * math.pi * i) / float(NUM_SECTORS)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            rad_h = right if cos_a >= 0 else left
            rad_v = up if sin_a >= 0 else down

            local_x = rad_h * cos_a
            local_z = rad_v * sin_a

            wx = cx + local_x * math.cos(az)
            wy = cy - local_x * math.sin(az)
            wz = cz + local_z

            ring.append(QgsPoint(wx, wy, wz))
        return ring

    def _get_two_pass_rings(self, u_data, v_data, in_shot):
        x1, y1, z1, l1, r1, u1, d1, az1, cl1 = u_data
        x2, y2, z2, l2, r2, u2, d2, az2, cl2 = v_data

        ring_u = self._generate_octagon_ring(x1, y1, z1, l1, r1, u1, d1, az1)
        ring_v = self._generate_octagon_ring(x2, y2, z2, l2, r2, u2, d2, az2)

        has_bend = False
        if in_shot:
            raw_prev = in_shot.get('azimuth') or in_shot.get('bearing_deg')
            if raw_prev:
                prev_az = math.radians(float(raw_prev))
                angle_diff = abs((az1 - prev_az + math.pi) % (2.0 * math.pi) - math.pi)
                if angle_diff >= CORNER_THRESHOLD_RAD:
                    has_bend = True

        if not has_bend:
            return [ring_u, ring_v]

        subdivided_rings = [ring_u]
        for t in [0.25, 0.75]:
            ix = x1 + (x2 - x1) * t
            iy = y1 + (y2 - y1) * t
            iz = z1 + (z2 - z1) * t

            il = l1 + (l2 - l1) * t
            ir = r1 + (r2 - r1) * t
            iu = u1 + (u2 - u1) * t
            id_ = d1 + (d2 - d1) * t
            iaz = az1 + (az2 - az1) * t

            subdivided_rings.append(self._generate_octagon_ring(ix, iy, iz, il, ir, iu, id_, iaz))

        subdivided_rings.append(ring_v)
        return subdivided_rings

    def _enable_station_labels(self, layer, field_name="station"):
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        text_format.setColor(QColor(20, 20, 20))

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.4)
        buffer_settings.setColor(QColor(255, 255, 255, 240))
        text_format.setBuffer(buffer_settings)

        pal_settings = QgsPalLayerSettings()
        pal_settings.setFormat(text_format)
        pal_settings.fieldName = field_name
        pal_settings.isExpression = False
        pal_settings.placement = QgsPalLayerSettings.Placement.AroundPoint

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_settings))
        layer.setLabelsEnabled(True)

    def _save_memory_layer_to_disk(self, mem_layer, target_path, layer_name):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

        transform_context = QgsProject.instance().transformContext()
        res = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem_layer,
            target_path,
            transform_context,
            options
        )
        error = res[0]
        error_msg = res[1]

        if error != QgsVectorFileWriter.WriterError.NoError:
            raise RuntimeError(f"Failed to save layer '{layer_name}' to disk: {error_msg}")

        disk_layer = QgsVectorLayer(target_path, layer_name, "ogr")
        if not disk_layer.isValid():
            raise RuntimeError(f"Could not load saved permanent layer from {target_path}")
        return disk_layer

    def _create_layers(self, shots, stations, incoming_shot, crs, plan_style="polygons", output_folder=""):
        crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        proj_to_wgs = QgsCoordinateTransform(crs, crs_wgs84, QgsProject.instance())

        def to_wgs84(px, py):
            pt_wgs = proj_to_wgs.transform(QgsPointXY(px, py))
            return round(pt_wgs.y(), 8), round(pt_wgs.x(), 8)

        tube_layer_mem = QgsVectorLayer(f"PolygonZ?crs={crs.authid()}", "Cave Octagon Passage 3D", "memory")
        tube_pr = tube_layer_mem.dataProvider()
        tube_pr.addAttributes([
            QgsField("segment", QMetaType.Type.QString),
            QgsField("facet", QMetaType.Type.Int),
            QgsField("from_st", QMetaType.Type.QString),
            QgsField("to_st", QMetaType.Type.QString)
        ])
        tube_layer_mem.updateFields()

        tube_features = []
        for s in shots:
            u = self._get_val(s, ['from_station', 'from', 'station_from'])
            v = self._get_val(s, ['to_station', 'to', 'station_to'])
            if u in stations and v in stations:
                rings = self._get_two_pass_rings(stations[u], stations[v], incoming_shot.get(u))

                for r_idx in range(len(rings) - 1):
                    ru = rings[r_idx]
                    rv = rings[r_idx + 1]

                    for i in range(NUM_SECTORS):
                        next_i = (i + 1) % NUM_SECTORS
                        u_pt1 = ru[i]
                        u_pt2 = ru[next_i]
                        v_pt1 = rv[i]
                        v_pt2 = rv[next_i]

                        quad_ring = QgsLineString([u_pt1, v_pt1, v_pt2, u_pt2, u_pt1])
                        poly = QgsPolygon()
                        poly.setExteriorRing(quad_ring)

                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry(poly))
                        feat.setAttributes([f"{u}->{v}", i, u, v])
                        tube_features.append(feat)

        tube_pr.addFeatures(tube_features)

        centerline_layer_mem = QgsVectorLayer(f"LineStringZ?crs={crs.authid()}", "Cave Centerline 3D", "memory")
        cl_pr = centerline_layer_mem.dataProvider()
        cl_pr.addAttributes([
            QgsField("from_st", QMetaType.Type.QString),
            QgsField("to_st", QMetaType.Type.QString),
            QgsField("length_m", QMetaType.Type.Double),
            QgsField("bearing_deg", QMetaType.Type.Double),
            QgsField("inc_deg", QMetaType.Type.Double)
        ])
        centerline_layer_mem.updateFields()

        cl_features = []
        for s in shots:
            u = self._get_val(s, ['from_station', 'from', 'station_from'])
            v = self._get_val(s, ['to_station', 'to', 'station_to'])
            if u in stations and v in stations:
                p1 = stations[u]
                p2 = stations[v]
                geom = QgsGeometry.fromPolyline([
                    QgsPoint(p1[0], p1[1], p1[2]),
                    QgsPoint(p2[0], p2[1], p2[2])
                ])

                length = float(self._get_val(s, ['length_m', 'length', 'dist']))
                az = round(math.degrees(stations[v][7]), 1)
                inc = round(math.degrees(stations[v][8]), 1)

                feat = QgsFeature()
                feat.setGeometry(geom)
                feat.setAttributes([u, v, length, az, inc])
                cl_features.append(feat)
        cl_pr.addFeatures(cl_features)

        geom_type = "LineString" if plan_style == "open spline curves" else ("PolygonZ" if plan_style == "3d polygons" else "Polygon")
        layer_title = f"Cave Passage 2D ({plan_style.title()})"
        passage_layer_mem = QgsVectorLayer(f"{geom_type}?crs={crs.authid()}", layer_title, "memory")
        pl_pr = passage_layer_mem.dataProvider()
        pl_pr.addAttributes([
            QgsField("segment", QMetaType.Type.QString),
            QgsField("from_st", QMetaType.Type.QString),
            QgsField("to_st", QMetaType.Type.QString),
            QgsField("from_lat", QMetaType.Type.Double),
            QgsField("from_lon", QMetaType.Type.Double),
            QgsField("to_lat", QMetaType.Type.Double),
            QgsField("to_lon", QMetaType.Type.Double)
        ])
        passage_layer_mem.updateFields()

        poly_features = []

        if "spline" in plan_style:
            left_chain = []
            right_chain = []
            chain_stations = [st for st in self.traverse_order if st in stations]

            for st_name in chain_stations:
                cx, cy, _, l_dist, r_dist, _, _, s_az, _ = stations[st_name]
                left_chain.append(QgsPointXY(cx - l_dist * math.cos(s_az), cy + l_dist * math.sin(s_az)))
                right_chain.append(QgsPointXY(cx + r_dist * math.cos(s_az), cy - r_dist * math.sin(s_az)))

            spline_left = self._catmull_rom_spline(left_chain, 12)
            spline_right = self._catmull_rom_spline(right_chain, 12)

            if plan_style == "open spline curves":
                f_left_line = QgsFeature()
                f_left_line.setGeometry(QgsGeometry.fromPolylineXY(spline_left))
                f_left_line.setAttributes(["Left Wall Spline", "", "", 0, 0, 0, 0])
                poly_features.append(f_left_line)

                f_right_line = QgsFeature()
                f_right_line.setGeometry(QgsGeometry.fromPolylineXY(spline_right))
                f_right_line.setAttributes(["Right Wall Spline", "", "", 0, 0, 0, 0])
                poly_features.append(f_right_line)
            else:
                continuous_ring = spline_left + list(reversed(spline_right)) + [spline_left[0]]
                f_spline_poly = QgsFeature()
                f_spline_poly.setGeometry(QgsGeometry.fromPolygonXY([continuous_ring]))
                f_spline_poly.setAttributes(["Continuous Spline Passage", "", "", 0, 0, 0, 0])
                poly_features.append(f_spline_poly)

        else:
            for idx, s in enumerate(shots):
                u = self._get_val(s, ['from_station', 'from', 'station_from'])
                v = self._get_val(s, ['to_station', 'to', 'station_to'])
                if u in stations and v in stations:
                    x1, y1, z1, l1, r1, _, _, az1, _ = stations[u]
                    x2, y2, z2, l2, r2, _, _, az2, _ = stations[v]

                    fl_x = x1 - l1 * math.cos(az1)
                    fl_y = y1 + l1 * math.sin(az1)
                    fr_x = x1 + r1 * math.cos(az1)
                    fr_y = y1 - r1 * math.sin(az1)

                    tl_x = x2 - l2 * math.cos(az2)
                    tl_y = y2 + l2 * math.sin(az2)
                    tr_x = x2 + r2 * math.cos(az2)
                    tr_y = y2 - r2 * math.sin(az2)

                    from_lat, from_lon = to_wgs84(x1, y1)
                    to_lat, to_lon = to_wgs84(x2, y2)

                    feat = QgsFeature()

                    if plan_style == "3d polygons":
                        ring3d = [
                            QgsPoint(fl_x, fl_y, z1),
                            QgsPoint(tl_x, tl_y, z2),
                            QgsPoint(tr_x, tr_y, z2),
                            QgsPoint(fr_x, fr_y, z1),
                            QgsPoint(fl_x, fl_y, z1)
                        ]
                        poly = QgsPolygon()
                        poly.setExteriorRing(QgsLineString(ring3d))
                        feat.setGeometry(QgsGeometry(poly))

                    elif plan_style == "artistic cave passage (experimental)":
                        artistic_ring = self._build_artistic_passage_envelope(
                            QgsPointXY(fl_x, fl_y),
                            QgsPointXY(tl_x, tl_y),
                            QgsPointXY(tr_x, tr_y),
                            QgsPointXY(fr_x, fr_y),
                            seed_val=idx * 17 + 101
                        )
                        feat.setGeometry(QgsGeometry.fromPolygonXY([artistic_ring]))

                    else:
                        quad = [
                            QgsPointXY(fl_x, fl_y),
                            QgsPointXY(tl_x, tl_y),
                            QgsPointXY(tr_x, tr_y),
                            QgsPointXY(fr_x, fr_y),
                            QgsPointXY(fl_x, fl_y)
                        ]
                        feat.setGeometry(QgsGeometry.fromPolygonXY([quad]))

                    feat.setAttributes([f"{u}->{v}", u, v, from_lat, from_lon, to_lat, to_lon])
                    poly_features.append(feat)

        pl_pr.addFeatures(poly_features)

        stations_layer_mem = QgsVectorLayer(f"PointZ?crs={crs.authid()}", "Cave Stations", "memory")
        st_pr = stations_layer_mem.dataProvider()
        st_pr.addAttributes([
            QgsField("station", QMetaType.Type.QString),
            QgsField("node_type", QMetaType.Type.QString),
            QgsField("alt_m", QMetaType.Type.Double)
        ])
        stations_layer_mem.updateFields()

        st_features = []
        for name, (x, y, z, left, right, up, down, az, _) in stations.items():
            nodes = [
                ("Center", x, y, z),
                ("Roof", x, y, z + up),
                ("Floor", x, y, z - down),
                ("Left Wall", x - left * math.cos(az), y + left * math.sin(az), z),
                ("Right Wall", x + right * math.cos(az), y - right * math.sin(az), z)
            ]
            for node_name, nx, ny, nz in nodes:
                f = QgsFeature()
                f.setGeometry(QgsGeometry.fromPoint(QgsPoint(nx, ny, nz)))
                st_label = name if node_name == "Center" else ""
                f.setAttributes([st_label, node_name, round(nz, 2)])
                st_features.append(f)
        st_pr.addFeatures(st_features)

        path_tube = os.path.join(output_folder, "cave_conduit_3d.gpkg")
        path_cl = os.path.join(output_folder, "cave_centerline_3d.gpkg")
        path_passage = os.path.join(output_folder, "cave_passage_2d.gpkg")
        path_stations = os.path.join(output_folder, "cave_stations.gpkg")

        tube_layer = self._save_memory_layer_to_disk(tube_layer_mem, path_tube, "Cave Octagon Passage 3D")
        centerline_layer = self._save_memory_layer_to_disk(centerline_layer_mem, path_cl, "Cave Centerline 3D")
        passage_layer = self._save_memory_layer_to_disk(passage_layer_mem, path_passage, layer_title)
        stations_layer = self._save_memory_layer_to_disk(stations_layer_mem, path_stations, "Cave Stations")

        self._apply_2d_style(passage_layer, plan_style)
        self._enable_station_labels(stations_layer, "station")

        if HAS_3D:
            self._apply_native_3d_renderers(tube_layer, centerline_layer, stations_layer)

        all_layers = [tube_layer, centerline_layer, passage_layer, stations_layer]
        QgsProject.instance().addMapLayers(all_layers)
        return all_layers

    def _apply_2d_style(self, layer, plan_style):
        try:
            if plan_style == "polygons":
                sym = QgsFillSymbol.createSimple({
                    'color': '0,0,0,0',
                    'outline_color': '30,30,30,255',
                    'outline_width': '0.4'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

            elif plan_style in ("filled polygons", "3d polygons"):
                sym = QgsFillSymbol.createSimple({
                    'color': '215,200,180,180',
                    'outline_color': '50,45,40,255',
                    'outline_width': '0.5'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

            elif plan_style == "shaded cylinders":
                sym = QgsFillSymbol.createSimple({
                    'color': '180,165,145,210',
                    'outline_color': '60,50,40,255',
                    'outline_width': '0.8',
                    'outline_style': 'solid'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

            elif plan_style == "open spline curves":
                line_sym = QgsLineSymbol.createSimple({
                    'color': '40,35,30,255',
                    'width': '0.7',
                    'capstyle': 'round'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(line_sym))

            elif plan_style == "filled spline curves":
                sym = QgsFillSymbol.createSimple({
                    'color': '225,215,200,200',
                    'outline_color': '35,30,25,255',
                    'outline_width': '0.6',
                    'joinstyle': 'round'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

            elif plan_style == "artistic cave passage (experimental)":
                sym = QgsFillSymbol.createSimple({
                    'color': '205,190,170,225',
                    'outline_color': '35,25,20,255',
                    'outline_width': '0.9',
                    'outline_style': 'solid',
                    'joinstyle': 'bevel'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

        except Exception as e:
            QgsMessageLog.logMessage(f"Style assignment note: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)

    def _on_centerline_geometry_changed(self, fid, geometry):
        if self._is_updating:
            return

        polyline = geometry.asPolyline()
        if len(polyline) < 2:
            return

        p1 = polyline[0]
        p2 = polyline[1]

        layer = self.active_centerline_layer
        feature = layer.getFeature(fid)
        from_st = feature["from_st"]
        to_st = feature["to_st"]

        if from_st not in self.stations or to_st not in self.stations:
            return

        z1 = self.stations[from_st][2]
        z2 = self.stations[to_st][2]

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dz = z2 - z1
        l_2d = math.hypot(dx, dy)

        new_bearing = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0

        if l_2d > 0.0:
            new_inc = math.degrees(math.atan2(dz, l_2d))
        else:
            new_inc = 90.0 if dz > 0 else (-90.0 if dz < 0 else 0.0)

        new_l3d = math.hypot(l_2d, dz)

        old_x, old_y = self.stations[to_st][0], self.stations[to_st][1]
        shift_x = p2.x() - old_x
        shift_y = p2.y() - old_y

        self._is_updating = True
        try:
            st_data = list(self.stations[to_st])
            st_data[0] = p2.x()
            st_data[1] = p2.y()
            st_data[7] = math.radians(new_bearing)
            st_data[8] = math.radians(new_inc)
            self.stations[to_st] = tuple(st_data)

            f_idx_bearing = layer.fields().indexOf("bearing_deg")
            f_idx_inc = layer.fields().indexOf("inc_deg")
            f_idx_length = layer.fields().indexOf("length_m")

            layer.changeAttributeValue(fid, f_idx_bearing, round(new_bearing, 1))
            layer.changeAttributeValue(fid, f_idx_inc, round(new_inc, 1))
            layer.changeAttributeValue(fid, f_idx_length, round(new_l3d, 2))

            if to_st in self.traverse_order:
                to_idx = self.traverse_order.index(to_st)
                for downstream_name in self.traverse_order[to_idx + 1:]:
                    d_data = list(self.stations[downstream_name])
                    d_data[0] += shift_x
                    d_data[1] += shift_y
                    self.stations[downstream_name] = tuple(d_data)

                    for feat in layer.getFeatures():
                        if feat["from_st"] == downstream_name:
                            line = feat.geometry().asPolyline()
                            if len(line) >= 2:
                                shifted_geom = QgsGeometry.fromPolyline([
                                    QgsPoint(line[0].x() + shift_x, line[0].y() + shift_y, line[0].z()),
                                    QgsPoint(line[1].x() + shift_x, line[1].y() + shift_y, line[1].z())
                                ])
                                layer.changeGeometry(feat.id(), shifted_geom)

            layer.triggerRepaint()
        finally:
            self._is_updating = False

    def export_edited_csv(self):
        if not self.active_centerline_layer or not self.active_centerline_layer.isValid():
            QMessageBox.warning(None, "No Active Layer", "Please import and generate a cave survey first.")
            return

        unit_dlg = UnitExportDialog(self.iface.mainWindow())
        if unit_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dist_unit, angle_unit = unit_dlg.get_units()

        dist_scale = 1.0
        if dist_unit == "ft":
            dist_scale = 3.280839895
        elif dist_unit == "in":
            dist_scale = 39.37007874

        angle_scale = 1.0
        if angle_unit == "grad":
            angle_scale = 400.0 / 360.0

        file_path, _ = QFileDialog.getSaveFileName(
            None, f"Export Cave Survey CSV ({dist_unit}, {angle_unit})", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            proj_crs = QgsProject.instance().crs()
            to_wgs = QgsCoordinateTransform(proj_crs, crs_wgs84, QgsProject.instance())

            features = list(self.active_centerline_layer.getFeatures())
            if not features:
                return

            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "from_station", "to_station", f"length_{dist_unit}", f"bearing_{angle_unit}",
                    f"inc_{angle_unit}", f"left_{dist_unit}", f"right_{dist_unit}",
                    f"up_{dist_unit}", f"down_{dist_unit}", "lat_or_y", "lon_or_x", f"alt_{dist_unit}", "crs"
                ])

                for idx, feat in enumerate(features):
                    u = feat["from_st"]
                    v = feat["to_st"]
                    raw_len_m = feat["length_m"]
                    raw_bearing_deg = feat["bearing_deg"]
                    raw_inc_deg = feat["inc_deg"]

                    out_len = round(raw_len_m * dist_scale, 2)
                    out_bearing = round(raw_bearing_deg * angle_scale, 2)
                    out_inc = round(raw_inc_deg * angle_scale, 2)

                    v_info = self.stations.get(v, (0, 0, 0, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, 0, 0))
                    u_info = self.stations.get(u, (0, 0, 0, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, DEFAULT_RADIUS_M, 0, 0))

                    left_val = round(v_info[3] * dist_scale, 2)
                    right_val = round(v_info[4] * dist_scale, 2)
                    up_val = round(v_info[5] * dist_scale, 2)
                    down_val = round(v_info[6] * dist_scale, 2)

                    lat_str, lon_str, alt_str, crs_str = "", "", "", ""
                    if idx == 0:
                        start_pt = to_wgs.transform(QgsPointXY(u_info[0], u_info[1]))
                        lat_str = f"{start_pt.y():.8f}"
                        lon_str = f"{start_pt.x():.8f}"
                        alt_str = f"{u_info[2] * dist_scale:.2f}"
                        crs_str = "EPSG:4326"

                    writer.writerow([
                        u, v, out_len, out_bearing, out_inc,
                        left_val, right_val, up_val, down_val,
                        lat_str, lon_str, alt_str, crs_str
                    ])

            QMessageBox.information(
                None, "Export Success",
                f"Updated survey exported successfully!\n\n"
                f"• Distances: {dist_unit}\n"
                f"• Angles: {angle_unit}\n"
                f"• File: {file_path}"
            )
        except Exception as e:
            QMessageBox.critical(None, "Export Error", f"Failed to export CSV:\n{str(e)}")

    def export_map_image(self):
        if not self.active_passage_layer or not self.active_passage_layer.isValid():
            QMessageBox.warning(
                None, "No Layers",
                "Please import cave data before exporting map images."
            )
            return

        dlg = MapExportDialog(self.iface.mainWindow())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        cave_name, area, surveyors, view_mode, underlay_layers = dlg.get_data()

        if "Profile" in view_mode:
            def render_cb(out_path, layers_to_draw, export_settings):
                self._export_profile_view_image(
                    cave_name, area, surveyors, out_path, export_settings
                )
            layer_items = {
                "profile": {
                    "name": "Elevation Profile",
                    "layer": None,
                    "visible": True
                }
            }
        else:
            def render_cb(out_path, layers_to_draw, export_settings):
                self._export_plan_view_image(
                    cave_name, area, surveyors, out_path,
                    layers_to_draw, export_settings
                )

            layer_items = {
                "passage": {
                    "name": "Cave Passage 2D",
                    "layer": self.active_passage_layer,
                    "visible": True
                },
                "centerline": {
                    "name": "Cave Centerline",
                    "layer": self.active_centerline_layer,
                    "visible": True
                },
                "stations": {
                    "name": "Survey Stations",
                    "layer": self.active_stations_layer,
                    "visible": True
                }
            }
            for idx, ly in enumerate(underlay_layers):
                layer_items[f"underlay_{idx}"] = {
                    "name": ly.name(),
                    "layer": ly,
                    "visible": True
                }

        try:
            preview_win = ImagePreviewDialog(
                render_cb,
                layer_items,
                title_desc=f"{cave_name} ({view_mode})",
                parent=self.iface.mainWindow()
            )
            if preview_win.exec() != QDialog.DialogCode.Accepted:
                return

            default_name = (
                f"{cave_name.lower().replace(' ', '_')}_"
                f"{'plan' if 'Plan' in view_mode else 'profile'}.png"
            )
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                f"Save {view_mode} Image",
                default_name,
                "PNG Images (*.png)"
            )
            if not file_path:
                return

            shutil.copyfile(preview_win.current_preview_path, file_path)
            QMessageBox.information(
                None,
                "Export Complete",
                f"Map image successfully saved:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                None,
                "Export Error",
                f"Failed to generate layout:\n{str(e)}"
            )

    def _export_plan_view_image(
        self, cave_name, area, surveyors, output_png,
        active_layers=None, export_settings=None
    ):
        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("CavePlanLayout")

        export_settings = export_settings or {}
        font_family = export_settings.get("font_family", "Arial")
        font_size = int(export_settings.get("font_size", 11))

        global_extent = QgsRectangle()
        base_cave_layers = [
            self.active_passage_layer,
            self.active_centerline_layer,
            self.active_stations_layer
        ]

        for lyr in base_cave_layers:
            if lyr and lyr.isValid() and lyr.featureCount() > 0:
                lyr_ext = lyr.extent()
                if not lyr_ext.isNull() and not lyr_ext.isEmpty():
                    if global_extent.isNull() or global_extent.isEmpty():
                        global_extent = QgsRectangle(lyr_ext)
                    else:
                        global_extent.combineExtentWith(lyr_ext)

        if global_extent.isNull() or global_extent.isEmpty():
            if self.stations:
                xs = [pt[0] for pt in self.stations.values()]
                ys = [pt[1] for pt in self.stations.values()]
                max_rad = max(
                    [max(pt[3], pt[4]) for pt in self.stations.values()] or [5.0]
                )
                global_extent = QgsRectangle(
                    min(xs) - max_rad, min(ys) - max_rad,
                    max(xs) + max_rad, max(ys) + max_rad
                )
            else:
                raise ValueError("No valid cave geometry found to calculate map boundaries.")

        cave_w = global_extent.width()
        cave_h = global_extent.height()

        is_tall = cave_h > (cave_w * 0.95)
        page = layout.pageCollection().page(0)
        page_w, page_h = (210.0, 297.0) if is_tall else (297.0, 210.0)
        page.setPageSize(QgsLayoutSize(page_w, page_h, QgsUnitTypes.LayoutUnit.LayoutMillimeters))

        margin_in_mm = 6.35
        map_x = margin_in_mm
        map_y = margin_in_mm
        map_w = page_w - (2.0 * margin_in_mm)
        map_h = page_h - (2.0 * margin_in_mm)

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutUnit.LayoutMillimeters))

        if active_layers is not None:
            ordered_layers = (
                [ly for ly in base_cave_layers if ly in active_layers] +
                [ly for ly in active_layers if ly not in base_cave_layers]
            )
        else:
            ordered_layers = base_cave_layers

        map_item.setLayers([ly for ly in ordered_layers if ly is not None])

        center_x = global_extent.center().x()
        center_y = global_extent.center().y()
        padded_w = cave_w * 1.25
        padded_h = cave_h * 1.25
        frame_aspect = map_w / map_h

        if (padded_w / padded_h) < frame_aspect:
            padded_w = padded_h * frame_aspect
        else:
            padded_h = padded_w / frame_aspect

        final_extent = QgsRectangle(
            center_x - (padded_w / 2.0),
            center_y - (padded_h / 2.0),
            center_x + (padded_w / 2.0),
            center_y + (padded_h / 2.0)
        )
        map_item.setExtent(final_extent)
        map_item.setFrameEnabled(True)
        layout.addLayoutItem(map_item)

        metadata_lines = [f"{cave_name or 'Unnamed Cave'}"]
        if area:
            metadata_lines.append(f"Area: {area}")
        metadata_lines.append("Plan View")
        if surveyors:
            metadata_lines.append(f"Primary Surveyor: {surveyors[0]}")
            for extra_s in surveyors[1:]:
                metadata_lines.append(f"  {extra_s}")

        full_text = "\n".join(metadata_lines)

        title_label = QgsLayoutItemLabel(layout)
        title_label.setText(full_text)
        title_font = QFont(font_family, font_size, QFont.Weight.Bold)
        title_label.setFont(title_font)

        fm = QFontMetrics(title_font)
        longest_line_px = max([fm.horizontalAdvance(line) for line in metadata_lines] or [100])
        total_text_height_px = fm.lineSpacing() * len(metadata_lines)

        card_w_mm = max(45.0, (longest_line_px / 3.78) + 8.0)
        card_h_mm = max(18.0, (total_text_height_px / 3.78) + 6.0)

        card_w_mm = min(card_w_mm, map_w * 0.55)
        card_h_mm = min(card_h_mm, map_h * 0.70)

        title_label.setBackgroundEnabled(True)
        title_label.setBackgroundColor(QColor(255, 255, 255, 225))
        title_label.setMarginX(2.5)
        title_label.setMarginY(2.5)

        title_label.attemptResize(QgsLayoutSize(card_w_mm, card_h_mm, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        title_label.attemptMove(
            QgsLayoutPoint(map_x + 4.0, map_y + 4.0, QgsUnitTypes.LayoutUnit.LayoutMillimeters)
        )
        layout.addLayoutItem(title_label)

        calc_scale = int(round(map_item.scale(), -1))
        scale_txt_label = QgsLayoutItemLabel(layout)
        scale_txt_label.setText(f"Scale 1:{calc_scale:,}")
        scale_txt_label.setFont(QFont(font_family, max(7, font_size - 2), QFont.Weight.Bold))
        scale_txt_label.setBackgroundEnabled(True)
        scale_txt_label.setBackgroundColor(QColor(255, 255, 255, 225))
        scale_txt_label.setMarginX(1.5)
        scale_txt_label.adjustSizeToText()
        scale_txt_label.attemptMove(
            QgsLayoutPoint(map_x + 4.0, map_y + map_h - 18.0, QgsUnitTypes.LayoutUnit.LayoutMillimeters)
        )
        layout.addLayoutItem(scale_txt_label)

        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setStyle("Single Box")
        scalebar.setUnits(Qgis.DistanceUnit.Meters)
        scalebar.setNumberOfSegments(2)
        scalebar.setNumberOfSegmentsLeft(0)
        scalebar.setLinkedMap(map_item)
        scalebar.applyDefaultSize()
        scalebar.setBackgroundEnabled(True)
        scalebar.setBackgroundColor(QColor(255, 255, 255, 225))
        scalebar.attemptMove(
            QgsLayoutPoint(map_x + 4.0, map_y + map_h - 12.0, QgsUnitTypes.LayoutUnit.LayoutMillimeters)
        )
        layout.addLayoutItem(scalebar)

        north_arrow = QgsLayoutItemPicture(layout)
        default_svg = ":/images/north_arrows/layout_default_north_arrow.svg"
        north_arrow.setPicturePath(default_svg)
        north_arrow.setRect(QRectF(0, 0, 18, 18))
        north_arrow.attemptMove(
            QgsLayoutPoint(map_x + map_w - 22.0, map_y + 4.0, QgsUnitTypes.LayoutUnit.LayoutMillimeters)
        )
        north_arrow.setLinkedMap(map_item)
        layout.addLayoutItem(north_arrow)

        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 300
        result = exporter.exportToImage(output_png, settings)

        if result != QgsLayoutExporter.ExportResult.Success:
            raise RuntimeError(f"QGIS Layout Exporter returned status: {result}")

    def _export_profile_view_image(self, cave_name, area, surveyors, output_png, export_settings=None):
        export_settings = export_settings or {}
        font_family = export_settings.get("font_family", "Arial")
        font_size = int(export_settings.get("font_size", 11))

        if not self.stations:
            raise ValueError("No survey stations loaded to plot elevation profile.")

        trunk_chain = []
        visited = set()
        current = self.traverse_order[0] if self.traverse_order else '1'
        trunk_chain.append(current)
        visited.add(current)

        for feat in self.active_centerline_layer.getFeatures():
            u = feat["from_st"]
            v = feat["to_st"]
            if u == trunk_chain[-1] and v not in visited:
                trunk_chain.append(v)
                visited.add(v)

        if len(trunk_chain) < 2:
            trunk_chain = [st for st in self.traverse_order if st in self.stations]

        prof_pts = []
        cum_dist = 0.0

        first_st = trunk_chain[0]
        x0, y0, z0, _, _, u0, d0, _, _ = self.stations[first_st]
        prof_pts.append((cum_dist, z0, u0, d0, first_st))

        prev_x, prev_y = x0, y0
        for st_name in trunk_chain[1:]:
            cur_x, cur_y, cur_z, _, _, cur_up, cur_down, _, _ = self.stations[st_name]
            horiz_dist = math.hypot(cur_x - prev_x, cur_y - prev_y)
            cum_dist += horiz_dist
            prof_pts.append((cum_dist, cur_z, cur_up, cur_down, st_name))
            prev_x, prev_y = cur_x, cur_y

        all_x = [p[0] for p in prof_pts]
        all_ceil = [p[1] + p[2] for p in prof_pts]
        all_floor = [p[1] - p[3] for p in prof_pts]

        min_x = 0.0
        max_x = max(all_x) if max(all_x) > 0 else 10.0
        min_y = min(all_floor) - 3.0
        max_y = max(all_ceil) + 3.0

        img_w, img_h = 3200, 2000
        margin_quarter_inch = 75

        pad_left = margin_quarter_inch + 110
        pad_right = margin_quarter_inch + 40
        pad_top = margin_quarter_inch + 150
        pad_bottom = margin_quarter_inch + 70

        plot_w = img_w - pad_left - pad_right
        plot_h = img_h - pad_top - pad_bottom

        scale_x = plot_w / (max_x - min_x) if max_x > min_x else 1.0
        scale_y = plot_h / (max_y - min_y) if max_y > min_y else 1.0

        def to_canvas(cx, cy):
            px = pad_left + (cx - min_x) * scale_x
            py = pad_top + (max_y - cy) * scale_y
            return QPointF(px, py)

        image = QImage(img_w, img_h, QImage.Format.Format_ARGB32)
        image.fill(QColor(255, 255, 255))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        grid_pen = QPen(QColor(230, 230, 230), 2, Qt.PenStyle.DashLine)
        axis_pen = QPen(QColor(60, 60, 60), 3, Qt.PenStyle.SolidLine)
        font_axis = QFont(font_family, max(10, font_size + 5))
        painter.setFont(font_axis)

        step_y = 2.0 if (max_y - min_y) <= 30 else 5.0
        cur_y_val = math.floor(min_y / step_y) * step_y
        while cur_y_val <= max_y:
            p_left = to_canvas(min_x, cur_y_val)
            p_right = to_canvas(max_x, cur_y_val)
            painter.setPen(grid_pen)
            painter.drawLine(p_left, p_right)

            painter.setPen(axis_pen)
            painter.drawText(int(p_left.x() - 140), int(p_left.y() + 8), f"{cur_y_val:.1f} m")
            cur_y_val += step_y

        step_x = 5.0 if max_x <= 50 else 10.0
        cur_x_val = 0.0
        while cur_x_val <= max_x:
            p_bot = to_canvas(cur_x_val, min_y)
            p_top = to_canvas(cur_x_val, max_y)
            painter.setPen(grid_pen)
            painter.drawLine(p_bot, p_top)

            painter.setPen(axis_pen)
            painter.drawText(int(p_bot.x() - 30), int(p_bot.y() + 45), f"{cur_x_val:.0f}m")
            cur_x_val += step_x

        passage_brush = QBrush(QColor(220, 210, 195, 220))
        passage_border = QPen(QColor(80, 70, 60), 4)

        for i in range(len(prof_pts) - 1):
            d1, z1, u1, d1_f, _ = prof_pts[i]
            d2, z2, u2, d2_f, _ = prof_pts[i + 1]

            poly = QPolygonF([
                to_canvas(d1, z1 - d1_f),
                to_canvas(d2, z2 - d2_f),
                to_canvas(d2, z2 + u2),
                to_canvas(d1, z1 + u1)
            ])
            painter.setBrush(passage_brush)
            painter.setPen(passage_border)
            painter.drawPolygon(poly)

        cl_pen = QPen(QColor(230, 80, 0), 6)
        painter.setPen(cl_pen)
        for i in range(len(prof_pts) - 1):
            pt1 = to_canvas(prof_pts[i][0], prof_pts[i][1])
            pt2 = to_canvas(prof_pts[i + 1][0], prof_pts[i + 1][1])
            painter.drawLine(pt1, pt2)

        node_brush = QBrush(QColor(220, 20, 20))
        font_st = QFont(font_family, max(12, font_size + 8), QFont.Weight.Bold)
        painter.setFont(font_st)

        for d_val, z_val, _, _, st_name in prof_pts:
            pt = to_canvas(d_val, z_val)
            painter.setPen(QPen(QColor(40, 40, 40), 2))
            painter.setBrush(node_brush)
            painter.drawEllipse(pt, 10, 10)

            painter.setPen(QColor(20, 20, 20))
            painter.drawText(
                QRectF(pt.x() + 15, pt.y() - 35, 420, 42),
                int(Qt.TextFlag.TextWordWrap),
                f"Stn {st_name} ({z_val:.1f}m)"
            )

        font_title = QFont(font_family, max(18, font_size * 2 + 8), QFont.Weight.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(30, 30, 30))
        painter.drawText(pad_left, margin_quarter_inch + 50, f"{cave_name} — Extended Elevation Profile")

        font_meta = QFont(font_family, max(10, font_size + 4))
        painter.setFont(font_meta)
        painter.setPen(QColor(90, 90, 90))

        profile_meta = []
        if area:
            profile_meta.append(f"Area: {area}")
        if surveyors:
            profile_meta.append("Surveyors: " + " | ".join(surveyors))
        profile_meta.append(f"Total Profile Traverse: {cum_dist:.1f} m")

        meta_y = margin_quarter_inch + 95
        max_meta_width = img_w - pad_left - pad_right
        for meta_line in profile_meta:
            painter.drawText(
                QRectF(pad_left, meta_y - 20, max_meta_width, 30),
                int(Qt.TextFlag.TextWordWrap),
                meta_line
            )
            meta_y += max(30, font_size * 3)

        painter.setPen(QPen(QColor(50, 50, 50), 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(pad_left, pad_top, plot_w, plot_h)

        faint_border_pen = QPen(QColor(210, 210, 210), 2, Qt.PenStyle.DashLine)
        painter.setPen(faint_border_pen)
        painter.drawRect(
            margin_quarter_inch,
            margin_quarter_inch,
            img_w - 2 * margin_quarter_inch,
            img_h - 2 * margin_quarter_inch
        )

        painter.end()

        if not image.save(output_png, "PNG"):
            raise RuntimeError(f"Failed to write image to {output_png}")

    def _export_3d_obj(self, shots, stations, incoming_shot, output_path):
        vertices = []
        faces = []

        for s in shots:
            u = self._get_val(s, ['from_station', 'from', 'station_from'])
            v = self._get_val(s, ['to_station', 'to', 'station_to'])
            if u in stations and v in stations:
                rings = self._get_two_pass_rings(stations[u], stations[v], incoming_shot.get(u))

                for r_idx in range(len(rings) - 1):
                    ru = rings[r_idx]
                    rv = rings[r_idx + 1]

                    for i in range(NUM_SECTORS):
                        next_i = (i + 1) % NUM_SECTORS
                        u1 = len(vertices) + 1
                        vertices.append((ru[i].x(), ru[i].y(), ru[i].z()))

                        u2 = len(vertices) + 1
                        vertices.append((ru[next_i].x(), ru[next_i].y(), ru[next_i].z()))

                        v1 = len(vertices) + 1
                        vertices.append((rv[i].x(), rv[i].y(), rv[i].z()))

                        v2 = len(vertices) + 1
                        vertices.append((rv[next_i].x(), rv[next_i].y(), rv[next_i].z()))

                        faces.append((u1, v1, u2))
                        faces.append((u2, v1, v2))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Cave Octagonal Conduit 3D Mesh\n")
            f.write(f"# Sectors: {NUM_SECTORS} | Two-Pass Corner Rounding >= {CORNER_THRESHOLD_DEG} deg\n")
            f.write(f"# Vertices: {len(vertices)}, Faces: {len(faces)}\n")
            for vx, vy, vz in vertices:
                f.write(f"v {vx:.4f} {vy:.4f} {vz:.4f}\n")
            for f1, f2, f3 in faces:
                f.write(f"f {f1} {f2} {f3}\n")
            f.flush()
            os.fsync(f.fileno())

        return len(vertices), len(faces)

    def _apply_native_3d_renderers(self, tube_layer, centerline_layer, stations_layer):
        try:
            tube_sym = QgsPolygon3DSymbol()
            mat_tube = self._create_material(QColor(215, 200, 180), specular=QColor(180, 180, 180))
            if mat_tube and hasattr(tube_sym, 'setMaterialSettings'):
                tube_sym.setMaterialSettings(mat_tube)

            if hasattr(tube_sym, 'setCullingMode') and hasattr(QgsPolygon3DSymbol, 'NoCulling'):
                tube_sym.setCullingMode(QgsPolygon3DSymbol.NoCulling)

            tube_renderer = QgsVectorLayer3DRenderer()
            tube_renderer.setSymbol(tube_sym)
            tube_layer.setRenderer3D(tube_renderer)
        except Exception as e:
            QgsMessageLog.logMessage(f"Tube 3D config note: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)

        try:
            cl_sym = QgsLine3DSymbol()
            if hasattr(cl_sym, 'setWidth'):
                cl_sym.setWidth(0.5)
            if hasattr(cl_sym, 'setRenderAsSimpleLines'):
                cl_sym.setRenderAsSimpleLines(False)

            mat_line = self._create_material(QColor(255, 120, 0))
            if mat_line and hasattr(cl_sym, 'setMaterialSettings'):
                cl_sym.setMaterialSettings(mat_line)

            cl_renderer = QgsVectorLayer3DRenderer()
            cl_renderer.setSymbol(cl_sym)
            centerline_layer.setRenderer3D(cl_renderer)
        except Exception as e:
            QgsMessageLog.logMessage(f"Centerline 3D config note: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)

        try:
            pt_sym = QgsPoint3DSymbol()
            if hasattr(pt_sym, 'setShape') and hasattr(QgsPoint3DSymbol, 'Shape'):
                pt_sym.setShape(QgsPoint3DSymbol.Shape.Sphere)
            elif hasattr(pt_sym, 'setShape') and hasattr(QgsPoint3DSymbol, 'Sphere'):
                pt_sym.setShape(QgsPoint3DSymbol.Sphere)

            if hasattr(pt_sym, 'setRadius'):
                pt_sym.setRadius(0.18)

            mat_pt = self._create_material(QColor(240, 40, 40))
            if mat_pt and hasattr(pt_sym, 'setMaterialSettings'):
                pt_sym.setMaterialSettings(mat_pt)

            pt_renderer = QgsVectorLayer3DRenderer()
            pt_renderer.setSymbol(pt_sym)
            stations_layer.setRenderer3D(pt_renderer)
        except Exception as e:
            QgsMessageLog.logMessage(f"Station 3D config note: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)

    def _create_material(self, diffuse, specular=QColor(255, 255, 255)):
        try:
            from qgis._3d import QgsPhongMaterialSettings
            mat = QgsPhongMaterialSettings()
            if hasattr(mat, 'setDiffuse'):
                mat.setDiffuse(diffuse)
            if hasattr(mat, 'setAmbient'):
                mat.setAmbient(diffuse.lighter(125))
            if hasattr(mat, 'setSpecular'):
                mat.setSpecular(specular)
            if hasattr(mat, 'setShininess'):
                mat.setShininess(32.0)
            return mat
        except Exception:
            return None

    def _launch_3d_view(self, layers):
        try:
            canvas3d = self.iface.new3DMapCanvas("Subsurface Cave 3D")
            if not canvas3d:
                return

            map_settings = canvas3d.mapSettings()
            if map_settings:
                try:
                    from qgis._3d import QgsFlatTerrainGenerator
                    terrain = QgsFlatTerrainGenerator()
                    terrain.setCrs(QgsProject.instance().crs())
                    map_settings.setTerrainGenerator(terrain)
                except Exception as e:
                    QgsMessageLog.logMessage(f"Terrain generator note: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)

                extent = layers[0].extent()
                for ly in layers:
                    extent.combineExtentWith(ly.extent())
                canvas3d.setViewFrom2DExtent(extent)
        except Exception as e:
            QgsMessageLog.logMessage(f"Could not auto-open 3D Canvas: {str(e)}", "CaveLRUD", Qgis.MessageLevel.Info)