import math
import flet.canvas as cv
import calendar
import json
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft
import flet_charts as fch

WEEK = ("一", "二", "三", "四", "五", "六", "日")
MAX_DAYS = 180

# S9.4 首页配色：克制蓝白，强调色只用于区分计划。
NAVY = "#172B4D"
PRIMARY = "#246FE5"
PALE_BLUE = "#EDF5FF"
PAGE_BG = "#F6F8FC"
MUTED = "#6D7E98"


def decode(value, default):
    try:
        return json.loads(value) if value else default
    except (ValueError, TypeError):
        return default


def rounded_seconds(seconds):
    """每条真实学习记录先四舍五入为整数秒（0.5 秒进 1）。"""
    return max(0, math.floor(float(seconds or 0) + 0.5))


def format_time(seconds):
    n = rounded_seconds(seconds)
    h, remain = divmod(n, 3600)
    m, s = divmod(remain, 60)
    if h:
        return f"{h}小时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def format_stat_duration(seconds):
    """统计图、图例、记录详情共用同一整数秒格式。"""
    return format_time(seconds)


def valid_record_segments(raw):
    """提取记录中的有效计时区间，暂停时段不在其中。"""
    segments = []
    for pair in decode(raw, []):
        try:
            a, b = float(pair[0]), float(pair[1])
            if b > a > 0:
                segments.append((a, b))
        except (ValueError, TypeError, IndexError, KeyError):
            continue
    return segments


def record_seconds_by_day(seconds, finished_at, segments_json):
    """先将单条记录取整，再按真实计时区间分给日期。

    跨午夜时将整数秒按有效计时比例分配；余数给占比最大的日期，
    确保一条记录在所有日期上的整数秒之和等于该记录的整数秒。
    """
    whole_seconds = rounded_seconds(seconds)
    if not whole_seconds:
        return {}

    segments = valid_record_segments(segments_json)
    if not segments:
        return {datetime.fromtimestamp(float(finished_at)).date(): whole_seconds}

    actual_lengths = defaultdict(float)
    for start, end in segments:
        cursor = start
        while cursor < end:
            current_day = datetime.fromtimestamp(cursor).date()
            midnight = datetime.combine(
                current_day + timedelta(days=1), datetime.min.time()
            ).timestamp()
            stop = min(end, midnight)
            if stop <= cursor:
                break
            actual_lengths[current_day] += stop - cursor
            cursor = stop

    total_length = sum(actual_lengths.values())
    if total_length <= 0:
        return {datetime.fromtimestamp(float(finished_at)).date(): whole_seconds}

    # 每个日期先向下取整，再把剩余整数秒依小数部分分配。
    exact = {
        day: whole_seconds * length / total_length
        for day, length in actual_lengths.items()
    }
    allocated = {day: math.floor(value) for day, value in exact.items()}
    remaining = whole_seconds - sum(allocated.values())
    order = sorted(exact, key=lambda day: (-(exact[day] - allocated[day]), day))
    for day in order[:remaining]:
        allocated[day] += 1
    return {day: value for day, value in allocated.items() if value > 0}


def study_breakdown(db_path, begin_day, end_day):
    """每次记录先取整，再汇总到计划名称；饼图总计取各项之和。"""
    totals = defaultdict(int)
    with sqlite3.connect(db_path) as db:
        records = db.execute("""
            SELECT title, seconds, finished_at, segments_json
            FROM records
            WHERE seconds > 0
        """).fetchall()

    for title, seconds, finished_at, segments_json in records:
        per_day = record_seconds_by_day(seconds, finished_at, segments_json)
        in_period = sum(
            amount for day, amount in per_day.items()
            if begin_day <= day <= end_day
        )
        if in_period:
            totals[str(title or "未命名计划")] += in_period
    return dict(totals)


def load_learning_records(db_path, start_day, end_day):
    """学习记录详情与饼图用完全相同的整数秒规则。"""
    with sqlite3.connect(db_path) as db:
        rows = db.execute("""
            SELECT id, title, seconds, finished_at, segments_json
            FROM records
            WHERE seconds > 0
            ORDER BY finished_at DESC, id DESC
        """).fetchall()

    results = []
    for record_id, title, seconds, finished_at, raw in rows:
        per_day = record_seconds_by_day(seconds, finished_at, raw)
        effective_seconds = sum(
            amount for day, amount in per_day.items()
            if start_day <= day <= end_day
        )
        if effective_seconds <= 0:
            continue

        segments = valid_record_segments(raw)
        if segments:
            first = min(a for a, _ in segments)
            last = max(b for _, b in segments)
            time_range = (
                datetime.fromtimestamp(first).strftime("%m-%d %H:%M")
                + " — "
                + datetime.fromtimestamp(last).strftime("%m-%d %H:%M")
            )
        else:
            time_range = (
                "开始时间未保存 · 结束 "
                + datetime.fromtimestamp(float(finished_at)).strftime("%m-%d %H:%M")
            )

        results.append({
            "id": record_id,
            "title": str(title or "未命名计划"),
            "time_range": time_range,
            "seconds": effective_seconds,
        })
    return results


def build_labeled_pie(sections, ranking, window_width):
    """饼图内显示名称，外侧用引导线标注时长。"""

    # S8.2：预留页面边距与统计卡片内边距。
    # 原先最小宽度 270 会让窄手机上的图表横向溢出。
    viewport = float(window_width or 390)
    card_margin = 72 if viewport < 400 else 80
    width = max(180, min(390, int(viewport - card_margin)))

    # 饼图两侧留给名称之外的时间标签与引导线。
    radius = min(106, max(48, (width - 146) / 2))
    diameter = radius * 2 + 12
    height = max(210 if viewport < 400 else 240, diameter + 40)

    cx, cy = width / 2, height / 2
    total = sum(seconds for _, seconds in ranking)

    for section in sections:
        section.radius = radius

    # 从正上方开始，顺时针确定每个扇形中心
    groups = {"left": [], "right": []}
    angle = -math.pi / 2

    for index, (name, seconds) in enumerate(ranking):
        sweep = 2 * math.pi * seconds / total
        mid = angle + sweep / 2

        dx = math.cos(mid)
        dy = math.sin(mid)

        side = "right" if dx >= 0 else "left"

        groups[side].append({
            "dx": dx,
            "dy": dy,
            "desired_y": cy + dy * (radius + 16),
            "label": format_stat_duration(seconds),
        })

        angle += sweep

    shapes = []

    # 将同侧标签适当错开，减少重叠
    for side, items in groups.items():
        items.sort(
            key=lambda item: item["desired_y"]
        )

        spaced = []

        for item in items:
            y = max(16, item["desired_y"])

            if spaced:
                y = max(y, spaced[-1] + 22)

            spaced.append(y)

        if spaced and spaced[-1] > height - 16:
            shift = spaced[-1] - (height - 16)
            spaced = [y - shift for y in spaced]

            if spaced[0] < 16:
                n = len(spaced)

                spaced = (
                    [height / 2]
                    if n == 1
                    else [
                        16 + i * (height - 32) / (n - 1)
                        for i in range(n)
                    ]
                )

        for item, label_y in zip(items, spaced):
            dx = item["dx"]
            dy = item["dy"]

            x0 = cx + dx * (radius - 4)
            y0 = cy + dy * (radius - 4)

            x1 = cx + dx * (radius + 9)
            y1 = cy + dy * (radius + 9)

            # 不足一分钟的标签靠近扇形
            if item["label"].endswith("秒"):
                x2 = x1 + (
                    12 if side == "right" else -12
                )
                text_x = (
                    x2 + 4 if side == "right"
                    else x2 - 27
                )
            else:
                x2 = (
                    width - 70
                    if side == "right"
                    else 70
                )
                text_x = (
                    width - 67
                    if side == "right"
                    else 1
                )

            line_paint = ft.Paint(
                color="#667085",
                stroke_width=1
            )


            shapes.extend([
                cv.Line(
                    x1=x0,
                    y1=y0,
                    x2=x1,
                    y2=y1,
                    paint=line_paint
                ),

                cv.Line(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=label_y,
                    paint=line_paint
                ),

                cv.Text(
                    x=text_x,
                    y=label_y - 9,
                    value=item["label"],
                    max_width=66,
                    text_align=(
                        ft.TextAlign.LEFT
                        if item["label"].endswith("秒")
                        else (
                            ft.TextAlign.LEFT
                            if side == "right"
                            else ft.TextAlign.RIGHT
                        )
                    ),
                    alignment=ft.Alignment.TOP_LEFT,
                    style=ft.TextStyle(
                        size=11,
                        color="#344054"
                    )
                )
            ])

    return ft.Stack(
        width=width,
        height=height,
        controls=[
            ft.Container(
                left=(width - diameter) / 2,
                top=(height - diameter) / 2,
                width=diameter,
                height=diameter,
                content=fch.PieChart(
                    sections=sections,
                    sections_space=1,
                    center_space_radius=0,
                    start_degree_offset=-90,
                    width=diameter,
                    height=diameter
                )
            ),

            cv.Canvas(
                width=width,
                height=height,
                shapes=shapes
            )
        ]
    )

