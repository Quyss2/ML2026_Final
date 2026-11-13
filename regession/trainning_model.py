"""Data preparation and model helpers for session revenue regression."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


EVENT_COLUMNS = (
    "event_time",
    "event_type",
    "product_id",
    "category_code",
    "brand",
    "price",
    "user_id",
    "user_session",
)
NUMERIC_FEATURES = (
    "n_view",
    "n_cart",
    "n_products",
    "n_categories",
    "n_brands",
    "avg_price",
    "max_price",
    "hour",
)
CATEGORICAL_FEATURES = ("top_category", "weekday")
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
DISPLAY_FEATURE_COLUMNS = (
    "user_session",
    "n_view",
    "n_cart",
    "n_products",
    "n_categories",
    "n_brands",
    "avg_price",
    "max_price",
    "top_category",
    "hour",
    "weekday",
    "revenue",
)
MODEL_NAMES = (
    "Linear",
    "Random Forest",
    "Gradient Boosting",
)


def load_events(path):
    """Read the event CSV, validating the columns used by this workflow."""
    data = pd.read_csv(path, low_memory=False)
    missing = sorted(set(EVENT_COLUMNS) - set(data.columns))
    if missing:
        raise ValueError(f"Thiếu cột bắt buộc trong dữ liệu: {', '.join(missing)}")
    data = data.copy()
    data["event_time"] = pd.to_datetime(data["event_time"], errors="coerce")
    return data


def preprocess_events(
    events,
    drop_duplicates=True,
    drop_invalid_price=True,
    fill_brand=True,
    split_category=True,
    drop_id_columns=True,
):
    """Clean event rows without changing the session-level target definition."""
    data = events.copy()
    required = {"event_time", "event_type", "price", "user_session"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Thiếu cột để tiền xử lý: {', '.join(missing)}")

    data["event_time"] = pd.to_datetime(data["event_time"], errors="coerce")
    data["price"] = pd.to_numeric(data["price"], errors="coerce")
    data["event_type"] = data["event_type"].fillna("unknown").astype(str).str.lower()
    if drop_duplicates:
        duplicate_columns = [column for column in data.columns if column != "id"]
        data = data.drop_duplicates(subset=duplicate_columns)
    data["user_session"] = data["user_session"].astype("string").str.strip()
    data["user_session"] = data["user_session"].replace("", pd.NA)
    data = data.dropna(subset=["user_session", "event_time"])
    if drop_invalid_price:
        data = data.dropna(subset=["price"])
        data = data[data["price"] > 0]
    else:
        data["price"] = data["price"].fillna(0).clip(lower=0)

    if fill_brand and "brand" in data:
        data["brand"] = data["brand"].fillna("unknown").astype(str).str.strip()
        data.loc[data["brand"].eq(""), "brand"] = "unknown"
    if split_category and "category_code" in data:
        categories = data["category_code"].fillna("unknown").astype(str).str.strip()
        categories = categories.mask(categories.eq(""), "unknown")
        levels = categories.str.extract(r"^([^.]+)(?:\.([^.]+))?")
        data["category_level1"] = levels[0].fillna("unknown").str.strip()
        data["category_level2"] = levels[1].fillna("unknown").str.strip()
        data["category_level1"] = data["category_level1"].replace("", "unknown")
        data["category_level2"] = data["category_level2"].replace("", "unknown")
        data = data.drop(columns=["category_code"])
    if drop_id_columns:
        data = data.drop(columns=["id", "category_id"], errors="ignore")

    if data.empty:
        raise ValueError("Không còn sự kiện nào sau khi tiền xử lý.")
    return data.sort_values(["user_session", "event_time"], kind="stable").reset_index(
        drop=True
    )


def _category_root(value):
    if pd.isna(value):
        return "unknown"
    category = str(value).strip().lower()
    return category.split(".", 1)[0] if category else "unknown"


def _make_preprocessor(encode=True, scale=True):
    categorical_encoder = (
        OneHotEncoder(handle_unknown="ignore")
        if encode
        else OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    )
    numeric_pipeline = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        numeric_pipeline.append(("scaler", StandardScaler()))
    return ColumnTransformer(
        transformers=[
            ("numeric", Pipeline(numeric_pipeline), list(NUMERIC_FEATURES)),
            ("categorical", categorical_encoder, list(CATEGORICAL_FEATURES)),
        ],
        remainder="drop",
    )


def build_session_features(events, window_size=5, only_cart=False, assume_sorted=False):
    """Build behavior features from the first N events and spend from all purchases."""
    if window_size < 1:
        raise ValueError("N sự kiện đầu phải lớn hơn 0.")
    required = {"event_time", "event_type", "price", "user_session"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"Thiếu cột để tạo đặc trưng: {', '.join(missing)}")

    required_columns = [
        "event_time",
        "event_type",
        "price",
        "user_session",
        "category_level1",
        "category_code",
        "product_id",
        "brand",
    ]
    columns = [column for column in required_columns if column in events.columns]
    data = events.loc[:, columns].copy()
    data["event_time"] = pd.to_datetime(data["event_time"], errors="coerce")
    data["price"] = pd.to_numeric(data["price"], errors="coerce").fillna(0).clip(lower=0)
    data["event_type"] = data["event_type"].fillna("unknown").astype(str).str.lower()
    data = data.dropna(subset=["user_session", "event_time"])
    if not assume_sorted:
        data = data.sort_values(["user_session", "event_time"], kind="stable")
    if data.empty:
        raise ValueError("Không có sự kiện hợp lệ để tạo đặc trưng.")
    if "product_id" not in data:
        data["product_id"] = pd.NA
    if "brand" not in data:
        data["brand"] = pd.NA
    if "category_level1" not in data:
        category_column = (
            "category_code" if "category_code" in data else None
        )
        data["category_level1"] = (
            data[category_column].map(_category_root)
            if category_column is not None
            else "unknown"
        )
    session_groups = data.groupby("user_session", sort=False)
    data["_position"] = session_groups.cumcount()
    first_events = data.loc[
        (data["_position"] < window_size) & data["event_type"].ne("purchase")
    ].copy()
    first_events["_category"] = (
        first_events["category_level1"]
        .astype("string")
        .fillna("unknown")
        .str.strip()
        .str.lower()
        .str.split(".", n=1)
        .str[0]
        .replace("", "unknown")
    )
    first_events["_brand"] = (
        first_events["brand"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
    )
    first_events["_is_view"] = first_events["event_type"].eq("view")
    first_events["_is_cart"] = first_events["event_type"].eq("cart")
    first_groups = first_events.groupby("user_session", sort=False)
    observed_aggregates = first_groups.agg(
        n_view=("_is_view", "sum"),
        n_cart=("_is_cart", "sum"),
        n_products=("product_id", "nunique"),
        n_categories=("_category", "nunique"),
        n_brands=("_brand", "nunique"),
    )
    first_positions = data.loc[data["_position"] < window_size]
    aggregates = first_positions.groupby("user_session", sort=False).agg(
        _session_start=("event_time", "first")
    ).join(observed_aggregates, how="left")
    initial_price_stats = first_groups["price"].agg(["mean", "max"])
    aggregates["avg_price"] = initial_price_stats["mean"]
    aggregates["max_price"] = initial_price_stats["max"]

    category_counts = (
        first_events.groupby(["user_session", "_category"], sort=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(
            ["user_session", "count", "_category"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("user_session")
        .set_index("user_session")["_category"]
        .rename("top_category")
    )
    aggregates = aggregates.join(category_counts)
    aggregates[["n_view", "n_cart", "n_products", "n_categories", "n_brands"]] = (
        aggregates[["n_view", "n_cart", "n_products", "n_categories", "n_brands"]]
        .fillna(0)
        .astype(int)
    )
    aggregates["top_category"] = aggregates["top_category"].fillna("unknown")
    aggregates["avg_price"] = aggregates["avg_price"].fillna(0.0)
    aggregates["max_price"] = aggregates["max_price"].fillna(0.0)
    aggregates["hour"] = aggregates["_session_start"].dt.hour
    aggregates["weekday"] = aggregates["_session_start"].dt.dayofweek

    purchases = data.loc[data["event_type"].eq("purchase")]
    revenue = purchases.groupby("user_session", sort=False)["price"].sum()
    aggregates["revenue"] = revenue.reindex(aggregates.index).fillna(0.0)
    if only_cart:
        aggregates = aggregates.loc[aggregates["n_cart"] > 0]
    if aggregates.empty:
        raise ValueError("Không có phiên phù hợp với điều kiện lọc (ví dụ: có cart).")

    aggregates.index.name = "user_session"
    return aggregates.reset_index().loc[
        :,
        [
            "user_session",
            "n_view",
            "n_cart",
            "n_products",
            "n_categories",
            "n_brands",
            "avg_price",
            "max_price",
            "top_category",
            "hour",
            "weekday",
            "revenue",
            "_session_start",
        ],
    ]


def chronological_split(features, train_pct=80):
    """Split whole sessions by start date, keeping later dates exclusively in tests."""
    if not 50 <= train_pct <= 95:
        raise ValueError("Tỷ lệ train phải nằm trong khoảng 50% đến 95%.")
    if len(features) < 2:
        raise ValueError("Cần ít nhất 2 phiên để chia train/tests.")

    starts = pd.to_datetime(features["_session_start"], errors="coerce")
    dates = np.array(sorted(starts.dropna().dt.normalize().unique()))
    if len(dates) < 2:
        raise ValueError("Cần dữ liệu thuộc ít nhất 2 ngày để chia theo thời gian.")
    split_index = min(max(int(len(dates) * train_pct / 100), 1), len(dates) - 1)
    cutoff = dates[split_index]
    train = features.loc[starts.dt.normalize() < cutoff].copy()
    test = features.loc[starts.dt.normalize() >= cutoff].copy()
    if train.empty or test.empty:
        raise ValueError("Không thể tạo tập train/tests không rỗng theo ngày.")
    return train.reset_index(drop=True), test.reset_index(drop=True), pd.Timestamp(cutoff)


class RevenueRegressor:
    """Persistable preprocessing + estimator with revenue-scale predictions."""

    def __init__(self, estimator, encode=True, scale=True, log_target=True):
        self.pipeline = Pipeline(
            [
                ("preprocess", _make_preprocessor(encode=encode, scale=scale)),
                ("regressor", estimator),
            ]
        )
        self.log_target = log_target

    def fit(self, features, revenue):
        target = np.asarray(revenue, dtype=float)
        if self.log_target:
            target = np.log1p(np.clip(target, 0, None))
        self.pipeline.fit(features.loc[:, list(FEATURE_COLUMNS)], target)
        return self

    def predict(self, features):
        predictions = self.pipeline.predict(features.loc[:, list(FEATURE_COLUMNS)])
        if self.log_target:
            predictions = np.expm1(predictions)
        return np.clip(np.asarray(predictions, dtype=float), 0, None)

    def feature_importances(self):
        preprocessor = self.pipeline.named_steps["preprocess"]
        estimator = self.pipeline.named_steps["regressor"]
        names = preprocessor.get_feature_names_out()
        if hasattr(estimator, "feature_importances_"):
            values = estimator.feature_importances_
        elif hasattr(estimator, "coef_"):
            values = np.abs(np.asarray(estimator.coef_)).ravel()
        else:
            return pd.Series(dtype=float)
        return pd.Series(values, index=names).sort_values(ascending=False)


def train_models(
    train,
    test,
    selected_models,
    n_estimators=200,
    max_depth=8,
    learning_rate=0.1,
    encode=True,
    scale=True,
    clip_p99=True,
    log_target=False,
):
    """Fit selected regressors and calculate tests metrics on the revenue scale."""
    if not selected_models:
        raise ValueError("Hãy chọn ít nhất một mô hình.")
    unknown_models = sorted(set(selected_models) - set(MODEL_NAMES))
    if unknown_models:
        raise ValueError(f"Mô hình không được hỗ trợ: {', '.join(unknown_models)}")
    if train.empty or test.empty:
        raise ValueError("Tập train và tests không được để trống.")

    y_train = train["revenue"].astype(float).clip(lower=0)
    y_test = test["revenue"].astype(float).clip(lower=0)
    upper_bound = float(y_train.quantile(0.99)) if clip_p99 else None
    fitted_target = y_train.clip(upper=upper_bound) if upper_bound is not None else y_train
    estimators = {
        "Linear": LinearRegression(),
        "Random Forest": RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        ),
    }

    results = {}
    x_train = train.loc[:, list(FEATURE_COLUMNS)]
    x_test = test.loc[:, list(FEATURE_COLUMNS)]
    for name in MODEL_NAMES:
        if name not in selected_models:
            continue
        model = RevenueRegressor(
            estimators[name],
            encode=encode,
            scale=scale if name == "Linear" else False,
            log_target=log_target,
        )
        model.fit(x_train, fitted_target)
        predictions = model.predict(x_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, predictions)))
        results[name] = {
            "model": model,
            "predictions": predictions,
            "metrics": {
                "mae": float(mean_absolute_error(y_test, predictions)),
                "rmse": rmse,
                "r2_log": float(
                    r2_score(np.log1p(y_test), np.log1p(predictions))
                ),
                "r2": float(r2_score(y_test, predictions)),
            },
            "clip_p99": upper_bound,
            "log_target": log_target,
        }
    return results


def save_model(model, path):
    """Save a fitted RevenueRegressor using joblib."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, destination)
    return destination


def load_model(path):
    """Load a model saved by save_model."""
    return joblib.load(path)
