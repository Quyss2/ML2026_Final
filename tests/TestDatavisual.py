import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.DataVisualizationEX import DataVisualizationEx
app=QApplication(sys.argv)
myui=DataVisualizationEx()
myui.setupUi(QMainWindow())
myui.showWindow()
app.exec()