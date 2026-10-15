import sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from SaleDatabaseProject.ui.SalesMainWindowEX import SalesMainWindowEx

app=QApplication(sys.argv)
myui=SalesMainWindowEx()
myui.setupUi(QMainWindow())
myui.showWindow()
app.exec()