class Storage:
    def __init__(self, path):
        self.path = Path(path)

        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    plan_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    tasks_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '未开始',
                    elapsed REAL NOT NULL DEFAULT 0,
                    started_at REAL,
                    segments_json TEXT NOT NULL DEFAULT '[]',
                    UNIQUE(group_id, plan_date)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER,
                    group_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    seconds REAL NOT NULL,
                    finished_at REAL NOT NULL,
                    reason TEXT NOT NULL,
                    segments_json TEXT NOT NULL
                )
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def unpack(row):
        if row is None:
            return None

        return {
            "id": row[0],
            "group_id": row[1],
            "plan_date": row[2],
            "title": row[3],
            "tasks": decode(row[4], []),
            "status": row[5],
            "elapsed": float(row[6] or 0),
            "started_at": row[7],
            "segments": decode(row[8], []),
        }

    def get(self, plan_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM plans WHERE id=?",
                (plan_id,),
            ).fetchone()

        return self.unpack(row)

    def plans_on(self, day):
        with self.connect() as db:
            rows = db.execute("""
                SELECT *
                FROM plans
                WHERE plan_date=?
                ORDER BY id DESC
            """, (day.isoformat(),)).fetchall()

        return [self.unpack(row) for row in rows]

    def group_count(self, group_id):
        with self.connect() as db:
            count = db.execute("""
                SELECT COUNT(*)
                FROM plans
                WHERE group_id=?
            """, (group_id,)).fetchone()[0]

        return count

    def create(self, title, task_names, start_day, end_day):
        title = title.strip()

        if not title:
            raise ValueError("计划名称不能为空。")

        count = (end_day - start_day).days + 1

        if not 1 <= count <= MAX_DAYS:
            raise ValueError(
                f"日期范围无效，最多安排{MAX_DAYS}天。"
            )

        if len(task_names) > 30:
            raise ValueError("子任务不能超过30项。")

        group_id = uuid.uuid4().hex

        tasks = [
            {"text": text, "done": False}
            for text in task_names
        ]

        tasks_json = json.dumps(
            tasks,
            ensure_ascii=False,
        )

        with self.connect() as db:
            for offset in range(count):
                current = start_day + timedelta(days=offset)

                db.execute("""
                    INSERT INTO plans (
                        group_id,
                        plan_date,
                        title,
                        tasks_json,
                        status,
                        elapsed,
                        started_at,
                        segments_json
                    )
                    VALUES (
                        ?, ?, ?, ?, '未开始', 0, NULL, '[]'
                    )
                """, (
                    group_id,
                    current.isoformat(),
                    title,
                    tasks_json,
                ))

        return count

    def edit_one(self, plan_id, title, task_names):
        plan = self.get(plan_id)

        if plan is None:
            raise ValueError("计划不存在。")

        if not title.strip():
            raise ValueError("计划名称不能为空。")

        if len(task_names) > 30:
            raise ValueError("子任务不能超过30项。")

        checked_names = {
            task["text"]
            for task in plan["tasks"]
            if task.get("done", False)
        }

        tasks = [
            {
                "text": text,
                "done": text in checked_names,
            }
            for text in task_names
        ]

        with self.connect() as db:
            db.execute("""
                UPDATE plans
                SET title=?, tasks_json=?
                WHERE id=?
            """, (
                title.strip(),
                json.dumps(tasks, ensure_ascii=False),
                plan_id,
            ))

    def check_task(self, plan_id, index, checked):
        with self.connect() as db:
            result = db.execute("""
                SELECT tasks_json
                FROM plans
                WHERE id=?
            """, (plan_id,)).fetchone()

            if result is None:
                return

            tasks = decode(result[0], [])

            if not 0 <= index < len(tasks):
                return

            tasks[index]["done"] = bool(checked)

            db.execute("""
                UPDATE plans
                SET tasks_json=?
                WHERE id=?
            """, (
                json.dumps(tasks, ensure_ascii=False),
                plan_id,
            ))

    def active(self):
        with self.connect() as db:
            row = db.execute("""
                SELECT *
                FROM plans
                WHERE status IN ('学习中', '已暂停')
                LIMIT 1
            """).fetchone()

        return self.unpack(row)

    def start(self, plan_id):
        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None:
                raise ValueError("计划不存在。")

            # 防止提前开始其他日期的计划，
            # 导致计划日期与统计日期不一致。
            today = date.today()
            planned_day = date.fromisoformat(
                plan["plan_date"]
            )

            if planned_day != today:
                raise ValueError(
                    f"这个计划安排在 {planned_day.isoformat()}，"
                    f"今天是 {today.isoformat()}。\n"
                    "只能在计划当天开始学习。"
                    "如需今天学习，请新建今天的计划。"
                )

            if plan["status"] not in ("未开始", "已完成"):
                raise ValueError("当前计划不能开始。")

            other = db.execute("""
                SELECT 1
                FROM plans
                WHERE id!=?
                  AND status IN ('学习中', '已暂停')
                LIMIT 1
            """, (plan_id,)).fetchone()

            if other:
                raise ValueError(
                    "请先结束另一项正在计时或暂停的计划。"
                )

            tasks = plan["tasks"]

            if plan["status"] == "已完成":
                tasks = [
                    dict(task, done=False)
                    for task in tasks
                ]

            db.execute("""
                UPDATE plans
                SET status='学习中',
                    elapsed=0,
                    started_at=?,
                    segments_json='[]',
                    tasks_json=?
                WHERE id=?
            """, (
                time.time(),
                json.dumps(tasks, ensure_ascii=False),
                plan_id,
            ))

    @staticmethod
    def stop_interval(plan, now):
        if (
            plan["status"] == "学习中"
            and plan["started_at"] is not None
        ):
            end = max(now, plan["started_at"])

            plan["elapsed"] += (
                end - plan["started_at"]
            )

            plan["segments"].append([
                plan["started_at"],
                end,
            ])

        plan["started_at"] = None

    def pause(self, plan_id):
        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None or plan["status"] != "学习中":
                raise ValueError("当前计划没有在计时。")

            self.stop_interval(plan, time.time())

            db.execute("""
                UPDATE plans
                SET status='已暂停',
                    elapsed=?,
                    started_at=NULL,
                    segments_json=?
                WHERE id=?
            """, (
                plan["elapsed"],
                json.dumps(plan["segments"]),
                plan_id,
            ))

    def resume(self, plan_id):
        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None or plan["status"] != "已暂停":
                raise ValueError("计划不在暂停状态。")

            other = db.execute("""
                SELECT 1
                FROM plans
                WHERE id!=?
                  AND status IN ('学习中', '已暂停')
                LIMIT 1
            """, (plan_id,)).fetchone()

            if other:
                raise ValueError("已有其他计时计划。")

            db.execute("""
                UPDATE plans
                SET status='学习中',
                    started_at=?
                WHERE id=?
            """, (time.time(), plan_id))

    def write_record(self, db, plan, reason, now):
        db.execute("""
            INSERT INTO records (
                plan_id,
                group_id,
                title,
                seconds,
                finished_at,
                reason,
                segments_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            plan["id"],
            plan["group_id"],
            plan["title"],
            plan["elapsed"],
            now,
            reason,
            json.dumps(plan["segments"]),
        ))

    def finish(self, plan_id):
        now = time.time()

        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None or plan["status"] not in (
                "学习中",
                "已暂停",
            ):
                raise ValueError("计划尚未开始或已经结束。")

            self.stop_interval(plan, now)

            self.write_record(
                db,
                plan,
                "完成计划",
                now,
            )

            db.execute("""
                UPDATE plans
                SET status='已完成',
                    elapsed=?,
                    started_at=NULL,
                    segments_json=?
                WHERE id=?
            """, (
                plan["elapsed"],
                json.dumps(plan["segments"]),
                plan_id,
            ))

        return plan["elapsed"]

    def delete(self, plan_id, all_dates=False):
        now = time.time()

        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None:
                return 0

            if all_dates:
                rows = db.execute("""
                    SELECT *
                    FROM plans
                    WHERE group_id=?
                """, (plan["group_id"],)).fetchall()

            else:
                rows = [
                    db.execute(
                        "SELECT * FROM plans WHERE id=?",
                        (plan_id,),
                    ).fetchone()
                ]

            items = [
                self.unpack(row)
                for row in rows
                if row is not None
            ]

            for item in items:
                if item["status"] in ("学习中", "已暂停"):
                    self.stop_interval(item, now)

                    self.write_record(
                        db,
                        item,
                        "删除时结束",
                        now,
                    )

            if all_dates:
                db.execute("""
                    DELETE FROM plans
                    WHERE group_id=?
                """, (plan["group_id"],))

            else:
                db.execute("""
                    DELETE FROM plans
                    WHERE id=?
                """, (plan_id,))

        return len(items)

    def recover(self, plan_id, include_gap):
        now = time.time()

        with self.connect() as db:
            plan = self.unpack(
                db.execute(
                    "SELECT * FROM plans WHERE id=?",
                    (plan_id,),
                ).fetchone()
            )

            if plan is None or plan["status"] != "学习中":
                return

            if include_gap:
                self.stop_interval(plan, now)

                db.execute("""
                    UPDATE plans
                    SET elapsed=?,
                        segments_json=?,
                        started_at=?
                    WHERE id=?
                """, (
                    plan["elapsed"],
                    json.dumps(plan["segments"]),
                    now,
                    plan_id,
                ))

            else:
                db.execute("""
                    UPDATE plans
                    SET status='已暂停',
                        started_at=NULL
                    WHERE id=?
                """, (plan_id,))

    def studied_days(self):
        # 与统计饼图、学习记录使用同一个整数秒计算函数。
        totals = defaultdict(int)
        with self.connect() as db:
            rows = db.execute("""
                SELECT seconds, finished_at, segments_json FROM records
            """).fetchall()
        for seconds, finished_at, segments_json in rows:
            for day, amount in record_seconds_by_day(
                seconds, finished_at, segments_json
            ).items():
                totals[day] += amount
        return totals


def main(page: ft.Page):
    page.title = "简学 · FocusPlan"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = PAGE_BG
    page.padding = 16

    directory = Path(
        os.getenv("FLET_APP_STORAGE_DATA")
        or Path(__file__).resolve().parent / "data"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 沿用上个日期范围版本的数据
    store = Storage(
        directory / "focusplan_range.db"
    )

    selected_day = date.today()
    visible_month = selected_day.replace(day=1)
    calendar_open = False
    stat_mode = "day"
    expanded_home_plans = set()
    swiped_home_plans = set()
    swipe_drag_distance = {}
    home_front_cards = {}  # Only currently rendered foreground cards.
    record_bulk_mode = False
    selected_record_ids = set()

    # S9.3 保留真实 View 页面栈：Android 返回键/边缘手势。
    body = None
    screen_stack = []  # (screen_key, body)
    page.views.clear()

    def bottom_navigation(selected):
        indexes = {"home": 0, "calendar": 1, "settings": 2}

        def change_tab(e):
            # The bar itself can update selection before page navigation.
            # Destination view must explicitly restore its own selection.
            index = e.control.selected_index
            if index == 0:
                show_home()
            elif index == 1:
                show_calendar()
            else:
                show_settings()

        return ft.NavigationBar(
            selected_index=indexes[selected],
            bgcolor="#FFFFFF",
            indicator_color="#E0EDFF",
            on_change=change_tab,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME,
                    label="首页",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.PIE_CHART_OUTLINE,
                    selected_icon=ft.Icons.PIE_CHART,
                    label="统计",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="设置",
                ),
            ],
        )

    def sync_current_nav():
        """Keep the selected bottom tab consistent when Android pops a View."""
        if not screen_stack or not page.views:
            return
        active = screen_stack[-1][0][0]
        if active in ("home", "calendar", "settings"):
            # A new NavigationBar instance resets stale client-side selection.
            page.views[-1].navigation_bar = bottom_navigation(active)

    def activate_screen(key):
        nonlocal body
        existing = next(
            (i for i in range(len(screen_stack) - 1, -1, -1)
             if screen_stack[i][0] == key),
            None,
        )
        if existing is not None:
            while len(screen_stack) > existing + 1:
                screen_stack.pop()
                page.views.pop()
            body = screen_stack[-1][1]
            sync_current_nav()
            return

        body = ft.Column(
            spacing=14,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        route = "/" if key == ("home",) else "/" + "/".join(map(str, key))
        view = ft.View(
            route=route,
            bgcolor=PAGE_BG,
            padding=16,
            can_pop=bool(screen_stack),
            controls=[ft.SafeArea(content=body, expand=True)],
        )
        page.views.append(view)
        screen_stack.append((key, body))
        sync_current_nav()

    def on_android_back(e):
        nonlocal body
        if len(screen_stack) <= 1:
            return
        page.views.pop()
        screen_stack.pop()
        key, body = screen_stack[-1]
        sync_current_nav()
        if key[0] == "home":
            show_home()
        elif key[0] == "calendar":
            show_calendar()
        elif key[0] == "settings":
            show_settings()
        elif key[0] == "detail":
            show_detail(key[1], key[2])
        else:
            # Return to an editor without discarding its input fields.
            page.update()

    page.on_view_pop = on_android_back

    def alert(title, message):
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Text(message),
                actions=[
                    ft.TextButton(
                        "知道了",
                        on_click=lambda e: page.pop_dialog(),
                    )
                ],
            )
        )

    def navigation():
        # The two main pages now share the bottom navigation bar.
        return ft.Container(height=0)

    def go_back(source):
        if source == "home":
            show_home()
        else:
            show_calendar()

    def plan_card(plan, source):
        return ft.Container(
            bgcolor="#FFFFFF",
            padding=18,
            border_radius=15,
            on_click=lambda e: show_detail(
                plan["id"],
                source,
            ),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                plan["title"],
                                size=19,
                                expand=True,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "✓"
                                if plan["status"] == "已完成"
                                else "",
                                size=24,
                                color="#16A34A",
                            ),
                        ]
                    ),
                    ft.Text(
                        plan["status"]
                        if plan["status"] in (
                            "学习中",
                            "已暂停",
                        )
                        else "查看详情 →",
                        size=13,
                        color="#667085",
                    ),
                ],
            ),
        )

    # S9.5：首页卡片保持轻量。所有展开/滑动状态只在内存里，
    # 不影响数据库和第二页。
    def classify_plan(title, index):
        name = title.lower()
        if any(k in name for k in ("英语", "单词", "阅读", "english", "词汇", "背诵")):
            return ft.Icons.MENU_BOOK_OUTLINED, "#2475DB", "#E8F2FF"
        if any(k in name for k in ("代码", "编程", "python", "算法", "项目", "java", "开发")):
            return ft.Icons.CODE, "#DE7337", "#FFF0E5"
        if any(k in name for k in ("运动", "跑步", "健身", "体能", "锻炼")):
            return ft.Icons.DIRECTIONS_RUN, "#805BD0", "#F1EAFE"
        palette = [
            (ft.Icons.BOOK_OUTLINED, "#2475DB", "#E8F2FF"),
            (ft.Icons.LAPTOP, "#DE7337", "#FFF0E5"),
            (ft.Icons.LIGHTBULB_OUTLINE, "#805BD0", "#F1EAFE"),
        ]
        return palette[index % len(palette)]

    def home_task_changed(plan_id, index, checked):
        store.check_task(plan_id, index, checked)
        show_home()

    def home_start(plan):
        if plan["status"] == "学习中":
            show_detail(plan["id"], "home")
        else:
            action = "resume" if plan["status"] == "已暂停" else "start"
            do_action(plan["id"], "home", action)

    def toggle_home_tasks(plan_id):
        if plan_id in expanded_home_plans:
            expanded_home_plans.remove(plan_id)
        else:
            expanded_home_plans.add(plan_id)
        show_home()

    # S9.9: 整张卡片统一识别横向滑动，不在拖动期间刷新布局。
    # drag_interval 限制发送到 Python 的事件频率；松手后原生动画滑开。
    # 手势层不绑定 on_tap，避免抢子任务、展开箭头和开始按钮的点击。
    HOME_ACTION_WIDTH = 207

    def on_home_swipe_start(e, plan_id):
        swipe_drag_distance[plan_id] = 0.0

    def on_home_swipe_update(e, plan_id):
        delta = getattr(getattr(e, "local_delta", None), "x", 0) or 0
        # 只累计滑动距离，不在这里调用 update()。
        swipe_drag_distance[plan_id] = (
            swipe_drag_distance.get(plan_id, 0.0) + float(delta)
        )

    def on_home_swipe_end(e, plan_id, card_width):
        movement = swipe_drag_distance.pop(plan_id, 0.0)
        velocity = getattr(e, "primary_velocity", 0) or 0
        was_open = plan_id in swiped_home_plans

        # 短距离快速滑动也能打开；轻微触碰不误操作。
        if movement <= -27 or velocity <= -500:
            should_open = True
        elif movement >= 27 or velocity >= 500:
            should_open = False
        else:
            # 点按或很小的晃动不改变当前展开状态。
            return

        old_open = list(swiped_home_plans)
        swiped_home_plans.clear()
        if should_open:
            swiped_home_plans.add(plan_id)

        # 切换时把原先已展开的另一张卡片收回。
        for other_id in old_open:
            if other_id != plan_id:
                other = home_front_cards.get(other_id)
                if other is not None:
                    other.offset = ft.Offset(0, 0)
                    other.update()

        foreground = home_front_cards.get(plan_id)
        if foreground is not None:
            foreground.offset = ft.Offset(
                -HOME_ACTION_WIDTH / card_width if should_open else 0,
                0,
            )
            foreground.update()

    def on_home_swipe_cancel(e, plan_id):
        swipe_drag_distance.pop(plan_id, None)

    def home_plan_card(plan, index):
        plan_id = plan["id"]
        status = plan["status"]
        items = plan["tasks"]
        icon_name, accent, icon_bg = classify_plan(plan["title"], index)
        expanded = plan_id in expanded_home_plans
        swiped = plan_id in swiped_home_plans

        # 标题保持点击展开；横向滑动由下方整卡手势层统一处理。
        card_width = min(480.0, max(240.0, float(page.width or 390) - 32))

        drag_title = ft.Container(
            on_click=lambda e, pid=plan_id: toggle_home_tasks(pid),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=35, height=35, bgcolor=icon_bg,
                        border_radius=11, alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon_name, size=19, color=accent),
                    ),
                    ft.Text(
                        plan["title"], size=16, weight=ft.FontWeight.BOLD,
                        color=NAVY, max_lines=2, expand=True,
                    ),
                ],
            ),
        )

        heading = ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(content=drag_title, expand=True),
                ft.IconButton(
                    icon=(ft.Icons.KEYBOARD_ARROW_UP if expanded
                          else ft.Icons.KEYBOARD_ARROW_DOWN),
                    icon_color=MUTED,
                    tooltip="收起子任务" if expanded else "展开子任务",
                    on_click=lambda e, pid=plan_id: toggle_home_tasks(pid),
                ),
            ],
        )

        card_contents = [heading]
        if expanded:
            if items:
                children = [
                    ft.Checkbox(
                        label=item.get("text", ""),
                        value=bool(item.get("done")),
                        active_color=accent,
                        on_change=lambda e, pid=plan_id, idx=i:
                            home_task_changed(pid, idx, bool(e.control.value)),
                    )
                    for i, item in enumerate(items)
                ]
            else:
                children = [ft.Text("当前暂无子任务", size=13, color=MUTED)]
            card_contents.append(
                ft.Container(
                    padding=6,
                    content=ft.Column(spacing=1, controls=children),
                )
            )

        if status == "已完成":
            # Completed cards show one check on the right, never '再次学习'.
            action = ft.Row(
                tight=True, spacing=4,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color="#25825B"),
                    ft.Text("已完成", size=13, color="#25825B", weight=ft.FontWeight.BOLD),
                ],
            )
        else:
            if status == "未开始":
                label = "开始计划"
                button_icon = ft.Icons.PLAY_ARROW
            elif status == "已暂停":
                label = "继续学习"
                button_icon = ft.Icons.PLAY_ARROW
            else:
                label = "学习中 · 查看"
                button_icon = ft.Icons.ARROW_FORWARD
            action = ft.Container(
                bgcolor="#EDF4FF", border_radius=10, padding=10,
                on_click=lambda e, p=plan: home_start(p),
                content=ft.Row(
                    tight=True, spacing=5,
                    controls=[
                        ft.Icon(button_icon, size=16, color=PRIMARY),
                        ft.Text(label, size=13, color=PRIMARY,
                                weight=ft.FontWeight.BOLD),
                    ],
                ),
            )

        card_contents.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[action],
            )
        )

        # 宽度固定在卡片内部；Stack 根据前景卡片自然高度调整。
        # 右侧三个操作始终位于卡片“背面”，不会跑到下方。
        reveal_width = HOME_ACTION_WIDTH

        def option_button(label, icon, callback, color, bg):
            return ft.Container(
                width=62,
                bgcolor=bg,
                border_radius=13,
                on_click=callback,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    spacing=7,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=38, height=38, border_radius=20,
                            bgcolor="#FFFFFF",
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(icon, color=color, size=20),
                        ),
                        ft.Text(label, size=11, color=color,
                                text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )

        actions_behind = ft.Container(
            right=0, top=0, bottom=0,
            width=reveal_width,
            bgcolor="#F4F6FA",
            border_radius=15,
            padding=4,
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    option_button(
                        "详情", ft.Icons.INFO_OUTLINE,
                        lambda e, pid=plan_id: show_detail(pid, "home"),
                        PRIMARY, "#EAF1FD",
                    ),
                    option_button(
                        "修改", ft.Icons.EDIT_OUTLINED,
                        lambda e, pid=plan_id: show_edit(pid, "home"),
                        "#B46C28", "#FFF2E7",
                    ),
                    option_button(
                        "删除", ft.Icons.DELETE_OUTLINE,
                        lambda e, pid=plan_id: show_delete(pid, "home"),
                        "#BC4242", "#FFF0EF",
                    ),
                ],
            ),
        )

        # 整卡在外层偏移动画中滑动；手势检测器跟着卡片一起移动。
        # 露出右侧按钮后，手势层不会固定盖在按钮上方。
        card_face = ft.Container(
            width=card_width,
            bgcolor="#FFFFFF", padding=14, border_radius=15,
            content=ft.Column(spacing=10, controls=card_contents),
        )
        swipe_surface = ft.GestureDetector(
            drag_interval=80,
            on_horizontal_drag_start=lambda e, pid=plan_id:
                on_home_swipe_start(e, pid),
            on_horizontal_drag_update=lambda e, pid=plan_id:
                on_home_swipe_update(e, pid),
            on_horizontal_drag_end=lambda e, pid=plan_id, w=card_width:
                on_home_swipe_end(e, pid, w),
            on_horizontal_drag_cancel=lambda e, pid=plan_id:
                on_home_swipe_cancel(e, pid),
            content=card_face,
        )
        foreground_card = ft.Container(
            width=card_width,
            offset=ft.Offset(-reveal_width / card_width if swiped else 0, 0),
            animate_offset=ft.Animation(165, ft.AnimationCurve.EASE_OUT_CUBIC),
            content=swipe_surface,
        )
        home_front_cards[plan_id] = foreground_card
        return ft.Stack(
            width=card_width,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            controls=[actions_behind, foreground_card],
        )

    def open_calendar_shortcut():
        nonlocal calendar_open
        calendar_open = True
        show_calendar()

    def open_records_shortcut():
        show_calendar()
        show_record_details()

    def about_app():
        alert(
            "关于 FocusPlan",
            "简学 · FocusPlan\n个人学习计划与专注记录应用。\n"
            "学习记录仅保存在当前设备的本地数据库，"
            "不会自动与电脑或其他手机同步。",
        )

    def more_menu():
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            icon_color=NAVY,
            tooltip="更多功能",
            items=[
                ft.PopupMenuItem(
                    content="学习记录",
                    on_click=lambda e: open_records_shortcut(),
                ),
                ft.PopupMenuItem(
                    content="设置",
                    on_click=lambda e: show_settings(),
                ),
                ft.PopupMenuItem(
                    content="关于应用",
                    on_click=lambda e: about_app(),
                ),
            ],
        )

    def show_home():
        activate_screen(("home",))
        home_front_cards.clear()
        today = date.today()
        plans = store.plans_on(today)
        completed = sum(p["status"] == "已完成" for p in plans)

        header = ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "FocusPlan",
                    size=25, weight=ft.FontWeight.BOLD,
                    color=NAVY, expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                    icon_color=NAVY,
                    tooltip="打开日历",
                    on_click=lambda e: open_calendar_shortcut(),
                ),
                more_menu(),
            ],
        )

        create_button = ft.Container(
            bgcolor=PRIMARY, border_radius=14, padding=15,
            on_click=lambda e: show_create("home"),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER, spacing=8,
                controls=[
                    ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, color="#FFFFFF", size=22),
                    ft.Text(
                        "新建计划", size=16, color="#FFFFFF",
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
            ),
        )

        section_title = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text("今日计划", size=19, color=NAVY, weight=ft.FontWeight.BOLD),
                ft.Text(f"{len(plans)} 个 · 已完成 {completed}", color=MUTED, size=12),
            ],
        )

        content = [
            header,
            create_button,
            section_title,
        ]
        if plans:
            content.extend(home_plan_card(p, i) for i, p in enumerate(plans))
        else:
            content.append(
                ft.Container(
                    padding=28, bgcolor="#FFFFFF", border_radius=16,
                    content=ft.Column(
                        spacing=9,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.EVENT_NOTE, size=37, color="#92ACCF"),
                            ft.Text("今天还没有计划", size=16, color=NAVY),
                            ft.Text(
                                "点击上方「新建计划」开始安排今天",
                                size=12, color=MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                    ),
                )
            )

        # 手机全宽、桌面限宽，页面布局与参考图一致。
        viewport = float(page.width or 390)
        usable = min(480, max(240, viewport - 32))
        body.controls = [
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=usable,
                        content=ft.Column(spacing=15, controls=content),
                    ),
                ],
            )
        ]
        page.update()

    def show_settings():
        activate_screen(("settings",))
        body.controls = [
            ft.Text("设置", size=27, color=NAVY, weight=ft.FontWeight.BOLD),
            ft.Container(
                bgcolor="#FFFFFF", padding=18, border_radius=16,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Text("FocusPlan", size=18, weight=ft.FontWeight.BOLD, color=NAVY),
                        ft.Text(
                            "当前版本包含学习计划、计时、日历和统计。"
                            "更多个性化设置暂未开放。",
                            size=13, color=MUTED,
                        ),
                        ft.Divider(),
                        ft.Text("数据说明", size=16, color=NAVY, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "你的学习记录存放在此设备本地，"
                            "卸载应用可能清除数据。不要卸载旧版后再安装新版。",
                            color=MUTED, size=13,
                        ),
                        ft.Button("关于应用", on_click=lambda e: about_app()),
                    ],
                ),
            ),
        ]
        page.update()

    # 第二页恢复为之前的展开日历布局
    def select_date(day):
        nonlocal selected_day, visible_month, calendar_open

        selected_day = day
        visible_month = day.replace(day=1)
        calendar_open = False

        show_calendar()

    def change_month(offset):
        nonlocal visible_month

        index = (
            visible_month.year * 12
            + visible_month.month
            - 1
            + offset
        )

        year, month_index = divmod(index, 12)

        if 1 <= year <= 9999:
            visible_month = date(
                year,
                month_index + 1,
                1,
            )

        show_calendar()

    def toggle_calendar():
        nonlocal calendar_open

        calendar_open = not calendar_open
        show_calendar()

    def calendar_panel(studied):
        # S8.2：按手机可用宽度计算七列尺寸，不再固定为 39 像素。
        # page 左右各 16、日历卡片左右各 12、六处间距各 3。
        viewport = float(page.width or 390)
        cell_width = max(24, min(47, (viewport - 32 - 24 - 18) / 7))
        cell_height = 40 if cell_width >= 37 else 36

        rows = [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Button(
                        "‹",
                        on_click=lambda e: change_month(-1),
                    ),
                    ft.Text(
                        f"{visible_month.year}年"
                        f"{visible_month.month}月",
                        size=17,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Button(
                        "›",
                        on_click=lambda e: change_month(1),
                    ),
                ],
            ),

            ft.Row(
                spacing=3,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=cell_width,
                        content=ft.Text(
                            "周" + name,
                            size=12,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    )
                    for name in WEEK
                ],
            ),
        ]

        weeks = calendar.monthcalendar(
            visible_month.year,
            visible_month.month,
        )

        for week in weeks:
            cells = []

            for number in week:
                if not number:
                    cells.append(
                        ft.Container(
                            width=cell_width,
                            height=cell_height,
                        )
                    )
                    continue

                day = date(
                    visible_month.year,
                    visible_month.month,
                    number,
                )

                seconds = studied.get(day, 0)

                if day == selected_day:
                    color = "#2563EB"
                elif seconds >= 7200:
                    color = "#15803D"
                elif seconds >= 3600:
                    color = "#22C55E"
                elif seconds > 0:
                    color = "#86EFAC"
                else:
                    color = "#F1F5F9"

                cells.append(
                    ft.Container(
                        width=cell_width,
                        height=cell_height,
                        bgcolor=color,
                        border_radius=7,
                        tooltip=(
                            f"{day.isoformat()} · "
                            f"{format_time(seconds)}"
                        ),
                        content=ft.Column(
                            tight=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    str(number),
                                    size=13,
                                    color=(
                                        "#FFFFFF"
                                        if day == selected_day
                                        else "#183B2C"
                                    ),
                                )
                            ],
                        ),
                        on_click=lambda e, d=day: select_date(d),
                    )
                )

            rows.append(
                ft.Row(
                    spacing=3,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=cells,
                )
            )

        rows.append(
            ft.Text(
                "绿色：有学习记录 · 蓝色：选中日期",
                size=12,
                color="#667085",
            )
        )

        return ft.Container(
            bgcolor="#FFFFFF",
            padding=12,
            border_radius=14,
            content=ft.Column(
                spacing=6,
                controls=rows,
            ),
        )



    def show_calendar():
        activate_screen(("calendar",))
        nonlocal stat_mode

        studied = store.studied_days()
        plans = store.plans_on(selected_day)

        # 计算日、周、月范围
        if stat_mode == "day":
            period_start = selected_day
            period_end = selected_day
            period_title = "当日专注"

        elif stat_mode == "week":
            period_start = selected_day - timedelta(
                days=selected_day.weekday()
            )
            period_end = period_start + timedelta(days=6)
            period_title = "本周专注"

        else:
            period_start = selected_day.replace(day=1)

            last_day = calendar.monthrange(
                selected_day.year,
                selected_day.month
            )[1]

            period_end = selected_day.replace(
                day=last_day
            )

            period_title = "本月专注"

        distribution = study_breakdown(
            store.path,
            period_start,
            period_end
        )

        total_seconds = sum(distribution.values())
        has_records = total_seconds > 0

        # 日期标题
        weekday = WEEK[selected_day.weekday()]

        date_title = (
            f"{selected_day.year}年"
            f"{selected_day.month}月"
            f"{selected_day.day}日 星期{weekday}"
        )

        def change_mode(mode):
            nonlocal stat_mode
            stat_mode = mode
            show_calendar()

        mode_buttons = [
            ft.Button(
                name + (" ✓" if stat_mode == value else ""),
                on_click=lambda e, m=value: change_mode(m)
            )
            for value, name in [
                ("day", "日"),
                ("week", "周"),
                ("month", "月")
            ]
        ]

        controls = [
            ft.Text(
                "日期与计划",
                size=29,
                weight=ft.FontWeight.BOLD
            ),

            # 顶部日期下拉
            ft.Container(
                bgcolor="#FFFFFF",
                border_radius=14,
                padding=16,
                on_click=lambda e: toggle_calendar(),
                content=ft.Row(
                    controls=[
                        ft.Text(
                            date_title,
                            expand=True,
                            size=17,
                            weight=ft.FontWeight.BOLD
                        ),
                        ft.Icon(
                            ft.Icons.KEYBOARD_ARROW_UP
                            if calendar_open
                            else ft.Icons.KEYBOARD_ARROW_DOWN
                        )
                    ]
                )
            )
        ]

        # 原月历及绿色深浅不变
        if calendar_open:
            controls.append(
                calendar_panel(studied)
            )

        # 学习时长分布主卡片
        chart_contents = [
            ft.Text(
                "专注时长分布",
                size=19,
                weight=ft.FontWeight.BOLD
            ),

            ft.Row(
                controls=mode_buttons,
                spacing=8
            )
        ]

        if not has_records:
            # 没有数据：显示空状态，不显示0秒
            chart_contents.append(
                ft.Container(
                    height=210,
                    content=ft.Column(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(
                                ft.Icons.PIE_CHART_OUTLINE,
                                size=42,
                                color="#A7B9B1"
                            ),

                            ft.Text(
                                "暂无专注数据",
                                size=17,
                                color="#667085"
                            ),

                            ft.Text(
                                "点击计划中的“开始计划”进行学习，"
                                "完成后即可查看时长分布。",
                                size=12,
                                color="#98A2B3",
                                text_align=ft.TextAlign.CENTER
                            )
                        ]
                    )
                )
            )

        else:
            # 有数据：显示彩色饼图和计划占比
            colors = [
                "#946134",
                "#B18D5C",
                "#D0BA90",
                "#F1DEAD",
                "#C9D8B9",
                "#99C9BD",
                "#8CBEC8"
            ]

            ranking = sorted(
                distribution.items(),
                key=lambda item: item[1],
                reverse=True
            )

            # 计划过多时，把较小部分归入其他
            if len(ranking) > 7:
                ranking = (
                    ranking[:6]
                    + [(
                        "其他计划",
                        sum(v for _, v in ranking[6:])
                    )]
                )

            # 使用每条记录的原始浮点时长，不人为补秒或重新分配。
            chart_sections = []
            legend_rows = []

            for i, (name, seconds) in enumerate(ranking):
                color = colors[i % len(colors)]
                percent = seconds / total_seconds * 100

                short_name = (
                    name[:5] + "…"
                    if len(name) > 6
                    else name
                )


                chart_sections.append(
                    fch.PieChartSection(
                        value=seconds,
                        color=color,
                        radius=85,

                        # 扇形内部仍然显示计划名称
                        title=short_name,
                        title_position=0.55,

                        title_style=ft.TextStyle(
                            size=11,
                            color=(
                                "#FFFFFF"
                                if i < 2
                                else "#344054"
                            ),
                            weight=ft.FontWeight.BOLD
                        )
                    )
                )


                legend_rows.append(
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(
                                width=13,
                                height=13,
                                border_radius=4,
                                bgcolor=color
                            ),

                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text(
                                        name,
                                        size=14
                                    ),

                                    ft.Text(
                                        format_stat_duration(seconds),
                                        size=12,
                                        color="#98A2B3"
                                    )
                                ]
                            ),

                            ft.Text(
                                f"{percent:.1f}%",
                                size=14,
                                color="#667085"
                            )
                        ]
                    )
                )

            total_label = format_stat_duration(total_seconds)


            chart_contents.extend([
                # 饼图：内部名称，外部时长引导线
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        build_labeled_pie(
                            chart_sections,
                            ranking,
                            page.width
                        )
                    ]
                ),

                # 总计：只用一行小字
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "总计 " + total_label,
                            size=14,
                            color="#667085"
                        )
                    ]
                ),

                ft.Divider(),

                # 原有名称、时长、百分比列表不变
                ft.Column(
                    spacing=14,
                    controls=legend_rows
                )
            ])


        controls.append(
            ft.Container(
                bgcolor="#FFFFFF",
                padding=16 if (page.width or 390) < 400 else 20,
                border_radius=16,
                content=ft.Column(
                    spacing=18,
                    controls=chart_contents
                )
            )
        )

        controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Button(
                        "查看学习记录",
                        on_click=lambda e: show_record_details()
                    )
                ]
            )
        )

        # 日期计划仍在下面
        controls.extend([
            ft.Text(
                f"{selected_day.isoformat()} 的学习计划",
                size=19,
                weight=ft.FontWeight.BOLD
            ),

            ft.Button(
                "＋ 为这一天新建计划",
                on_click=lambda e: show_create("calendar")
            )
        ])

        if not plans:
            controls.append(
                ft.Text(
                    "这一天还没有计划。",
                    color="#667085"
                )
            )

        controls.extend(
            plan_card(plan, "calendar")
            for plan in plans
        )

        body.controls = controls
        page.update()

    def delete_learning_record(record_id):
        """只删除指定的一条学习记录，不删除计划卡片。"""

        def confirm(e):
            try:
                with store.connect() as db:
                    db.execute(
                        "DELETE FROM records WHERE id=?",
                        (record_id,)
                    )
            except sqlite3.Error as exc:
                page.pop_dialog()
                alert("删除失败", str(exc))
                return

            page.pop_dialog()

            # 刷新学习记录页面
            show_record_details()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("删除学习记录？"),
                content=ft.Text(
                    "删除后，这次学习的时长将从"
                    "日、周、月统计和饼图中移除。"
                    "此操作不可撤销。"
                ),
                actions=[
                    ft.TextButton(
                        "取消",
                        on_click=lambda e: page.pop_dialog()
                    ),
                    ft.TextButton(
                        "确认删除",
                        on_click=confirm
                    )
                ]
            )
        )

    def set_record_bulk_mode(enabled):
        nonlocal record_bulk_mode
        record_bulk_mode = bool(enabled)
        selected_record_ids.clear()
        show_record_details()

    def toggle_record_selected(record_id, checked):
        if checked:
            selected_record_ids.add(record_id)
        else:
            selected_record_ids.discard(record_id)
        show_record_details()

    def toggle_all_visible_records(visible_ids):
        if visible_ids and visible_ids.issubset(selected_record_ids):
            selected_record_ids.difference_update(visible_ids)
        else:
            selected_record_ids.update(visible_ids)
        show_record_details()

    def confirm_bulk_delete(visible_ids):
        # 只允许删除当前日／周／月范围内已经勾选的记录。
        delete_ids = sorted(selected_record_ids.intersection(visible_ids))
        if not delete_ids:
            alert("请选择记录", "请先勾选需要删除的学习记录。")
            return

        confirmed = False

        def delete_selected(e):
            nonlocal confirmed, record_bulk_mode
            if confirmed:
                return
            confirmed = True
            try:
                # 使用同一事务；任一失败都不会只删掉一部分。
                with store.connect() as db:
                    db.executemany(
                        "DELETE FROM records WHERE id=?",
                        [(record_id,) for record_id in delete_ids],
                    )
            except sqlite3.Error as exc:
                confirmed = False
                page.pop_dialog()
                alert("删除失败", str(exc))
                return

            page.pop_dialog()
            selected_record_ids.clear()
            record_bulk_mode = False
            show_record_details()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"删除已选的 {len(delete_ids)} 条学习记录？"),
                content=ft.Text(
                    "删除后对应学习时长会从日／周／月统计及饼图中移除。"
                    "若记录跨越多天，会删除整条记录。"
                    "计划卡片不会被删除，此操作不可撤销。"
                ),
                actions=[
                    ft.TextButton(
                        "取消", on_click=lambda e: page.pop_dialog()
                    ),
                    ft.TextButton("确认删除", on_click=delete_selected),
                ],
            )
        )

    def show_record_details():
        nonlocal record_bulk_mode
        if not screen_stack or screen_stack[-1][0] != ("records",):
            record_bulk_mode = False
            selected_record_ids.clear()
        activate_screen(("records",))
        # 读取当前日、周、月范围
        if stat_mode == "day":
            begin = selected_day
            end = selected_day

        elif stat_mode == "week":
            begin = selected_day - timedelta(
                days=selected_day.weekday()
            )
            end = begin + timedelta(days=6)

        else:
            begin = selected_day.replace(day=1)

            last_day = calendar.monthrange(
                selected_day.year,
                selected_day.month
            )[1]

            end = selected_day.replace(day=last_day)

        records = load_learning_records(
            store.path,
            begin,
            end
        )

        visible_ids = {record["id"] for record in records}
        selected_record_ids.intersection_update(visible_ids)

        controls = [
            ft.Button(
                "← 返回统计",
                on_click=lambda e: show_calendar()
            ),
            ft.Row(
                controls=[
                    ft.Text(
                        "学习记录", size=28,
                        weight=ft.FontWeight.BOLD, expand=True,
                    ),
                    ft.TextButton(
                        "取消批量" if record_bulk_mode else "批量删除",
                        on_click=lambda e: set_record_bulk_mode(
                            not record_bulk_mode
                        ),
                    ),
                ],
            ),
            ft.Text(
                begin.isoformat()
                if begin == end
                else (
                        begin.isoformat()
                        + " 至 "
                        + end.isoformat()
                ),
                color="#667085",
                size=14
            )
        ]

        if not records:
            controls.append(
                ft.Container(
                    height=200,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        "暂无学习记录",
                        size=16,
                        color="#98A2B3"
                    )
                )
            )

        else:
            if record_bulk_mode:
                controls.append(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.TextButton(
                                "取消全选" if visible_ids.issubset(selected_record_ids)
                                else "全选",
                                on_click=lambda e, ids=visible_ids:
                                    toggle_all_visible_records(ids),
                            ),
                            ft.Button(
                                f"删除已选（{len(selected_record_ids)}）",
                                disabled=not selected_record_ids,
                                on_click=lambda e, ids=visible_ids:
                                    confirm_bulk_delete(ids),
                            ),
                        ],
                    )
                )

            for record in records:
                controls.append(
                    ft.Container(
                        bgcolor="#FFFFFF",
                        padding=18,
                        border_radius=15,
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                ft.Row(
                                    controls=(
                                        ([ft.Checkbox(
                                            value=record["id"] in selected_record_ids,
                                            on_change=lambda e, rid=record["id"]:
                                                toggle_record_selected(
                                                    rid, bool(e.control.value)
                                                ),
                                        )] if record_bulk_mode else [])
                                        + [
                                        ft.Text(
                                            record["title"],
                                            size=18,
                                            expand=True,
                                            weight=ft.FontWeight.BOLD
                                        ),
                                        ft.Text(
                                            format_stat_duration(
                                                record["seconds"]
                                            ),
                                            color="#43826B",
                                            weight=ft.FontWeight.BOLD
                                        )
                                    ]
                                    )
                                ),
                                ft.Text(
                                    record["time_range"],
                                    size=13,
                                    color="#667085"
                                ),
                                ft.TextButton(
                                    "删除这条记录",
                                    on_click=lambda e, rid=record["id"]:
                                    delete_learning_record(rid)
                                )
                            ]
                        )
                    )
                )

        body.controls = controls
        page.update()

    # 新建计划：默认仅当天
    def show_create(source):
        activate_screen(("create", source))
        nonlocal selected_day

        default_day = (
            date.today()
            if source == "home"
            else selected_day
        )

        start_day = default_day
        end_day = default_day + timedelta(days=6)

        title = ft.TextField(
            label="计划名称",
            max_length=60,
        )

        tasks = ft.TextField(
            label="子任务（每行一项，可留空）",
            multiline=True,
            min_lines=4,
            max_lines=8,
        )

        mode = ft.Dropdown(
            label="安排日期",
            value="single",
            options=[
                ft.DropdownOption(
                    key="single",
                    text="仅当天（默认）",
                ),
                ft.DropdownOption(
                    key="range",
                    text="连续多天",
                ),
            ],
        )

        start_button = ft.Button(
            "开始日期：" + start_day.isoformat()
        )

        end_button = ft.Button(
            "结束日期：" + end_day.isoformat()
        )

        date_panel = ft.Column(
            visible=False,
            spacing=8,
            controls=[
                ft.Text(
                    "点击日期即可选择，无需手动输入。",
                    size=12,
                    color="#667085",
                ),
                start_button,
                end_button,
            ],
        )

        error = ft.Text(color="#D92D20")

        def mode_changed(e):
            date_panel.visible = mode.value == "range"
            page.update()

        mode.on_select = mode_changed

        def start_changed(e):
            nonlocal start_day, end_day

            selected = e.control.value

            start_day = (
                selected.date()
                if isinstance(selected, datetime)
                else selected
            )

            if end_day < start_day:
                end_day = start_day + timedelta(days=1)

            start_button.content = (
                "开始日期：" + start_day.isoformat()
            )

            end_button.content = (
                "结束日期：" + end_day.isoformat()
            )

            page.update()

        def end_changed(e):
            nonlocal end_day

            selected = e.control.value

            end_day = (
                selected.date()
                if isinstance(selected, datetime)
                else selected
            )

            end_button.content = (
                "结束日期：" + end_day.isoformat()
            )

            page.update()

        start_picker = ft.DatePicker(
            value=datetime.combine(
                start_day,
                datetime.min.time(),
            ),
            first_date=datetime(2020, 1, 1),
            last_date=datetime(2040, 12, 31),
            help_text="选择开始日期",
            on_change=start_changed,
        )

        end_picker = ft.DatePicker(
            value=datetime.combine(
                end_day,
                datetime.min.time(),
            ),
            first_date=datetime(2020, 1, 1),
            last_date=datetime(2040, 12, 31),
            help_text="选择结束日期",
            on_change=end_changed,
        )

        start_button.on_click = (
            lambda e: page.show_dialog(start_picker)
        )

        end_button.on_click = (
            lambda e: page.show_dialog(end_picker)
        )

        def submit(e):
            nonlocal selected_day

            name = (title.value or "").strip()

            lines = [
                line.strip()
                for line in (
                    tasks.value or ""
                ).splitlines()
                if line.strip()
            ]

            if not name:
                error.value = "计划名称不能为空。"
                page.update()
                return

            if mode.value == "range":
                first = start_day
                last = end_day
            else:
                first = default_day
                last = default_day

            try:
                count = store.create(
                    name,
                    lines,
                    first,
                    last,
                )

            except (ValueError, sqlite3.Error) as exc:
                error.value = str(exc)
                page.update()
                return

            selected_day = first
            go_back(source)

            alert(
                "创建成功",
                f"已安排 {count} 天。",
            )

        body.controls = [
            ft.Button(
                "← 返回",
                on_click=lambda e: go_back(source),
            ),

            ft.Text(
                "新建计划",
                size=26,
                weight=ft.FontWeight.BOLD,
            ),

            title,
            tasks,
            mode,
            date_panel,
            error,

            ft.Button(
                "保存计划",
                on_click=submit,
            ),
        ]

        page.update()

    # 修改只影响当前卡片
    def show_edit(plan_id, source):
        activate_screen(("edit", plan_id, source))
        plan = store.get(plan_id)

        if plan is None:
            go_back(source)
            return

        title = ft.TextField(
            label="计划名称",
            value=plan["title"],
        )

        tasks = ft.TextField(
            label="子任务（每行一项）",
            value="\n".join(
                task["text"]
                for task in plan["tasks"]
            ),
            multiline=True,
            min_lines=4,
            max_lines=8,
        )

        error = ft.Text(color="#D92D20")

        def submit(e):
            name = (title.value or "").strip()

            lines = [
                line.strip()
                for line in (
                    tasks.value or ""
                ).splitlines()
                if line.strip()
            ]

            try:
                store.edit_one(
                    plan_id,
                    name,
                    lines,
                )
            except (ValueError, sqlite3.Error) as exc:
                error.value = str(exc)
                page.update()
                return

            # Direct edits opened from a swipe return home; edits opened
            # from a detail view return that existing detail view.
            if len(screen_stack) >= 2 and screen_stack[-2][0][0] == "detail":
                show_detail(plan_id, source)
            else:
                go_back(source)

        body.controls = [
            ft.Button(
                "← 返回",
                on_click=lambda e: on_android_back(e) if len(screen_stack) > 1
                else go_back(source),
            ),

            ft.Text(
                "修改计划",
                size=26,
                weight=ft.FontWeight.BOLD,
            ),

            ft.Text(
                "只修改当前日期，其他日期不变。",
                color="#667085",
            ),

            title,
            tasks,
            error,

            ft.Button(
                "保存修改",
                on_click=submit,
            ),
        ]

        page.update()

    # 删除范围按扇贝截图
    def show_delete(plan_id, source):
        plan = store.get(plan_id)

        if plan is None:
            go_back(source)
            return

        count = store.group_count(
            plan["group_id"]
        )

        deleted = False

        def confirm(all_dates):
            nonlocal deleted

            if deleted:
                return

            deleted = True

            try:
                removed = store.delete(
                    plan_id,
                    all_dates,
                )

            except sqlite3.Error as exc:
                deleted = False
                page.pop_dialog()
                alert("删除失败", str(exc))
                return

            page.pop_dialog()
            go_back(source)

            alert(
                "已删除",
                f"删除 {removed} 张计划卡片，"
                "历史学习记录仍然保留。",
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("删除任务"),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text(
                            f"该任务安排在 {count} 个日期，"
                            "请选择删除范围。"
                        ),

                        ft.Button(
                            "仅当天",
                            on_click=lambda e: confirm(False),
                        ),

                        ft.Button(
                            "所有日期",
                            on_click=lambda e: confirm(True),
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton(
                        "取消",
                        on_click=lambda e: page.pop_dialog(),
                    )
                ],
            )
        )

    def do_action(plan_id, source, action):
        try:
            getattr(store, action)(plan_id)

        except (ValueError, sqlite3.Error) as exc:
            alert("操作失败", str(exc))
            return

        show_detail(plan_id, source)

    def show_finish(plan_id, source):
        finished = False

        def confirm(e):
            nonlocal finished

            if finished:
                return

            finished = True

            try:
                seconds = store.finish(plan_id)

            except (ValueError, sqlite3.Error) as exc:
                page.pop_dialog()
                alert("操作失败", str(exc))
                return

            page.pop_dialog()
            show_detail(plan_id, source)

            alert(
                "学习完成",
                "本次学习时长："
                + format_time(seconds),
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("完成计划？"),
                content=ft.Text(
                    "确认后结束计时，并保存学习记录。"
                ),
                actions=[
                    ft.TextButton(
                        "继续学习",
                        on_click=lambda e: page.pop_dialog(),
                    ),

                    ft.TextButton(
                        "确认完成",
                        on_click=confirm,
                    ),
                ],
            )
        )

    # S9.5：详情页只保留标题、状态、子任务和必要操作。
    def show_detail(plan_id, source):
        activate_screen(("detail", plan_id, source))
        plan = store.get(plan_id)
        if plan is None:
            go_back(source)
            return

        status = plan["status"]
        tasks = plan["tasks"]
        status_colors = {
            "未开始": ("#EEF2F8", "#65748B"),
            "学习中": ("#E7F0FF", PRIMARY),
            "已暂停": ("#FFF2E3", "#AF702C"),
            "已完成": ("#E6F5EC", "#25825B"),
        }
        badge_bg, badge_fg = status_colors.get(status, ("#EEF2F8", MUTED))

        def detail_button(label, callback, tone="light"):
            bg = {"primary": PRIMARY, "light": "#EDF3FC", "danger": "#FFF0EE"}[tone]
            fg = {"primary": "#FFFFFF", "light": NAVY, "danger": "#B53B38"}[tone]
            return ft.Container(
                bgcolor=bg, border_radius=11, padding=13,
                on_click=callback,
                content=ft.Text(
                    label, color=fg, size=14,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.BOLD,
                ),
            )

        title_section = ft.Container(
            bgcolor="#FFFFFF", border_radius=15, padding=18,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text(plan["title"], size=23, color=NAVY,
                            weight=ft.FontWeight.BOLD),
                    ft.Row(
                        controls=[
                            ft.Container(
                                bgcolor=badge_bg, border_radius=8, padding=8,
                                content=ft.Text(status, color=badge_fg, size=12),
                            ),
                        ],
                    ),
                ] + ([
                    ft.Text("本次学习时长：" + format_time(plan["elapsed"]),
                            size=13, color=MUTED)
                ] if status == "已完成" else []),
            ),
        )

        checklist = [
            ft.Checkbox(
                label=task.get("text", ""),
                value=bool(task.get("done")),
                active_color=PRIMARY,
                on_change=lambda e, i=index: store.check_task(
                    plan_id, i, bool(e.control.value)
                ),
            ) for index, task in enumerate(tasks)
        ] or [ft.Text("当前暂无子任务", color=MUTED, size=13)]

        task_section = ft.Container(
            bgcolor="#FFFFFF", border_radius=15, padding=18,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Text("子任务", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Divider(color="#EEF1F5"),
                    *checklist,
                ],
            ),
        )

        actions = []
        if status in ("未开始", "已完成"):
            actions.append(detail_button(
                "开始计划" if status == "未开始" else "再次学习",
                lambda e: do_action(plan_id, source, "start"), "primary",
            ))
        elif status == "学习中":
            actions.extend([
                detail_button("暂停", lambda e: do_action(plan_id, source, "pause")),
                detail_button("完成计划", lambda e: show_finish(plan_id, source), "primary"),
            ])
        elif status == "已暂停":
            actions.extend([
                detail_button("继续学习", lambda e: do_action(plan_id, source, "resume"), "primary"),
                detail_button("完成计划", lambda e: show_finish(plan_id, source)),
            ])

        controls = [
            ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=NAVY,
                        tooltip="返回",
                        on_click=lambda e: go_back(source),
                    ),
                    ft.Text("计划详情", size=18, color=NAVY,
                            weight=ft.FontWeight.BOLD),
                ],
            ),
            title_section,
            task_section,
            ft.Row(spacing=10, wrap=True, controls=actions),
            ft.Divider(color="#E7EBF3"),
            ft.Row(
                spacing=10, wrap=True,
                controls=[
                    detail_button("修改计划", lambda e: show_edit(plan_id, source)),
                    detail_button("删除计划", lambda e: show_delete(plan_id, source), "danger"),
                ],
            ),
        ]
        body.controls = controls
        page.update()

    def recovery_dialog(plan):
        resolved = False

        def resolve(include_gap):
            nonlocal resolved

            if resolved:
                return

            resolved = True

            store.recover(
                plan["id"],
                include_gap,
            )

            page.pop_dialog()

            source = (
                "home"
                if plan["plan_date"] == date.today().isoformat()
                else "calendar"
            )

            show_detail(
                plan["id"],
                source,
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("恢复上次计时"),
                content=ft.Text(
                    "只有确认关闭期间确实在学习，"
                    "才计入这段时间。"
                ),
                actions=[
                    ft.TextButton(
                        "保留已有时长并暂停",
                        on_click=lambda e: resolve(False),
                    ),

                    ft.TextButton(
                        "确认一直在学习",
                        on_click=lambda e: resolve(True),
                    ),
                ],
            )
        )

    show_home()

    print(
        "简学数据库：",
        store.path,
    )

    active_plan = store.active()

    if (
        active_plan is not None
        and active_plan["status"] == "学习中"
    ):
        recovery_dialog(active_plan)


if __name__ == "__main__":
    ft.run(main)
