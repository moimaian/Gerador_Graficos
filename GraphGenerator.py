#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
#
# CODRUG – Computational Drug Discovery Platform
# Copyright (C) 2024–2026 Moisés Maia
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

# ==========================================================================================================================================
# ====================================================== IMPORTING LIBRARY =================================================================
# ==========================================================================================================================================
import os
import sys
import subprocess
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QMessageBox, QGroupBox, QColorDialog,
    QMainWindow, QToolBar, QAction,
    QDialog, QTableWidget, QTableWidgetItem,
    QListWidget, QAbstractItemView
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

try:
    import seaborn as sns
    _HAS_SEABORN = True
except Exception:
    _HAS_SEABORN = False

# ==========================================================================================================================================
# ====================================================== HELPERS METHODS ===================================================================
# ==========================================================================================================================================
def _warn(parent, title, msg):
    QMessageBox.warning(parent, title, msg)

def ensure_openpyxl(parent=None) -> bool:
    """
    Check whether openpyxl is installed.
    If not, ask the user if they want to install it now.
    Returns True if openpyxl is available at the end.
    """
    try:
        import openpyxl
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

def _series_to_numeric(s: pd.Series) -> pd.Series:
    # Converts numbers with comma decimal (e.g., "3,14") to float.
    if s.dtype == object:
        s2 = s.astype(str).str.strip()
        # remove NBSP if exists
        s2 = s2.str.replace("\u00a0", "", regex=False)
        # decimal comma -> dot
        s2 = s2.str.replace(",", ".", regex=False)
        return pd.to_numeric(s2, errors="coerce")
    return pd.to_numeric(s, errors="coerce")

def _find_group_column(df: pd.DataFrame):
    """Procura uma coluna de grupos por nome (Class/Classes/Group/Groups)."""
    targets = {"class", "classes", "group", "groups"}
    for c in df.columns:
        if str(c).strip().lower() in targets:
            return str(c)
    return None

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

    ydf = ydf.apply(_series_to_numeric)
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
            weight="bold",
            color=color
        )

def _annotate_points_with_text(ax, xs, ys, texts, color=None, dx=4, dy=4):
    for x, y, t in zip(xs, ys, texts):
        if not np.isfinite(y):
            continue
        ax.annotate(
            _fmt_val(t),          # texto (pode ser y original)
            (x, y),               # posição (pode ser cum)
            textcoords="offset points",
            xytext=(dx, dy),
            ha="left",
            va="bottom",
            fontsize=10,
            weight="bold",
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

# ==========================================================================================================================================
# ====================================================== PLOT METHODS ======================================================================
# ==========================================================================================================================================
def plot_bar(
    df: pd.DataFrame,
    dpi: int,
    trend_mode: str = "None",
    show_legend: bool = False,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    label_mark: bool = False,
    color_mode: str = "Palette (multi-color)",
    palette_name: str = "Dark2",
    single_color: str = "#1f77b4"
):
    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    x_pos = np.arange(len(x))
    n_series = len(ydf.columns)
    width = 0.8 / max(n_series, 1)

    # -----------------------------
    # 1) DRAW BARS (no double-draw)
    # -----------------------------
    bars_by_series = []  # keep handles for label_mark and trend line

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
        bars_by_series.append((x_pos, y, bars, None))  # (xcenters, y, bars, color)

        if label_mark:
            _annotate_bars(ax, bars)

    else:
        # General case: color per series (column)
        if color_mode.startswith("Single"):
            series_colors = [single_color] * n_series
        else:
            series_colors = _get_series_colors(n_series, "Palette", palette_name, single_color)

        for i, col in enumerate(ydf.columns):
            y = ydf[col].to_numpy(dtype=float)
            pos = x_pos - (0.4 - width / 2) + i * width  # center of each bar in grouped layout
            bars = ax.bar(pos, y, width=width, label=str(col), color=series_colors[i])

            bars_by_series.append((pos, y, bars, series_colors[i]))

            if label_mark:
                _annotate_bars(ax, bars)

    # -----------------------------
    # 2) TRENDLINE (use numeric x_pos)
    # -----------------------------
    if trend_mode != "None":
        # For bars, we always fit against numeric positions
        for pos, y, _, _c in bars_by_series:
            # remove NaNs
            pos = np.asarray(pos, dtype=float)
            y = np.asarray(y, dtype=float)
            m = np.isfinite(pos) & np.isfinite(y)
            if m.sum() < 2:
                continue

            xs = pos[m]
            ys = y[m]
            order = np.argsort(xs)
            xs = xs[order]
            ys = ys[order]

            # Choose model
            if trend_mode.startswith("Linear"):
                deg = 1
                coeffs = np.polyfit(xs, ys, deg)
                y_fit = np.polyval(coeffs, xs)
                ax.plot(xs, y_fit, color="#222222", linewidth=2)

            elif trend_mode.startswith("Quadratic"):
                deg = 2
                coeffs = np.polyfit(xs, ys, deg)
                y_fit = np.polyval(coeffs, xs)
                ax.plot(xs, y_fit, color="#222222", linewidth=2)

            elif trend_mode.startswith("Cubic"):
                deg = 3
                coeffs = np.polyfit(xs, ys, deg)
                y_fit = np.polyval(coeffs, xs)
                ax.plot(xs, y_fit, color="#222222", linewidth=2)

            elif trend_mode == "Moving Average":
                # moving average over ordered points
                window = max(3, len(xs) // 10)
                y_ma = pd.Series(ys).rolling(window=window, center=True).mean().to_numpy()
                ax.plot(xs, y_ma, color="#222222", linewidth=2)

            elif trend_mode == "Logarithmic":
                # requires x > 0
                m2 = xs > 0
                if m2.sum() >= 2:
                    coeffs = np.polyfit(np.log(xs[m2]), ys[m2], 1)
                    y_fit = coeffs[0] * np.log(xs[m2]) + coeffs[1]
                    ax.plot(xs[m2], y_fit, color="#222222", linewidth=2)

            # "GAMs" not implemented here (needs pygam). You can add later if you want.

    # -----------------------------
    # 3) Labels/title/legend
    # -----------------------------
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14, fontweight="bold")

    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title or "Bar Chart", fontsize=14, fontweight="bold")

    ax.set_xticks(x_pos)
    ax.set_xticklabels([str(v) for v in x], rotation=0, ha="center")

    if show_legend:
        ax.legend()

    plt.tight_layout()
    return fig

