from collections import Counter, defaultdict
from datetime import date, datetime

import matplotlib.dates as mdates

from ui.DatavVisualization import Ui_MainWindow


class DataVisualizationEx(Ui_MainWindow):
    EVENT_COLORS = {
        "view": "#3b82f6",
        "cart": "#f59e0b",
        "purchase": "#10b981",
    }

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.MainWindow = MainWindow
        self.updateCharts([])

    def showWindow(self):
        self.MainWindow.show()
        self.MainWindow.raise_()
        self.MainWindow.activateWindow()

    @staticmethod
    def _value(record, field):
        if isinstance(record, dict):
            return record.get(field)
        return getattr(record, field, None)

    @staticmethod
    def _as_datetime(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _new_axes(self, canvas):
        canvas.fig.clear()
        axes = canvas.fig.add_subplot(111)
        axes.set_facecolor("white")
        axes.tick_params(colors="#64748b", labelsize=8)
        for side in ("top", "right"):
            axes.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            axes.spines[side].set_color("#e2e8f0")
        return axes

    @staticmethod
    def _empty_chart(axes, message="Không có dữ liệu phù hợp"):
        axes.set_axis_off()
        axes.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            color="#64748b",
            transform=axes.transAxes,
        )

    @staticmethod
    def _finish(canvas):
        canvas.draw_idle()

    def _update_kpis(self, records):
        users = {
            self._value(record, "user_id")
            for record in records
            if self._value(record, "user_id") is not None
        }
        purchase_records = [
            record
            for record in records
            if str(self._value(record, "event_type") or "").lower() == "purchase"
        ]
        revenue = sum(
            price
            for record in purchase_records
            if (price := self._as_number(self._value(record, "price"))) is not None
        )
        purchase_sessions = {
            self._value(record, "user_session")
            for record in purchase_records
            if self._value(record, "user_session") is not None
        }
        view_sessions = {
            self._value(record, "user_session")
            for record in records
            if str(self._value(record, "event_type") or "").lower() == "view"
            and self._value(record, "user_session") is not None
        }
        conversion = (
            100 * len(purchase_sessions & view_sessions) / len(view_sessions)
            if view_sessions
            else 0
        )
        avg_order = revenue / len(purchase_records) if purchase_records else 0

        self.lblKpiEventsValue.setText(f"{len(records):,}")
        self.lblKpiEventsNote.setText(
            f"số phiên: {len({self._value(row, 'user_session') for row in records if self._value(row, 'user_session') is not None}):,}"
        )
        self.lblKpiUsersValue.setText(f"{len(users):,}")
        self.lblKpiUsersNote.setText("người dùng duy nhất")
        self.lblKpiRevenueValue.setText(f"{revenue:,.2f}")
        self.lblKpiRevenueNote.setText(f"số lượt mua: {len(purchase_records):,}")
        self.lblKpiAvgOrderValue.setText(f"{avg_order:,.2f}")
        self.lblKpiAvgOrderNote.setText("giá trị trung bình mỗi lượt mua")
        self.lblKpiConversionValue.setText(f"{conversion:.2f}%")
        self.lblKpiConversionNote.setText("phiên có mua / phiên có xem")

    def plotTimeline(self, records):
        axes = self._new_axes(self.canvasTimeline)
        timeline = defaultdict(Counter)
        timestamps = []
        for record in records:
            timestamp = self._as_datetime(self._value(record, "event_time"))
            if timestamp is None:
                continue
            timestamps.append((timestamp, record))

        if not timestamps:
            self._empty_chart(axes)
        else:
            first_timestamp = min(timestamp for timestamp, _ in timestamps)
            last_timestamp = max(timestamp for timestamp, _ in timestamps)
            show_time = (last_timestamp - first_timestamp).total_seconds() < 7 * 24 * 60 * 60

            for timestamp, record in timestamps:
                bucket = (
                    timestamp.replace(second=0, microsecond=0)
                    if show_time
                    else timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                )
                event = str(self._value(record, "event_type") or "unknown").lower()
                timeline[bucket][event] += 1

            time_points = sorted(timeline)
            events = sorted(
                {event for counts in timeline.values() for event in counts},
                key=lambda event: (event not in self.EVENT_COLORS, event),
            )
            for event in events[:6]:
                axes.plot(
                    time_points,
                    [timeline[point][event] for point in time_points],
                    marker="o" if len(time_points) < 20 else None,
                    markersize=3,
                    linewidth=1.8,
                    label=event,
                    color=self.EVENT_COLORS.get(event),
                )
            locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
            date_format = (
                "%H:%M"
                if show_time and first_timestamp.date() == last_timestamp.date()
                else "%d/%m %H:%M"
                if show_time
                else "%d/%m"
            )
            axes.xaxis.set_major_locator(locator)
            axes.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
            axes.grid(axis="y", color="#e2e8f0", linewidth=0.7)
            axes.set_ylabel("Số sự kiện", color="#64748b")
            axes.set_xlabel(
                "Thời gian (giờ:phút)" if show_time else "Ngày",
                color="#64748b",
            )
            axes.tick_params(axis="x", rotation=30)
            axes.legend(frameon=False, ncol=min(4, len(events)), fontsize=8)
        self._finish(self.canvasTimeline)

    def plotFunnel(self, records):
        axes = self._new_axes(self.canvasFunnel)
        events = ("view", "cart", "purchase")
        counts = Counter(
            str(self._value(record, "event_type") or "").lower()
            for record in records
        )
        values = [counts[event] for event in events]
        if not any(values):
            self._empty_chart(axes)
        else:
            bars = axes.barh(
                ["Xem", "Thêm giỏ", "Mua hàng"],
                values,
                color=[self.EVENT_COLORS[event] for event in events],
            )
            axes.invert_yaxis()
            axes.set_xlabel("Số sự kiện", color="#64748b")
            axes.grid(axis="x", color="#e2e8f0", linewidth=0.7)
            axes.set_axisbelow(True)
            for bar, value in zip(bars, values):
                axes.text(
                    bar.get_width(),
                    bar.get_y() + bar.get_height() / 2,
                    f" {value:,}",
                    va="center",
                    color="#334155",
                    fontsize=8,
                )
        self._finish(self.canvasFunnel)

    def plotEventShare(self, records):
        axes = self._new_axes(self.canvasShare)
        counts = Counter(
            str(self._value(record, "event_type") or "Không xác định")
            for record in records
        )
        if not counts:
            self._empty_chart(axes)
        else:
            labels, values = zip(*counts.most_common(8))
            colors = [
                self.EVENT_COLORS.get(str(label).lower(), "#94a3b8")
                for label in labels
            ]
            axes.pie(
                values,
                labels=labels,
                colors=colors,
                autopct="%1.1f%%",
                startangle=90,
                textprops={"color": "#334155", "fontsize": 8},
            )
            axes.axis("equal")
        self._finish(self.canvasShare)

    def plotBrands(self, records):
        axes = self._new_axes(self.canvasBrands)
        revenue = Counter()
        for record in records:
            if str(self._value(record, "event_type") or "").lower() != "purchase":
                continue
            brand = self._value(record, "brand") or "Không xác định"
            price = self._as_number(self._value(record, "price"))
            if price is not None:
                revenue[str(brand)] += price

        top = revenue.most_common(10)
        if not top:
            self._empty_chart(axes)
        else:
            labels, values = zip(*reversed(top))
            bars = axes.barh(labels, values, color="#3b82f6")
            axes.set_xlabel("Doanh thu", color="#64748b")
            axes.grid(axis="x", color="#e2e8f0", linewidth=0.7)
            axes.set_axisbelow(True)
            axes.tick_params(axis="y", labelsize=7)
            for bar, value in zip(bars, values):
                axes.text(
                    bar.get_width(),
                    bar.get_y() + bar.get_height() / 2,
                    f" {value:,.2f}",
                    va="center",
                    color="#334155",
                    fontsize=7,
                )
        self._finish(self.canvasBrands)

    def plotCategories(self, records):
        axes = self._new_axes(self.canvasCategories)
        purchases = Counter()
        views = Counter()
        purchasers = defaultdict(set)
        viewers = defaultdict(set)
        for record in records:
            category = self._value(record, "category_code") or "Không xác định"
            category = str(category)
            event = str(self._value(record, "event_type") or "").lower()
            session = self._value(record, "user_session")
            if event == "purchase":
                purchases[category] += 1
                if session is not None:
                    purchasers[category].add(session)
            elif event == "view":
                views[category] += 1
                if session is not None:
                    viewers[category].add(session)

        top = purchases.most_common(10)
        if not top:
            self._empty_chart(axes)
        else:
            labels, values = zip(*reversed(top))
            bars = axes.barh(labels, values, color="#10b981")
            axes.set_xlabel("Lượt mua (CR theo phiên)", color="#64748b")
            axes.grid(axis="x", color="#e2e8f0", linewidth=0.7)
            axes.set_axisbelow(True)
            axes.tick_params(axis="y", labelsize=7)
            for bar, category, value in zip(bars, labels, values):
                conversion = (
                    100 * len(purchasers[category] & viewers[category])
                    / len(viewers[category])
                    if viewers[category]
                    else 0
                )
                axes.text(
                    bar.get_width(),
                    bar.get_y() + bar.get_height() / 2,
                    f" {value:,} ({conversion:.1f}%)",
                    va="center",
                    color="#334155",
                    fontsize=7,
                )
        self._finish(self.canvasCategories)

    def plotPriceDistribution(self, records):
        axes = self._new_axes(self.canvasPrice)
        prices = {
            event: [
                price
                for record in records
                if str(self._value(record, "event_type") or "").lower() == event
                and (price := self._as_number(self._value(record, "price"))) is not None
            ]
            for event in ("view", "purchase")
        }
        if not any(prices.values()):
            self._empty_chart(axes)
        else:
            axes.hist(
                [prices["view"], prices["purchase"]],
                bins=12,
                label=["Xem", "Mua hàng"],
                color=[self.EVENT_COLORS["view"], self.EVENT_COLORS["purchase"]],
                alpha=0.75,
            )
            axes.set_xlabel("Giá", color="#64748b")
            axes.set_ylabel("Số sự kiện", color="#64748b")
            axes.grid(axis="y", color="#e2e8f0", linewidth=0.7)
            axes.legend(frameon=False)
        self._finish(self.canvasPrice)

    def plotActivityHeatmap(self, records):
        axes = self._new_axes(self.canvasHeatmap)
        matrix = [[0] * 24 for _ in range(7)]
        for record in records:
            timestamp = self._as_datetime(self._value(record, "event_time"))
            if timestamp is not None:
                matrix[timestamp.weekday()][timestamp.hour] += 1

        if not any(any(day) for day in matrix):
            self._empty_chart(axes)
        else:
            image = axes.imshow(matrix, aspect="auto", cmap="Blues", origin="upper")
            axes.set_yticks(range(7), ["T2", "T3", "T4", "T5", "T6", "T7", "CN"])
            axes.set_xticks(range(0, 24, 2), range(0, 24, 2))
            axes.set_xlabel("Giờ trong ngày", color="#64748b")
            axes.set_ylabel("Thứ", color="#64748b")
            self.canvasHeatmap.fig.colorbar(
                image, ax=axes, fraction=0.046, pad=0.04, label="Số sự kiện"
            )
        self._finish(self.canvasHeatmap)

    def updateCharts(self, records):
        records = list(records or [])
        self._update_kpis(records)
        self.plotTimeline(records)
        self.plotFunnel(records)
        self.plotEventShare(records)
        self.plotBrands(records)
        self.plotCategories(records)
        self.plotPriceDistribution(records)
        self.plotActivityHeatmap(records)
