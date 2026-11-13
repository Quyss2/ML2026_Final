
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)
from PyQt6.QtCore import QDateTime, QObject, QThread, pyqtSignal
from dal.data_dao import DataDAO
from ui.mainwindow import Ui_MainWindow


class _ClassificationDataWorker(QObject):
    completed = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            records = DataDAO.show_all_data()
            if records is None:
                raise RuntimeError("Không thể tải dữ liệu sự kiện từ cơ sở dữ liệu.")

            from prediction.classification import PurchaseClassifier

            cleaned_records, report = PurchaseClassifier.clean_records(records)
            self.completed.emit(cleaned_records, report)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindowEx(QMainWindow):
    DATA_FIELDS = DataDAO.COLUMNS
    EDITABLE_FIELDS = DataDAO.EDITABLE_COLUMNS

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.displayedData = []
        self.regressionWindow = None
        self.regressionUi = None
        self.classificationWindow = None
        self.classificationUi = None
        self._classificationThread = None
        self._classificationWorker = None
        self.currentPage = 1
        self.pageSize = 10
        self.totalRecords = 0
        self.currentPageFilters = {}
        self.setupSignalAndLot()
        self.ui.tblData.itemSelectionChanged.connect(self.updateSelectedCount)
        self.setupFilterOptions()
        self.updatePriceRange()
        self.showDataBase()

    def setupSignalAndLot(self):
        self.ui.btnRefresh.clicked.connect(self.refreshData)
        self.ui.btnAdd.clicked.connect(self.addData)
        self.ui.btnDelete.clicked.connect(self.deleteData)
        self.ui.btnEdit.clicked.connect(self.editData)
        self.ui.btnExport.clicked.connect(self.exportData)
        self.ui.cbFilterEventType.currentIndexChanged.connect(
            lambda _index: self.updatePriceRange()
        )
        self.ui.cbFilterBrand.currentIndexChanged.connect(
            lambda _index: self.updatePriceRange()
        )
        self.ui.cbFilterCategory.currentIndexChanged.connect(
            lambda _index: self.updatePriceRange()
        )
        self.ui.btnApplyFilter.clicked.connect(self.ApplyFilter)
        self.ui.btnClearFilter.clicked.connect(self.ClearFilter)
        self.ui.btnDataVisualization.clicked.connect(self.openDataVisualization)
        self.ui.btnRegression.clicked.connect(self.openRegression)
        self.ui.btnClassification.clicked.connect(self.openClassification)
        self.ui.cbPageSize.currentIndexChanged.connect(self.changePageSize)
        self.ui.btnFirstPage.clicked.connect(lambda: self.loadPage(1))
        self.ui.btnPrevPage.clicked.connect(lambda: self.loadPage(self.currentPage - 1))
        self.ui.btnNextPage.clicked.connect(lambda: self.loadPage(self.currentPage + 1))
        self.ui.btnLastPage.clicked.connect(lambda: self.loadPage(self.lastPage))

    def showDataBase(self):
        self._loadDataPage(self.currentFilters(), page=1)

    @property
    def lastPage(self):
        return max(1, (self.totalRecords + self.pageSize - 1) // self.pageSize)

    def _loadDataPage(self, filters, page=None):
        if page is not None:
            self.currentPage = page

        total_records = DataDAO.count_data(filters)
        if total_records is None:
            QMessageBox.warning(self, "Lỗi", "Không thể đếm dữ liệu từ cơ sở dữ liệu.")
            return False

        page_count = max(1, (total_records + self.pageSize - 1) // self.pageSize)
        self.currentPage = min(max(1, self.currentPage), page_count)
        data_list = DataDAO.filter_data(
            filters,
            limit=self.pageSize,
            offset=(self.currentPage - 1) * self.pageSize,
        )
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải dữ liệu từ cơ sở dữ liệu.")
            return False

        self.totalRecords = total_records
        self.currentPageFilters = dict(filters)
        self._displayData(data_list)
        self.ui.lblPage.setText(f"Trang {self.currentPage} / {page_count}")
        self.ui.btnFirstPage.setEnabled(self.currentPage > 1)
        self.ui.btnPrevPage.setEnabled(self.currentPage > 1)
        self.ui.btnNextPage.setEnabled(self.currentPage < page_count)
        self.ui.btnLastPage.setEnabled(self.currentPage < page_count)
        return True

    def loadPage(self, page):
        self._loadDataPage(self.currentPageFilters, page=page)

    def changePageSize(self, index):
        try:
            text = self.ui.cbPageSize.itemText(index)
            self.pageSize = int(text.split("/", 1)[0].strip())
        except (ValueError, IndexError):
            QMessageBox.warning(self, "Lỗi", "Kích thước trang không hợp lệ.")
            return
        self._loadDataPage(self.currentPageFilters, page=1)

    def _displayData(self, data_list):
        self.displayedData = list(data_list)
        table = self.ui.tblData
        sorting_enabled = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setRowCount(len(data_list))
        fields = self.DATA_FIELDS[:table.columnCount()]
        for row_index, record in enumerate(data_list):
            for column_index, field in enumerate(fields):
                value = getattr(record, field)
                text = "" if value is None else str(value)
                table.setItem(row_index, column_index, QTableWidgetItem(text))

        table.setSortingEnabled(sorting_enabled)
        self.ui.lblRecordCount.setText(f"Tổng: {self.totalRecords} bản ghi")
        self.updateSelectedCount()

    # Bộ lọc
    def setupFilterOptions(self, preserve_selection=False):
        fields = self.DATA_FIELDS[:self.ui.tblData.columnCount()]
        column_combo = self.ui.cbFilterColumn
        selected_column = column_combo.currentData() if preserve_selection else "all"
        column_combo.clear()
        column_combo.addItem("Tất cả cột", "all")
        for column_index, field in enumerate(fields):
            header = self.ui.tblData.horizontalHeaderItem(column_index)
            label = header.text() if header is not None else field
            column_combo.addItem(label, field)
        selected_index = column_combo.findData(selected_column)
        column_combo.setCurrentIndex(max(selected_index, 0))

        options = {
            "cbFilterEventType": ("event_type", "Tất cả loại sự kiện"),
            "cbFilterBrand": ("brand", "Tất cả thương hiệu"),
            "cbFilterCategory": ("category_code", "Tất cả danh mục"),
        }
        values_by_combo = {}
        for combo_name, (column, _) in options.items():
            values = DataDAO.get_distinct_values(column)
            if values is None:
                QMessageBox.warning(
                    self,
                    "Lỗi",
                    f"Không thể tải danh sách giá trị cho cột {column}.",
                )
                return False
            values_by_combo[combo_name] = values

        for combo_name, (_, placeholder) in options.items():
            combo = getattr(self.ui, combo_name)
            selected_value = combo.currentData() if preserve_selection else None
            values = values_by_combo[combo_name]
            if selected_value is not None and selected_value not in values:
                values.append(selected_value)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(placeholder, None)
            for value in values:
                combo.addItem(str(value), value)
            selected_index = combo.findData(selected_value)
            combo.setCurrentIndex(max(selected_index, 0))
            combo.blockSignals(False)
        return True

    def _selectedCategoryFilters(self):
        return {
            "event_type": self.ui.cbFilterEventType.currentData(),
            "brand": self.ui.cbFilterBrand.currentData(),
            "category_code": self.ui.cbFilterCategory.currentData(),
        }

    def updatePriceRange(self, preserve_values=False):
        old_from = self.ui.spnPriceFrom.value()
        old_to = self.ui.spnPriceTo.value()
        old_time_from = self.ui.dtFilterFrom.dateTime().toPyDateTime()
        old_time_to = self.ui.dtFilterTo.dateTime().toPyDateTime()
        filter_ranges = DataDAO.get_filter_ranges(self._selectedCategoryFilters())
        if filter_ranges is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải khoảng thời gian và giá từ cơ sở dữ liệu.")
            return

        min_price = filter_ranges["min_price"]
        max_price = filter_ranges["max_price"]
        if min_price is None or max_price is None:
            min_price = max_price = 0

        min_price = float(min_price)
        max_price = float(max_price)
        self.ui.spnPriceFrom.setRange(min_price, max_price)
        self.ui.spnPriceTo.setRange(min_price, max_price)
        self.ui.spnPriceFrom.setValue(
            min(max(old_from, min_price), max_price) if preserve_values else min_price
        )
        self.ui.spnPriceTo.setValue(
            min(max(old_to, min_price), max_price) if preserve_values else max_price
        )

        min_event_time = filter_ranges["min_event_time"]
        max_event_time = filter_ranges["max_event_time"]
        if min_event_time is not None and max_event_time is not None:
            if hasattr(min_event_time, "to_pydatetime"):
                min_event_time = min_event_time.to_pydatetime()
            if hasattr(max_event_time, "to_pydatetime"):
                max_event_time = max_event_time.to_pydatetime()
            minimum = QDateTime.fromString(
                min_event_time.strftime("%Y-%m-%d %H:%M:%S"),
                "yyyy-MM-dd HH:mm:ss",
            )
            maximum = QDateTime.fromString(
                max_event_time.strftime("%Y-%m-%d %H:%M:%S"),
                "yyyy-MM-dd HH:mm:ss",
            )
            self.ui.dtFilterFrom.setDateTimeRange(minimum, maximum)
            self.ui.dtFilterTo.setDateTimeRange(minimum, maximum)
            self.ui.dtFilterFrom.setDateTime(
                self._clampDateTime(old_time_from, min_event_time, max_event_time)
                if preserve_values
                else minimum
            )
            self.ui.dtFilterTo.setDateTime(
                self._clampDateTime(old_time_to, min_event_time, max_event_time)
                if preserve_values
                else maximum
            )

    @staticmethod
    def _clampDateTime(value, minimum, maximum):
        if value < minimum:
            value = minimum
        elif value > maximum:
            value = maximum
        return QDateTime.fromString(
            value.strftime("%Y-%m-%d %H:%M:%S"),
            "yyyy-MM-dd HH:mm:ss",
        )

    def currentFilters(self):
        return {
            **self._selectedCategoryFilters(),
            "event_time_from": self.ui.dtFilterFrom.dateTime().toPyDateTime(),
            "event_time_to": self.ui.dtFilterTo.dateTime().toPyDateTime(),
            "price_from": self.ui.spnPriceFrom.value(),
            "price_to": self.ui.spnPriceTo.value(),
            "search_text": self.ui.edtSearch.text().strip(),
            "search_column": self.ui.cbFilterColumn.currentData(),
        }

    def refreshData(self):
        if not self.setupFilterOptions(preserve_selection=True):
            return
        self.updatePriceRange(preserve_values=True)
        if self._loadDataPage(self.currentFilters()):
            self._updateOpenVisualization()

    def updateSelectedCount(self):
        selected_count = len(self.ui.tblData.selectionModel().selectedRows())
        self.ui.lblSelected.setText(f"Đã chọn: {selected_count}")

    def _recordDialog(self, title, initial_values=None):
        initial_values = initial_values or {}
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        inputs = {}
        labels = {
            "event_time": "Thời gian (YYYY-MM-DD HH:MM:SS)",
            "event_type": "Loại sự kiện",
            "product_id": "Mã sản phẩm",
            "category_id": "Mã danh mục",
            "category_code": "Danh mục",
            "brand": "Thương hiệu",
            "price": "Giá",
            "user_id": "Mã người dùng",
            "user_session": "Phiên",
        }
        for field in self.EDITABLE_FIELDS:
            editor = QLineEdit(dialog)
            value = initial_values.get(field)
            editor.setText("" if value is None else str(value))
            inputs[field] = editor
            form.addRow(labels[field], editor)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addWidget(buttons)
        result = {}

        def submit():
            try:
                for field in self.EDITABLE_FIELDS:
                    text = inputs[field].text().strip()
                    if not text:
                        result[field] = None
                    elif field in ("product_id", "category_id", "user_id"):
                        result[field] = int(text)
                    elif field == "price":
                        value = Decimal(text)
                        if not value.is_finite():
                            raise ValueError("Giá phải là một số hợp lệ.")
                        result[field] = value
                    elif field == "event_time":
                        result[field] = datetime.fromisoformat(
                            text.replace("T", " ")
                        )
                    else:
                        result[field] = text
            except (ValueError, InvalidOperation) as error:
                QMessageBox.warning(
                    dialog,
                    "Dữ liệu không hợp lệ",
                    f"Vui lòng kiểm tra các trường số và thời gian. {error}",
                )
                return
            dialog.accept()

        buttons.accepted.connect(submit)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return result

    def _selectedRecordIds(self):
        table = self.ui.tblData
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()})
        record_ids = []
        for row in rows:
            item = table.item(row, 0)
            if item is not None:
                try:
                    record_ids.append(int(item.text()))
                except ValueError:
                    QMessageBox.warning(self, "Lỗi", "ID bản ghi được chọn không hợp lệ.")
                    return None
        return record_ids

    def ApplyFilter(self):
        if self._loadDataPage(self.currentFilters(), page=1):
            self._updateOpenVisualization()

    def ClearFilter(self):
        for combo in (
            self.ui.cbFilterColumn,
            self.ui.cbFilterEventType,
            self.ui.cbFilterBrand,
            self.ui.cbFilterCategory,
        ):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.ui.edtSearch.clear()
        self.updatePriceRange()
        self.ApplyFilter()

    # CRUD
    def addData(self):
        values = self._recordDialog("Thêm bản ghi")
        if values is None:
            return
        if DataDAO.insert_data(values) is None:
            QMessageBox.warning(self, "Lỗi", "Không thể thêm bản ghi vào cơ sở dữ liệu.")
            return
        self.refreshData()

    def deleteData(self):
        record_ids = self._selectedRecordIds()
        if record_ids is None:
            return
        if not record_ids:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn bản ghi cần xoá.")
            return
        answer = QMessageBox.question(
            self,
            "Xác nhận xoá",
            f"Bạn có chắc muốn xoá {len(record_ids)} bản ghi đã chọn?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not DataDAO.delete_data(record_ids):
            QMessageBox.warning(self, "Lỗi", "Không thể xoá bản ghi khỏi cơ sở dữ liệu.")
            return
        self.refreshData()

    def editData(self):
        record_ids = self._selectedRecordIds()
        if record_ids is None:
            return
        if len(record_ids) != 1:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn đúng một bản ghi để sửa.")
            return
        row = self.ui.tblData.selectionModel().selectedRows()[0].row()
        initial_values = {
            field: self.ui.tblData.item(row, column).text()
            if self.ui.tblData.item(row, column) is not None
            else ""
            for column, field in enumerate(self.DATA_FIELDS[1:], start=1)
        }
        values = self._recordDialog("Sửa bản ghi", initial_values)
        if values is None:
            return
        if not DataDAO.update_data(record_ids[0], values):
            QMessageBox.warning(self, "Lỗi", "Không thể cập nhật bản ghi trong cơ sở dữ liệu.")
            return
        self.refreshData()

    def exportData(self):
        file_path = Path(__file__).resolve().parent.parent / "databases" / "cleaned_data.csv"
        data_list = DataDAO.filter_data(self.currentPageFilters)
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải dữ liệu để xuất.")
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(self.DATA_FIELDS)
                for record in data_list:
                    writer.writerow(
                        [
                            getattr(record, field)
                            if getattr(record, field) is not None
                            else ""
                            for field in self.DATA_FIELDS
                        ]
                    )
        except OSError as error:
            QMessageBox.warning(self, "Lỗi", f"Không thể ghi tệp CSV: {error}")
            return
        QMessageBox.information(
            self,
            "Xuất dữ liệu",
            f"Đã xuất {len(data_list)} bản ghi ra tệp CSV:\n{file_path}",
        )

    def openDataVisualization(self):
        from ui.DataVisualizationEX import DataVisualizationEx
        if getattr(self, "dataVisualizationWindow", None) is None:
            self.dataVisualizationWindow = QMainWindow()
            self.dataVisualizationUi = DataVisualizationEx()
            self.dataVisualizationUi.setupUi(self.dataVisualizationWindow)
        if not self._updateOpenVisualization():
            return
        self.dataVisualizationUi.showWindow()

    def _updateOpenVisualization(self):
        if getattr(self, "dataVisualizationUi", None) is None:
            return False
        data_list = DataDAO.filter_data(self.currentPageFilters)
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải dữ liệu để trực quan hóa.")
            return False
        self.dataVisualizationUi.updateCharts(data_list)
        return True

    def openRegression(self):
        from ui.regression_EX import RegressionScreenEx

        if self.regressionWindow is None:
            self.regressionWindow = QMainWindow()
            self.regressionUi = RegressionScreenEx()
            self.regressionUi.setupUi(self.regressionWindow)
        self.regressionUi.showWindow()
    def openClassification(self):
        from ui.classificationUI import ClassificationPage

        if self.classificationWindow is not None:
            self.classificationWindow.show()
            self.classificationWindow.raise_()
            self.classificationWindow.activateWindow()
            return

        window = QMainWindow(self)
        window.setWindowTitle("Phân loại khả năng mua hàng")
        window.resize(1450, 900)
        page = ClassificationPage([])
        page.trainButton.setEnabled(False)
        page.status.setText("Đang tải và tiền xử lý dữ liệu sự kiện...")
        window.setCentralWidget(page)
        self.classificationWindow = window
        self.classificationUi = page
        window.show()

        thread = QThread(self)
        worker = _ClassificationDataWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._classificationDataLoaded)
        worker.failed.connect(self._classificationDataFailed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._classificationLoadFinished)
        self._classificationThread = thread
        self._classificationWorker = worker
        thread.start()

    def _classificationDataLoaded(self, records, report):
        if self.classificationUi is not None:
            self.classificationUi.setCleanedData(records, report)
        if not records and self.classificationWindow is not None:
            QMessageBox.information(
                self,
                "Thông báo",
                "Cơ sở dữ liệu chưa có dữ liệu sự kiện phù hợp để phân loại.",
            )

    def _classificationDataFailed(self, message):
        QMessageBox.warning(
            self,
            "Lỗi tải dữ liệu",
            f"Không thể mở Classification: {message}",
        )
        if self.classificationWindow is not None:
            self.classificationWindow.close()
        self.classificationWindow = None
        self.classificationUi = None

    def _classificationLoadFinished(self):
        self._classificationThread = None
        self._classificationWorker = None
