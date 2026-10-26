
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.LoginSrceenEx1 import LoginSrceenEx

app = QApplication(sys.argv)

login_window = QMainWindow()
login_ui = LoginSrceenEx()
login_ui.setupUi(login_window)

login_window.show()

sys.exit(app.exec())
