from pathlib import Path
import pickle
import zipfile

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.exceptions import NotFittedError
from sklearn.utils.validation import check_is_fitted

from regession.trainning_model import (
    DISPLAY_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    MODEL_NAMES,
    RevenueRegressor,
    build_session_features,
    chronological_split,
    load_events,
    load_model,
    preprocess_events,
    save_model,
    train_models,
)
from ui.regression_page import Ui_RegressionPage


class FeatureBuildThread(QThread):
    features_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, events, window_size, only_cart, parent=None):
        super().__init__(parent)
        self.events = events
        self.window_size = window_size
        self.only_cart = only_cart

    def run(self):
        try:
            features = build_session_features(
                self.events,
                window_size=self.window_size,
                only_cart=self.only_cart,
                assume_sorted=True,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.features_ready.emit(features)


class RegressionScreenEx(Ui_RegressionPage):
    """Controller for the generated session-revenue regression interface."""

    PREVIEW_LIMIT = 500
    FEATURE_PREVIEW_LIMIT = 500
    LOADED_MODEL_LABEL = "Mô hình đã nạp"

    def setupUi(self, RegressionPage):
        self.MainWindow = RegressionPage
        if isinstance(RegressionPage, QMainWindow):
            self.page = QWidget(RegressionPage)
            super().setupUi(self.page)
            RegressionPage.setCentralWidget(self.page)
            RegressionPage.setWindowTitle(self.page.windowTitle())
        else:
            self.page = RegressionPage
            super().setupUi(self.page)
        for checkbox in (
            self.chkDropDuplicates,
            self.chkDropInvalidPrice,
            self.chkFillBrand,
            self.chkSplitCategory,
            self.chkDropColumns,
        ):
            checkbox.setChecked(True)
            checkbox.setEnabled(False)
        for label_name in (
            "lblPredView",
            "lblPredCart",
            "lblPredProducts",
            "lblPredCategories",
            "lblPredBrands",
            "lblPredCategory",
            "lblPredAvgPrice",
            "lblPredMaxPrice",
            "lblPredHour",
            "lblPredWeekday",
            "lblPredModel",
        ):
            label = getattr(self, label_name)
            label.setWordWrap(True)
            label.setMaximumWidth(145)
        self.framePredictResult.setMaximumWidth(300)
        self.cboChartType.setMaximumWidth(260)
        self.cboChartModel.setMaximumWidth(150)
        self.events = None
        self.processed_events = None
        self.session_features = None
        self.train_data = None
        self.test_data = None
        self.cutoff_date = None
        self.results = {}
        self.best_model_name = None
        self.loaded_model = None
        self.loaded_model_path = None
        self._chart_canvas = None
        self._feature_worker = None
        self._connect_signals()
        self.spinWindowN.valueChanged.connect(self.updatePredictionLimits)
        self.spinWindowN.valueChanged.connect(self._featureSettingsChanged)
        self.chkOnlyCart.toggled.connect(self._featureSettingsChanged)
        self.spinTrainPct.valueChanged.connect(self._splitSettingsChanged)
        for checkbox in (
            self.chkDropDuplicates,
            self.chkDropInvalidPrice,
            self.chkFillBrand,
            self.chkSplitCategory,
            self.chkDropColumns,
        ):
            checkbox.toggled.connect(self._preprocessingSettingsChanged)
        self.updatePredictionLimits(self.spinWindowN.value())
        self.uiState(False)
        self._log("Sẵn sàng. Tải dữ liệu events để bắt đầu.")

    def _connect_signals(self):
        self.btnLoadData.clicked.connect(self.loadData)
        self.btnPreprocess.clicked.connect(self.preprocessData)
        self.btnBuildFeatures.clicked.connect(self.buildFeatures)
        self.btnSplit.clicked.connect(self.splitData)
        self.btnTrain.clicked.connect(self.trainModels)
        self.btnSaveModel.clicked.connect(self.saveBestModel)
        self.btnLoadModel.clicked.connect(self.loadTrainedModel)
        self.btnPredict.clicked.connect(self.predictRevenue)
        self.btnDrawChart.clicked.connect(self.drawChart)

    def updatePredictionLimits(self, window_size):
        for control in (
            self.spinPredView,
            self.spinPredCart,
            self.spinPredProducts,
            self.spinPredCategories,
            self.spinPredBrands,
        ):
            control.setMaximum(window_size)

    def _featureSettingsChanged(self, *_):
        if self.session_features is None:
            return
        self.session_features = None
        self.lblSessionCount.setText("Số phiên sau khi lọc: --")
        self.tblFeatures.setRowCount(0)
        self.btnSplit.setEnabled(False)
        self._invalidate_training()
        self._log("Thay đổi cửa sổ/điều kiện lọc; hãy tạo lại bảng đặc trưng.")

    def _preprocessingSettingsChanged(self, *_):
        if self.processed_events is None:
            return
        self.processed_events = None
        self.session_features = None
        self.lblPreprocessStatus.setText("Trạng thái: thay đổi tùy chọn, cần xử lý lại")
        self.lblSessionCount.setText("Số phiên sau khi lọc: --")
        self.tblFeatures.setRowCount(0)
        self.btnBuildFeatures.setEnabled(False)
        self.btnSplit.setEnabled(False)
        self._invalidate_training()
        self._log("Đã đổi tùy chọn tiền xử lý; hãy chạy lại tiền xử lý.")

    def _splitSettingsChanged(self, *_):
        if self.train_data is None and self.test_data is None:
            return
        self._invalidate_training()
        self.btnSplit.setEnabled(self.session_features is not None)
        self._log("Đã thay đổi tỷ lệ train; hãy chia dữ liệu lại.")

    def uiState(self, has_data):
        self.btnPreprocess.setEnabled(has_data)
        self.btnBuildFeatures.setEnabled(False)
        self.btnSplit.setEnabled(False)
        self.btnTrain.setEnabled(False)
        self.btnSaveModel.setEnabled(self.loaded_model is not None)
        self.btnLoadModel.setEnabled(True)
        self.btnPredict.setEnabled(self.loaded_model is not None)
        self.btnDrawChart.setEnabled(False)

    def showWindow(self):
        self.MainWindow.show()
        self.MainWindow.raise_()
        self.MainWindow.activateWindow()

    def _log(self, message):
        self.txtLog.appendPlainText(message)

    def _error(self, title, error):
        message = str(error)
        self._log(f"LỖI - {title}: {message}")
        QMessageBox.critical(self.MainWindow, title, message)

    def _default_data_path(self):
        return Path(__file__).resolve().parents[1] / "databases" / "cleaned_data.csv"

    def loadData(self):
        path = self._default_data_path()
        if not path.is_file():
            selected_path, _ = QFileDialog.getOpenFileName(
                self.MainWindow,
                "Chọn tệp dữ liệu sự kiện",
                str(path.parent),
                "CSV (*.csv)",
            )
            if not selected_path:
                self._log("Đã hủy chọn tệp dữ liệu.")
                return
            path = Path(selected_path)
        try:
            data = load_events(path)
        except (OSError, ValueError, pd.errors.ParserError) as error:
            self._error("Không thể tải dữ liệu", error)
            return

        self.events = data
        self.processed_events = None
        self.session_features = None
        self.train_data = None
        self.test_data = None
        self.results = {}
        self.best_model_name = None
        self.lblRowCount.setText(f"{len(data):,} dòng")
        self.lblPreprocessStatus.setText("Trạng thái: đã tải dữ liệu")
        self.lblSessionCount.setText("Số phiên sau khi lọc: --")
        self.lblSplitInfo.setText("Train: -- phiên | Test: -- phiên")
        self.lblBestModel.setText("Mô hình tốt nhất: --")
        self._clear_model_display()
        self.tblPreview.setRowCount(0)
        self.uiState(True)
        self._log(f"Đã tải {len(data):,} sự kiện từ {path}.")
        self.preprocessData()

    def preprocessData(self):
        if self.events is None:
            self._error("Chưa có dữ liệu", "Hãy tải dữ liệu sự kiện trước.")
            return
        try:
            processed = preprocess_events(
                self.events,
                drop_duplicates=self.chkDropDuplicates.isChecked(),
                drop_invalid_price=self.chkDropInvalidPrice.isChecked(),
                fill_brand=self.chkFillBrand.isChecked(),
                split_category=self.chkSplitCategory.isChecked(),
                drop_id_columns=self.chkDropColumns.isChecked(),
            )
        except (ValueError, TypeError) as error:
            self._error("Tiền xử lý thất bại", error)
            return

        self.processed_events = processed
        self.session_features = None
        self.train_data = None
        self.test_data = None
        self.results = {}
        self.best_model_name = None
        self.lblPreprocessStatus.setText(
            f"Trạng thái: hoàn tất ({len(processed):,}/{len(self.events):,} dòng)"
        )
        self.lblRowCount.setText(f"{len(processed):,} dòng sau xử lý")
        self.btnBuildFeatures.setEnabled(True)
        self._fill_table(
            self.tblPreview,
            processed.loc[:, self._eventDisplayColumns(processed)],
            self.PREVIEW_LIMIT,
        )
        self.tabResult.setCurrentWidget(self.tabData)
        self._invalidate_training()
        self.btnSplit.setEnabled(False)
        self._log(
            f"Tiền xử lý hoàn tất: còn {len(processed):,} sự kiện; "
            f"đã loại {len(self.events) - len(processed):,} dòng."
        )

    @staticmethod
    def _eventDisplayColumns(data):
        preferred = (
            "event_time",
            "event_type",
            "product_id",
            "category_level1",
            "category_level2",
            "brand",
            "price",
            "user_id",
            "user_session",
        )
        return [column for column in preferred if column in data.columns]

    def buildFeatures(self):
        if self.processed_events is None:
            self._error("Chưa tiền xử lý", "Hãy thực hiện bước tiền xử lý trước.")
            return
        if self._feature_worker is not None:
            return

        self.btnBuildFeatures.setEnabled(False)
        self.btnBuildFeatures.setText("Đang tạo bảng đặc trưng...")
        self.btnLoadData.setEnabled(False)
        self.btnPreprocess.setEnabled(False)
        self.btnSplit.setEnabled(False)
        self.spinWindowN.setEnabled(False)
        self.chkOnlyCart.setEnabled(False)
        self.progressTrain.setRange(0, 0)
        self._log("Đang tạo đặc trưng theo phiên ở tiến trình nền...")

        worker = FeatureBuildThread(
            self.processed_events,
            self.spinWindowN.value(),
            self.chkOnlyCart.isChecked(),
            self.MainWindow,
        )
        self._feature_worker = worker
        worker.features_ready.connect(self._featuresBuilt)
        worker.failed.connect(self._featureBuildFailed)
        worker.finished.connect(self._featureBuildFinished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _featuresBuilt(self, features):

        self.session_features = features
        self.train_data = None
        self.test_data = None
        self.results = {}
        self.best_model_name = None
        self.lblSessionCount.setText(f"Số phiên sau khi lọc: {len(features):,}")
        display_features = features.loc[:, list(DISPLAY_FEATURE_COLUMNS)].rename(
            columns={"revenue": "revenue (y)"}
        )
        self._fill_table(
            self.tblFeatures,
            display_features,
            self.FEATURE_PREVIEW_LIMIT,
        )
        self._invalidate_training()
        self.btnSplit.setEnabled(True)
        self._log(
            f"Đã tạo {len(features):,} phiên; đặc trưng dùng {self.spinWindowN.value()} "
            "sự kiện đầu, mục tiêu là tổng giá purchase cả phiên."
        )

    def _featureBuildFailed(self, message):
        self._error("Không thể tạo đặc trưng", message)

    def _featureBuildFinished(self):
        self._feature_worker = None
        self.progressTrain.setRange(0, 100)
        self.btnLoadData.setEnabled(True)
        self.btnPreprocess.setEnabled(self.events is not None)
        self.btnBuildFeatures.setText("Tạo bảng đặc trưng theo phiên")
        self.btnBuildFeatures.setEnabled(self.processed_events is not None)
        self.btnSplit.setEnabled(self.session_features is not None)
        self.spinWindowN.setEnabled(True)
        self.chkOnlyCart.setEnabled(True)

    def splitData(self):
        if self.session_features is None:
            self._error("Chưa có đặc trưng", "Hãy tạo bảng đặc trưng theo phiên trước.")
            return
        try:
            train, test, cutoff = chronological_split(
                self.session_features, self.spinTrainPct.value()
            )
        except ValueError as error:
            self._error("Không thể chia dữ liệu", error)
            return

        self.train_data = train
        self.test_data = test
        self.cutoff_date = cutoff
        self.results = {}
        self.best_model_name = None
        self._clear_model_display()
        self.lblSplitInfo.setText(
            f"Train: {len(train):,} phiên | Test: {len(test):,} phiên"
        )
        self.btnTrain.setEnabled(True)
        self.btnSaveModel.setEnabled(False)
        self.btnLoadModel.setEnabled(True)
        self.btnPredict.setEnabled(False)
        self.btnDrawChart.setEnabled(False)
        self.lblBestModel.setText("Mô hình tốt nhất: --")
        self._log(
            f"Chia theo ngày hoàn tất: train trước {cutoff:%Y-%m-%d} "
            f"({len(train):,}), tests từ ngày đó trở đi ({len(test):,})."
        )

    def _selected_models(self):
        options = (
            ("Linear", self.chkLinear),
            ("Random Forest", self.chkRandomForest),
            ("Gradient Boosting", self.chkGradientBoosting),
        )
        return [name for name, checkbox in options if checkbox.isChecked()]

    def trainModels(self):
        if self.train_data is None or self.test_data is None:
            self._error("Chưa chia dữ liệu", "Hãy thực hiện bước chia dữ liệu trước.")
            return
        selected = self._selected_models()
        if not selected:
            self._error("Chưa chọn mô hình", "Hãy chọn ít nhất một mô hình hồi quy.")
            return

        self.btnTrain.setEnabled(False)
        self.progressTrain.setValue(5)
        self._log(f"Bắt đầu huấn luyện: {', '.join(selected)}.")
        try:
            results = train_models(
                self.train_data,
                self.test_data,
                selected_models=selected,
                n_estimators=self.spinNEstimators.value(),
                max_depth=self.spinMaxDepth.value(),
                learning_rate=self.dsbLearningRate.value(),
                encode=self.chkEncode.isChecked(),
                scale=self.chkScale.isChecked(),
                clip_p99=self.chkClipP99.isChecked(),
                log_target=self.chkLog1p.isChecked(),
            )
        except (ValueError, TypeError, RuntimeError) as error:
            self.progressTrain.setValue(0)
            self.btnTrain.setEnabled(True)
            self._error("Huấn luyện thất bại", error)
            return

        self.results = results
        self.best_model_name = min(
            results, key=lambda name: results[name]["metrics"]["rmse"]
        )
        self.progressTrain.setValue(100)
        self._fill_metrics()
        self._updateEvaluationSummary()
        self.cboChartModel.clear()
        self.cboPredModel.clear()
        for name in MODEL_NAMES:
            if name in results:
                self.cboChartModel.addItem(name)
                self.cboPredModel.addItem(name)
        if self.loaded_model is not None:
            self.cboPredModel.addItem(self.LOADED_MODEL_LABEL)
        self.cboPredModel.setCurrentText(self.best_model_name)
        self.btnSaveModel.setEnabled(True)
        self.btnPredict.setEnabled(True)
        self.btnDrawChart.setEnabled(True)
        self.btnTrain.setEnabled(True)
        self._log(
            "Huấn luyện hoàn tất. Chỉ số trên tập tests theo thời gian; "
            "mô hình tốt nhất được chọn theo RMSE để phục vụ dự báo tổng doanh thu."
        )
        for name, result in results.items():
            metrics = result["metrics"]
            self._log(
                f"{name}: MAE={metrics['mae']:,.3f}, RMSE={metrics['rmse']:,.3f}, "
                f"R²(log)={metrics['r2_log']:.4f}, R²={metrics['r2']:.4f}"
            )

    def _fill_metrics(self):
        row_names = {
            "Linear": 0,
            "Random Forest": 1,
            "Gradient Boosting": 2,
        }
        self.tblMetrics.setRowCount(4)
        self.tblMetrics.clearContents()
        for name, result in self.results.items():
            row = row_names[name]
            metrics = result["metrics"]
            values = (
                metrics["mae"],
                metrics["rmse"],
                metrics["r2_log"],
                metrics["r2"],
            )
            for column, value in enumerate(values):
                text = (
                    "--"
                    if value is None
                    else f"{value:,.4f}"
                    if column >= 2
                    else f"{value:,.2f}"
                )
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tblMetrics.setItem(row, column, item)

        actual = self.test_data["revenue"].to_numpy(dtype=float)
        zero_predictions = np.zeros_like(actual)
        baseline_values = (
            mean_absolute_error(actual, zero_predictions),
            np.sqrt(mean_squared_error(actual, zero_predictions)),
            r2_score(np.log1p(actual), zero_predictions),
            r2_score(actual, zero_predictions),
        )
        for column, value in enumerate(baseline_values):
            text = (
                "--"
                if value is None
                else f"{value:,.4f}"
                if column >= 2
                else f"{value:,.2f}"
            )
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tblMetrics.setItem(3, column, item)

    def _updateEvaluationSummary(self):
        actual = self.test_data["revenue"].to_numpy(dtype=float)
        zero_predictions = np.zeros_like(actual)
        baseline_mae = mean_absolute_error(actual, zero_predictions)
        baseline_rmse = np.sqrt(mean_squared_error(actual, zero_predictions))
        purchase_rate = 100 * np.mean(actual > 0)
        average_revenue = np.mean(actual)
        best_metrics = self.results[self.best_model_name]["metrics"]
        rmse_change = 100 * (baseline_rmse - best_metrics["rmse"]) / baseline_rmse
        comparison = (
            f"RMSE cải thiện {rmse_change:.1f}% so với baseline."
            if rmse_change > 0
            else f"RMSE kém baseline {abs(rmse_change):.1f}%."
        )
        mae_note = (
            f"MAE {best_metrics['mae']:,.2f} USD, baseline "
            f"{baseline_mae:,.2f} USD."
        )
        if best_metrics["mae"] > baseline_mae:
            mae_note += " Baseline tốt hơn cho sai số phiên điển hình."
        self.lblEvalSummary.setText(
            f"Tập tests: {purchase_rate:.2f}% phiên có mua; doanh thu trung bình "
            f"{average_revenue:,.2f} USD/phiên. Baseline 0 USD — "
            f"MAE {baseline_mae:,.2f}, RMSE {baseline_rmse:,.2f}. "
            f"{mae_note}"
        )
        self.lblBestModel.setText(
            f"Mô hình tốt nhất theo RMSE: {self.best_model_name} — "
            f"{best_metrics['rmse']:,.2f} USD ({comparison})"
        )

    def saveBestModel(self):
        name = self.cboPredModel.currentText()
        if name == self.LOADED_MODEL_LABEL and self.loaded_model is not None:
            model = self.loaded_model
        elif name in self.results:
            model = self.results[name]["model"]
        else:
            self._error("Chưa có mô hình", "Hãy huấn luyện hoặc nạp mô hình trước.")
            return

        path = (
            Path(__file__).resolve().parents[1]
            / "regession"
            / "trained"
            / "session_revenue.joblib"
        )
        try:
            saved_path = save_model(model, path)
        except (OSError, ValueError, TypeError, ImportError) as error:
            self._error("Không thể xuất mô hình", error)
            return
        self._log(f"Đã xuất mô hình {name} tại {saved_path}.")

    def loadTrainedModel(self):
        selected_path, _ = QFileDialog.getOpenFileName(
            self.MainWindow,
            "Nạp mô hình hồi quy (chỉ chọn tệp do ứng dụng xuất)",
            str(Path(__file__).resolve().parents[1] / "models"),
            "Mô hình Joblib (*.joblib)",
        )
        if not selected_path:
            self._log("Đã hủy nạp mô hình.")
            return

        path = Path(selected_path)
        try:
            model = load_model(path)
        except (
            OSError,
            ValueError,
            EOFError,
            ImportError,
            AttributeError,
            TypeError,
            pickle.UnpicklingError,
            zipfile.BadZipFile,
        ) as error:
            self._error("Không thể nạp mô hình", error)
            return
        allowed_estimators = (
            LinearRegression,
            RandomForestRegressor,
            GradientBoostingRegressor,
        )
        estimator = getattr(
            getattr(model, "pipeline", None),
            "named_steps",
            {},
        ).get("regressor")
        if (
            not isinstance(model, RevenueRegressor)
            or type(estimator) not in allowed_estimators
        ):
            self._error(
                "Mô hình không tương thích",
                "Chỉ hỗ trợ mô hình Linear, Random Forest hoặc Gradient Boosting.",
            )
            return
        try:
            check_is_fitted(model.pipeline)
        except NotFittedError:
            self._error("Mô hình chưa huấn luyện", "Tệp mô hình chưa được fit.")
            return
        except (AttributeError, TypeError) as error:
            self._error("Mô hình không tương thích", error)
            return

        self.loaded_model = model
        self.loaded_model_path = path
        self._refresh_prediction_models()
        self.cboPredModel.setCurrentText(self.LOADED_MODEL_LABEL)
        self.btnPredict.setEnabled(True)
        self.btnSaveModel.setEnabled(True)
        self.lblBestModel.setText(f"Mô hình đã nạp: {path.name}")
        self._log(
            f"Đã nạp mô hình từ {path}. Có thể dự đoán ngay; "
            "tệp mô hình không chứa kết quả đánh giá/biểu đồ tập tests."
        )

    def _refresh_prediction_models(self):
        selected = self.cboPredModel.currentText()
        self.cboPredModel.clear()
        for name in MODEL_NAMES:
            if name in self.results:
                self.cboPredModel.addItem(name)
        if self.loaded_model is not None:
            self.cboPredModel.addItem(self.LOADED_MODEL_LABEL)
        if self.cboPredModel.findText(selected) >= 0:
            self.cboPredModel.setCurrentText(selected)
        elif self.best_model_name and self.cboPredModel.findText(self.best_model_name) >= 0:
            self.cboPredModel.setCurrentText(self.best_model_name)

    def predictRevenue(self):
        name = self.cboPredModel.currentText()
        if name == self.LOADED_MODEL_LABEL and self.loaded_model is not None:
            model = self.loaded_model
        elif name in self.results:
            model = self.results[name]["model"]
        else:
            self._error("Mô hình không hợp lệ", "Mô hình đã chọn chưa được huấn luyện.")
            return
        features = pd.DataFrame(
            [
                {
                    "n_view": self.spinPredView.value(),
                    "n_cart": self.spinPredCart.value(),
                    "n_products": self.spinPredProducts.value(),
                    "n_categories": self.spinPredCategories.value(),
                    "n_brands": self.spinPredBrands.value(),
                    "avg_price": self.dsbPredAvgPrice.value(),
                    "max_price": self.dsbPredMaxPrice.value(),
                    "top_category": self.cboPredCategory.currentText(),
                    "hour": self.spinPredHour.value(),
                    "weekday": self.cboPredWeekday.currentIndex(),
                }
            ],
            columns=list(FEATURE_COLUMNS),
        )
        revenue = model.predict(features)[0]
        self.lblPredictResult.setText(f"{revenue:,.2f} USD")
        self._log(f"Dự đoán doanh thu phiên ({name}): {revenue:,.2f} USD.")

    def drawChart(self):
        if not self.results or self.test_data is None:
            self._error("Chưa có kết quả", "Hãy huấn luyện mô hình trước khi vẽ.")
            return
        name = self.cboChartModel.currentText()
        if name not in self.results:
            self._error("Mô hình không hợp lệ", "Mô hình đã chọn chưa được huấn luyện.")
            return
        if self._chart_canvas is None:
            self._chart_canvas = FigureCanvasQTAgg(Figure(figsize=(8, 5)))
            self.verticalLayoutFrameChart.removeWidget(self.lblChartPlaceholder)
            self.lblChartPlaceholder.hide()
            self.verticalLayoutFrameChart.addWidget(self._chart_canvas)

        figure = self._chart_canvas.figure
        figure.clear()
        axes = figure.add_subplot(111)
        axes.set_facecolor("#ffffff")
        chart_type = self.cboChartType.currentIndex()
        actual = self.test_data["revenue"].to_numpy(dtype=float)
        predicted = self.results[name]["predictions"]

        if chart_type == 0:
            axes.scatter(actual, predicted, alpha=0.55, color="#2563eb")
            bounds = [
                min(actual.min(), predicted.min()),
                max(actual.max(), predicted.max()),
            ]
            axes.plot(bounds, bounds, "--", color="#dc2626", label="Dự đoán hoàn hảo")
            axes.set_xlabel("Doanh thu thực tế")
            axes.set_ylabel("Doanh thu dự đoán")
            axes.legend()
        elif chart_type == 1:
            axes.scatter(predicted, actual - predicted, alpha=0.55, color="#7c3aed")
            axes.axhline(0, color="#dc2626", linestyle="--")
            axes.set_xlabel("Doanh thu dự đoán")
            axes.set_ylabel("Phần dư (thực tế - dự đoán)")
        elif chart_type == 2:
            importance = self.results[name]["model"].feature_importances().head(15)
            if importance.empty:
                axes.text(
                    0.5,
                    0.5,
                    "Mô hình không cung cấp độ quan trọng đặc trưng.",
                    ha="center",
                    va="center",
                    transform=axes.transAxes,
                )
                axes.set_axis_off()
            else:
                labels = importance.index.str.replace(
                    r"^(numeric|categorical)__", "", regex=True
                )
                axes.barh(labels[::-1], importance.to_numpy()[::-1], color="#1e40af")
                axes.set_xlabel("Độ quan trọng / |hệ số|")
        else:
            daily = self.test_data[["_session_start", "revenue"]].copy()
            daily["predicted"] = predicted
            daily["date"] = pd.to_datetime(daily["_session_start"]).dt.normalize()
            summary = daily.groupby("date")[["revenue", "predicted"]].sum()
            axes.plot(summary.index, summary["revenue"], marker="o", label="Thực tế")
            axes.plot(summary.index, summary["predicted"], marker="o", label="Dự báo")
            axes.set_xlabel("Ngày bắt đầu phiên")
            axes.set_ylabel("Doanh thu")
            axes.legend()

        axes.grid(axis="y", color="#e5e7eb", linewidth=0.7)
        axes.set_title(f"{self.cboChartType.currentText()} — {name}")
        figure.tight_layout()
        self._chart_canvas.draw_idle()
        self.tabResult.setCurrentWidget(self.tabChart)

    def _invalidate_training(self):
        self.train_data = None
        self.test_data = None
        self.results = {}
        self.best_model_name = None
        self._clear_model_display()
        self.lblSplitInfo.setText("Train: -- phiên | Test: -- phiên")
        self.lblBestModel.setText(
            f"Mô hình đã nạp: {self.loaded_model_path.name}"
            if self.loaded_model_path is not None
            else "Mô hình tốt nhất: --"
        )
        self.btnTrain.setEnabled(False)
        self.btnSaveModel.setEnabled(self.loaded_model is not None)
        self.btnPredict.setEnabled(self.loaded_model is not None)
        self.btnDrawChart.setEnabled(False)

    def _clear_model_display(self):
        self.progressTrain.setValue(0)
        self.tblMetrics.clearContents()
        self.cboChartModel.clear()
        self._refresh_prediction_models()
        self.lblEvalSummary.setText("Baseline: dự đoán 0 USD cho mọi phiên.")

    @staticmethod
    def _format_value(value):
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{value:,.2f}"
        if isinstance(value, (int, np.integer)):
            return f"{value:,}"
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _fill_table(self, table, data, limit):
        shown = data.head(limit)
        table.setSortingEnabled(False)
        table.setRowCount(len(shown))
        table.setColumnCount(len(shown.columns))
        table.setHorizontalHeaderLabels([str(column) for column in shown.columns])
        for row_index, row in enumerate(shown.itertuples(index=False, name=None)):
            for column_index, value in enumerate(row):
                table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(self._format_value(value)),
                )
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        if len(data) > limit:
            self._log(f"Bảng chỉ hiển thị {limit:,}/{len(data):,} dòng đầu.")
