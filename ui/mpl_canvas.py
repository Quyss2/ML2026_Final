
from PyQt6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.fig = Figure(facecolor="white", layout="constrained")
        super().__init__(self.fig)
        if parent is not None:
            self.setParent(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: transparent;")
