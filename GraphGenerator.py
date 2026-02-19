#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import numpy as np
import pandas as pd

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QMessageBox, QGroupBox, QColorDialog,
    QMainWindow, QToolBar, QAction,
    QDialog, QTableWidget, QTableWidgetItem
)

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

try:
    import seaborn as sns
    _HAS_SEABORN = True
except Exception:
    _HAS_SEABORN = False


def _warn(parent, title, msg):
    QMessageBox.warning(parent, title, msg)


def _info(parent, title, msg):
    QMessageBox.information(parent, title, msg)


def ensure_openpyxl(parent=None) -> bool:
    """
    Check whether openpyxl is installed.
    If not, ask the user if they want to install it now.
    Returns True if openpyxl is available at the end.
    """
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        reply = QMessageBox.question(
            parent,
            "Missing dependency",
            "To open XLSX files you must install the 'openpyxl' library.\n\n"
            "Do you want to install it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                QMessageBox.information(
                    parent,
                    "Installed",
                    "openpyxl was installed successfully.\n\nPlease try loading the XLSX file again."
                )
                return True
            except Exception as e:
                QMessageBox.critical(
                    parent,
                    "Installation error",
                    f"Failed to install openpyxl.\n\n{e}"
                )
                return False
        else:
            QMessageBox.warning(
                parent,
                "Cancelled",
                "XLSX files cannot be opened without openpyxl."
            )
            return False


def load_xy_table(path: str, parent=None) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.read_csv(path, sep=";")

    elif ext in (".xlsx", ".xls"):
        if not ensure_openpyxl(parent):
            raise RuntimeError("openpyxl not available")

        # 1) Try default header
        df = pd.read_excel(path, engine="openpyxl")

        # If the XLSX first row is data (not header), pandas may create numeric column names
        # In this case, read without header.
        if any(isinstance(c, (int, float, np.integer, np.floating)) for c in df.columns):
            df = pd.read_excel(path, engine="openpyxl", header=None)
            if df.shape[1] >= 2:
                df = df.rename(columns={0: "X", 1: "Y"})
    else:
        raise ValueError("Unsupported format. Please use CSV or XLSX.")

    if df is None or df.empty:
        raise ValueError("Empty or invalid file.")

    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    if df.empty:
        raise ValueError("No valid data found in the file.")

    return df


def extract_x_y(df: pd.DataFrame):
    """
    Rules:
    1) If there is a column named 'X' (case-insensitive), use it as X and the rest as Y.
    2) Otherwise, if the first column is mostly non-numeric (names), use it as X and the remaining numeric columns as Y.
    3) Otherwise, X = row index (1..n) and Y = numeric columns.
    """
    cols = list(df.columns)
    cols_lower = {str(c).strip().lower(): c for c in cols}

    # Case 1: explicit X column
    if "x" in cols_lower:
        x_col = cols_lower["x"]
        x = df[x_col].astype(str).to_numpy()
        ydf = df.drop(columns=[x_col])
    else:
        first = df.iloc[:, 0]
        first_num = pd.to_numeric(first, errors="coerce")
        non_numeric_ratio = first_num.isna().mean()

        # Case 2: first column looks categorical (names)
        if non_numeric_ratio >= 0.5:
            x = first.astype(str).to_numpy()
            ydf = df.iloc[:, 1:].copy()
        else:
            # Case 3: fallback
            x = np.arange(1, len(df) + 1)
            ydf = df.copy()

    ydf = ydf.apply(pd.to_numeric, errors="coerce")
    ydf = ydf.dropna(axis=1, how="all")

    if ydf.empty:
        raise ValueError("No numeric columns found for Y.")

    return x, ydf


