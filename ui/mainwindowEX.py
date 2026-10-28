
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)
from dal.data_dao import DataDAO
from ui.mainwindow import Ui_MainWindow


class MainWindowEx(QMainWindow):
    DATA_FIELDS = DataDAO.COLUMNS
    EDITABLE_FIELDS = DataDAO.EDITABLE_COLUMNS

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setupSignalAndLot()
        self.ui.tblData.itemSelectionChanged.connect(self.updateSelectedCount)
        self.showDataBase()
        self.setupFilterOptions()
        self.updatePriceRange()

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

    def showDataBase(self):
        data_list = DataDAO.show_all_data()
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải dữ liệu từ cơ sở dữ liệu.")
            return

        self._displayData(data_list)

    def _displayData(self, data_list):
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
        self.ui.lblRecordCount.setText(f"Tổng: {len(data_list)} bản ghi")
        self.updateSelectedCount()

    def setupFilterOptions(self, preserve_selection=False):
        fields = self.DATA_FIELDS[:self.ui.tblData.columnCount()]
        column_combo = self.ui.cbFilterColumn
        selected_column = column_combo.currentData() if preserve_selection else "all"
        column_combo.clear()
        column_combo.addItem("Tất cả cột", "all")
        for field in fields:
            column_combo.addItem(field, field)
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
        price_range = DataDAO.get_price_range(self._selectedCategoryFilters())
        if price_range is None:
            QMessageBox.warning(self, "Lỗi", "Không thể tải khoảng giá từ cơ sở dữ liệu.")
            return

        min_price, max_price = price_range
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

    def currentFilters(self):
        return {
            **self._selectedCategoryFilters(),
            "price_from": self.ui.spnPriceFrom.value(),
            "price_to": self.ui.spnPriceTo.value(),
            "search_text": self.ui.edtSearch.text().strip(),
            "search_column": self.ui.cbFilterColumn.currentData(),
        }

    def refreshData(self):
        if not self.setupFilterOptions(preserve_selection=True):
            return
        self.updatePriceRange(preserve_values=True)
        self.ApplyFilter()

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
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất dữ liệu",
            "data.csv",
            "CSV (*.csv)",
        )
        if not file_path:
            return
        data_list = DataDAO.filter_data(self.currentFilters())
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
            f"Đã xuất {len(data_list)} bản ghi ra tệp CSV.",
        )

    # Bộ lọc
    def ApplyFilter(self):
        data_list = DataDAO.filter_data(self.currentFilters())
        if data_list is None:
            QMessageBox.warning(self, "Lỗi", "Không thể lọc dữ liệu từ cơ sở dữ liệu.")
            return
        self._displayData(data_list)

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
        self.showDataBase()