def plot_line(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, title: str = "", xlabel: str = "", ylabel: str = "", label_mark: bool = False,
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

    if trend_mode != "None":
        x_vals = np.asarray(x, dtype=float)
        y_vals = np.asarray(ydf, dtype=float)

        order = np.argsort(x_vals)
        x_sorted = x_vals[order]
        y_sorted = y_vals[order]

        if trend_mode.startswith("Linear"):
            coeffs = np.polyfit(x_sorted, y_sorted, 1)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode.startswith("Quadratic"):
            coeffs = np.polyfit(x_sorted, y_sorted, 2)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode.startswith("Cubic"):
            coeffs = np.polyfit(x_sorted, y_sorted, 3)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode == "Moving Average":
            window = max(3, len(x_sorted)//10)
            y_ma = pd.Series(y_sorted).rolling(window=window, center=True).mean()
            ax.plot(x_sorted, y_ma, color="black", linewidth=2)

        elif trend_mode == "Logarithmic":
            x_pos = x_sorted[x_sorted > 0]
            y_pos = y_sorted[:len(x_pos)]
            coeffs = np.polyfit(np.log(x_pos), y_pos, 1)
            y_fit = coeffs[0]*np.log(x_pos) + coeffs[1]
            ax.plot(x_pos, y_fit, color="black", linewidth=2)

    if show_legend == True:
        ax.legend()
    plt.tight_layout()
    return fig

def plot_scatter(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, title: str = "", xlabel: str = "", ylabel: str = "", label_mark: bool = False,
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

    if trend_mode != "None":
        x_vals = np.asarray(x, dtype=float)
        y_vals = np.asarray(ydf, dtype=float)

        order = np.argsort(x_vals)
        x_sorted = x_vals[order]
        y_sorted = y_vals[order]

        if trend_mode.startswith("Linear"):
            coeffs = np.polyfit(x_sorted, y_sorted, 1)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode.startswith("Quadratic"):
            coeffs = np.polyfit(x_sorted, y_sorted, 2)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode.startswith("Cubic"):
            coeffs = np.polyfit(x_sorted, y_sorted, 3)
            y_fit = np.polyval(coeffs, x_sorted)
            ax.plot(x_sorted, y_fit, color="black", linewidth=2)

        elif trend_mode == "Moving Average":
            window = max(3, len(x_sorted)//10)
            y_ma = pd.Series(y_sorted).rolling(window=window, center=True).mean()
            ax.plot(x_sorted, y_ma, color="black", linewidth=2)

        elif trend_mode == "Logarithmic":
            x_pos = x_sorted[x_sorted > 0]
            y_pos = y_sorted[:len(x_pos)]
            coeffs = np.polyfit(np.log(x_pos), y_pos, 1)
            y_fit = coeffs[0]*np.log(x_pos) + coeffs[1]
            ax.plot(x_pos, y_fit, color="black", linewidth=2)

    ax.spines[["top", "right"]].set_visible(False)
    if show_legend == True:
        ax.legend()
    plt.tight_layout()
    return fig

def plot_area_stacked(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, title: str = "", xlabel: str = "", ylabel: str = "", label_mark: bool = False,
              color_mode: str = "Palette (multi-color)",
              palette_name: str = "Dark2",
              single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    if color_mode.startswith("Single"):
        colors = [single_color] * len(ydf.columns)
    else:
        colors = _get_series_colors(len(ydf.columns), "Palette", palette_name, single_color)

    x_plot = np.arange(len(x), dtype=float)
    ax.stackplot(
        x_plot,
        *[ydf[c].to_numpy(dtype=float) for c in ydf.columns],
        labels=[str(c) for c in ydf.columns],
        colors=colors
    )
    ax.set_xticks(x_plot)
    ax.set_xticklabels([str(v) for v in x])
    
    if label_mark:
        x_plot = np.arange(len(x), dtype=float)

        # Se você ainda está usando stackplot com x (strings), passe a usar x_plot
        # e depois seta os labels:
        ax.set_xticks(x_plot)
        ax.set_xticklabels([str(v) for v in x], rotation=0, ha="center")

        cum = np.zeros(len(x_plot), dtype=float)

        for i, col in enumerate(ydf.columns):
            yvals = ydf[col].to_numpy(dtype=float)
            yvals_safe = np.nan_to_num(yvals, nan=0.0)

            cum = cum + yvals_safe  # topo empilhado

            # marcação no TOPO da camada
            ax.plot(
                x_plot, cum,
                marker="o", linestyle="None",
                markersize=4, color=colors[i]
            )

            # texto mostra o valor da camada (yvals), mas posicionado no topo (cum)
            _annotate_points_with_text(ax, x_plot, cum, yvals_safe, color="#222222")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title or "Area Chart (Stacked)")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)

    if trend_mode != "None":
        ysum = ydf.sum(axis=1).to_frame("Sum")
        add_trendlines(ax, x, ysum, trend_mode)

    if show_legend == True:
        ax.legend()
    plt.tight_layout()
    return fig

def plot_area_overlapped(
    df: pd.DataFrame,
    dpi: int,
    trend_mode: str = "None",
    show_legend: bool = False,
    label_mark: bool = False,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    color_mode: str = "Palette (multi-color)",
    palette_name: str = "Dark2",
    single_color: str = "#1f77b4"
):
    fig, ax = plt.subplots(figsize=(12, 6))

    x, ydf = extract_x_y(df)
    colors = _get_series_colors(len(ydf.columns), color_mode, palette_name, single_color)

    # ---- OVERLAPPED AREA (not stacked) ----
    for i, col in enumerate(ydf.columns):
        yvals = ydf[col].to_numpy(dtype=float)

        ax.fill_between(
            x,
            yvals,
            alpha=0.6,                # ← 60% transparency
            color=colors[i],
            label=str(col)
        )

        # Optional markers + value labels
        ax.plot(x, yvals, marker="o", linestyle="None", color=colors[i], markersize=4)

        if label_mark:
            _annotate_points(ax, x, yvals, color="#222222")

        # Optional trendline
        if trend_mode != "None" and len(x) > 1:
            z = np.polyfit(x, yvals, 1)
            p = np.poly1d(z)
            ax.plot(x, p(x), linestyle="--", color=colors[i], alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    # ---- Titles ----
    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Area Chart (Overlapped)", fontsize=14)

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    if show_legend == True:
        ax.legend()

    fig.tight_layout()
    return fig

def plot_box(
    df: pd.DataFrame,
    dpi: int,
    trend_mode: str = "None",
    show_legend: bool = False,
    label_mark: bool = False,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    color_mode: str = "Palette (multi-color)",
    palette_name: str = "Dark2",
    single_color: str = "#1f77b4"
):
    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    x_arr = np.asarray(x)
    x_is_numeric = np.issubdtype(x_arr.dtype, np.number)

    # ==========================================================
    # CASE 1: X categórico + 1 coluna Y -> boxplot por categoria
    # ==========================================================
    if (len(ydf.columns) == 1) and (not x_is_numeric):
        ycol = ydf.columns[0]
        tmp = pd.DataFrame({
            "X": pd.Series(x).astype(str),
            "Y": _series_to_numeric(ydf[ycol])
        }).dropna()

        labels = []
        data = []
        for k, g in tmp.groupby("X", sort=False):
            labels.append(str(k))
            data.append(g["Y"].to_numpy(dtype=float))

        bp = ax.boxplot(
            data,
            labels=labels,
            patch_artist=True,
            medianprops=dict(color="#222222", linewidth=1),
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

        # Colors: one per category
        if color_mode.startswith("Single"):
            box_colors = [single_color] * len(data)
        else:
            box_colors = _get_series_colors(len(data), "Palette", palette_name, single_color)

        for patch, c in zip(bp["boxes"], box_colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)

        # Label Mark: whiskers/Q1/Q2/Q3 + outliers
        if label_mark:
            x_offset = 0.35
            for i, arr in enumerate(data, start=1):
                if arr.size == 0:
                    continue

                Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])
                IQR = Q3 - Q1
                limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
                limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()

                x_pos = i + x_offset
                ax.text(x_pos, limit_below, _fmt_val(limit_below), ha="left", va="center", fontsize=10)
                ax.text(x_pos, Q1, _fmt_val(Q1), ha="left", va="center", fontsize=10)
                ax.text(x_pos, Q2, _fmt_val(Q2), ha="left", va="center", fontsize=10, color="darkred", fontweight="bold")
                ax.text(x_pos, Q3, _fmt_val(Q3), ha="left", va="center", fontsize=10)
                ax.text(x_pos, limit_above, _fmt_val(limit_above), ha="left", va="center", fontsize=10)

            for i, fl in enumerate(bp.get("fliers", []), start=1):
                ys = fl.get_ydata()
                if ys is None or len(ys) == 0:
                    continue
                x_pos = i + x_offset
                for y0 in ys:
                    if np.isfinite(y0):
                        ax.text(x_pos, y0, f"{_fmt_val(y0)}", ha="left", va="center",
                                fontsize=10, color="darkred", fontweight="bold")

        # Labels
        if not xlabel:
            xlabel = "Category"
        if not ylabel:
            ylabel = str(ycol)

    # ==========================================================
    # CASE 2: múltiplas colunas Y -> boxplot por coluna (padrão)
    # ==========================================================
    else:
        data = [ydf[c].dropna().to_numpy(dtype=float) for c in ydf.columns]
        labels = [str(c) for c in ydf.columns]

        bp = ax.boxplot(
            data,
            labels=labels,
            patch_artist=True,
            medianprops=dict(color="#222222", linewidth=1),
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

        if color_mode.startswith("Single"):
            box_colors = [single_color] * len(labels)
        else:
            box_colors = _get_series_colors(len(labels), "Palette", palette_name, single_color)

        for patch, c in zip(bp["boxes"], box_colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)

        if label_mark:
            x_offset = 0.15
            for i, arr in enumerate(data, start=1):
                if arr.size == 0:
                    continue

                Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])
                IQR = Q3 - Q1
                limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
                limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()

                x_pos = i + x_offset
                ax.text(x_pos, limit_below, _fmt_val(limit_below), ha="left", va="center", fontsize=10, color="black")
                ax.text(x_pos, Q1, _fmt_val(Q1), ha="left", va="center", fontsize=10, color="black")
                ax.text(x_pos, Q2, _fmt_val(Q2), ha="left", va="center", fontsize=10, color="black", fontweight="bold")
                ax.text(x_pos, Q3, _fmt_val(Q3), ha="left", va="center", fontsize=10, color="black")
                ax.text(x_pos, limit_above, _fmt_val(limit_above), ha="left", va="center", fontsize=10, color="black")

            for i, fl in enumerate(bp.get("fliers", []), start=1):
                ys = fl.get_ydata()
                if ys is None or len(ys) == 0:
                    continue
                x_pos = i + x_offset
                for y0 in ys:
                    if np.isfinite(y0):
                        ax.text(x_pos, y0, f"{_fmt_val(y0)}", ha="left", va="center",
                                fontsize=10, color="darkred", fontweight="bold")

    # ---- title / labels ----
    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Box Plot", fontsize=14)

    if xlabel:
        ax.set_xlabel(xlabel, fontsize=14)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig

def plot_heatmap(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, label_mark: bool = False, title: str = "", xlabel: str = "", ylabel: str = "",
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

def plot_violin(
    df: pd.DataFrame,
    dpi: int,
    trend_mode: str = "None",
    show_legend: bool = False,
    label_mark: bool = False,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    color_mode: str = "Palette (multi-color)",
    palette_name: str = "Dark2",
    single_color: str = "#1f77b4"
):
    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    # ===== CASE 1: X categórico + 1 coluna Y =====
    if len(ydf.columns) == 1 and not np.issubdtype(np.asarray(x).dtype, np.number):
        ycol = ydf.columns[0]
        tmp = pd.DataFrame({
            "X": x,
            "Y": _series_to_numeric(ydf[ycol])
        }).dropna()

        groups = []
        labels = []

        for k, g in tmp.groupby("X", sort=False):
            labels.append(str(k))
            groups.append(g["Y"].to_numpy(dtype=float))

        parts = ax.violinplot(
            groups,
            showmeans=False,
            showmedians=True,
            showextrema=True
        )

        # ---- colors ----
        if color_mode.startswith("Single"):
            colors = [single_color] * len(groups)
        else:
            colors = _get_series_colors(len(groups), "Palette", palette_name, single_color)

        for pc, c in zip(parts["bodies"], colors):
            pc.set_facecolor(c)
            pc.set_alpha(0.6)

        ax.set_xticks(np.arange(1, len(labels) + 1))
        ax.set_xticklabels(labels)

        # ---- LABEL MARK (quartis + whiskers + outliers) ----
        if label_mark:
            x_offset = 0.35  # deslocamento horizontal (igual ao boxplot)

            for i, arr in enumerate(groups, start=1):
                if arr.size == 0:
                    continue

                Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])
                IQR = Q3 - Q1

                limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
                limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()

                x_pos = i + x_offset

                ax.text(x_pos, limit_below, _fmt_val(limit_below),
                        ha="left", va="center", fontsize=10)
                # ax.text(x_pos, Q1, _fmt_val(Q1),
                #         ha="left", va="center", fontsize=10)
                ax.text(x_pos, Q2, _fmt_val(Q2),
                        ha="left", va="center",
                        fontsize=10, fontweight="bold", color="darkred")
                # ax.text(x_pos, Q3, _fmt_val(Q3),
                #         ha="left", va="center", fontsize=10)
                ax.text(x_pos, limit_above, _fmt_val(limit_above),
                        ha="left", va="center", fontsize=10)

                # # outliers
                # outliers = arr[(arr < (Q1 - 1.5 * IQR)) | (arr > (Q3 + 1.5 * IQR))]
                # for y0 in outliers:
                #     if np.isfinite(y0):
                #         ax.text(
                #             x_pos, y0, f"{_fmt_val(y0)}",
                #             ha="left", va="center",
                #             fontsize=9, color="darkred", fontweight="bold"
                #         )

    # ===== CASE 2: múltiplas colunas Y =====
    else:
        data = [ydf[c].dropna().to_numpy(dtype=float) for c in ydf.columns]
        labels = [str(c) for c in ydf.columns]

        parts = ax.violinplot(
            data,
            showmeans=False,
            showmedians=True,
            showextrema=True
        )

        if color_mode.startswith("Single"):
            colors = [single_color] * len(data)
        else:
            colors = _get_series_colors(len(data), "Palette", palette_name, single_color)

        for pc, c in zip(parts["bodies"], colors):
            pc.set_facecolor(c)
            pc.set_alpha(0.6)

        ax.set_xticks(np.arange(1, len(labels) + 1))
        ax.set_xticklabels(labels)

        # ---- LABEL MARK ----
        if label_mark:
            x_offset = 0.35

            for i, arr in enumerate(data, start=1):
                if arr.size == 0:
                    continue

                Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])
                IQR = Q3 - Q1

                limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
                limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()

                x_pos = i + x_offset

                ax.text(x_pos, limit_below, _fmt_val(limit_below), ha="left", va="center", fontsize=10)
                # ax.text(x_pos, Q1, _fmt_val(Q1), ha="left", va="center", fontsize=10)
                ax.text(x_pos, Q2, _fmt_val(Q2),
                        ha="left", va="center",
                        fontsize=10, fontweight="bold", color="darkred")
                # ax.text(x_pos, Q3, _fmt_val(Q3), ha="left", va="center", fontsize=10)
                ax.text(x_pos, limit_above, _fmt_val(limit_above), ha="left", va="center", fontsize=10)

                # outliers = arr[(arr < (Q1 - 1.5 * IQR)) | (arr > (Q3 + 1.5 * IQR))]
                # for y0 in outliers:
                #     if np.isfinite(y0):
                #         ax.text(
                #             x_pos, y0, f"{_fmt_val(y0)}",
                #             ha="left", va="center",
                #             fontsize=9, color="darkred", fontweight="bold"
                #         )

    # ---- labels / title ----
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    ax.set_title(title or "Violin Plot", fontsize=14, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    return fig

def plot_histogram(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, label_mark: bool = False, title: str = "",
                   xlabel: str = "", ylabel: str = "",
                   color_mode: str = "Palette (multi-color)",
                   palette_name: str = "Dark2",
                   single_color: str = "#1f77b4"):

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    n = len(ydf.columns)
    colors = _get_series_colors(n, color_mode, palette_name, single_color)

    # overlay hist para múltiplas séries
    for i, col in enumerate(ydf.columns):
        vals = ydf[col].dropna().to_numpy(dtype=float)
        ax.hist(vals, bins="auto", alpha=0.6 if n > 1 else 0.8, label=str(col), color=colors[i])

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Histogram", fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)
    if n > 1:
        if show_legend == True:
            ax.legend()

    plt.tight_layout()
    return fig

def _kde_1d(values: np.ndarray, grid: np.ndarray):
    """KDE simples (gaussiana) sem SciPy."""
    v = values[np.isfinite(values)]
    if v.size < 2:
        return np.zeros_like(grid)

    # Silverman's rule of thumb
    std = np.std(v, ddof=1)
    if std <= 0:
        return np.zeros_like(grid)

    n = v.size
    bw = 1.06 * std * (n ** (-1 / 5))
    if bw <= 0:
        return np.zeros_like(grid)

    # KDE
    diff = (grid[:, None] - v[None, :]) / bw
    dens = np.exp(-0.5 * diff * diff).sum(axis=1) / (n * bw * np.sqrt(2 * np.pi))
    return dens

def plot_density(df: pd.DataFrame, dpi: int, trend_mode: str = "None", show_legend: bool = False, label_mark: bool = False, title: str = "",
                 xlabel: str = "", ylabel: str = "",
                 color_mode: str = "Palette (multi-color)",
                 palette_name: str = "Dark2",
                 single_color: str = "#1f77b4"):

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    n = len(ydf.columns)
    colors = _get_series_colors(n, color_mode, palette_name, single_color)

    # define grid comum
    all_vals = np.concatenate([ydf[c].dropna().to_numpy(dtype=float) for c in ydf.columns if ydf[c].notna().any()])
    all_vals = all_vals[np.isfinite(all_vals)]
    if all_vals.size == 0:
        raise ValueError("No valid numeric values for density plot.")

    xmin, xmax = np.min(all_vals), np.max(all_vals)
    if xmin == xmax:
        xmin -= 1.0
        xmax += 1.0

    grid = np.linspace(xmin, xmax, 400)

    for i, col in enumerate(ydf.columns):
        vals = ydf[col].dropna().to_numpy(dtype=float)
        dens = _kde_1d(vals, grid)
        ax.plot(grid, dens, label=str(col), color=colors[i], linewidth=2)

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Density (KDE)", fontsize=14)

    ax.spines[["top", "right"]].set_visible(False)
    if n > 1:
        if show_legend == True:
            ax.legend()

    plt.tight_layout()
    return fig

def plot_bar_2d_category(df: pd.DataFrame, group_col: str, y_col: str | None,
                         title: str = "", xlabel: str = "", ylabel: str = "",
                         palette_name: str = "tab10", single_color: str = "#1f77b4",
                         color_mode: str = "Palette (multi-color)",
                         label_mark: bool = False):
    fig, ax = plt.subplots(figsize=(12, 6))

    g = df[group_col].astype(str)

    if y_col is None:
        # frequência
        counts = g.value_counts(sort=False)
        cats = counts.index.tolist()
        y = counts.to_numpy(dtype=float)
        x_pos = np.arange(len(cats))
        if color_mode.startswith("Single"):
            colors = [single_color] * len(cats)
        else:
            colors = _get_series_colors(len(cats), "Palette", palette_name, single_color)
        bars = ax.bar(x_pos, y, color=colors)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(cats)
        if label_mark:
            _annotate_bars(ax, bars)
        if not ylabel:
            ylabel = "Frequency"
    else:
        # média por categoria
        yv = _series_to_numeric(df[y_col])
        tmp = pd.DataFrame({"group": g, "y": yv}).dropna()
        agg = tmp.groupby("group", sort=False)["y"].mean()
        cats = agg.index.tolist()
        y = agg.to_numpy(dtype=float)
        x_pos = np.arange(len(cats))
        if color_mode.startswith("Single"):
            colors = [single_color] * len(cats)
        else:
            colors = _get_series_colors(len(cats), "Palette", palette_name, single_color)
        bars = ax.bar(x_pos, y, color=colors)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(cats)
        if label_mark:
            _annotate_bars(ax, bars)
        if not ylabel:
            ylabel = f"Mean({y_col})"

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Bar Chart", fontsize=14)

    if xlabel:
        ax.set_xlabel(xlabel)
    else:
        ax.set_xlabel(group_col)

    if ylabel:
        ax.set_ylabel(ylabel)

    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig

def _split_by_group(df: pd.DataFrame, group_col: str, y_col: str):
    g = df[group_col].astype(str)
    y = _series_to_numeric(df[y_col])
    tmp = pd.DataFrame({"group": g, "y": y}).dropna()
    groups = []
    labels = []
    for k, gg in tmp.groupby("group", sort=False):
        labels.append(str(k))
        groups.append(gg["y"].to_numpy(dtype=float))
    return labels, groups

def plot_box_2d_category(df: pd.DataFrame, group_col: str, y_col: str,
                         title: str = "", xlabel: str = "", ylabel: str = "",
                         palette_name: str = "tab10", single_color: str = "#1f77b4",
                         color_mode: str = "Palette (multi-color)",
                         label_mark: bool = False):
    fig, ax = plt.subplots(figsize=(12, 6))
    labels, groups = _split_by_group(df, group_col, y_col)

    bp = ax.boxplot(
        groups, labels=labels, patch_artist=True,
        medianprops=dict(color="#333333", linewidth=2),
        whiskerprops=dict(color="#444444", linewidth=1.5),
        capprops=dict(color="#444444", linewidth=1.5),
        boxprops=dict(edgecolor="#444444", linewidth=1.5),
    )

    if color_mode.startswith("Single"):
        box_colors = [single_color] * len(labels)
    else:
        box_colors = _get_series_colors(len(labels), "Palette", palette_name, single_color)

    for patch, c in zip(bp["boxes"], box_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)

    # Label mark: quartis/outliers (usa seu padrão de deslocamento à direita)
    if label_mark:
        x_offset = 0.35
        for i, arr in enumerate(groups, start=1):
            if arr.size == 0:
                continue
            Q1, Q2, Q3 = np.percentile(arr, [25, 50, 75])
            IQR = Q3 - Q1
            limit_below = arr[arr >= (Q1 - 1.5 * IQR)].min()
            limit_above = arr[arr <= (Q3 + 1.5 * IQR)].max()
            x_pos = i + x_offset

            ax.text(x_pos, limit_below, _fmt_val(limit_below), ha="left", va="center", fontsize=10)
            ax.text(x_pos, Q1, _fmt_val(Q1), ha="left", va="center", fontsize=10)
            ax.text(x_pos, Q2, _fmt_val(Q2), ha="left", va="center", fontsize=10, color="darkred", fontweight="bold")
            ax.text(x_pos, Q3, _fmt_val(Q3), ha="left", va="center", fontsize=10)
            ax.text(x_pos, limit_above, _fmt_val(limit_above), ha="left", va="center", fontsize=10)

        # outliers (bp["fliers"] por box)
        for i, fl in enumerate(bp.get("fliers", []), start=1):
            ys = fl.get_ydata()
            if ys is None or len(ys) == 0:
                continue
            x_pos = i + x_offset
            for y0 in ys:
                if np.isfinite(y0):
                    ax.text(x_pos, y0, f"out={_fmt_val(y0)}", ha="left", va="center", fontsize=9)

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title("Box Plot", fontsize=14)

    ax.set_xlabel(xlabel or group_col)
    ax.set_ylabel(ylabel or y_col)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig

def plot_violin_2d_category(df: pd.DataFrame, group_col: str, y_col: str,
                            title: str = "", xlabel: str = "", ylabel: str = "",
                            palette_name: str = "tab10", single_color: str = "#1f77b4",
                            color_mode: str = "Palette (multi-color)"):
    fig, ax = plt.subplots(figsize=(12, 6))
    labels, groups = _split_by_group(df, group_col, y_col)

    parts = ax.violinplot(groups, showmeans=False, showmedians=True, showextrema=True)

    if color_mode.startswith("Single"):
        colors = [single_color] * len(labels)
    else:
        colors = _get_series_colors(len(labels), "Palette", palette_name, single_color)

    for pc, c in zip(parts["bodies"], colors):
        pc.set_facecolor(c)
        pc.set_alpha(0.6)

    ax.set_xticks(np.arange(1, len(labels) + 1))
    ax.set_xticklabels(labels)

    ax.set_xlabel(xlabel or group_col)
    ax.set_ylabel(ylabel or y_col)
    ax.set_title(title, fontsize=14, fontweight="bold") if title else ax.set_title("Violin", fontsize=14)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig

def plot_scatter_2d_numeric_with_group(df: pd.DataFrame, x_col: str, y_col: str, group_col: str,
                                       title: str = "", xlabel: str = "", ylabel: str = "",
                                       palette_name: str = "tab10", single_color: str = "#1f77b4",
                                       color_mode: str = "Palette (multi-color)",
                                       label_mark: bool = False, trend_mode: str = "None", show_legend: bool = False):
    fig, ax = plt.subplots(figsize=(12, 6))

    x = _series_to_numeric(df[x_col])
    y = _series_to_numeric(df[y_col])
    g = df[group_col].astype(str)

    tmp = pd.DataFrame({"x": x, "y": y, "g": g}).dropna()

    cats = list(tmp["g"].unique())
    if color_mode.startswith("Single"):
        colors = {c: single_color for c in cats}
    else:
        palette = _get_series_colors(len(cats), "Palette", palette_name, single_color)
        colors = {c: palette[i] for i, c in enumerate(cats)}

    for c in cats:
        d = tmp[tmp["g"] == c]
        ax.scatter(d["x"], d["y"], label=str(c), color=colors[c])
        if label_mark:
            _annotate_points(ax, d["x"].to_numpy(), d["y"].to_numpy(), color=colors[c])

    ax.set_title(title, fontsize=14, fontweight="bold") if title else ax.set_title("Scatter Plot", fontsize=14)
    ax.set_xlabel(xlabel or x_col)
    ax.set_ylabel(ylabel or y_col)
    # Optional global trendline (over all points)
    if trend_mode and len(tmp) >= 2:
        xn = tmp["x"].to_numpy(dtype=float)
        yn = tmp["y"].to_numpy(dtype=float)
        m = np.isfinite(xn) & np.isfinite(yn)
        if m.sum() >= 2:
            coef = np.polyfit(xn[m], yn[m], 1)
            yfit = coef[0] * xn + coef[1]
            ax.plot(xn, yfit, linestyle="--", linewidth=2, color="#222222", label="Trendline")
            if show_legend == True:
                ax.legend()
    
    if show_legend == True:
        ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig

def plot_scatter_3d_numeric_with_optional_group(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    z_col: str,
    group_col: str | None = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    zlabel: str = "",
    palette_name: str = "tab10",
    single_color: str = "#1f77b4",
    color_mode: str = "Palette (multi-color)",
    label_mark: bool = False,
    trend_mode: str = "None",
    show_legend: bool = False
):
    # Import local para evitar dependência quando 3D não é usado
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    x = _series_to_numeric(df[x_col])
    y = _series_to_numeric(df[y_col])
    z = _series_to_numeric(df[z_col])

    if group_col is not None:
        g = df[group_col].astype(str)
        tmp = pd.DataFrame({"x": x, "y": y, "z": z, "g": g}).dropna()
    else:
        tmp = pd.DataFrame({"x": x, "y": y, "z": z}).dropna()

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")

    ax.set_title(title or f"3D Scatter: {x_col} vs {y_col} vs {z_col}", fontsize=14, fontweight="bold")
    ax.set_xlabel(xlabel or x_col)
    ax.set_ylabel(ylabel or y_col)
    ax.set_zlabel(zlabel or z_col)
    ax.grid(True, linestyle="--", alpha=0.2, linewidth=1)

    # ---------- Com grupos ----------
    if group_col is not None and "g" in tmp.columns:
        cats = list(tmp["g"].unique())

        if color_mode.startswith("Single"):
            color_map = {c: single_color for c in cats}
        else:
            pal = _get_series_colors(len(cats), "Palette", palette_name, single_color)
            color_map = {c: pal[i] for i, c in enumerate(cats)}

        for c in cats:
            d = tmp[tmp["g"] == c]
            ax.scatter(
                d["x"].to_numpy(dtype=float),
                d["y"].to_numpy(dtype=float),
                d["z"].to_numpy(dtype=float),
                s=30,
                alpha=0.75,
                color=color_map[c],
                depthshade=True,
                label=f"{c} (n={len(d)})"
            )

            # Label mark (opcional) – em 3D tende a poluir; aqui anotamos o valor de Z
            if label_mark:
                for xi, yi, zi in zip(d["x"], d["y"], d["z"]):
                    ax.text(float(xi), float(yi), float(zi), _fmt_val(zi), fontsize=8, color="#222222")

        if show_legend == True:
            ax.legend()

    # ---------- Sem grupos ----------
    else:
        ax.scatter(
            tmp["x"].to_numpy(dtype=float),
            tmp["y"].to_numpy(dtype=float),
            tmp["z"].to_numpy(dtype=float),
            s=30,
            alpha=0.75,
            color=single_color,
            depthshade=True
        )

        if label_mark:
            for xi, yi, zi in zip(tmp["x"], tmp["y"], tmp["z"]):
                ax.text(float(xi), float(yi), float(zi), _fmt_val(zi), fontsize=8, color="#222222")

    plt.tight_layout()
    return fig

PLOTTERS = {
    "Bar": plot_bar,
    "Line": plot_line,
    "Scatter": plot_scatter,
    "Area (Stacked)": plot_area_stacked,
    "Area (Overlapped)": plot_area_overlapped,
    "Box Plot": plot_box,
    "Histogram": plot_histogram,
    "Density(KDE)": plot_density,
    "Violin": plot_violin,
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

# ==========================================================================================================================================
# ====================================================== MAIN CLASS ========================================================================
# ==========================================================================================================================================
class GraphGeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Graph Generator")
        self.resize(800, 450)

        self.file_path = ""
        self.single_color = None  # hex string: "#RRGGBB"

        root = QVBoxLayout(self)
        box = QGroupBox()
        grid = QGridLayout(box)

        # 0) Title
        grid.addWidget(QLabel("Title:"), 0, 0, 1, 1)
        self.le_title = QLineEdit()
        self.le_title.setPlaceholderText("Optional")
        grid.addWidget(self.le_title, 0, 1, 1, 3)

        # 1) Input file
        grid.addWidget(QLabel("Input file (CSV/XLSX):"), 1, 0, 1, 1)
        self.le_file = QLineEdit()
        self.le_file.setReadOnly(True)
        grid.addWidget(self.le_file, 1, 1, 1, 2)

        self.btn_attach = QPushButton("Select data file…")
        self.btn_attach.clicked.connect(self.attach_file)
        grid.addWidget(self.btn_attach, 1, 3, 1, 1)
        
        # Dimensions
        grid.addWidget(QLabel("Dimensions:"), 2, 0, 1, 1)

        self.ck_1d = QCheckBox("1D")
        self.ck_2d = QCheckBox("2D")
        self.ck_3d = QCheckBox("3D")

        grid.addWidget(self.ck_1d, 2, 1, 1, 1)
        grid.addWidget(self.ck_2d, 2, 2, 1, 1)
        grid.addWidget(self.ck_3d, 2, 3, 1, 1)

        # Default (keep current behavior): 1D
        self.ck_1d.setChecked(True)

        # Column selectors:
        grid.addWidget(QLabel("Select Columns:"), 4, 0, 1, 1)
        grid.addWidget(QLabel("X values:"), 3, 1, 1, 1, alignment=Qt.AlignLeft)
        self.lw_x = QListWidget()
        self.lw_x.setSelectionMode(QAbstractItemView.SingleSelection)
        grid.addWidget(self.lw_x, 4, 1, 1, 1)  

        grid.addWidget(QLabel("Y values:"), 3, 2, 1, 1, alignment=Qt.AlignLeft)
        self.lw_y = QListWidget()
        self.lw_y.setSelectionMode(QAbstractItemView.ExtendedSelection)
        grid.addWidget(self.lw_y, 4, 2, 1, 1)  

        grid.addWidget(QLabel("Z values:"), 3, 3, 1, 1, alignment=Qt.AlignLeft)
        self.lw_z = QListWidget()
        self.lw_z.setSelectionMode(QAbstractItemView.ExtendedSelection)
        grid.addWidget(self.lw_z, 4, 3, 1, 1)        
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 2); grid.setColumnStretch(2, 2); grid.setColumnStretch(3, 2)
        
        self.lw_x.itemSelectionChanged.connect(lambda: self._update_chart_type_options(self._last_df) if hasattr(self, "_last_df") else None)
        self.lw_y.itemSelectionChanged.connect(lambda: self._update_chart_type_options(self._last_df) if hasattr(self, "_last_df") else None)
        
        # cache of columns after loading a file
        self._last_df = None
        self._all_cols = []
        self._numeric_cols = []
        self._categorical_cols = []

        # Z disabled in 1D
        self.lw_z.setEnabled(False)

        # Behavior: dimensions are mutually exclusive
        self.ck_1d.stateChanged.connect(self._on_dim_changed)
        self.ck_2d.stateChanged.connect(self._on_dim_changed)
        self.ck_3d.stateChanged.connect(self._on_dim_changed)

        # 3) Chart type
        grid.addWidget(QLabel("Chart type:"), 5, 0, 1, 1)
        self.cb_plot = QComboBox()
        self.cb_plot.addItems(list(PLOTTERS.keys()))
        grid.addWidget(self.cb_plot, 5, 1, 1, 1)

        # 3) Resolution
        grid.addWidget(QLabel("Resolution (dpi):"), 5, 2, 1, 1, alignment=Qt.AlignRight)
        self.le_dpi = QLineEdit("300")
        self.le_dpi.setValidator(QIntValidator(50, 2400, self))
        self.le_dpi.setMaximumWidth(120)
        grid.addWidget(self.le_dpi, 5, 3, 1, 1)

        # 3) Trendline, mark_labels and legend
        grid.addWidget(QLabel("Select trendline:"), 6, 0, 1, 1)
        self.cb_trend = QComboBox()
        self.cb_trend.addItems("None;Linear(1st degree);Quadratic(2nd degree);Cubic(3rd degree);Moving Average;Logarithmic".split(";"))
        grid.addWidget(self.cb_trend, 6, 1, 1, 1)
        
        self.ck_legend = QCheckBox("Show legend")
        grid.addWidget(self.ck_legend, 6, 2, 1, 1)

        self.ck_label = QCheckBox("Show label mark")
        grid.addWidget(self.ck_label, 6, 3, 1, 1)

        # 4) Colors
        grid.addWidget(QLabel("Colors:"), 8, 0)

        self.cb_colors = QComboBox()
        self.cb_colors.addItems([
            "Single color (all series)",
            "Palette (multi-color)"
        ])
        grid.addWidget(self.cb_colors, 8, 1)
        # Default: Palette (multi-color)
        self.cb_colors.setCurrentText("Palette (multi-color)")

        self.btn_color = QPushButton("Pick color…")
        self.btn_color.clicked.connect(self.pick_single_color)
        grid.addWidget(self.btn_color, 8, 2)

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
        grid.addWidget(self.cb_palette, 8, 3)

        # Enable/disable palette button correctly when user changes mode
        self.cb_colors.currentIndexChanged.connect(self._update_color_mode_ui)

        # Apply initial state (Palette enabled, Pick color disabled)
        self._update_color_mode_ui()

        # 5) X-axis label
        grid.addWidget(QLabel("X-axis label:"), 9, 0)
        self.le_xlabel = QLineEdit()
        self.le_xlabel.setPlaceholderText("Optional")
        grid.addWidget(self.le_xlabel, 9, 1, 1, 3)

        # 6) Y-axis label
        grid.addWidget(QLabel("Y-axis label:"), 10, 0)
        self.le_ylabel = QLineEdit()
        self.le_ylabel.setPlaceholderText("Optional")
        grid.addWidget(self.le_ylabel, 10, 1, 1, 3)
        
        # 7) Z-axis label (for 3D mode)
        grid.addWidget(QLabel("Z-axis label:"), 11, 0)
        self.le_zlabel = QLineEdit()
        self.le_zlabel.setPlaceholderText("Optional")
        grid.addWidget(self.le_zlabel, 11, 1, 1, 3)
        
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

    def _update_chart_type_options(self, df: pd.DataFrame):
        # ===== 3D mode: only Scatter =====
        if self.ck_3d.isChecked():
            self.cb_plot.blockSignals(True)
            self.cb_plot.clear()
            self.cb_plot.addItems(["Scatter"])
            self.cb_plot.setCurrentText("Scatter")
            self.cb_plot.blockSignals(False)
            return

        # ===== 2D mode: ONLY Scatter =====
        if self.ck_2d.isChecked():
            self.cb_plot.blockSignals(True)
            self.cb_plot.clear()
            self.cb_plot.addItems(["Scatter"])
            self.cb_plot.setCurrentText("Scatter")
            self.cb_plot.blockSignals(False)
            return

        # ===== 1D mode: keep all options =====
        base_1d = [
            "Bar", "Line", "Scatter",
            "Area (Stacked)", "Area (Overlapped)",
            "Box Plot", "Heatmap",
            "Violin", "Histogram", "Density(KDE)"
        ]

        self.cb_plot.blockSignals(True)
        cur = self.cb_plot.currentText()
        self.cb_plot.clear()
        self.cb_plot.addItems(base_1d)
        if cur in base_1d:
            self.cb_plot.setCurrentText(cur)
        self.cb_plot.blockSignals(False)

    def _update_color_mode_ui(self):
        is_single = self.cb_colors.currentText().startswith("Single")
        self.btn_color.setEnabled(is_single)     # Single => enable Pick color
        self.cb_palette.setEnabled(not is_single) # Palette => enable combobox

    def _refresh_column_lists_by_mode(self):
        """
        1D: X shows ONLY categorical; Y shows ONLY numeric; Z disabled
        2D: X shows ONLY numeric; Y shows ONLY numeric; Z disabled
        3D: X/Y/Z show ONLY numeric; Z enabled
        """

        if self._last_df is None:
            return

        is_1d = self.ck_1d.isChecked()
        is_2d = self.ck_2d.isChecked()
        is_3d = self.ck_3d.isChecked()

        # choose what each list should display
        if is_1d:
            x_cols = self._categorical_cols
            y_cols = self._numeric_cols
            z_cols = []
        else:
            # 2D and 3D: only numeric columns everywhere
            x_cols = self._numeric_cols
            y_cols = self._numeric_cols
            z_cols = self._numeric_cols if is_3d else []

        # clear selections first (avoid “stale” invalid selections)
        self.lw_x.blockSignals(True)
        self.lw_y.blockSignals(True)
        self.lw_z.blockSignals(True)

        self.lw_x.clear()
        self.lw_y.clear()
        self.lw_z.clear()

        self.lw_x.addItems(x_cols)
        self.lw_y.addItems(y_cols)
        self.lw_z.addItems(z_cols)

        # selection modes
        if is_1d:
            self.lw_y.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.lw_z.setEnabled(False)

        elif is_2d:
            self.lw_y.setSelectionMode(QAbstractItemView.SingleSelection)
            self.lw_z.setEnabled(False)

        else:
            # 3D
            self.lw_y.setSelectionMode(QAbstractItemView.SingleSelection)
            self.lw_z.setSelectionMode(QAbstractItemView.SingleSelection)
            self.lw_z.setEnabled(True)

        self.lw_x.blockSignals(False)
        self.lw_y.blockSignals(False)
        self.lw_z.blockSignals(False)

        # optionally: auto-select sensible defaults
        # 1D: pick first categorical as X
        if is_1d and self.lw_x.count() > 0:
            self.lw_x.setCurrentRow(0)
        # 2D/3D: pick first numeric as X and second numeric as Y if possible
        if (is_2d or is_3d) and self.lw_x.count() > 0:
            self.lw_x.setCurrentRow(0)
        if (is_2d or is_3d) and self.lw_y.count() > 1:
            self.lw_y.setCurrentRow(1)
        if is_3d and self.lw_z.count() > 2:
            self.lw_z.setCurrentRow(2)

    def _on_dim_changed(self):
        sender = self.sender()

        # exclusividade
        if sender == self.ck_1d and self.ck_1d.isChecked():
            self.ck_2d.setChecked(False)
            self.ck_3d.setChecked(False)
        elif sender == self.ck_2d and self.ck_2d.isChecked():
            self.ck_1d.setChecked(False)
            self.ck_3d.setChecked(False)
        elif sender == self.ck_3d and self.ck_3d.isChecked():
            self.ck_1d.setChecked(False)
            self.ck_2d.setChecked(False)

        is_1d = self.ck_1d.isChecked()
        is_2d = self.ck_2d.isChecked()
        is_3d = self.ck_3d.isChecked()

        # Z só em 3D
        self.lw_z.setEnabled(is_3d)

        # Em 1D: Y multi; Em 2D: Y single; Em 3D: X/Y/Z single
        if is_1d:
            self.lw_y.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.lw_z.setEnabled(False)

        elif is_2d:
            self.lw_y.clearSelection()
            self.lw_y.setSelectionMode(QAbstractItemView.SingleSelection)
            self.lw_z.setEnabled(False)

        else:
            # 3D
            self.lw_y.clearSelection()
            self.lw_z.clearSelection()

            self.lw_y.setSelectionMode(QAbstractItemView.SingleSelection)
            self.lw_z.setSelectionMode(QAbstractItemView.SingleSelection)

            self.lw_z.setEnabled(True)

        # refresh visible columns when dimension changes
        self._refresh_column_lists_by_mode()

        # update chart options as well (2D/3D -> scatter only, etc.)
        if self._last_df is not None:
            self._update_chart_type_options(self._last_df)
        # refresh visible columns when dimension changes
        self._refresh_column_lists_by_mode()

        # update chart options as well (2D/3D -> scatter only, etc.)
        if self._last_df is not None:
            self._update_chart_type_options(self._last_df)

        # Atualiza opções de gráficos (se já tiver df carregado)
        if hasattr(self, "_last_df") and self._last_df is not None:
            self._update_chart_type_options(self._last_df)

    def _populate_column_lists(self, df: pd.DataFrame):
        self._last_df = df

        self._all_cols = [str(c) for c in df.columns]

        # classify columns
        numeric_cols = []
        categorical_cols = []

        for c in df.columns:
            name = str(c)
            if self._is_column_numeric(df, name):
                numeric_cols.append(name)
            else:
                categorical_cols.append(name)

        self._numeric_cols = numeric_cols
        self._categorical_cols = categorical_cols

        # enable/disable dimension checkboxes based on numeric columns count
        nnum = len(self._numeric_cols)
        self.ck_2d.setEnabled(nnum >= 2)
        self.ck_3d.setEnabled(nnum >= 3)

        # if user selected an invalid dimension (e.g. 3D but not enough numeric cols), fallback to 1D
        if self.ck_3d.isChecked() and not self.ck_3d.isEnabled():
            self.ck_1d.setChecked(True)
        if self.ck_2d.isChecked() and not self.ck_2d.isEnabled():
            self.ck_1d.setChecked(True)

        # refresh visible columns based on current mode
        self._refresh_column_lists_by_mode()
        self._update_chart_type_options(df)

    def _get_selected_columns(self, lw: QListWidget):
        return [it.text() for it in lw.selectedItems()]

    def _is_column_numeric(self, df: pd.DataFrame, colname: str) -> bool:
        if colname not in df.columns:
            return False
        s = _series_to_numeric(df[colname])
        return s.notna().mean() >= 0.5

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
            # Fill mapping selectors
            self._populate_column_lists(df)
            self.show_dataframe(df)
        except Exception as e:
            QMessageBox.critical(self, "File read error", str(e))
            return

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
        trend_mode = self.cb_trend.currentText().strip()
        show_legend = self.ck_legend.isChecked()        
        label_mark = self.ck_label.isChecked()
        xlabel = (self.le_xlabel.text() or "").strip()
        ylabel = (self.le_ylabel.text() or "").strip()
        zlabel = (self.le_zlabel.text() or "").strip()

        color_mode = self.cb_colors.currentText()
        palette_name = self.cb_palette.currentText()
        single_color = self.single_color
        if color_mode.startswith("Single") and not single_color:
            single_color = "#1f77b4"

        # --- Manual mapping (Part 1: 1D only) ---
        if self.ck_1d.isChecked():
            sel_x = self._get_selected_columns(self.lw_x)
            sel_y = self._get_selected_columns(self.lw_y)

            # If user selected something, enforce mapping; otherwise fallback to current auto-extract
            if sel_x or sel_y:
                if len(sel_x) != 1:
                    _warn(self, "Warning", "In 1D mode you must select exactly ONE X column (classes/labels).")
                    return

                x_col = sel_x[0]

                # X must be NON-numeric (classes)
                if self._is_column_numeric(df, x_col):
                    _warn(self, "Warning", "In 1D mode, X must be a categorical (text) column. Please select a non-numeric column for X.")
                    return

                if len(sel_y) == 0:
                    _warn(self, "Warning", "In 1D mode you must select at least ONE numeric column for Y.")
                    return

                # Y must be numeric
                bad_y = [c for c in sel_y if not self._is_column_numeric(df, c)]
                if bad_y:
                    _warn(self, "Warning", f"These Y columns are not numeric (or not mostly numeric): {', '.join(bad_y)}")
                    return

                # Build a mapped dataframe compatible with current pipeline: X + Ys
                mapped = pd.DataFrame()
                mapped["X"] = df[x_col].astype(str)

                for c in sel_y:
                    mapped[c] = df[c]

                df = mapped  # <- overwrite df, then your existing plotters keep working
        # ---------- 2D MODE ----------
        if self.ck_2d.isChecked():
            sel_x = self._get_selected_columns(self.lw_x)
            sel_y = self._get_selected_columns(self.lw_y)  # em 2D deve ser 1

            if len(sel_x) != 1 or len(sel_y) != 1:
                _warn(self, "Warning", "In 2D mode you must select exactly ONE numeric X column and ONE numeric Y column.")
                return

            x_col = sel_x[0]
            y_col = sel_y[0]

            # both must be numeric
            if not self._is_column_numeric(df, x_col):
                _warn(self, "Warning", "In 2D mode, X must be numeric (scatter).")
                return

            if not self._is_column_numeric(df, y_col):
                _warn(self, "Warning", "In 2D mode, Y must be numeric (scatter).")
                return

            group_col = _find_group_column(df)

            if group_col is None:
                # No grouping column -> single-color scatter, allow trendline + label_mark
                mapped = pd.DataFrame({
                    "X": _series_to_numeric(df[x_col]),
                    y_col: df[y_col]
                })

                fig = plot_scatter(
                    df=mapped,
                    dpi=dpi,
                    trend_mode=trend_mode,
                    show_legend=show_legend,
                    title=title or "Scatter Plot",
                    xlabel=xlabel or x_col,
                    ylabel=ylabel or y_col,
                    label_mark=label_mark,
                    color_mode="Single color (all series)",
                    palette_name=palette_name,
                    single_color=single_color
                )
            else:
                # With grouping column -> colored by categories, allow label_mark and (optional) trendline over all points
                fig = plot_scatter_2d_numeric_with_group(
                    df=df,
                    x_col=x_col,
                    y_col=y_col,
                    group_col=group_col,
                    title=title or "Scatter Plot",
                    xlabel=xlabel or x_col,
                    ylabel=ylabel or y_col,
                    palette_name=palette_name,
                    single_color=single_color,
                    color_mode=color_mode,
                    label_mark=label_mark,
                    trend_mode=trend_mode,
                    show_legend=show_legend
                )

            self.viewer = PlotViewer(fig, dpi=dpi, parent=self)
            self.viewer.show()
            return
        # ---------- end 2D MODE ----------


        # ---------- 3D MODE ----------
        if self.ck_3d.isChecked():
            # Chart type forced to Scatter
            if self.cb_plot.currentText().strip() != "Scatter":
                self.cb_plot.setCurrentText("Scatter")

            sel_x = self._get_selected_columns(self.lw_x)
            sel_y = self._get_selected_columns(self.lw_y)
            sel_z = self._get_selected_columns(self.lw_z)

            if len(sel_x) != 1 or len(sel_y) != 1 or len(sel_z) != 1:
                _warn(self, "Warning", "In 3D mode you must select exactly ONE numeric column for X, Y, and Z.")
                return

            x_col, y_col, z_col = sel_x[0], sel_y[0], sel_z[0]

            # Must be numeric
            bad = [c for c in (x_col, y_col, z_col) if not self._is_column_numeric(df, c)]
            if bad:
                _warn(self, "Warning", f"In 3D mode, X/Y/Z must be numeric. Non-numeric (or mostly non-numeric): {', '.join(bad)}")
                return

            # Trendline not supported in 3D
            if trend_mode != "None":
                QMessageBox.information(
                    self,
                    "Info",
                    "Trendline is not supported in 3D scatter. It will be ignored."
                )

            group_col = _find_group_column(df)

            fig = plot_scatter_3d_numeric_with_optional_group(
                df=df,
                x_col=x_col,
                y_col=y_col,
                z_col=z_col,
                group_col=group_col,
                title=title or f"3D Scatter: {x_col} vs {y_col} vs {z_col}",
                xlabel=xlabel or x_col,
                ylabel=ylabel or y_col,
                zlabel=zlabel or z_col,
                palette_name=palette_name,
                single_color=single_color,
                color_mode=color_mode,
                label_mark=label_mark,
            )

            self.viewer = PlotViewer(fig, dpi=dpi, parent=self)
            self.viewer.show()
            return
        # ---------- end 3D MODE ----------
        
        try:
            plotter = PLOTTERS[plot_type]
            fig = plotter(
                df=df,
                dpi=dpi,
                trend_mode=trend_mode,
                show_legend=show_legend,
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

# ==========================================================================================================================================
# ====================================================== MAIN FUNCTION =====================================================================
# ==========================================================================================================================================

def main():
    app = QApplication(sys.argv)
    w = GraphGeneratorUI()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
