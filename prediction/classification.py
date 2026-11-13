"""Session-level purchase classification for the e-commerce events dataset."""

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import math
import re

import numpy as np


class ClassificationError(ValueError):
    """Raised when the available events cannot support a classification task."""


class PurchaseClassifier:
    """Train a logistic-regression model to predict purchase at session level."""

    NUMERIC_FEATURES = (
        "view_count",
        "cart_count",
        "other_count",
        "event_count",
        "unique_products",
        "unique_categories",
        "unique_brands",
        "avg_price",
        "max_price",
        "duration_minutes",
        "hour",
        "weekday",
    )
    MAX_CATEGORY_FEATURES = 15
    MAX_BRAND_FEATURES = 15
    MAX_TRAINING_SESSIONS = 20000
    NULL_TEXT_VALUES = frozenset(("", "none", "null", "nan", "n/a", "na"))
    EVENT_ALIASES = {
        "view": "view",
        "product_view": "view",
        "product view": "view",
        "cart": "cart",
        "add_to_cart": "cart",
        "add to cart": "cart",
        "addtocart": "cart",
        "purchase": "purchase",
        "buy": "purchase",
    }

    def __init__(self):
        self.weights = None
        self.means = None
        self.scales = None
        self.categories = ()
        self.brands = ()
        self.feature_names = ()

    @staticmethod
    def _value(record, field):
        if isinstance(record, dict):
            return record.get(field)
        return getattr(record, field, None)

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.casefold() in PurchaseClassifier.NULL_TEXT_VALUES else text

    @classmethod
    def clean_records(cls, records):
        """Normalize event fields and report rows removed or repaired for modeling."""
        report = {
            "raw_count": 0,
            "clean_count": 0,
            "removed_missing_session": 0,
            "removed_missing_event_type": 0,
            "removed_invalid_time": 0,
            "removed_invalid_time_sessions": 0,
            "removed_invalid_time_session_rows": 0,
            "removed_duplicate_id": 0,
            "repaired_event_type": 0,
            "repaired_text_fields": 0,
            "repaired_price": 0,
        }
        cleaned = []
        seen_ids = set()
        invalid_time_sessions = set()
        text_fields = ("category_code", "brand")

        for source in records or ():
            report["raw_count"] += 1
            row = dict(source) if isinstance(source, dict) else {
                field: getattr(source, field, None)
                for field in (
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
            }

            session = cls._text(row.get("user_session"))
            if not session:
                report["removed_missing_session"] += 1
                continue
            row["user_session"] = session

            event_type = cls._text(row.get("event_type")).casefold()
            if not event_type:
                report["removed_missing_event_type"] += 1
                continue
            normalized_event = re.sub(r"[\s-]+", "_", event_type)
            canonical_event = cls.EVENT_ALIASES.get(
                event_type,
                cls.EVENT_ALIASES.get(normalized_event, normalized_event),
            )
            if row.get("event_type") != canonical_event:
                report["repaired_event_type"] += 1
            row["event_type"] = canonical_event

            record_id = cls._text(row.get("id"))
            if record_id:
                if record_id in seen_ids:
                    report["removed_duplicate_id"] += 1
                    continue
                seen_ids.add(record_id)

            event_time = cls._datetime(row.get("event_time"))
            if event_time is None:
                report["removed_invalid_time"] += 1
                invalid_time_sessions.add(session)
            row["event_time"] = event_time

            for field in text_fields:
                original = row.get(field)
                normalized = cls._text(original)
                if normalized:
                    normalized = normalized.casefold()
                value = normalized or None
                if original != value:
                    report["repaired_text_fields"] += 1
                row[field] = value

            price = cls._number(row.get("price"))
            if price is None or price < 0:
                if row.get("price") is not None:
                    report["repaired_price"] += 1
                row["price"] = None
            else:
                if row.get("price") != price:
                    report["repaired_price"] += 1
                row["price"] = price

            cleaned.append(row)

        if invalid_time_sessions:
            retained = [
                row for row in cleaned
                if row["user_session"] not in invalid_time_sessions
            ]
            report["removed_invalid_time_sessions"] = len(invalid_time_sessions)
            report["removed_invalid_time_session_rows"] = (
                len(cleaned) - len(retained)
            )
            cleaned = retained

        report["clean_count"] = len(cleaned)
        report["removed_count"] = report["raw_count"] - report["clean_count"]
        report["repaired_count"] = (
            report["repaired_event_type"]
            + report["repaired_text_fields"]
            + report["repaired_price"]
        )
        return cleaned, report

    @staticmethod
    def _number(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _datetime(value):
        if value is None or str(value).strip().casefold() in (
            "",
            "nat",
            "nan",
            "none",
            "null",
        ):
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if hasattr(value, "to_pydatetime"):
            converted = value.to_pydatetime()
            if isinstance(converted, datetime):
                return PurchaseClassifier._datetime(converted)
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            return None

    @classmethod
    def build_sessions(cls, records):
        """Build one leakage-safe example per session with observable signals."""
        grouped = defaultdict(list)
        for record in records or ():
            session = cls._text(cls._value(record, "user_session"))
            if not session:
                continue
            event_type = cls._text(cls._value(record, "event_type")).casefold()
            grouped[session].append(
                (
                    event_type,
                    cls._datetime(cls._value(record, "event_time")),
                    record,
                )
            )

        examples = []
        for session_records in grouped.values():
            purchase_times = []
            purchase_count = 0
            for event_type, event_time, _ in session_records:
                if event_type == "purchase":
                    purchase_count += 1
                    if event_time is not None:
                        purchase_times.append(event_time)
            has_purchase = purchase_count > 0
            if has_purchase and len(purchase_times) != purchase_count:
                continue
            first_purchase = min(purchase_times) if purchase_times else None
            views = carts = other = 0
            products, categories, brands = set(), Counter(), Counter()
            prices, timestamps = [], []
            for event_type, event_time, record in session_records:
                if event_type == "purchase":
                    continue
                if has_purchase and (
                    event_time is None or event_time >= first_purchase
                ):
                    continue

                if event_type == "view":
                    views += 1
                elif event_type in ("cart", "add_to_cart", "add-to-cart", "addtocart"):
                    carts += 1
                else:
                    other += 1

                product = cls._text(cls._value(record, "product_id"))
                category = cls._text(cls._value(record, "category_code"))
                brand = cls._text(cls._value(record, "brand"))
                if product:
                    products.add(product)
                if category:
                    categories[category] += 1
                if brand:
                    brands[brand] += 1
                price = cls._number(cls._value(record, "price"))
                if price is not None:
                    prices.append(price)
                if event_time is not None:
                    timestamps.append(event_time)

            if not views + carts + other:
                continue
            first_time = min(timestamps) if timestamps else None
            last_time = max(timestamps) if timestamps else None
            duration = 0.0
            hour = weekday = 0
            if first_time is not None:
                hour, weekday = first_time.hour, first_time.weekday()
                if last_time is not None:
                    duration = max(
                        0.0,
                        (last_time - first_time).total_seconds() / 60.0,
                    )

            features = {
                "view_count": float(views),
                "cart_count": float(carts),
                "other_count": float(other),
                "event_count": float(views + carts + other),
                "unique_products": float(len(products)),
                "unique_categories": float(len(categories)),
                "unique_brands": float(len(brands)),
                "avg_price": sum(prices) / len(prices) if prices else 0.0,
                "max_price": max(prices) if prices else 0.0,
                "duration_minutes": duration,
                "hour": float(hour),
                "weekday": float(weekday),
                "category": categories.most_common(1)[0][0] if categories else "",
                "brand": brands.most_common(1)[0][0] if brands else "",
            }
            examples.append((features, int(has_purchase)))
        return examples

    @classmethod
    def _top_values(cls, examples, field, limit):
        counts = Counter(
            features[field] for features, _ in examples if features.get(field)
        )
        return tuple(
            value for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        )

    @classmethod
    def _matrix(cls, examples, categories, brands):
        names = list(cls.NUMERIC_FEATURES)
        names.extend(f"category={value}" for value in categories)
        names.extend(f"brand={value}" for value in brands)
        matrix = np.zeros((len(examples), len(names)), dtype=np.float64)
        if not examples:
            return matrix, np.empty(0, dtype=np.float64), names

        feature_rows = [features for features, _ in examples]
        labels = np.fromiter(
            (label for _, label in examples),
            dtype=np.float64,
            count=len(examples),
        )
        matrix[:, :len(cls.NUMERIC_FEATURES)] = np.asarray(
            [
                [features.get(field, 0.0) for field in cls.NUMERIC_FEATURES]
                for features in feature_rows
            ],
            dtype=np.float64,
        )
        category_index = {value: index for index, value in enumerate(categories)}
        brand_index = {value: index for index, value in enumerate(brands)}
        rows = np.arange(len(examples))
        category_columns = np.fromiter(
            (category_index.get(features.get("category"), -1) for features in feature_rows),
            dtype=np.intp,
            count=len(examples),
        )
        known_categories = category_columns >= 0
        matrix[
            rows[known_categories],
            len(cls.NUMERIC_FEATURES) + category_columns[known_categories],
        ] = 1.0
        brand_columns = np.fromiter(
            (brand_index.get(features.get("brand"), -1) for features in feature_rows),
            dtype=np.intp,
            count=len(examples),
        )
        known_brands = brand_columns >= 0
        matrix[
            rows[known_brands],
            len(cls.NUMERIC_FEATURES) + len(categories) + brand_columns[known_brands],
        ] = 1.0
        return matrix, labels, names

    @staticmethod
    def _fit_logistic(matrix, labels, iterations=70):
        means = matrix[:, :len(PurchaseClassifier.NUMERIC_FEATURES)].mean(axis=0)
        scales = matrix[:, :len(PurchaseClassifier.NUMERIC_FEATURES)].std(axis=0)
        scales[scales < 1e-8] = 1.0
        normalized = matrix.copy()
        numeric_count = len(PurchaseClassifier.NUMERIC_FEATURES)
        normalized[:, :numeric_count] = (
            normalized[:, :numeric_count] - means
        ) / scales
        design = np.column_stack((normalized, np.ones(len(normalized))))
        weights = np.zeros(design.shape[1], dtype=np.float64)
        for _ in range(iterations):
            logits = np.clip(design @ weights, -30.0, 30.0)
            probabilities = 1.0 / (1.0 + np.exp(-logits))
            gradient = design.T @ (probabilities - labels) / len(labels)
            gradient[:-1] += 0.01 * weights[:-1]
            weights -= 0.15 * gradient
        return weights, means, scales

    @staticmethod
    def _probabilities(matrix, weights, means, scales):
        numeric_count = len(PurchaseClassifier.NUMERIC_FEATURES)
        normalized = matrix.copy()
        normalized[:, :numeric_count] = (
            normalized[:, :numeric_count] - means
        ) / scales
        design = np.column_stack((normalized, np.ones(len(normalized))))
        logits = np.clip(design @ weights, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-logits))

    @staticmethod
    def _metrics(labels, probabilities):
        predicted = probabilities >= 0.5
        actual = labels.astype(bool)
        true_positive = int(np.sum(predicted & actual))
        true_negative = int(np.sum(~predicted & ~actual))
        false_positive = int(np.sum(predicted & ~actual))
        false_negative = int(np.sum(~predicted & actual))
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "accuracy": (true_positive + true_negative) / len(labels),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }

    def train(self, records, training_rate=0.8):
        records, _ = self.clean_records(records)
        return self._train_cleaned(records, training_rate)

    def _train_cleaned(self, records, training_rate=0.8):
        if (
            not isinstance(training_rate, (int, float))
            or not math.isfinite(training_rate)
            or not 0.5 <= training_rate <= 0.9
        ):
            raise ClassificationError(
                "Tỷ lệ dữ liệu huấn luyện phải nằm trong khoảng 50% đến 90%."
            )
        examples = self.build_sessions(records)
        if len(examples) < 6:
            raise ClassificationError(
                "Cần ít nhất 6 phiên có tín hiệu trước mua hàng để huấn luyện."
            )

        example_labels = np.fromiter(
            (target for _, target in examples),
            dtype=np.int8,
            count=len(examples),
        )
        class_indices = {
            label: np.flatnonzero(example_labels == label)
            for label in (0, 1)
        }
        if any(len(indices) < 2 for indices in class_indices.values()):
            raise ClassificationError(
                "Dữ liệu cần có ít nhất 2 phiên mua và 2 phiên không mua."
            )

        available_session_count = len(examples)
        rng = np.random.default_rng(42)
        if len(examples) > self.MAX_TRAINING_SESSIONS:
            positive_share = len(class_indices[1]) / len(examples)
            positive_limit = min(
                len(class_indices[1]),
                max(2, round(self.MAX_TRAINING_SESSIONS * positive_share)),
                self.MAX_TRAINING_SESSIONS - 2,
            )
            negative_limit = min(
                len(class_indices[0]),
                max(2, self.MAX_TRAINING_SESSIONS - positive_limit),
            )
            positive_indices = rng.choice(
                class_indices[1], size=positive_limit, replace=False
            )
            negative_indices = rng.choice(
                class_indices[0], size=negative_limit, replace=False
            )
            selected = np.concatenate((positive_indices, negative_indices))
            rng.shuffle(selected)
            examples = [examples[index] for index in selected]
            example_labels = example_labels[selected]
            class_indices = {
                label: np.flatnonzero(example_labels == label)
                for label in (0, 1)
            }

        train_indices, test_indices = [], []
        for indices in class_indices.values():
            indices = rng.permutation(indices)
            test_count = min(
                len(indices) - 1,
                max(1, round(len(indices) * (1.0 - training_rate))),
            )
            test_indices.extend(indices[:test_count])
            train_indices.extend(indices[test_count:])

        train_indices = np.asarray(train_indices, dtype=int)
        test_indices = np.asarray(test_indices, dtype=int)
        train_examples = [examples[index] for index in train_indices]
        test_examples = [examples[index] for index in test_indices]

        categories = self._top_values(
            train_examples, "category", self.MAX_CATEGORY_FEATURES
        )
        brands = self._top_values(
            train_examples, "brand", self.MAX_BRAND_FEATURES
        )
        train_matrix, train_labels, _ = self._matrix(
            train_examples, categories, brands
        )
        test_matrix, test_labels, _ = self._matrix(
            test_examples, categories, brands
        )

        test_weights, test_means, test_scales = self._fit_logistic(
            train_matrix, train_labels
        )
        test_probabilities = self._probabilities(
            test_matrix, test_weights, test_means, test_scales
        )
        metrics = self._metrics(test_labels, test_probabilities)

        categories = self._top_values(
            examples, "category", self.MAX_CATEGORY_FEATURES
        )
        brands = self._top_values(examples, "brand", self.MAX_BRAND_FEATURES)
        matrix, labels, feature_names = self._matrix(examples, categories, brands)
        self.weights, self.means, self.scales = self._fit_logistic(matrix, labels)
        self.categories, self.brands = categories, brands
        self.feature_names = tuple(feature_names)
        return {
            **metrics,
            "session_count": len(examples),
            "available_session_count": available_session_count,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "purchase_rate": float(labels.mean()),
        }

    def coefficients(self):
        if self.weights is None:
            raise ClassificationError("Hãy huấn luyện hoặc tải mô hình trước.")
        return sorted(
            zip(self.feature_names, self.weights[:-1].tolist()),
            key=lambda item: abs(item[1]),
            reverse=True,
        )

    def export_model(self):
        if self.weights is None:
            raise ClassificationError("Hãy huấn luyện mô hình trước khi lưu.")
        return {
            "version": 1,
            "weights": self.weights.tolist(),
            "means": self.means.tolist(),
            "scales": self.scales.tolist(),
            "categories": list(self.categories),
            "brands": list(self.brands),
            "feature_names": list(self.feature_names),
        }

    def load_model(self, payload):
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ClassificationError("Tệp mô hình không đúng định dạng hoặc phiên bản.")
        try:
            weights = np.asarray(payload["weights"], dtype=np.float64)
            means = np.asarray(payload["means"], dtype=np.float64)
            scales = np.asarray(payload["scales"], dtype=np.float64)
            categories = tuple(payload["categories"])
            brands = tuple(payload["brands"])
            feature_names = tuple(payload["feature_names"])
        except (KeyError, TypeError, ValueError) as error:
            raise ClassificationError("Dữ liệu trong tệp mô hình không hợp lệ.") from error

        numeric_count = len(self.NUMERIC_FEATURES)
        expected_features = numeric_count + len(categories) + len(brands)
        if (
            means.shape != (numeric_count,)
            or scales.shape != (numeric_count,)
            or weights.shape != (expected_features + 1,)
            or len(feature_names) != expected_features
            or not np.isfinite(weights).all()
            or not np.isfinite(means).all()
            or not np.isfinite(scales).all()
            or np.any(scales <= 0)
            or not all(isinstance(value, str) for value in categories + brands + feature_names)
        ):
            raise ClassificationError("Cấu trúc hoặc giá trị của mô hình không hợp lệ.")

        self.weights = weights
        self.means = means
        self.scales = scales
        self.categories = categories
        self.brands = brands
        self.feature_names = feature_names

    def predict_proba(self, features):
        if self.weights is None:
            raise ClassificationError("Hãy huấn luyện mô hình trước khi dự đoán.")
        if not isinstance(features, dict):
            raise ClassificationError("Đặc trưng dự đoán phải ở dạng từ điển.")
        values = {}
        for field in self.NUMERIC_FEATURES:
            number = self._number(features.get(field))
            if number is None:
                raise ClassificationError(
                    f"Đặc trưng '{field}' phải là một số hữu hạn."
                )
            values[field] = number
        for field in (
            "view_count",
            "cart_count",
            "other_count",
            "event_count",
            "unique_products",
            "unique_categories",
            "unique_brands",
            "avg_price",
            "max_price",
            "duration_minutes",
        ):
            if values[field] < 0:
                raise ClassificationError(
                    f"Đặc trưng '{field}' không được nhỏ hơn 0."
                )
        for field in (
            "view_count",
            "cart_count",
            "other_count",
            "event_count",
            "unique_products",
            "unique_categories",
            "unique_brands",
        ):
            if not values[field].is_integer():
                raise ClassificationError(
                    f"Đặc trưng '{field}' phải là số nguyên."
                )
        if values["event_count"] != (
            values["view_count"] + values["cart_count"] + values["other_count"]
        ):
            raise ClassificationError(
                "Tổng sự kiện phải bằng tổng lượt xem, thêm giỏ hàng và sự kiện khác."
            )
        if values["event_count"] == 0:
            raise ClassificationError("Phiên cần có ít nhất một sự kiện.")
        if any(
            values[field] > values["event_count"]
            for field in ("unique_products", "unique_categories", "unique_brands")
        ):
            raise ClassificationError(
                "Số lượng sản phẩm, danh mục hoặc thương hiệu khác nhau "
                "không thể lớn hơn tổng số sự kiện."
            )
        if values["avg_price"] > values["max_price"]:
            raise ClassificationError(
                "Giá trung bình không thể lớn hơn giá cao nhất."
            )
        if not 0 <= values["hour"] <= 23 or not values["hour"].is_integer():
            raise ClassificationError("Giờ bắt đầu phải là số nguyên từ 0 đến 23.")
        if not 0 <= values["weekday"] <= 6 or not values["weekday"].is_integer():
            raise ClassificationError("Ngày trong tuần phải là số nguyên từ 0 đến 6.")

        row = [values[field] for field in self.NUMERIC_FEATURES]
        row.extend(
            1.0 if self._text(features.get("category")).casefold() == category else 0.0
            for category in self.categories
        )
        row.extend(
            1.0 if self._text(features.get("brand")).casefold() == brand else 0.0
            for brand in self.brands
        )
        matrix = np.asarray([row], dtype=np.float64)
        return float(
            self._probabilities(matrix, self.weights, self.means, self.scales)[0]
        )
