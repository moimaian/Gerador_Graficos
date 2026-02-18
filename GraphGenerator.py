#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import numpy as np
import pandas as pd

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QMessageBox, QGroupBox, QColorDialog, QMainWindow, QToolBar, QAction, QDialog, QTableWidget, QTableWidgetItem
)

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

try:
    import seaborn as sns
    _HAS_SEABORN = True
except Exception:
    _HAS_SEABORN = False


def _warn(parent, title, msg):
    QMessageBox.warning(parent, title, msg)


def _info(parent, title, msg):
    QMessageBox.information(parent, title, msg)


import subprocess
import sys
from PyQt5.QtWidgets import QMessageBox


def ensure_openpyxl(parent=None) -> bool:
    """
    Verifica se openpyxl está instalado.
    Caso não esteja, pergunta ao usuário se deseja instalar.
    Retorna True se openpyxl estiver disponível ao final.
    """
    try:
        import openpyxl
        return True
    except ImportError:
        reply = QMessageBox.question(
            parent,
            "Dependência ausente",
            "Para abrir arquivos XLSX é necessário instalar a biblioteca 'openpyxl'.\n\n"
            "Deseja instalar agora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "openpyxl"]
                )
                return True
            except Exception as e:
                QMessageBox.critical(
                    parent,
                    "Erro na instalação",
                    f"Falha ao instalar openpyxl.\n\n{e}"
                )
                return False
        else:
            QMessageBox.warning(
                parent,
                "Operação cancelada",
                "Não é possível abrir arquivos XLSX sem o openpyxl."
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
            raise RuntimeError("openpyxl não disponível")

        # 1) tenta com header padrão
        df = pd.read_excel(path, engine="openpyxl")

        # Se o XLSX tiver a 1ª linha como DADO (e não cabeçalho),
        # pandas pode transformar o "cabeçalho" em números (ex.: 53).
        # Nesse caso, relê sem header.
        if any(isinstance(c, (int, float, np.integer, np.floating)) for c in df.columns):
            df = pd.read_excel(path, engine="openpyxl", header=None)

            # se tiver só 2 colunas, padroniza nomes
            if df.shape[1] >= 2:
                df = df.rename(columns={0: "X", 1: "Y"})

    else:
        raise ValueError("Formato não suportado. Use CSV ou XLSX.")

    if df is None or df.empty:
        raise ValueError("Arquivo vazio ou inválido.")

    # remove colunas totalmente vazias
    df = df.dropna(axis=1, how="all")

    # remove linhas totalmente vazias
    df = df.dropna(axis=0, how="all")

    if df.empty:
        raise ValueError("Não há dados válidos no arquivo.")

    return df


def extract_x_y(df: pd.DataFrame):
    """
    Regras:
    1) Se existir coluna 'X' (case-insensitive), usa ela como X e o restante como Y.
    2) Caso contrário, se a 1ª coluna for majoritariamente NÃO numérica (nomes),
       usa essa 1ª coluna como X e o restante (numérico) como Y.
    3) Se nada disso acontecer, usa X = índice (linhas) e Y = colunas numéricas.
    """
    # normaliza nomes
    cols = list(df.columns)
    cols_lower = {str(c).strip().lower(): c for c in cols}

    # Caso 1: coluna X explícita
    if "x" in cols_lower:
        x_col = cols_lower["x"]
        x = df[x_col].astype(str).to_numpy()
        ydf = df.drop(columns=[x_col])

    else:
        # Testa se a 1ª coluna é categórica (nomes)
        first = df.iloc[:, 0]
        first_num = pd.to_numeric(first, errors="coerce")

        non_numeric_ratio = first_num.isna().mean()  # fração que NÃO virou número

        if non_numeric_ratio >= 0.5:  # maioria são nomes -> use como X
            x = first.astype(str).to_numpy()
            ydf = df.iloc[:, 1:].copy()
        else:
            # fallback: X por índice (linhas)
            x = np.arange(1, len(df) + 1)
            ydf = df.copy()

    # Mantém apenas colunas numéricas para Y
    ydf = ydf.apply(pd.to_numeric, errors="coerce")
    ydf = ydf.dropna(axis=1, how="all")

    if ydf.empty:
        raise ValueError("Não encontrei colunas numéricas para Y (colunas).")

    return x, ydf



def add_trendlines(ax, x, ydf: pd.DataFrame):
    # Ajuste linear (1º grau) por série
    # Para barras: tendência usando a soma/mean por categoria (conforme caso)
    x_num = np.arange(len(x)) if not np.issubdtype(np.array(x).dtype, np.number) else np.asarray(x, dtype=float)
    for col in ydf.columns:
        y = ydf[col].to_numpy(dtype=float)
        m = np.isfinite(x_num) & np.isfinite(y)
        if m.sum() < 2:
            continue
        coef = np.polyfit(x_num[m], y[m], 1)
        yfit = coef[0] * x_num + coef[1]
        ax.plot(np.arange(len(x)) if x_num is not None and x_num.ndim == 1 and not np.issubdtype(np.array(x).dtype, np.number) else x_num,
                yfit, linestyle="--", linewidth=2, label=f"Tendência ({col})")


def plot_bar(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
             color_mode: str = "Paleta (várias cores)",
             palette_name: str = "Dark2",
             single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    x_pos = np.arange(len(x))
    n_series = len(ydf.columns)
    width = 0.8 / max(n_series, 1)

    # Caso especial: 1 coluna Y + "Paleta" => cores POR BARRA (cada categoria um tom)
    if (not color_mode.startswith("Uma cor")) and (n_series == 1):
        if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
            bar_colors = sns.color_palette(palette_name, n_colors=len(x))
        else:
            cmap = plt.get_cmap(palette_name)
            bar_colors = [cmap(i / max(len(x) - 1, 1)) for i in range(len(x))]

        col = ydf.columns[0]
        y = ydf[col].to_numpy(dtype=float)

        bars = ax.bar(x_pos, y, width=0.8, label=str(col), color=bar_colors)

        for b in bars:
            h = b.get_height()
            if np.isfinite(h):
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    h + (0.01 * np.nanmax(y) if np.nanmax(y) != 0 else 0.1),
                    f"{h:g}",
                    va="bottom",
                    ha="center",
                    color=b.get_facecolor(),
                    weight="bold",
                    fontsize=12
                )

        if trendline:
            add_trendlines(ax, x_pos, ydf)

    else:
        # Caso geral: cores POR SÉRIE (coluna)
        if color_mode.startswith("Uma cor"):
            series_colors = [single_color] * n_series
        else:
            if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
                series_colors = sns.color_palette(palette_name, n_colors=n_series)
            else:
                cmap = plt.get_cmap(palette_name)
                series_colors = [cmap(i / max(n_series - 1, 1)) for i in range(n_series)]

        for i, col in enumerate(ydf.columns):
            y = ydf[col].to_numpy(dtype=float)
            pos = x_pos - (0.4 - width / 2) + i * width
            bars = ax.bar(pos, y, width=width, label=str(col), color=series_colors[i])

            for b in bars:
                h = b.get_height()
                if np.isfinite(h):
                    ax.text(
                        b.get_x() + b.get_width() / 2,
                        h + (0.01 * np.nanmax(y) if np.nanmax(y) != 0 else 0.1),
                        f"{h:g}",
                        va="bottom",
                        ha="center",
                        color=b.get_facecolor(),
                        weight="bold",
                        fontsize=12
                    )

        if trendline:
            add_trendlines(ax, x_pos, ydf)

    ax.set_xlabel("X", fontsize=14)
    ax.set_ylabel("Y", fontsize=14)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title or "Gráfico de Barras", fontsize=14)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([str(v) for v in x], rotation=0, ha="center")

    # legenda apenas se fizer sentido
    if len(ydf.columns) > 1 or trendline:
        ax.legend()

    plt.tight_layout()
    return fig


