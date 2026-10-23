import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.LoginSrceenEx1 import LoginSrceenEx

app=QApplication(sys.argv)
myui=LoginSrceenEx()
myui.setupUi(QMainWindow())
myui.showWindow()
app.exec()