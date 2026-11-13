import json
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QObject, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from prediction.classification import ClassificationError, PurchaseClassifier


class _TrainingWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, classifier, records, training_rate):
        super().__init__()
        self.classifier = classifier
        self.records = records
        self.training_rate = training_rate

    def run(self):
        try:
            self.completed.emit(
                self.classifier._train_cleaned(self.records, self.training_rate)
            )
        except Exception as error:
            self.failed.emit(str(error))


class ClassificationPage(QWidget):
    """Full-page UI for training and using the purchase classifier."""

    MODEL_PATH = (
        Path(__file__).resolve().parents[1]
        / "prediction"
        / "trained"
        / "purchase_classifier.json"
    )

    def __init__(self, records, parent=None):
        super().__init__(parent)
        self.setObjectName("contentWidget")
        self.records, self.cleaningReport = PurchaseClassifier.clean_records(records)
        self._value_counts = {
            "category_code": Counter(),
            "brand": Counter(),
        }
        for record in self.records:
            for field, counts in self._value_counts.items():
                value = record.get(field)
                if value:
                    counts[value] += 1
        self.classifier = PurchaseClassifier()
        self._training_thread = None
        self._training_worker = None
        self._last_metrics = None
        self._last_training_rate = None
        self._current_training_rate = None

        self.setStyleSheet(
            "QWidget#contentWidget {background: #f1f5f9; color: #334155; "
            "font-family: 'Segoe UI';}"
            "QWidget#classificationContent {background: #f1f5f9;}"
            "QWidget#contentWidget QLabel {background: transparent; color: #334155;}"
            "QWidget#contentWidget QLabel#lblPageTitle {font-size: 24px; "
            "font-weight: bold; color: #0f172a;}"
            "QWidget#contentWidget QLabel#lblPageDesc {font-size: 13px; color: #64748b;}"
            "QFrame#classificationCard, QFrame#metricCard {"
            "background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;}"
            "QFrame#classificationCard QLabel {background: transparent;}"
            "QLabel#sectionTitle {font-size: 15px; font-weight: bold; color: #0f172a;}"
            "QLabel#metricTitle {font-size: 11px; font-weight: bold; color: #64748b;}"
            "QLabel#metricValue {font-size: 22px; font-weight: bold; color: #0f172a;}"
            "QLabel#statusLabel {color: #475569;}"
            "QLabel#predictionResult {font-size: 16px; font-weight: bold; color: #0f172a;}"
            "QWidget#contentWidget QLineEdit, QWidget#contentWidget QComboBox, "
            "QWidget#contentWidget QSpinBox, QWidget#contentWidget QDoubleSpinBox {"
            "background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; "
            "padding: 0 10px; min-height: 34px; color: #0f172a; font-size: 13px;}"
            "QWidget#contentWidget QLineEdit:focus, QWidget#contentWidget QComboBox:focus, "
            "QWidget#contentWidget QSpinBox:focus, QWidget#contentWidget "
            "QDoubleSpinBox:focus {border: 1px solid #2563eb;}"
            "QWidget#contentWidget QPushButton {background: #ffffff; color: #334155; "
            "border: 1px solid #cbd5e1; border-radius: 6px; padding: 0 16px; "
            "min-height: 34px; font-size: 13px; font-weight: bold;}"
            "QWidget#contentWidget QPushButton:hover {background: #f1f5f9;}"
            "QWidget#contentWidget QPushButton:disabled {color: #94a3b8; "
            "background: #f8fafc;}"
            "QWidget#contentWidget QPushButton#btnAdd, "
            "QWidget#contentWidget QPushButton#btnApplyFilter {background: #2563eb; "
            "color: #ffffff; border: none;}"
            "QWidget#contentWidget QPushButton#btnAdd:hover, "
            "QWidget#contentWidget QPushButton#btnApplyFilter:hover {background: #1d4ed8;}"
            "QTableWidget {background: #ffffff; alternate-background-color: #f8fafc; "
            "border: 1px solid #e2e8f0; border-radius: 6px; gridline-color: #f1f5f9; "
            "color: #0f172a; font-size: 13px; "
            "selection-background-color: #dbeafe; selection-color: #0f172a;}"
            "QHeaderView::section {background: #f1f5f9; color: #475569; "
            "font-weight: bold; border: none; border-bottom: 1px solid #e2e8f0; "
            "padding: 10px 12px;}"
            "QProgressBar {height: 16px; border: 1px solid #cbd5e1; border-radius: 7px; "
            "background: #f1f5f9; text-align: center; color: #334155;}"
            "QProgressBar::chunk {background: #2563eb; border-radius: 6px;}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("classificationContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(14)

        title = QLabel("Phân loại khả năng mua hàng")
        title.setObjectName("lblPageTitle")
        description = QLabel(
            "Huấn luyện mô hình dự đoán phiên truy cập có phát sinh mua hàng hay không "
            "từ hành vi xem, thêm giỏ hàng, sản phẩm, thương hiệu, danh mục và thời gian."
        )
        description.setObjectName("lblPageDesc")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)

        training_card = self._card("DỮ LIỆU VÀ HUẤN LUYỆN")
        training_layout = QVBoxLayout(training_card)
        training_layout.setContentsMargins(16, 14, 16, 14)
        training_layout.setSpacing(10)
        training_header = QHBoxLayout()
        self.datasetSummary = QLabel(
            f"Nguồn dữ liệu: events (CSDL) · "
            f"{self.cleaningReport['raw_count']:,} dòng đầu vào · "
            f"{self.cleaningReport['clean_count']:,} dòng hợp lệ"
        )
        self.datasetSummary.setObjectName("statusLabel")
        rate_label = QLabel("Tỷ lệ huấn luyện:")
        self.trainingRate = QSpinBox(self)
        self.trainingRate.setRange(50, 90)
        self.trainingRate.setValue(80)
        self.trainingRate.setSuffix("%")
        self.trainButton = QPushButton("Huấn luyện mô hình")
        self.trainButton.setObjectName("btnApplyFilter")
        self.evaluateButton = QPushButton("Đánh giá mô hình")
        self.evaluateButton.setEnabled(False)
        self.saveButton = QPushButton("Xuất mô hình")
        self.saveButton.setEnabled(False)
        self.loadButton = QPushButton("Tải mô hình")
        training_header.addWidget(self.datasetSummary)
        training_header.addStretch(1)
        training_header.addWidget(rate_label)
        training_header.addWidget(self.trainingRate)
        training_header.addWidget(self.trainButton)
        training_header.addWidget(self.evaluateButton)
        training_header.addWidget(self.saveButton)
        training_header.addWidget(self.loadButton)
        training_layout.addLayout(training_header)
        self.status = QLabel(
            "Mô hình chưa được huấn luyện. Dữ liệu được gom theo phiên người dùng."
        )
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)
        training_layout.addWidget(self.status)
        self.cleaningSummary = QLabel(self._cleaning_summary())
        self.cleaningSummary.setObjectName("statusLabel")
        self.cleaningSummary.setWordWrap(True)
        training_layout.addWidget(self.cleaningSummary)
        self.preprocessingSummary = QLabel(
            "Chuẩn hóa loại sự kiện, khoảng trắng và giá trị thiếu; "
            "thời gian được chuyển về cùng định dạng. Đặc trưng số được chuẩn hóa "
            "theo z-score trên dữ liệu huấn luyện, danh mục/thương hiệu được mã hóa one-hot."
        )
        self.preprocessingSummary.setObjectName("statusLabel")
        self.preprocessingSummary.setWordWrap(True)
        training_layout.addWidget(self.preprocessingSummary)
        layout.addWidget(training_card)

        data_card = self._card("DỮ LIỆU SAU LÀM SẠCH")
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(12, 12, 12, 12)
        data_layout.setSpacing(8)
        data_heading = QLabel("Bản ghi sự kiện dùng để phân loại theo phiên")
        data_heading.setObjectName("sectionTitle")
        data_layout.addWidget(data_heading)
        self.dataTable = QTableWidget()
        self.dataTable.setColumnCount(8)
        self.dataTable.setHorizontalHeaderLabels(
            (
                "Thời gian",
                "Loại sự kiện",
                "Mã sản phẩm",
                "Danh mục",
                "Thương hiệu",
                "Giá",
                "Người dùng",
                "Phiên",
            )
        )
        self.dataTable.setRowCount(min(200, len(self.records)))
        self.dataTable.setAlternatingRowColors(True)
        self.dataTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dataTable.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.dataTable.verticalHeader().setVisible(False)
        self.dataTable.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.dataTable.horizontalHeader().setStretchLastSection(True)
        self.dataTable.setMinimumHeight(230)
        self._populate_data_table()
        data_layout.addWidget(self.dataTable)

        metrics_card = self._card("KẾT QUẢ ĐÁNH GIÁ")
        metrics_layout = QVBoxLayout(metrics_card)
        metrics_layout.setContentsMargins(16, 14, 16, 14)
        metrics_layout.setSpacing(12)
        metrics_heading = QLabel("Chỉ số trên tập kiểm tra")
        metrics_heading.setObjectName("sectionTitle")
        metrics_layout.addWidget(metrics_heading)
        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        self.metricValues = {}
        for index, (key, label) in enumerate(
            (
                ("accuracy", "ACCURACY"),
                ("precision", "PRECISION"),
                ("recall", "RECALL"),
                ("f1", "F1-SCORE"),
            )
        ):
            tile = self._card()
            tile.setObjectName("metricCard")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(14, 10, 14, 10)
            tile_layout.setSpacing(2)
            metric_title = QLabel(label)
            metric_title.setObjectName("metricTitle")
            metric_value = QLabel("—")
            metric_value.setObjectName("metricValue")
            tile_layout.addWidget(metric_title)
            tile_layout.addWidget(metric_value)
            metric_grid.addWidget(tile, 0, index)
            self.metricValues[key] = metric_value
        metrics_layout.addLayout(metric_grid)
        self.evaluationSummary = QLabel("Chưa có kết quả đánh giá.")
        self.evaluationSummary.setObjectName("statusLabel")
        self.evaluationSummary.setWordWrap(True)
        metrics_layout.addWidget(self.evaluationSummary)

        coefficient_card = self._card("HỆ SỐ MÔ HÌNH")
        coefficient_layout = QVBoxLayout(coefficient_card)
        coefficient_layout.setContentsMargins(12, 12, 12, 12)
        coefficient_layout.setSpacing(8)
        coefficient_heading = QLabel("Đặc trưng có ảnh hưởng lớn")
        coefficient_heading.setObjectName("sectionTitle")
        coefficient_layout.addWidget(coefficient_heading)
        self.coefficientTable = QTableWidget()
        self.coefficientTable.setColumnCount(2)
        self.coefficientTable.setHorizontalHeaderLabels(("Đặc trưng", "Hệ số"))
        self.coefficientTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.coefficientTable.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.coefficientTable.verticalHeader().setVisible(False)
        self.coefficientTable.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.coefficientTable.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.coefficientTable.setMinimumHeight(230)
        coefficient_layout.addWidget(self.coefficientTable)

        results_layout = QHBoxLayout()
        results_layout.setSpacing(14)
        results_layout.addWidget(data_card, 3)
        results_side = QVBoxLayout()
        results_side.setSpacing(14)
        results_side.addWidget(coefficient_card, 2)
        results_side.addWidget(metrics_card, 1)
        results_layout.addLayout(results_side, 2)
        layout.addLayout(results_layout)

        prediction_card = self._card("DỰ ĐOÁN CHO MỘT PHIÊN")
        prediction_layout = QVBoxLayout(prediction_card)
        prediction_layout.setContentsMargins(16, 14, 16, 14)
        prediction_layout.setSpacing(12)
        prediction_heading = QLabel("Nhập các tín hiệu quan sát được của phiên")
        prediction_heading.setObjectName("sectionTitle")
        prediction_layout.addWidget(prediction_heading)

        self.viewCount = self._integer_input(0, 1000000, 1)
        self.cartCount = self._integer_input(0, 1000000, 0)
        self.otherCount = self._integer_input(0, 1000000, 0)
        self.productCount = self._integer_input(0, 1000000, 1)
        self.categoryCount = self._integer_input(0, 1000000, 1)
        self.brandCount = self._integer_input(0, 1000000, 1)
        self.avgPrice = self._number_input(0, 1000000000, 0.0)
        self.maxPrice = self._number_input(0, 1000000000, 0.0)
        self.duration = self._number_input(0, 1000000, 0.0)
        self.hour = self._integer_input(0, 23, 12)
        self.weekday = QComboBox(self)
        for day in ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"):
            self.weekday.addItem(day)
        self.category = self._category_input()
        self.brand = self._category_input()
        self._set_category_options(
            self.category,
            self._most_common_value("category_code"),
        )
        self._set_category_options(self.brand, self._most_common_value("brand"))

        fields = (
            ("Số lượt xem", self.viewCount),
            ("Số lượt thêm giỏ hàng", self.cartCount),
            ("Sự kiện khác", self.otherCount),
            ("Số sản phẩm khác nhau", self.productCount),
            ("Số danh mục khác nhau", self.categoryCount),
            ("Số thương hiệu khác nhau", self.brandCount),
            ("Giá trung bình", self.avgPrice),
            ("Giá cao nhất", self.maxPrice),
            ("Thời lượng phiên (phút)", self.duration),
            ("Giờ bắt đầu (0–23)", self.hour),
            ("Ngày trong tuần", self.weekday),
            ("Danh mục phổ biến nhất", self.category),
            ("Thương hiệu phổ biến nhất", self.brand),
        )
        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(14)
        field_grid.setVerticalSpacing(10)
        for index, (label, widget) in enumerate(fields):
            column = index % 2
            row = (index // 2) * 2
            field_label = QLabel(label)
            field_label.setProperty("role", "filterLabel")
            field_grid.addWidget(field_label, row, column)
            field_grid.addWidget(widget, row + 1, column)
        field_grid.setColumnStretch(0, 1)
        field_grid.setColumnStretch(1, 1)
        prediction_layout.addLayout(field_grid)

        prediction_actions = QHBoxLayout()
        self.predictButton = QPushButton("Dự đoán phiên này")
        self.predictButton.setObjectName("btnAdd")
        self.predictButton.setEnabled(False)
        prediction_actions.addStretch(1)
        prediction_actions.addWidget(self.predictButton)
        prediction_layout.addLayout(prediction_actions)
        self.predictionResult = QLabel("Hãy huấn luyện mô hình trước khi dự đoán.")
        self.predictionResult.setObjectName("predictionResult")
        self.predictionResult.setWordWrap(True)
        prediction_layout.addWidget(self.predictionResult)
        self.probabilityBar = QProgressBar()
        self.probabilityBar.setRange(0, 1000)
        self.probabilityBar.setValue(0)
        self.probabilityBar.setFormat("Xác suất mua hàng: %p%")
        prediction_layout.addWidget(self.probabilityBar)
        layout.addWidget(prediction_card)
        layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll)
        self.trainButton.clicked.connect(self.trainModel)
        self.evaluateButton.clicked.connect(self.evaluateModel)
        self.saveButton.clicked.connect(self.saveModel)
        self.loadButton.clicked.connect(self.loadModel)
        self.predictButton.clicked.connect(self.predict)

    def _cleaning_summary(self):
        report = self.cleaningReport
        removed_reasons = (
            report["removed_missing_session"]
            + report["removed_missing_event_type"]
            + report["removed_invalid_time"]
            + report["removed_duplicate_id"]
        )
        return (
            f"Làm sạch: đã loại {report['removed_count']:,} dòng "
            f"(thiếu phiên: {report['removed_missing_session']:,}, "
            f"thiếu loại sự kiện: {report['removed_missing_event_type']:,}, "
            f"thời gian lỗi: {report['removed_invalid_time']:,} dòng; "
            f"loại toàn bộ {report['removed_invalid_time_sessions']:,} phiên "
            f"({report['removed_invalid_time_session_rows']:,} dòng), "
            f"ID trùng: {report['removed_duplicate_id']:,}); "
            f"đã chuẩn hóa/sửa {report['repaired_count']:,} trường"
            + (
                f" trong {removed_reasons:,} dòng bị loại."
                if removed_reasons
                else "."
            )
        )

    def _most_common_value(self, field):
        counts = self._value_counts.get(field, Counter())
        return tuple(
            value
            for value, _ in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )[:100]
        )

    def _populate_data_table(self):
        fields = (
            "event_time",
            "event_type",
            "product_id",
            "category_code",
            "brand",
            "price",
            "user_id",
            "user_session",
        )
        for row, record in enumerate(self.records[: self.dataTable.rowCount()]):
            for column, field in enumerate(fields):
                if isinstance(record, dict):
                    value = record.get(field)
                else:
                    value = getattr(record, field, None)
                text = "" if value is None else str(value)
                self.dataTable.setItem(row, column, QTableWidgetItem(text))

    @staticmethod
    def _card(title=None):
        frame = QFrame()
        frame.setObjectName("classificationCard")
        if title:
            frame.setAccessibleName(title)
        return frame

    @staticmethod
    def _integer_input(minimum, maximum, value):
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        return widget

    @staticmethod
    def _number_input(minimum, maximum, value):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(2)
        widget.setValue(value)
        return widget

    def _category_input(self):
        combo = QComboBox(self)
        combo.addItem("Không xác định", "")
        combo.setEditable(True)
        return combo

    def _prediction_features(self):
        category = self.category.currentData()
        brand = self.brand.currentData()
        if category is None:
            category = self.category.currentText().strip()
        if brand is None:
            brand = self.brand.currentText().strip()
        view_count = self.viewCount.value()
        cart_count = self.cartCount.value()
        other_count = self.otherCount.value()
        return {
            "view_count": view_count,
            "cart_count": cart_count,
            "other_count": other_count,
            "event_count": view_count + cart_count + other_count,
            "unique_products": self.productCount.value(),
            "unique_categories": self.categoryCount.value(),
            "unique_brands": self.brandCount.value(),
            "avg_price": self.avgPrice.value(),
            "max_price": self.maxPrice.value(),
            "duration_minutes": self.duration.value(),
            "hour": self.hour.value(),
            "weekday": self.weekday.currentIndex(),
            "category": category,
            "brand": brand,
        }

    def trainModel(self):
        if self._training_thread is not None:
            return
        self.trainButton.setEnabled(False)
        self.predictButton.setEnabled(False)
        self.evaluateButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self._last_metrics = None
        self._current_training_rate = self.trainingRate.value()
        self.classifier = PurchaseClassifier()
        self.status.setText("Đang gom sự kiện theo phiên và huấn luyện mô hình...")
        self.evaluationSummary.setText("Đang tính các chỉ số trên tập kiểm tra.")
        self.predictionResult.setText("Đang huấn luyện mô hình...")
        self.coefficientTable.setRowCount(0)

        thread = QThread(self)
        worker = _TrainingWorker(
            self.classifier,
            self.records,
            self._current_training_rate / 100,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._training_succeeded)
        worker.failed.connect(self._training_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._training_finished)
        self._training_thread = thread
        self._training_worker = worker
        thread.start()

    def _training_succeeded(self, metrics):
        sampling_note = (
            f" (đã lấy mẫu từ {metrics['available_session_count']:,} phiên hợp lệ)"
            if metrics["available_session_count"] > metrics["session_count"]
            else ""
        )
        self.status.setText(
            f"Đã huấn luyện {metrics['session_count']:,} phiên "
            f"(huấn luyện: {metrics['train_count']:,}, "
            f"kiểm tra: {metrics['test_count']:,}); "
            f"tỷ lệ phiên mua: {metrics['purchase_rate']:.1%}"
            f"{sampling_note}."
        )
        self._last_metrics = metrics
        self._last_training_rate = self._current_training_rate
        self.evaluateButton.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.evaluationSummary.setText(
            "Mô hình đã huấn luyện. Nhấn «Đánh giá mô hình» để xem kết quả trên tập kiểm tra."
        )
        self._fill_coefficient_table()
        self._set_category_options(self.category, self.classifier.categories)
        self._set_category_options(self.brand, self.classifier.brands)
        self.predictionResult.setText("Mô hình đã sẵn sàng để dự đoán.")
        self.probabilityBar.setValue(0)
        self.predictButton.setEnabled(True)

    def evaluateModel(self):
        metrics = getattr(self, "_last_metrics", None)
        if metrics is None:
            return
        for key, label in self.metricValues.items():
            label.setText(f"{metrics[key]:.1%}")
        self.evaluationSummary.setText(
            f"Chia {self._last_training_rate}% huấn luyện / "
            f"{100 - self._last_training_rate}% kiểm tra. Ma trận nhầm lẫn "
            "(mua đúng / không mua đúng / báo mua nhầm / bỏ sót mua): "
            f"{metrics['true_positive']} / {metrics['true_negative']} / "
            f"{metrics['false_positive']} / {metrics['false_negative']}."
        )

    def _fill_coefficient_table(self):
        coefficients = self.classifier.coefficients()
        self.coefficientTable.setRowCount(min(20, len(coefficients)))
        for row, (feature, coefficient) in enumerate(coefficients[:20]):
            self.coefficientTable.setItem(row, 0, QTableWidgetItem(feature))
            self.coefficientTable.setItem(
                row, 1, QTableWidgetItem(f"{coefficient:.5f}")
            )

    def _training_failed(self, message):
        self.status.setText(f"Không thể huấn luyện: {message}")
        self.evaluationSummary.setText("Không có kết quả đánh giá.")
        self.predictionResult.setText("Cần dữ liệu hợp lệ để huấn luyện mô hình.")
        self.probabilityBar.setValue(0)
        self._last_metrics = None
        self._last_training_rate = None
        self._current_training_rate = None
        self.coefficientTable.setRowCount(0)

    def _training_finished(self):
        self._training_thread = None
        self._training_worker = None
        self.trainButton.setEnabled(True)

    @staticmethod
    def _set_category_options(combo, values):
        current_text = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Không xác định", "")
        for value in values:
            combo.addItem(value, value)
        if current_text in ("", "Không xác định"):
            combo.setCurrentIndex(0)
        elif current_text:
            index = combo.findData(current_text)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                combo.setCurrentText(current_text)
        combo.blockSignals(False)

    def predict(self):
        try:
            probability = self.classifier.predict_proba(self._prediction_features())
        except (ClassificationError, ValueError, TypeError, OverflowError) as error:
            self.status.setText(f"Không thể dự đoán: {error}")
            return
        prediction = (
            "Có khả năng mua hàng"
            if probability >= 0.5
            else "Chưa có khả năng mua hàng"
        )
        self.predictionResult.setText(
            f"{prediction} — xác suất mua hàng ước tính: {probability:.1%}."
        )
        self.probabilityBar.setValue(round(probability * 1000))

    def saveModel(self):
        try:
            payload = self.classifier.export_model()
        except ClassificationError as error:
            self.status.setText(f"Không thể lưu mô hình: {error}")
            return
        file_path = self.MODEL_PATH
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except OSError as error:
            QMessageBox.warning(self, "Lưu mô hình", f"Không thể ghi tệp: {error}")
            return
        self.status.setText(f"Đã xuất mô hình: {file_path}")

    def loadModel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Tải mô hình phân loại",
            str(self.MODEL_PATH.parent),
            "JSON (*.json)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            classifier = PurchaseClassifier()
            classifier.load_model(payload)
        except (OSError, json.JSONDecodeError, ClassificationError) as error:
            QMessageBox.warning(self, "Tải mô hình", f"Không thể tải mô hình: {error}")
            return
        self.classifier = classifier
        self._set_category_options(self.category, classifier.categories)
        self._set_category_options(self.brand, classifier.brands)
        self._fill_coefficient_table()
        self._last_metrics = None
        self._last_training_rate = None
        self._current_training_rate = None
        self.evaluateButton.setEnabled(False)
        self.saveButton.setEnabled(True)
        self.predictButton.setEnabled(True)
        for label in self.metricValues.values():
            label.setText("—")
        self.evaluationSummary.setText(
            "Mô hình đã tải; chỉ số đánh giá không được lưu trong tệp mô hình."
        )
        self.status.setText(f"Đã tải mô hình: {file_path}")
        self.predictionResult.setText("Mô hình đã sẵn sàng để dự đoán.")