def _get_series_colors(n, color_mode, palette_name, single_color):
    if color_mode.startswith("Uma cor"):
        return [single_color] * n
    if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
        return sns.color_palette(palette_name, n_colors=n)
    cmap = plt.get_cmap(palette_name)
    return [cmap(i / max(n - 1, 1)) for i in range(n)]


def plot_line(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
              color_mode: str = "Paleta (várias cores)",
              palette_name: str = "Dark2",
              single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = _get_series_colors(len(ydf.columns), color_mode, palette_name, single_color)

    for i, col in enumerate(ydf.columns):
        ax.plot(x, ydf[col].to_numpy(dtype=float), marker="o", label=str(col), color=colors[i])

    ax.set_title(title or "Gráfico de Linhas")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.spines[["top", "right"]].set_visible(False)

    if trendline:
        add_trendlines(ax, x, ydf)

    ax.legend()
    plt.tight_layout()
    return fig

def plot_scatter(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
                 color_mode: str = "Paleta (várias cores)",
                 palette_name: str = "Dark2",
                 single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = _get_series_colors(len(ydf.columns), color_mode, palette_name, single_color)

    for i, col in enumerate(ydf.columns):
        ax.scatter(x, ydf[col].to_numpy(dtype=float), label=str(col), color=colors[i])

    ax.set_title(title or "Gráfico de Dispersão")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.spines[["top", "right"]].set_visible(False)

    if trendline:
        add_trendlines(ax, x, ydf)

    ax.legend()
    plt.tight_layout()
    return fig

def plot_area(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
              color_mode: str = "Paleta (várias cores)",
              palette_name: str = "Dark2",
              single_color: str = "#1f77b4"):

    x, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    # cores por série (stackplot precisa de uma cor por camada)
    if color_mode.startswith("Uma cor"):
        colors = [single_color] * len(ydf.columns)
    else:
        if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
            colors = sns.color_palette(palette_name, n_colors=len(ydf.columns))
        else:
            cmap = plt.get_cmap(palette_name)
            n = max(len(ydf.columns), 1)
            colors = [cmap(i / max(n - 1, 1)) for i in range(n)]

    ax.stackplot(
        x,
        *[ydf[c].to_numpy(dtype=float) for c in ydf.columns],
        labels=[str(c) for c in ydf.columns],
        colors=colors
    )

    ax.set_title(title or "Gráfico de Área (Stacked)")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.spines[["top", "right"]].set_visible(False)

    if trendline:
        ysum = ydf.sum(axis=1).to_frame("Soma")
        add_trendlines(ax, x, ysum)

    ax.legend(loc="upper left")
    plt.tight_layout()
    return fig


def plot_box(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
             color_mode: str = "Paleta (várias cores)",
             palette_name: str = "Dark2",
             single_color: str = "#1f77b4"):

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))

    data = [ydf[c].dropna().to_numpy(dtype=float) for c in ydf.columns]

    bp = ax.boxplot(data, labels=[str(c) for c in ydf.columns], patch_artist=True)

    # aplicar cores por box
    if color_mode.startswith("Uma cor"):
        box_colors = [single_color] * len(ydf.columns)
    else:
        if _HAS_SEABORN and palette_name in ["Dark2", "Set2", "Set3", "tab10", "tab20", "Paired", "Accent"]:
            box_colors = sns.color_palette(palette_name, n_colors=len(ydf.columns))
        else:
            cmap = plt.get_cmap(palette_name)
            n = max(len(ydf.columns), 1)
            box_colors = [cmap(i / max(n - 1, 1)) for i in range(n)]

    for patch, c in zip(bp["boxes"], box_colors):
        patch.set_facecolor(c)

    ax.set_title(title or "Boxplot")
    ax.set_ylabel("Y")
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    return fig

