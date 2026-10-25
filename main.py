
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import flet as ft


def duration(seconds):
    seconds = max(0, round(seconds))
    hours, remain = divmod(seconds, 3600)
    minutes, sec = divmod(remain, 60)
    return f"{hours}小时{minutes}分{sec}秒" if hours else f"{minutes}分{sec}秒"


def main(page: ft.Page):
    page.title = "简学 · FocusPlan"
    page.bgcolor = "#F6F8FC"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    # Android 使用 App 私有存储目录
    # PyCharm 直接运行时使用项目下的 data 文件夹
    data_dir = Path(
        os.getenv("FLET_APP_STORAGE_DATA")
        or Path(__file__).parent / "data"
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "focusplan.db"

    def connect():
        return sqlite3.connect(db_path)

    # 初始化数据库
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                tasks_json TEXT NOT NULL,
                status TEXT NOT NULL,
                elapsed REAL NOT NULL,
                started_at REAL,
                segments_json TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                title TEXT NOT NULL,
                seconds REAL NOT NULL,
                finished_at REAL NOT NULL,
                reason TEXT NOT NULL,
                segments_json TEXT NOT NULL
            )
        """)

    # 保存计划
    def save_plan(p):
        values = (
            p["title"],
            json.dumps(p["tasks"], ensure_ascii=False),
            p["status"],
            p["elapsed"],
            p["started_at"],
            json.dumps(p["segments"])
        )

        with connect() as db:
            if p.get("id") is None:
                cur = db.execute("""
                    INSERT INTO plans
                    (title, tasks_json, status, elapsed,
                     started_at, segments_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, values)
                p["id"] = cur.lastrowid

            else:
                db.execute("""
                    UPDATE plans SET
                        title=?,
                        tasks_json=?,
                        status=?,
                        elapsed=?,
                        started_at=?,
                        segments_json=?
                    WHERE id=?
                """, values + (p["id"],))

    # 保存学习记录，并更新或删除计划
    def save_record_and_plan(p, reason, remove=False):
        values = (
            p["id"],
            p["title"],
            p["elapsed"],
            time.time(),
            reason,
            json.dumps(p["segments"])
        )

        with connect() as db:
            db.execute("""
                INSERT INTO records
                (plan_id, title, seconds, finished_at,
                 reason, segments_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, values)

            if remove:
                db.execute(
                    "DELETE FROM plans WHERE id=?",
                    (p["id"],)
                )
            else:
                db.execute("""
                    UPDATE plans SET
                        title=?,
                        tasks_json=?,
                        status=?,
                        elapsed=?,
                        started_at=?,
                        segments_json=?
                    WHERE id=?
                """, (
                    p["title"],
                    json.dumps(p["tasks"], ensure_ascii=False),
                    p["status"],
                    p["elapsed"],
                    p["started_at"],
                    json.dumps(p["segments"]),
                    p["id"]
                ))

    # 启动程序时读取保存的计划
    def load_plans():
        with connect() as db:
            rows = db.execute("""
                SELECT id, title, tasks_json, status,
                       elapsed, started_at, segments_json
                FROM plans
                ORDER BY id
            """).fetchall()

        return [
            dict(
                id=r[0],
                title=r[1],
                tasks=json.loads(r[2]),
                status=r[3],
                elapsed=r[4],
                started_at=r[5],
                segments=json.loads(r[6])
            )
            for r in rows
        ]

    plans = load_plans()

    active = next(
        (
            p for p in plans
            if p["status"] in ("学习中", "已暂停")
        ),
        None
    )

    recovered = (
        active if active and active["status"] == "学习中"
        else None
    )

    body = ft.Column(
        spacing=16,
        expand=True,
        scroll=ft.ScrollMode.AUTO
    )
    page.add(ft.SafeArea(content=body, expand=True))

    def notice(title, message):
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Text(message),
                actions=[
                    ft.TextButton(
                        "知道了",
                        on_click=lambda e: page.pop_dialog()
                    )
                ]
            )
        )

    # 首页
    def show_home():
        controls = [
            ft.Text(
                "简学 · FocusPlan",
                size=15,
                color="#667085"
            ),
            ft.Text(
                "今日计划",
                size=30,
                weight=ft.FontWeight.BOLD
            ),
            ft.Button(
                "＋ 新建计划",
                on_click=lambda e: show_form()
            )
        ]

        if not plans:
            controls.append(
                ft.Text("今天还没有计划，点击上方按钮创建吧。")
            )

        for p in plans:
            controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        p["title"],
                                        size=19,
                                        expand=True,
                                        weight=ft.FontWeight.BOLD
                                    ),
                                    ft.Text(
                                        "✓" if p["status"] == "已完成" else "",
                                        color="#16A34A",
                                        size=24
                                    )
                                ]
                            ),
                            ft.Text(
                                p["status"]
                                if p["status"] in ("学习中", "已暂停")
                                else "点击查看详情 →",
                                color="#667085",
                                size=13
                            )
                        ],
                        spacing=8
                    ),
                    bgcolor="#FFFFFF",
                    padding=20,
                    border_radius=16,
                    on_click=lambda e, item=p: show_detail(item)
                )
            )

        body.controls = controls
        page.update()

    # 创建和修改计划
    def show_form(p=None):
        editing = p is not None

        existing = (
            [dict(t) for t in p["tasks"]]
            if editing else []
        )

        title = ft.TextField(
            label="计划名称",
            value=p["title"] if editing else "",
            max_length=40
        )

        tasks = ft.TextField(
            label="子任务（每行一项）",
            multiline=True,
            min_lines=4,
            max_lines=8,
            value="\n".join(t["text"] for t in existing)
        )

        error = ft.Text(color="#D92D20")

        def save(e):
            name = (title.value or "").strip()
            lines = [
                x.strip()
                for x in (tasks.value or "").splitlines()
                if x.strip()
            ]

            if not name or len(lines) > 30:
                error.value = "名称不能为空，且子任务不能超过30项"
                page.update()
                return

            new_tasks = []

            for i, line in enumerate(lines):
                done = (
                    i < len(existing)
                    and existing[i]["text"] == line
                    and existing[i]["done"]
                )

                new_tasks.append({
                    "text": line,
                    "done": bool(done)
                })

            if editing:
                p["title"] = name
                p["tasks"] = new_tasks
                save_plan(p)

            else:
                item = {
                    "id": None,
                    "title": name,
                    "tasks": new_tasks,
                    "status": "未开始",
                    "elapsed": 0.0,
                    "started_at": None,
                    "segments": []
                }

                save_plan(item)
                plans.append(item)

            show_home()

        body.controls = [
            ft.Button(
                "← 返回",
                on_click=lambda e: (
                    show_detail(p) if editing else show_home()
                )
            ),
            ft.Text(
                "修改计划" if editing else "新建计划",
                size=26,
                weight=ft.FontWeight.BOLD
            ),
            title,
            tasks,
            error,
            ft.Button(
                "保存修改" if editing else "保存计划",
                on_click=save
            )
        ]

        page.update()

    # 结束当前计时段
    def stop_interval(p):
        if (
            p["status"] == "学习中"
            and p["started_at"] is not None
        ):
            end = time.time()
            start = p["started_at"]

            p["elapsed"] += max(0.0, end - start)
            p["segments"].append([start, end])

        p["started_at"] = None

    # 开始学习
    def start(p):
        nonlocal active

        if active is not None:
            notice(
                "已有计时计划",
                "请先完成或删除当前正在计时的计划。"
            )
            return

        p.update(
            status="学习中",
            elapsed=0.0,
            started_at=time.time(),
            segments=[]
        )

        active = p
        save_plan(p)
        show_detail(p)

    # 暂停
    def pause(p):
        if p["status"] != "学习中":
            return

        stop_interval(p)
        p["status"] = "已暂停"

        save_plan(p)
        show_detail(p)

    # 继续
    def resume(p):
        if p["status"] != "已暂停":
            return

        p["started_at"] = time.time()
        p["status"] = "学习中"

        save_plan(p)
        show_detail(p)

    # 完成计划
    def finish(p):
        done = False

        def confirm(e):
            nonlocal active, done

            if done:
                return

            done = True
            stop_interval(p)
            p["status"] = "已完成"

            save_record_and_plan(p, "完成计划")
            active = None

            page.pop_dialog()
            show_detail(p)

            notice(
                "学习完成",
                f"本次学习时长：{duration(p['elapsed'])}"
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("完成计划？"),
                content=ft.Text(
                    "确认后停止计时，并显示学习时长。"
                ),
                actions=[
                    ft.TextButton(
                        "继续学习",
                        on_click=lambda e: page.pop_dialog()
                    ),
                    ft.TextButton(
                        "确认完成",
                        on_click=confirm
                    )
                ]
            )
        )

    # 删除计划
    def delete(p):
        once = False

        def confirm(e):
            nonlocal active, once

            if once:
                return

            once = True

            was_active = p["status"] in (
                "学习中", "已暂停"
            )

            if was_active:
                stop_interval(p)

                save_record_and_plan(
                    p,
                    "删除时结束",
                    remove=True
                )
                active = None

            else:
                # 没开始就删除，不产生学习记录
                with connect() as db:
                    db.execute(
                        "DELETE FROM plans WHERE id=?",
                        (p["id"],)
                    )

            plans.remove(p)

            page.pop_dialog()
            show_home()

            if was_active:
                notice(
                    "已删除",
                    "计时已结束，历史时长已保存。"
                    "统计页会在 S7 加入。"
                )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("删除计划"),
                content=ft.Text(
                    "如已开始计时，会保存本次时长。"
                    "确定删除吗？"
                ),
                actions=[
                    ft.TextButton(
                        "取消",
                        on_click=lambda e: page.pop_dialog()
                    ),
                    ft.TextButton(
                        "确定删除",
                        on_click=confirm
                    )
                ]
            )
        )

    # 已完成的计划可以再次学习
    def again(p):
        if p["status"] != "已完成":
            return

        for t in p["tasks"]:
            t["done"] = False

        start(p)

    # 计划详情
    def show_detail(p):
        status = p["status"]
        options = []

        if status == "未开始":
            options.append(
                ft.Button(
                    "开始计划",
                    on_click=lambda e: start(p)
                )
            )

        elif status == "学习中":
            options += [
                ft.Button(
                    "暂停",
                    on_click=lambda e: pause(p)
                ),
                ft.Button(
                    "完成计划",
                    on_click=lambda e: finish(p)
                )
            ]

        elif status == "已暂停":
            options += [
                ft.Button(
                    "继续学习",
                    on_click=lambda e: resume(p)
                ),
                ft.Button(
                    "完成计划",
                    on_click=lambda e: finish(p)
                )
            ]

        else:
            options.append(
                ft.Button(
                    "再次开始",
                    on_click=lambda e: again(p)
                )
            )

        task_controls = [
            ft.Checkbox(
                label=t["text"],
                value=t["done"],
                on_change=lambda e, task=t: check_task(
                    e, p, task
                )
            )
            for t in p["tasks"]
        ] or [ft.Text("暂无子任务")]

        body.controls = [
            ft.Button(
                "← 返回首页",
                on_click=lambda e: show_home()
            ),
            ft.Text(
                p["title"],
                size=28,
                weight=ft.FontWeight.BOLD
            ),
            ft.Text(
                "状态：" + status,
                color="#2563EB"
            ),
            *(
                [
                    ft.Text(
                        "本次学习时长："
                        + duration(p["elapsed"])
                    )
                ]
                if status == "已完成"
                else []
            ),
            ft.Container(
                content=ft.Column(
                    controls=task_controls,
                    spacing=10
                ),
                bgcolor="#FFFFFF",
                padding=20,
                border_radius=16
            ),
            ft.Row(
                controls=options,
                wrap=True
            ),
            ft.Row(
                controls=[
                    ft.Button(
                        "修改计划",
                        on_click=lambda e: show_form(p)
                    ),
                    ft.Button(
                        "删除计划",
                        on_click=lambda e: delete(p)
                    )
                ],
                wrap=True
            )
        ]

        page.update()

    # 子任务勾选
    def check_task(e, p, t):
        t["done"] = bool(e.control.value)
        save_plan(p)
        page.update()

    # 异常退出后的恢复提示
    def recover(p):

        def continue_counting(e):
            now = time.time()

            # 只有用户确认才补计中断时间
            p["segments"].append([
                p["started_at"], now
            ])

            p["elapsed"] += max(
                0.0,
                now - p["started_at"]
            )

            p["started_at"] = now

            save_plan(p)
            page.pop_dialog()
            show_detail(p)

        def keep_and_pause(e):
            # 不确定的时间不计入
            p["started_at"] = None
            p["status"] = "已暂停"

            save_plan(p)
            page.pop_dialog()
            show_detail(p)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("发现上次未结束的计时"),
                content=ft.Text(
                    "确认这段时间正常学习过，"
                    "可以选择继续累计。"
                    "否则选择暂停，不计入不确定的时间。"
                ),
                actions=[
                    ft.TextButton(
                        "保持已存时长并暂停",
                        on_click=keep_and_pause
                    ),
                    ft.TextButton(
                        "确认时间并继续",
                        on_click=continue_counting
                    )
                ]
            )
        )

    show_home()

    print("简学数据库：", db_path)

    if recovered:
        recover(recovered)


if __name__ == "__main__":
    ft.run(main)
