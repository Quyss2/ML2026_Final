
import sys
import csv

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox
)

from ui.classificationUI import ClassificationPage


def load_data(file_path):
    """Đọc dữ liệu E-commerce từ file CSV."""
    records = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            records.append(row)

    return records


def main():
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    # Chọn file dữ liệu
    file_path, _ = QFileDialog.getOpenFileName(
        None,
        "Chọn dữ liệu E-commerce",
        "",
        "CSV Files (*.csv)"
    )

    if not file_path:
        return

    try:
        records = load_data(file_path)

        if not records:
            QMessageBox.warning(
                None,
                "Thông báo",
                "File dữ liệu không có bản ghi nào."
            )
            return

        # Khởi tạo giao diện phân loại
        window = ClassificationPage(records)
        window.setWindowTitle("E-commerce - Phân loại khả năng mua hàng")
        window.resize(1450, 900)
        window.show()

        sys.exit(app.exec())

    except Exception as error:
        QMessageBox.critical(
            None,
            "Lỗi khởi chạy",
            f"Không thể chạy giao diện:\n{error}"
        )


if __name__ == "__main__":
    main()