def plot_heatmap(df: pd.DataFrame, dpi: int, trendline: bool, title: str,
                 color_mode: str = "Paleta (várias cores)",
                 palette_name: str = "viridis",
                 single_color: str = "#1f77b4"):

    from matplotlib.colors import LinearSegmentedColormap

    _, ydf = extract_x_y(df)
    fig, ax = plt.subplots(figsize=(12, 6))
    data = ydf.to_numpy(dtype=float)

    # "Uma cor" => cria colormap do branco até a cor escolhida
    if color_mode.startswith("Uma cor"):
        cmap = LinearSegmentedColormap.from_list("single", ["#ffffff", single_color])
    else:
        cmap = palette_name  # colormap padrão do matplotlib

    im = ax.imshow(data, aspect="auto", cmap=cmap)

    ax.set_title(title or "Heatmap")
    ax.set_xlabel("Colunas (Y)")
    ax.set_ylabel("Linhas (X)")
    ax.set_xticks(np.arange(len(ydf.columns)))
    ax.set_xticklabels([str(c) for c in ydf.columns], rotation=45, ha="right")
    fig.colorbar(im, ax=ax)

    plt.tight_layout()
    return fig

PLOTTERS = {
    "Barras": plot_bar,
    "Linhas": plot_line,
    "Dispersão": plot_scatter,
    "Área (Stacked)": plot_area,
    "Boxplot": plot_box,
    "Heatmap": plot_heatmap,
}