def add_trendlines(ax, x, ydf: pd.DataFrame):
    x_num = np.arange(len(x)) if not np.issubdtype(np.array(x).dtype, np.number) else np.asarray(x, dtype=float)
    for col in ydf.columns:
        y = ydf[col].to_numpy(dtype=float)
        m = np.isfinite(x_num) & np.isfinite(y)
        if m.sum() < 2:
            continue
        coef = np.polyfit(x_num[m], y[m], 1)
        yfit = coef[0] * x_num + coef[1]
        ax.plot(
            np.arange(len(x)) if x_num is not None and x_num.ndim == 1 and not np.issubdtype(np.array(x).dtype, np.number) else x_num,
            yfit,
            linestyle="--",
            linewidth=2,
            label=f"Trend ({col})"
        )


def _get_series_colors(n, color_mode, palette_name, single_color):
    if color_mode.startswith("Single"):
        return [single_color] * n
    if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
        return sns.color_palette(palette_name, n_colors=n)
    cmap = plt.get_cmap(palette_name)
    return [cmap(i / max(n - 1, 1)) for i in range(n)]

def _fmt_val(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        # formatação simples e “bonita”
        if abs(float(v)) >= 1000:
            return f"{float(v):.0f}"
        if abs(float(v)) >= 10:
            return f"{float(v):.2f}".rstrip("0").rstrip(".")
        return f"{float(v):.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(v)


def _annotate_points(ax, xs, ys, color=None, dx=4, dy=4):
    # anota valores ao lado do ponto
    for x, y in zip(xs, ys):
        if not np.isfinite(y):
            continue
        ax.annotate(
            _fmt_val(y),
            (x, y),
            textcoords="offset points",
            xytext=(dx, dy),
            ha="left",
            va="bottom",
            fontsize=10,
            color=color
        )


def _annotate_bars(ax, bars, dy=3):
    for b in bars:
        h = b.get_height()
        if not np.isfinite(h):
            continue
        ax.annotate(
            _fmt_val(h),
            (b.get_x() + b.get_width() / 2, h),
            textcoords="offset points",
            xytext=(0, dy),
            ha="center",
            va="bottom",
            fontsize=12,
            weight="bold",
            color=b.get_facecolor()
        )

def plot_bar(df: pd.DataFrame, dpi: int, trendline: bool, title: str, xlabel: str = "", ylabel: str = "", label_mark: bool = False,
             color_mode: str = "Palette (multi-color)",
             palette_name: str = "Dark2",
             single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    x_pos = np.arange(len(x))
    n_series = len(ydf.columns)
    width = 0.8 / max(n_series, 1)

    # Special case: 1 Y column + palette => color per bar (category)
    if (not color_mode.startswith("Single")) and (n_series == 1):
        if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
            bar_colors = sns.color_palette(palette_name, n_colors=len(x))
        else:
            cmap = plt.get_cmap(palette_name)
            bar_colors = [cmap(i / max(len(x) - 1, 1)) for i in range(len(x))]

        col = ydf.columns[0]
        y = ydf[col].to_numpy(dtype=float)

        bars = ax.bar(x_pos, y, width=0.8, label=str(col), color=bar_colors)
        if label_mark:
            _annotate_bars(ax, bars)

        if trendline:
            add_trendlines(ax, x_pos, ydf)

    else:
        # General case: color per series (column)
        if color_mode.startswith("Single"):
            series_colors = [single_color] * n_series
        else:
            series_colors = _get_series_colors(n_series, "Palette", palette_name, single_color)

        for i, col in enumerate(ydf.columns):
            y = ydf[col].to_numpy(dtype=float)
            pos = x_pos - (0.4 - width / 2) + i * width
            bars = ax.bar(pos, y, width=width, label=str(col), color=series_colors[i])
            if label_mark:
                _annotate_bars(ax, bars)

        if trendline:
            add_trendlines(ax, x_pos, ydf)

    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14, fontweight="bold")

    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title or "Bar Chart", fontsize=14, fontweight="bold")

    ax.set_xticks(x_pos)
    ax.set_xticklabels([str(v) for v in x], rotation=0, ha="center")

    if len(ydf.columns) > 1 or trendline:
        ax.legend()

    plt.tight_layout()
    return fig


