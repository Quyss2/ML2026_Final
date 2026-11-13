import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.regression_EX import RegressionScreenEx

app = QApplication(sys.argv)
myui = RegressionScreenEx()
myui.setupUi(QMainWindow())
myui.showWindow()
app.exec()