class PlotViewer(QMainWindow):
    def __init__(self, fig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visualização do Gráfico")
        self.resize(1000, 650)

        self.fig = fig
        self.canvas = FigureCanvas(self.fig)
        self.setCentralWidget(self.canvas)

        # Toolbar padrão do matplotlib (zoom, pan, etc.)
        self.addToolBar(NavigationToolbar(self.canvas, self))

        # Toolbar de salvar
        tb = QToolBar("Salvar", self)
        self.addToolBar(tb)

        act_png = QAction("Salvar .png", self)
        act_svg = QAction("Salvar .svg", self)
        act_tiff = QAction("Salvar .tiff", self)
        act_jpg = QAction("Salvar .jpg", self)
        act_saveas = QAction("Salvar como…", self)

        act_png.triggered.connect(lambda: self.save_as("png"))
        act_svg.triggered.connect(lambda: self.save_as("svg"))
        act_tiff.triggered.connect(lambda: self.save_as("tiff"))
        act_jpg.triggered.connect(lambda: self.save_as("jpg"))
        act_saveas.triggered.connect(lambda: self.save_as_dialog())

        tb.addAction(act_png)
        tb.addAction(act_svg)
        tb.addAction(act_tiff)
        tb.addAction(act_jpg)
        tb.addSeparator()
        tb.addAction(act_saveas)

    def save_as(self, ext: str):
        # nome sugerido
        suggested = f"grafico.{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Salvar como {ext.upper()}",
            suggested,
            f"{ext.upper()} (*.{ext})"
        )
        if not path:
            return

        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"

        try:
            # dpi só impacta raster (png/jpg/tiff). SVG ignora dpi na prática.
            self.fig.savefig(path, dpi=300 if ext in ("png", "jpg", "tiff") else None)
            QMessageBox.information(self, "Sucesso", f"Salvo em:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))

    def save_as_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar gráfico",
            "grafico.png",
            "PNG (*.png);;SVG (*.svg);;TIFF (*.tiff);;JPG (*.jpg)"
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower().replace(".", "")
        if ext not in ("png", "svg", "tiff", "jpg"):
            QMessageBox.warning(self, "Aviso", "Escolha um formato válido: png, svg, tiff ou jpg.")
            return

        try:
            self.fig.savefig(path, dpi=300 if ext in ("png", "jpg", "tiff") else None)
            QMessageBox.information(self, "Sucesso", f"Salvo em:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))


class GraphGeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerador de Gráficos")
        self.resize(720, 400)

        self.file_path = ""

        root = QVBoxLayout(self)

        box = QGroupBox("Configurações")
        grid = QGridLayout(box)

        # Tipo de gráfico
        grid.addWidget(QLabel("Tipo de gráfico:"), 0, 0)
        self.cb_plot = QComboBox()
        self.cb_plot.addItems(list(PLOTTERS.keys()))
        grid.addWidget(self.cb_plot, 0, 1, 1, 3)

        # DPI
        grid.addWidget(QLabel("Resolução (dpi):"), 1, 0)
        self.le_dpi = QLineEdit("300")
        self.le_dpi.setValidator(QIntValidator(50, 2400, self))
        self.le_dpi.setMaximumWidth(120)
        grid.addWidget(self.le_dpi, 1, 1)

        # Trendline
        self.ck_trend = QCheckBox("Mostrar linha de tendência")
        grid.addWidget(self.ck_trend, 1, 2, 1, 2)

        # Paleta / cor
        grid.addWidget(QLabel("Cores:"), 2, 0)

        self.cb_colors = QComboBox()
        self.cb_colors.addItems([
            "Uma cor (todas as séries)",
            "Paleta (várias cores)"
        ])
        grid.addWidget(self.cb_colors, 2, 1)

        self.btn_color = QPushButton("Escolher cor…")
        self.btn_color.clicked.connect(self.pick_single_color)
        grid.addWidget(self.btn_color, 2, 2)

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
        grid.addWidget(self.cb_palette, 2, 3)

        self.single_color = None  # hex string, ex: "#1f77b4"

        # Ajuste visual inicial
        self.cb_colors.currentIndexChanged.connect(self._update_color_mode_ui)
        self._update_color_mode_ui()

        # Arquivo
        grid.addWidget(QLabel("Arquivo (CSV/XLSX):"), 3, 0)
        self.le_file = QLineEdit()
        self.le_file.setReadOnly(True)
        grid.addWidget(self.le_file, 3, 1, 1, 2)

        self.btn_attach = QPushButton("Anexar arquivo…")
        self.btn_attach.clicked.connect(self.attach_file)
        grid.addWidget(self.btn_attach, 3, 3)

        # Título (opcional)
        grid.addWidget(QLabel("Título (opcional):"), 4, 0)
        self.le_title = QLineEdit()
        grid.addWidget(self.le_title, 4, 1, 1, 3)

        root.addWidget(box)

        # Botão inferior
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_generate = QPushButton("Gerar Gráfico")
        self.btn_generate.setMinimumHeight(38)
        self.btn_generate.clicked.connect(self.generate_chart)
        bottom.addWidget(self.btn_generate)
        root.addLayout(bottom)

    def show_dataframe(self, df: pd.DataFrame):
        dialog = QDialog(self)
        dialog.setWindowTitle("Visualização do Arquivo Selecionado")
        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        max_rows = min(200, len(df))  # limite para não travar
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

        btn_save = QPushButton("Salvar")
        btn_save.setFixedSize(200, 30)
        btn_close = QPushButton("Fechar")
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
            # Usa o diretório do arquivo carregado como base
            initial_dir = os.path.dirname(self.file_path) if getattr(self, "file_path", "") else os.path.expanduser("~")
            file_path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Salvar dados",
                os.path.join(initial_dir, "dados_exportados.csv"),
                "CSV (*.csv);;Excel (*.xlsx)"
            )
            if file_path:
                try:
                    if file_path.lower().endswith(".xlsx"):
                        # garante openpyxl se for salvar xlsx
                        if not ensure_openpyxl(dialog):
                            return
                        df.to_excel(file_path, index=False)
                    else:
                        df.to_csv(file_path, index=False)
                    QMessageBox.information(dialog, "Salvo", f"Dados salvos em:\n{file_path}")
                except Exception as e:
                    QMessageBox.critical(dialog, "Erro ao salvar", str(e))

        btn_save.clicked.connect(save_dialog)
        btn_close.clicked.connect(dialog.accept)

        dialog.resize(900, 500)
        dialog.exec_()

    def _update_color_mode_ui(self):
        single = (self.cb_colors.currentText() == "Uma cor (todas as séries)")
        self.btn_color.setEnabled(single)
        self.cb_palette.setEnabled(not single)

    def pick_single_color(self):
        c = QColorDialog.getColor(parent=self)
        if c and c.isValid():
            self.single_color = c.name()  # "#RRGGBB"
            # Opcional: mostrar no texto do botão
            self.btn_color.setText(f"Cor: {self.single_color}")

    def attach_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione um arquivo",
            "",
            "Dados (*.csv *.xlsx *.xls);;CSV (*.csv);;Excel (*.xlsx *.xls)"
        )
        if not path:
            return

        self.file_path = path
        self.le_file.setText(path)

        # Carrega e mostra dataframe
        try:
            df = load_xy_table(self.file_path, parent=self)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao ler arquivo", str(e))
            return

        # Exibe prévia do dataframe
        self.show_dataframe(df)

    def generate_chart(self):
        if not self.file_path:
            _warn(self, "Aviso", "Selecione um arquivo CSV ou XLSX.")
            return

        dpi_txt = (self.le_dpi.text() or "").strip()
        if not dpi_txt:
            _warn(self, "Aviso", "Informe a resolução (dpi).")
            return

        try:
            dpi = int(dpi_txt)
            if dpi <= 0:
                raise ValueError
        except Exception:
            _warn(self, "Aviso", "O dpi deve ser um número inteiro válido (ex.: 300).")
            return

        plot_type = self.cb_plot.currentText().strip()
        if plot_type not in PLOTTERS:
            _warn(self, "Aviso", "Selecione um tipo de gráfico.")
            return

        # Lê dados
        try:
            df = load_xy_table(self.file_path, parent=self)
        except Exception as e:
            _warn(self, "Erro ao ler arquivo", str(e))
            return

        title = (self.le_title.text() or "").strip()
        trend = self.ck_trend.isChecked()

        # Cores
        color_mode = self.cb_colors.currentText()
        palette_name = self.cb_palette.currentText()
        single_color = self.single_color
        if color_mode.startswith("Uma cor") and not single_color:
            single_color = "#1f77b4"

        # Gera figura (plotter agora retorna fig)
        try:
            plotter = PLOTTERS[plot_type]
            fig = plotter(
                df=df,
                dpi=dpi,                 # você pode usar dpi em fontes/tamanho se quiser; save fica no viewer
                trendline=trend,
                title=title,
                color_mode=color_mode,
                palette_name=palette_name,
                single_color=single_color
            )
        except Exception as e:
            _warn(self, "Erro ao gerar gráfico", str(e))
            return

        # Abre janela de visualização
        self.viewer = PlotViewer(fig, parent=self)  # mantém referência p/ não fechar
        self.viewer.show()