def plot_line(df: pd.DataFrame, dpi: int, trendline: bool, title: str, xlabel: str = "", ylabel: str = "", label_mark: bool = False,
              color_mode: str = "Palette (multi-color)",
              palette_name: str = "Dark2",
              single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = _get_series_colors(len(ydf.columns), color_mode, palette_name, single_color)

    for i, col in enumerate(ydf.columns):
        yvals = ydf[col].to_numpy(dtype=float)
        line = ax.plot(x, yvals, marker="o", label=str(col), color=colors[i])[0]
        if label_mark:
            _annotate_points(ax, x, yvals, color=line.get_color())

    ax.set_title(title or "Line Chart")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)

    if trendline:
        add_trendlines(ax, x, ydf)

    ax.legend()
    plt.tight_layout()
    return fig


def plot_scatter(df: pd.DataFrame, dpi: int, trendline: bool, title: str, xlabel: str = "", ylabel: str = "", label_mark: bool = False,
                 color_mode: str = "Palette (multi-color)",
                 palette_name: str = "Dark2",
                 single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = _get_series_colors(len(ydf.columns), color_mode, palette_name, single_color)

    for i, col in enumerate(ydf.columns):
        yvals = ydf[col].to_numpy(dtype=float)
        sc = ax.scatter(x, yvals, label=str(col), color=colors[i])
        if label_mark:
            _annotate_points(ax, x, yvals, color=colors[i])

    ax.set_title(title or "Scatter Plot")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    if trendline:
        add_trendlines(ax, x, ydf)

    ax.legend()
    plt.tight_layout()
    return fig


def plot_area(df: pd.DataFrame, dpi: int, trendline: bool, title: str, xlabel: str = "", ylabel: str = "", label_mark: bool = False,
              color_mode: str = "Palette (multi-color)",
              palette_name: str = "Dark2",
              single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    if color_mode.startswith("Single"):
        colors = [single_color] * len(ydf.columns)
    else:
        colors = _get_series_colors(len(ydf.columns), "Palette", palette_name, single_color)

    ax.stackplot(
        x,
        *[ydf[c].to_numpy(dtype=float) for c in ydf.columns],
        labels=[str(c) for c in ydf.columns],
        colors=colors
    )

    if label_mark:
        # marca o topo de cada camada por x e escreve o valor daquela camada
        cum = np.zeros(len(x), dtype=float)
        for i, col in enumerate(ydf.columns):
            yvals = ydf[col].to_numpy(dtype=float)
            cum = cum + np.nan_to_num(yvals, nan=0.0)
            ax.plot(x, cum, marker="o", linestyle="None", markersize=4, color=colors[i])
            _annotate_points(ax, x, yvals, color=colors[i])

    ax.set_title(title or "Area Chart (Stacked)")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)

    if trendline:
        ysum = ydf.sum(axis=1).to_frame("Sum")
        add_trendlines(ax, x, ysum)

    ax.legend(loc="upper left")
    plt.tight_layout()
    return fig


def plot_box(df: pd.DataFrame, dpi: int, trendline: bool, label_mark: bool, title: str, xlabel: str = "", ylabel: str = "",
             color_mode: str = "Palette (multi-color)",
             palette_name: str = "Dark2",
             single_color: str = "#1f77b4"):

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    data = [ydf[c].dropna().to_numpy(dtype=float) for c in ydf.columns]
    bp = ax.boxplot(
        data,
        labels=[str(c) for c in ydf.columns],
        patch_artist=True,
        medianprops=dict(color="#222222", linewidth=1),   # ← mediana cinza escuro
        whiskerprops=dict(color="#222222", linewidth=1.5),
        capprops=dict(color="#222222", linewidth=1.5),
        boxprops=dict(edgecolor="#222222", linewidth=1.5),
        flierprops=dict(
            marker="o",
            markerfacecolor="yellow",
            markeredgecolor="darkred",
            markeredgewidth=1.5,
            markersize=6,
            alpha=1
        )
    )

    if label_mark:
        x_offset = 0.1  # deslocamento horizontal para a direita

        for i, col in enumerate(ydf.columns, start=1):
            arr = ydf[col].dropna().to_numpy(dtype=float)
            if arr.size == 0:
                continue

            Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])

            # limites (whiskers teóricos)
            IQR = Q3 - Q1
            limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
            limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()

            x_pos = i + x_offset

            ax.text(
                x_pos, limit_below, _fmt_val(limit_below),
                ha="left", va="center", fontsize=10, color="black"
            )
            ax.text(
                x_pos, Q1, _fmt_val(Q1),
                ha="left", va="center", fontsize=10, color="black"
            )
            ax.text(
                x_pos, Q2, _fmt_val(Q2),
                ha="left", va="center", fontsize=10, color="black", fontweight="bold"
            )
            ax.text(
                x_pos, Q3, _fmt_val(Q3),
                ha="left", va="center", fontsize=10, color="black"
            )
            ax.text(
                x_pos, limit_above, _fmt_val(limit_above),
                ha="left", va="center", fontsize=10, color="black"
            )

        for i, fl in enumerate(bp.get("fliers", []), start=1):
            xs = fl.get_xdata()
            ys = fl.get_ydata()

            if ys is None or len(ys) == 0:
                continue

            # mesma lógica de deslocamento à direita
            x_pos = i + x_offset

            for y0 in ys:
                if not np.isfinite(y0):
                    continue

                ax.text(
                    x_pos, y0, f"{_fmt_val(y0)}",
                    ha="left", va="center",
                    fontsize=10, color="darkred", fontweight="bold"
                )

    if color_mode.startswith("Single"):
        box_colors = [single_color] * len(ydf.columns)
    else:
        box_colors = _get_series_colors(len(ydf.columns), "Palette", palette_name, single_color)

    for patch, c in zip(bp["boxes"], box_colors):
        patch.set_facecolor(c)

    ax.set_title(title or "Box Plot")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    return fig


