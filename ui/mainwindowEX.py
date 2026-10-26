
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTableWidgetItem
from dal.data_dao import DataDAO
from ui.mainwindow import Ui_MainWindow


class MainWindowEx(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setupSignalAndLot()
        self.showDataBase()

    def setupSignalAndLot(self):
        self.ui.btnRefresh.clicked.connect(self.showDataBase)

    def showDataBase(self):
        data_list = DataDAO.show_all_data()
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải dữ liệu từ cơ sở dữ liệu.")
            return

        table = self.ui.tblData
        sorting_enabled = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setRowCount(len(data_list))
        fields = (
            "id",
            "event_time",
            "event_type",
            "product_id",
            "category_id",
            "category_code",
            "brand",
            "price",
            "user_id",
            "user_session",
        )
        for row_index, record in enumerate(data_list):
            for column_index, field in enumerate(fields):
                value = getattr(record, field)
                text = "" if value is None else str(value)
                table.setItem(row_index, column_index, QTableWidgetItem(text))

        table.setSortingEnabled(sorting_enabled)
        self.ui.lblRecordCount.setText(f"Tổng: {len(data_list)} bản ghi")