def main():
    app = QApplication(sys.argv)
    w = GraphGeneratorUI()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


    def generate_chart(self):
        if not self.file_path:
            _warn(self, "Aviso", "Selecione um arquivo CSV ou XLSX.")
            return

        dpi_txt = (self.le_dpi.text() or "").strip()
        if not dpi_txt:
            _warn(self, "Aviso", "Informe a resolução (dpi).")
            return

        try:
            dpi = int(dpi_txt)
            if dpi <= 0:
                raise ValueError
        except Exception:
            _warn(self, "Aviso", "O dpi deve ser um número inteiro válido (ex.: 300).")
            return

        plot_type = self.cb_plot.currentText().strip()
        if plot_type not in PLOTTERS:
            _warn(self, "Aviso", "Selecione um tipo de gráfico.")
            return

        # Lê dados
        try:
            df = load_xy_table(self.file_path, parent=self)
        except Exception as e:
            _warn(self, "Erro ao ler arquivo", str(e))
            return

        title = (self.le_title.text() or "").strip()
        trend = self.ck_trend.isChecked()

        # Cores
        color_mode = self.cb_colors.currentText()
        palette_name = self.cb_palette.currentText()
        single_color = self.single_color
        if color_mode.startswith("Uma cor") and not single_color:
            single_color = "#1f77b4"

        # Gera figura (plotter agora retorna fig)
        try:
            plotter = PLOTTERS[plot_type]
            fig = plotter(
                df=df,
                dpi=dpi,                 # você pode usar dpi em fontes/tamanho se quiser; save fica no viewer
                trendline=trend,
                title=title,
                color_mode=color_mode,
                palette_name=palette_name,
                single_color=single_color
            )
        except Exception as e:
            _warn(self, "Erro ao gerar gráfico", str(e))
            return

        # Abre janela de visualização
        self.viewer = PlotViewer(fig, parent=self)  # mantém referência p/ não fechar
        self.viewer.show()

def main():
    app = QApplication(sys.argv)
    w = GraphGeneratorUI()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
