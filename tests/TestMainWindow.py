import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.mainwindowEX import MainWindowEx

app=QApplication(sys.argv)
myui=MainWindowEx()
myui.show()

app.exec()