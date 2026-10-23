from PyQt6.QtWidgets import QMessageBox

from ui.loginscreen1 import Ui_MainWindow
class LoginSrceenEx(Ui_MainWindow):
    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.MainWindow=MainWindow
        self.setupSignalAndLot()
    def showWindow(self):
        self.MainWindow.show()
    def setupSignalAndLot(self):
        self.pushButtonLogin.clicked.connect(self.process_login)
        self.pushButtonGoRegister.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.pushButtonGoLogin.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButtonExit.clicked.connect(self.MainWindow.close)
        self.pushButtonRegister.clicked.connect(self.process_resign)
    def process_resign(self):
        from dal.user_dao import UserDAO
        uid = self.regUsername.text()
        pwd = self.regPassword.text()
        regc = self.regConfirm.text()
        if pwd != regc:
            self.msgBox = QMessageBox()
            self.msgBox.setText("Passwords do not match")
            self.msgBox.exec()
            return
        us = UserDAO.register(uid, pwd)
        self.msgBox=QMessageBox()
        if us is None:
            self.msgBox.setText("Register failed")
        else:
            self.msgBox.setText("Register Successful")
        self.msgBox.exec()
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