def plot_heatmap(df: pd.DataFrame, dpi: int, trendline: bool, label_mark: bool, title: str, xlabel: str = "", ylabel: str = "",
                 color_mode: str = "Palette (multi-color)",
                 palette_name: str = "viridis",
                 single_color: str = "#1f77b4"):

    from matplotlib.colors import LinearSegmentedColormap

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    data = ydf.to_numpy(dtype=float)

    if color_mode.startswith("Single"):
        cmap = LinearSegmentedColormap.from_list("single", ["#ffffff", single_color])
    else:
        cmap = palette_name

    im = ax.imshow(data, aspect="auto", cmap=cmap)

    ax.set_title(title or "Heatmap")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.set_xticks(np.arange(len(ydf.columns)))
    ax.set_xticklabels([str(c) for c in ydf.columns], rotation=45, ha="right")
    fig.colorbar(im, ax=ax)

    plt.tight_layout()
    return fig


PLOTTERS = {
    "Bar": plot_bar,
    "Line": plot_line,
    "Scatter": plot_scatter,
    "Area (Stacked)": plot_area,
    "Box Plot": plot_box,
    "Heatmap": plot_heatmap,
}

class DpiNavigationToolbar(NavigationToolbar2QT):
    def __init__(self, canvas, parent=None, dpi=300):
        self._export_dpi = int(dpi)
        super().__init__(canvas, parent)

    def set_export_dpi(self, dpi: int):
        self._export_dpi = int(dpi)

    def save_figure(self, *args):
        # diálogo igual ao toolbar, mas com dpi garantido
        filetypes = (
            "PNG (*.png);;JPG (*.jpg);;TIFF (*.tiff);;PDF (*.pdf);;EPS (*.eps);;SVG (*.svg);;All files (*.*)"
        )
        path, _ = QFileDialog.getSaveFileName(self.parent(), "Save chart", "chart.png", filetypes)
        if not path:
            return

        ext = os.path.splitext(path)[1].lower().replace(".", "")
        if ext not in ("png", "jpg", "tiff", "pdf", "eps", "svg"):
            # se o usuário não colocou extensão, assume png
            path = path + ".png"
            ext = "png"

        try:
            # dpi só importa para raster
            dpi = self._export_dpi if ext in ("png", "jpg", "tiff") else None
            self.canvas.figure.savefig(path, dpi=dpi)
            QMessageBox.information(self.parent(), "Saved", f"File saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self.parent(), "Save error", str(e))

class PlotViewer(QMainWindow):
    def __init__(self, fig, dpi=300, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chart Preview")
        self.resize(1000, 650)

        self.fig = fig
        self.dpi = int(dpi)

        self.canvas = FigureCanvas(self.fig)
        self.setCentralWidget(self.canvas)

        # Toolbar customizado (salva com dpi correto)
        self.nav = DpiNavigationToolbar(self.canvas, self, dpi=self.dpi)
        self.addToolBar(self.nav)

        self._update_info()

    def _update_info(self):
        w_in = float(self.fig.get_figwidth())
        h_in = float(self.fig.get_figheight())
        w_px = int(round(w_in * self.dpi))
        h_px = int(round(h_in * self.dpi))
        self.statusBar().showMessage(f"DPI = {self.dpi}  /  Resolution = {w_px} x {h_px} px")

    def save_as(self, ext: str):
        suggested = f"chart.{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save as {ext.upper()}",
            suggested,
            f"{ext.upper()} (*.{ext})"
        )
        if not path:
            return
        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"

        try:
            self.fig.savefig(path, dpi=self.dpi if ext in ("png", "jpg", "tiff") else None)
            QMessageBox.information(self, "Saved", f"File saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def save_as_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save chart",
            "chart.png",
            "PNG (*.png);;SVG (*.svg);;TIFF (*.tiff);;JPG (*.jpg)"
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower().replace(".", "")
        if ext not in ("png", "svg", "tiff", "jpg"):
            QMessageBox.warning(self, "Warning", "Please choose a valid format: png, svg, tiff, or jpg.")
            return

        try:
            self.fig.savefig(path, dpi=self.dpi if ext in ("png", "jpg", "tiff") else None)
            QMessageBox.information(self, "Saved", f"File saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))


class GraphGeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chart Generator")
        self.resize(720, 420)

        self.file_path = ""
        self.single_color = None  # hex string: "#RRGGBB"

        root = QVBoxLayout(self)

        box = QGroupBox()
        grid = QGridLayout(box)

        # 0) Title
        grid.addWidget(QLabel("Title:"), 0, 0)
        self.le_title = QLineEdit()
        self.le_title.setPlaceholderText("Optional")
        grid.addWidget(self.le_title, 0, 1, 1, 3)

        # 1) Input file
        grid.addWidget(QLabel("Input file (CSV/XLSX):"), 1, 0)
        self.le_file = QLineEdit()
        self.le_file.setReadOnly(True)
        grid.addWidget(self.le_file, 1, 1, 1, 2)

        self.btn_attach = QPushButton("Attach file…")
        self.btn_attach.clicked.connect(self.attach_file)
        grid.addWidget(self.btn_attach, 1, 3)

        # 2) Chart type
        grid.addWidget(QLabel("Chart type:"), 2, 0)
        self.cb_plot = QComboBox()
        self.cb_plot.addItems(list(PLOTTERS.keys()))
        grid.addWidget(self.cb_plot, 2, 1, 1, 3)

        # 3) Resolution
        grid.addWidget(QLabel("Resolution (dpi):"), 3, 0)
        self.le_dpi = QLineEdit("300")
        self.le_dpi.setValidator(QIntValidator(50, 2400, self))
        self.le_dpi.setMaximumWidth(120)
        grid.addWidget(self.le_dpi, 3, 1)

        # 3) Trendline and labels
        self.ck_trend = QCheckBox("Show trendline")
        grid.addWidget(self.ck_trend, 3, 2, 1, 1)

        self.ck_label = QCheckBox("Label mark")
        grid.addWidget(self.ck_label, 3, 3, 1, 1)

        # 4) Colors
        grid.addWidget(QLabel("Colors:"), 4, 0)

        self.cb_colors = QComboBox()
        self.cb_colors.addItems([
            "Single color (all series)",
            "Palette (multi-color)"
        ])
        grid.addWidget(self.cb_colors, 4, 1)

        self.btn_color = QPushButton("Pick color…")
        self.btn_color.clicked.connect(self.pick_single_color)
        grid.addWidget(self.btn_color, 4, 2)

        self.cb_palette = QComboBox()
        self.cb_palette.addItems([
            "Dark2",
            "Set2",
            "Set3",
            "tab10",
            "tab20",
            "Paired",
            "Accent",
            "viridis",
            "plasma",
            "magma",
            "cividis",
        ])
        grid.addWidget(self.cb_palette, 4, 3)

        # 5) X-axis label
        grid.addWidget(QLabel("X-axis label:"), 5, 0)
        self.le_xlabel = QLineEdit()
        self.le_xlabel.setPlaceholderText("Optional")
        grid.addWidget(self.le_xlabel, 5, 1, 1, 3)

        # 6) Y-axis label
        grid.addWidget(QLabel("Y-axis label:"), 6, 0)
        self.le_ylabel = QLineEdit()
        self.le_ylabel.setPlaceholderText("Optional")
        grid.addWidget(self.le_ylabel, 6, 1, 1, 3)

        root.addWidget(box)

        bottom = QHBoxLayout()
        # bottom.addStretch(1)
        self.btn_generate = QPushButton("Generate chart")
        self.btn_generate.setStyleSheet("""
    QPushButton {
        background-color: #B7E4C7;   /* Verde pastel claro */
        color: #333333;              /* Cinza escuro */
        font-size: 12pt;
        font-weight: bold;
        border: 1px solid #222;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #74C69D;   /* Verde pastel médio ao passar o mouse */
        color: #000000;  /* Preto */
    }
    QPushButton:pressed {
        background-color: #40916C;   /* Verde pastel escuro ao clicar */
        color: #000000;  /* Preto */
    }
    """)
        self.btn_generate.setMinimumHeight(40)
        self.btn_generate.setFixedWidth(200)
        self.btn_generate.clicked.connect(self.generate_chart)
        bottom.addWidget(self.btn_generate)
        root.addLayout(bottom)

    def _update_color_mode_ui(self):
        single = (self.cb_colors.currentText().startswith("Single"))
        self.btn_color.setEnabled(single)
        self.cb_palette.setEnabled(not single)

    def pick_single_color(self):
        c = QColorDialog.getColor(parent=self)
        if c and c.isValid():
            self.single_color = c.name()
            self.btn_color.setText(f"Color: {self.single_color}")

    def show_dataframe(self, df: pd.DataFrame):
        dialog = QDialog(self)
        dialog.setWindowTitle("Selected file preview")
        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        max_rows = min(200, len(df))
        table.setRowCount(max_rows)
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels([str(c) for c in df.columns])

        for i in range(max_rows):
            for j, col in enumerate(df.columns):
                val = df.iloc[i, j]
                table.setItem(i, j, QTableWidgetItem("" if pd.isna(val) else str(val)))

        table.resizeColumnsToContents()
        layout.addWidget(table)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.setFixedSize(200, 30)
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(200, 30)

        row_count_label = QLabel(f"Rows: {len(df)}")
        row_count_label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #333; margin-left: 20px;")
        row_count_label.setFixedSize(150, 30)

        column_count_label = QLabel(f"Columns: {len(df.columns)}")
        column_count_label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #333; margin-left: 20px;")
        column_count_label.setFixedSize(170, 30)

        btn_layout.addWidget(btn_save, alignment=Qt.AlignCenter)
        btn_layout.addStretch(1)
        btn_layout.addWidget(btn_close, alignment=Qt.AlignCenter)
        btn_layout.addStretch(1)
        btn_layout.addWidget(row_count_label, alignment=Qt.AlignCenter)
        btn_layout.addStretch(1)
        btn_layout.addWidget(column_count_label, alignment=Qt.AlignCenter)

        layout.addLayout(btn_layout)

        def save_dialog():
            initial_dir = os.path.dirname(self.file_path) if self.file_path else os.path.expanduser("~")
            file_path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Save data",
                os.path.join(initial_dir, "exported_data.csv"),
                "CSV (*.csv);;Excel (*.xlsx)"
            )
            if file_path:
                try:
                    if file_path.lower().endswith(".xlsx"):
                        if not ensure_openpyxl(dialog):
                            return
                        df.to_excel(file_path, index=False)
                    else:
                        df.to_csv(file_path, index=False)
                    QMessageBox.information(dialog, "Saved", f"Data saved to:\n{file_path}")
                except Exception as e:
                    QMessageBox.critical(dialog, "Save error", str(e))

        btn_save.clicked.connect(save_dialog)
        btn_close.clicked.connect(dialog.accept)

        dialog.resize(900, 500)
        dialog.exec_()

    def attach_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            "",
            "Data (*.csv *.xlsx *.xls);;CSV (*.csv);;Excel (*.xlsx *.xls)"
        )
        if not path:
            return

        self.file_path = path
        self.le_file.setText(path)

        try:
            df = load_xy_table(self.file_path, parent=self)
        except Exception as e:
            QMessageBox.critical(self, "File read error", str(e))
            return

        self.show_dataframe(df)

    def generate_chart(self):
        if not self.file_path:
            _warn(self, "Warning", "Please select a CSV or XLSX file.")
            return

        dpi_txt = (self.le_dpi.text() or "").strip()
        if not dpi_txt:
            _warn(self, "Warning", "Please enter the resolution (dpi).")
            return

        try:
            dpi = int(dpi_txt)
            if dpi <= 0:
                raise ValueError
        except Exception:
            _warn(self, "Warning", "DPI must be a valid integer (e.g., 300).")
            return

        plot_type = self.cb_plot.currentText().strip()
        if plot_type not in PLOTTERS:
            _warn(self, "Warning", "Please select a chart type.")
            return

        try:
            df = load_xy_table(self.file_path, parent=self)
        except Exception as e:
            _warn(self, "File read error", str(e))
            return

        title = (self.le_title.text() or "").strip()
        trend = self.ck_trend.isChecked()
        label_mark = self.ck_label.isChecked()
        xlabel = (self.le_xlabel.text() or "").strip()
        ylabel = (self.le_ylabel.text() or "").strip()

        color_mode = self.cb_colors.currentText()
        palette_name = self.cb_palette.currentText()
        single_color = self.single_color
        if color_mode.startswith("Single") and not single_color:
            single_color = "#1f77b4"

        try:
            plotter = PLOTTERS[plot_type]
            fig = plotter(
                df=df,
                dpi=dpi,
                trendline=trend,
                label_mark=label_mark,
                title=title,
                xlabel=xlabel,
                ylabel=ylabel,
                color_mode=color_mode,
                palette_name=palette_name,
                single_color=single_color
            )
        except Exception as e:
            _warn(self, "Chart generation error", str(e))
            return

        self.viewer = PlotViewer(fig, dpi=dpi, parent=self)
        self.viewer.show()


def main():
    app = QApplication(sys.argv)
    w = GraphGeneratorUI()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
