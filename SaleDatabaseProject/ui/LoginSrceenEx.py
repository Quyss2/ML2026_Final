from PyQt6.QtWidgets import QMessageBox

from ui.LoginScreen import Ui_MainWindow
class LoginSrceenEx(Ui_MainWindow):
    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.MainWindow=MainWindow
        self.setupSignalAndLot()
    def showWindow(self):
        self.MainWindow.show()

    def setupSignalAndLot(self):
        self.pushButtonLogin.clicked.connect(self.process_login)
        pass
    def process_login(self):
        from dal.user_dao import UserDAO
        uid = self.admin.text()
        pwd = self.password.text()
        us = UserDAO.login(uid, pwd)
        self.msgBox=QMessageBox()
        if us is None:
            self.msgBox.setText("Login failed")
        else:
            self.msgBox.setText("Login Successful")
        self.msgBox.exec()