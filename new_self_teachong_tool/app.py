"""BREW fine-teaching tool (PyQt5). Screens follow mockups/brew-cup-teaching.html:
robot connect → pick motion → teaching (run / step, adjust Hold with 1 mm jog, save, UNHOLD).

Run:  python new_self_teachong_tool/app.py            (on Windows the "가짜 로봇" box starts checked)
Not yet: collision / can't-reach recovery, ICE/COF/POW/PIC, dispensers, BREWX/SLIM.
"""
import ipaddress
import os
import sys
import threading
import traceback

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)

import devices as dv
import motions

LIMIT = 30   # ponytail: one ±mm clamp from the saved Hold, per-point limits once real envelopes are known

QSS = """
QWidget { font-family:'Noto Sans CJK KR','Malgun Gothic',sans-serif; font-size:15px; color:#1f3a30; }
QMainWindow, QDialog, #page { background:#eef2ef; }
QFrame[card="true"] { background:#ffffff; border:1px solid #d3ddd6; border-radius:14px; }
QFrame[card="true"][active="true"] { border:2px solid #1f6a4f; }
QLabel { background:transparent; }
QLabel[sub="true"] { color:#5f7068; font-size:13px; }
QLabel[bad="true"] { color:#a8580f; font-weight:600; }
QLabel[good="true"] { color:#1f6a4f; font-weight:600; }
QPushButton { background:#ffffff; border:1px solid #d3ddd6; border-radius:9px; padding:8px 14px; min-height:26px; }
QPushButton:hover { background:#e1eee5; }
QPushButton:checked, QPushButton[primary="true"] { background:#1f6a4f; color:#ffffff; border-color:#1f6a4f; font-weight:600; }
QPushButton:disabled { color:#a3b0aa; background:#f4f6f5; border-color:#e3e9e5; }
QPushButton:checked:disabled { background:#8fb5a3; color:#ffffff; border-color:#8fb5a3; }
QPushButton#stop { border:2px solid #a8580f; color:#a8580f; font-weight:700; min-width:110px; min-height:40px; }
QPushButton#back { border:2px solid #1f6a4f; color:#1f6a4f; font-weight:600; min-height:44px; }
QPushButton[jog="true"] { min-height:48px; font-size:17px; font-weight:600; }
QLineEdit { background:#ffffff; border:1px solid #d3ddd6; border-radius:9px; padding:6px 10px; min-height:26px; }
QCheckBox { background:transparent; }
"""


class Bus(QObject):
    """Worker threads hand UI work back to the Qt thread through this one signal."""
    call = pyqtSignal(object)


def card():
    f = QFrame()
    f.setProperty("card", True)
    return f


def label(text="", **props):
    w = QLabel(text)
    w.setWordWrap(True)
    for k, v in props.items():
        w.setProperty(k, v)
    return w


def button(text, on=None, **props):
    b = QPushButton(text)
    for k, v in props.items():
        b.setProperty(k, v)
    if on:
        b.clicked.connect(on)
    return b


def restyle(w, **props):
    for k, v in props.items():
        w.setProperty(k, v)
    w.style().unpolish(w)
    w.style().polish(w)


def set_msg(w, text, kind=""):
    w.setText(text)
    restyle(w, bad=kind == "bad", good=kind == "good")


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BREW 미세티칭")
        self.resize(1180, 760)
        self.bus = Bus()
        self.bus.call.connect(lambda fn: fn())
        self.robot = self.store = self.rail = None
        self.hw, self.mode, self.ip, self.fake = "BREW", "NORMAL", "", False
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.connect_page = ConnectPage(self)
        self.teach_page = TeachPage(self)
        self.stack.addWidget(self.connect_page)
        self.stack.addWidget(self.teach_page)

    def ui(self, fn):
        self.bus.call.emit(fn)

    def bg(self, work, done=None, fail=None):
        """Run work() on a thread; done(result) / fail(exc) back on the UI thread."""
        def run():
            try:
                r = work()
            except Exception as e:  # noqa: BLE001 — every failure is shown to the user
                if fail:
                    self.ui(lambda e=e: fail(e))   # bind now: Python clears `e` when the except block ends
                return
            if done:
                self.ui(lambda: done(r))
        threading.Thread(target=run, daemon=True).start()

    def closeEvent(self, e):
        if self.robot:
            self.robot.close()
        super().closeEvent(e)


# ───────────────────────────── ① connect + pick ─────────────────────────────
class ConnectPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("page")
        outer = QHBoxLayout(self)
        outer.addStretch()

        c = card()
        c.setFixedWidth(430)
        v = QVBoxLayout(c)
        v.setContentsMargins(20, 18, 20, 18)
        v.addWidget(label("<b style='letter-spacing:3px'>BARIS</b>"))
        v.addWidget(label("<span style='font-size:19px;font-weight:700'>로봇 연결</span>"))
        v.addWidget(label("① 장비", sub=True))
        row = QHBoxLayout()
        self.hw_btns = []
        for name, ready in (("BREW", True), ("BREWX", False), ("SLIM", False), ("SLIM LEFT", False)):
            b = button(name if ready else f"{name}\n준비 중")
            b.setCheckable(True)
            b.setChecked(name == "BREW")
            b.setEnabled(ready)
            self.hw_btns.append((b, ready))
            row.addWidget(b)
        v.addLayout(row)
        v.addWidget(label("② 동작 모드", sub=True))
        row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        for name in ("NORMAL", "FAST"):
            b = button(name)
            b.setCheckable(True)
            b.setChecked(name == "NORMAL")
            self.mode_group.addButton(b)
            row.addWidget(b)
        v.addLayout(row)
        v.addWidget(label("③ 로봇 IP", sub=True))
        row = QHBoxLayout()
        self.ip = QLineEdit("192.168.0.13")
        self.go = button("연결", self.toggle, primary=True)
        row.addWidget(self.ip, 1)
        row.addWidget(self.go)
        v.addLayout(row)
        self.fake = QCheckBox("가짜 로봇 (로봇 없이 화면만 확인)")
        self.fake.setChecked(os.name == "nt")
        v.addWidget(self.fake)
        v.addWidget(label("연결하면 매장 운영 프로그램의 로봇 제어는 잠시 멈춰요.", sub=True))
        self.msg = label()
        v.addWidget(self.msg)
        v.addStretch()
        outer.addWidget(c)

        self.pick = card()
        self.pick.setFixedWidth(430)
        v = QVBoxLayout(self.pick)
        v.setContentsMargins(20, 18, 20, 18)
        v.addWidget(label("<span style='font-size:19px;font-weight:700'>무엇을 티칭할까요?</span>"))
        grid = QGridLayout()
        self.pick_btns = []
        for i, (key, name, ready) in enumerate((("CUP", "컵", True), ("ICE", "얼음", False), ("COF", "커피", False),
                                               ("POW", "파우더", False), ("PIC", "픽업존", False))):
            b = button(f"{name}\n{'4개' if ready else '준비 중'}", lambda _=False, k=key: self.choose(k))
            b.setMinimumHeight(72)
            b.setStyleSheet("font-size:17px; font-weight:600; text-align:left; padding-left:16px;")
            b.setEnabled(ready)
            self.pick_btns.append((b, ready))
            grid.addWidget(b, i // 2, i % 2)
        v.addLayout(grid)
        v.addWidget(label("BREW는 고르면 레일을 같이 연결해요. 이때 레일 서보가 켜져요.", sub=True))
        self.pick_msg = label()
        v.addWidget(self.pick_msg)
        v.addStretch()
        outer.addWidget(self.pick)
        outer.addStretch()
        self.refresh()

    def refresh(self, busy=False):
        a, on = self.app, self.app.robot is not None
        for b, ready in self.hw_btns:
            b.setEnabled(ready and not on and not busy)
        for b in self.mode_group.buttons():
            b.setEnabled(not on and not busy)
        self.ip.setEnabled(not on and not busy)
        self.fake.setEnabled(not on and not busy)
        self.go.setEnabled(not busy)
        self.go.setText("연결 끊기" if on else "연결")
        restyle(self.go, primary=not on)
        self.pick.setEnabled(on and not busy)
        for b, ready in self.pick_btns:
            b.setEnabled(ready and on and not busy)
        if on:
            set_msg(self.msg, f"로봇 연결됨 · {a.hw} · {a.mode}" + (" · 가짜 로봇" if a.fake else ""), "good")

    def toggle(self):
        a = self.app
        if a.robot:
            a.robot.close()
            a.robot = a.store = a.rail = None
            set_msg(self.msg, "연결을 끊었어요.")
            set_msg(self.pick_msg, "")
            self.refresh()
            return
        ip = self.ip.text().strip()
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            set_msg(self.msg, "IP 형식이 맞지 않아요. 예: 192.168.0.13", "bad")
            return
        a.ip, a.fake, a.mode = ip, self.fake.isChecked(), self.mode_group.checkedButton().text()
        set_msg(self.msg, "로봇에 연결하는 중…")
        self.refresh(busy=True)

        def work():
            robot = dv.Robot.connect(ip, fake=a.fake)
            try:
                store = dv.FakeStore() if a.fake else dv.Store()
            except Exception:
                robot.close()
                raise
            return robot, store

        def done(r):
            a.robot, a.store = r
            self.refresh()

        def fail(e):
            self.refresh()
            set_msg(self.msg, f"연결하지 못했어요. 로봇 전원, 랜선, IP를 확인하고 다시 눌러 주세요.\n({e})", "bad")
        a.bg(work, done, fail)

    def choose(self, dp):
        a = self.app
        if a.hw == "BREW" and a.rail is None:
            set_msg(self.pick_msg, "레일 연결하는 중… (서보가 켜져요)")
            self.refresh(busy=True)

            def done(rail):
                a.rail = rail
                set_msg(self.pick_msg, "")
                self.refresh()
                self.open_teach(dp)

            def fail(e):
                self.refresh()
                set_msg(self.pick_msg, f"레일에 연결하지 못했어요. 레일 전원을 확인하고 다시 눌러 주세요.\n({e})", "bad")
            a.bg(lambda: dv.connect_rail(a.fake), done, fail)
            return
        self.open_teach(dp)

    def open_teach(self, dp):
        self.app.teach_page.enter(dp)
        self.app.stack.setCurrentWidget(self.app.teach_page)


# ───────────────────────────── ② teaching ─────────────────────────────
class TeachPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("page")
        self.n, self.idx, self.busy, self.step_mode, self.target = 1, -1, False, False, None
        self.dlg = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)

        head = QHBoxLayout()
        head.addWidget(label("<b style='letter-spacing:3px'>BARIS BREW</b>"))
        self.title = label()
        self.title.setStyleSheet("font-size:19px; font-weight:700;")
        head.addWidget(self.title)
        self.info = label(sub=True)
        self.info.setWordWrap(False)
        head.addWidget(self.info)
        head.addSpacing(12)
        head.addWidget(label("번호", sub=True))
        self.slot_group = QButtonGroup(self)
        for n in range(1, 5):
            b = button(str(n), lambda _=False, k=n: self.set_slot(k))
            b.setCheckable(True)
            self.slot_group.addButton(b, n)
            head.addWidget(b)
        head.addStretch()
        self.stop_btn = button("■ 정지", self.stop)
        self.stop_btn.setObjectName("stop")
        head.addWidget(self.stop_btn)
        root.addLayout(head)

        body = QHBoxLayout()
        # left: what the robot is doing now (numbers instead of the mockup's drawing)
        now = card()
        nv = QVBoxLayout(now)
        nv.setContentsMargins(24, 20, 24, 20)
        nv.addWidget(label("지금", sub=True))
        self.now_step = label("준비")
        self.now_step.setStyleSheet("font-size:28px; font-weight:700;")
        nv.addWidget(self.now_step)
        nv.addSpacing(16)
        nv.addWidget(label("로봇 현재 위치 (mm)", sub=True))
        self.now_pose = label()
        self.now_pose.setStyleSheet("font-size:24px; font-family:Consolas,monospace;")
        nv.addWidget(self.now_pose)
        nv.addSpacing(10)
        nv.addWidget(label("목표까지 남은 거리", sub=True))
        self.now_left = label("—")
        self.now_left.setStyleSheet("font-size:24px; font-weight:600;")
        nv.addWidget(self.now_left)
        nv.addStretch()
        self.status = label()
        self.status.setStyleSheet("font-size:16px;")
        nv.addWidget(self.status)
        body.addWidget(now, 1)

        # right: phases with their steps, then help + back
        side = QVBoxLayout()
        self.phase_box = QVBoxLayout()
        side.addLayout(self.phase_box)
        side.addStretch()
        back = button("← 다른 동작 고르기\n컵 · 얼음 · 커피 · 파우더 · 픽업존", self.back)
        back.setObjectName("back")
        self.back_btn = back
        side.addWidget(back)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(380)
        body.addWidget(sw)
        root.addLayout(body, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(200)

    # ── model ──
    def enter(self, dp):
        a = self.app
        self.info.setText(f"{a.hw} · {a.mode} · {a.ip}" + (" · 가짜 로봇" if a.fake else ""))
        self.set_slot(1)

    def set_slot(self, n):
        self.n, self.idx, self.step_mode = n, -1, False
        self.slot_group.button(n).setChecked(True)
        self.m = motions.cup(self.app.mode, n)
        self.flat, self.groups = [], []
        for gid, name, steps in self.m["phases"]:
            self.groups.append((gid, name, len(self.flat), len(self.flat) + len(steps) - 1))
            self.flat += steps
        self.title.setText("컵 미세티칭")
        self.say(f"컵 {n}번이에요. ① HOLD부터 시작하세요.")
        self.build()

    def group(self, gid):
        return next(g for g in self.groups if g[0] == gid)

    def build(self):
        while self.phase_box.count():
            w = self.phase_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.cards, self.step_labels = {}, []
        for gid, name, s, e in self.groups:
            c = card()
            v = QVBoxLayout(c)
            h = QHBoxLayout()
            h.addWidget(label(f"<b>{name}</b>"))
            h.addStretch()
            run = button("실행", lambda _=False, g=gid: self.run_phase(g), primary=True)
            one = button("한 단계씩", lambda _=False, g=gid: self.run_one(g))
            h.addWidget(run)
            h.addWidget(one)
            v.addLayout(h)
            for i in range(s, e + 1):
                st = self.flat[i]
                lab = label(f"{i + 1}. {st['title']}" + ("  · 미세티칭" if st.get("teach") else ""))
                v.addWidget(lab)
                self.step_labels.append(lab)
            self.cards[gid] = (c, run, one)
            self.phase_box.addWidget(c)
        self.refresh()

    def can_run(self, gid):
        if self.busy or self.dlg:
            return False
        if gid == "hold":
            return True
        _, _, s, e = self.group("unhold")
        return self.idx == self.group("hold")[3] or s <= self.idx < e

    def refresh(self):
        for gid, (c, run, one) in self.cards.items():
            ok = self.can_run(gid)
            run.setEnabled(ok)
            one.setEnabled(ok)
            _, _, s, e = self.group(gid)
            restyle(c, active=s <= self.idx + 1 <= e and ok)
        for i, lab in enumerate(self.step_labels):
            style = "font-weight:700; color:#1f6a4f;" if i == self.idx and self.busy else \
                    "color:#a3b0aa;" if i <= self.idx else ""
            lab.setStyleSheet(style)
        for b in self.slot_group.buttons():
            b.setEnabled(not self.busy and not self.dlg)
        self.back_btn.setEnabled(not self.busy and not self.dlg)
        if self.dlg:
            self.dlg.set_busy(self.busy)

    def say(self, text):
        self.status.setText(text)

    def tick(self):
        r = self.app.robot
        if not r or not self.isVisible():
            return
        p = r.pose()
        self.now_pose.setText(f"X {p[0]:8.1f}   Y {p[1]:8.1f}   Z {p[2]:8.1f}")
        if self.target:
            d = sum((a - b) ** 2 for a, b in zip(p[:3], self.target[:3])) ** 0.5
            self.now_left.setText(f"{d:.0f} mm")
        else:
            self.now_left.setText("—")
        if self.dlg:
            self.dlg.update_readout(p)

    # ── running ──
    def start(self, work, then=None):
        """Run work() on a thread with the UI locked; then() on success."""
        a = self.app
        self.busy = True
        self.refresh()

        def done(_):
            self.busy, self.target = False, None
            self.refresh()
            if then:
                then()

        def fail(e):
            self.busy, self.target = False, None
            if self.dlg:   # stopped / failed while adjusting: the robot is near the cup, start over from HOLD
                self.dlg.close()
                self.dlg = None
            self.refresh()
            if isinstance(e, dv.Stopped):
                self.say("멈췄어요. 수동 모드로 로봇을 안전한 곳으로 옮긴 뒤 ① HOLD부터 다시 실행하세요.")
                self.idx = -1
                self.refresh()
            else:
                self.show_error(e)
        a.bg(work, done, fail)

    def do_step(self, i):
        """Thread side: run one step and mark it done."""
        a, st = self.app, self.flat[i]
        self.idx = i - 1
        a.ui(lambda: (self.now_step.setText(f"{i + 1}. {st['title']}"), self.refresh_running(i)))
        if st["kind"] == "rail":
            pulse = a.store.rail_pulse(self.m["rail_cmd"], self.n)
            if pulse is None:
                raise dv.MotionError("DB에 이 칸의 레일 위치가 없어요")
            if a.rail:
                a.rail.move_to_pulse_and_wait(target_pulse=pulse, pps=100000, tol=50, timeout_s=20.0, log_poll=False)
        elif st["kind"] == "grip":
            a.robot.gripper(dv.GRIP_OPEN if st["grip"] == "open" else a.store.gripper_close())
        else:
            for kind, where in st["moves"]:
                target = where(a.store)
                self.target = target if kind == "L" else None
                a.robot.move(kind, target)
        self.idx = i

    def refresh_running(self, i):
        self.idx = i - 1
        for k, lab in enumerate(self.step_labels):
            lab.setStyleSheet("font-weight:700; color:#1f6a4f;" if k == i else "color:#a3b0aa;" if k < i else "")

    def run_phase(self, gid):
        _, name, s, e = self.group(gid)
        self.step_mode = False
        first = s if gid == "hold" else self.idx + 1
        self.say(f"{name} 실행 중…")

        def work():
            for i in range(first, e + 1):
                self.do_step(i)
        self.start(work, lambda: self.after(gid))

    def run_one(self, gid):
        _, name, s, e = self.group(gid)
        i = s if gid == "hold" and not (s <= self.idx < e and self.step_mode) else self.idx + 1
        if i == s and gid == "hold":
            yes = QMessageBox.question(self, "로봇이 움직여요",
                                       f"{name}: 한 단계씩 시작할게요.\n로봇 주변에 사람이나 물건이 없는지 확인하세요.",
                                       QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if yes != QMessageBox.Yes:
                return
        self.step_mode = True
        self.say(f"{i + 1}. {self.flat[i]['title']} 실행 중…")
        self.start(lambda: self.do_step(i), lambda: self.after(gid) if i == e else
                   self.say(f"{i + 1}. {self.flat[i]['title']} 완료. 다음 단계를 누르세요."))

    def after(self, gid):
        self.now_step.setText(f"{self.group(gid)[1]} 완료")
        if gid == "hold":
            self.say("컵을 잡았어요. 위치를 조정하세요.")
            self.open_adjust()
        else:
            self.idx = -1
            self.refresh()
            self.say("② UNHOLD 완료. 다시 하려면 ① HOLD부터 실행하세요.")

    def stop(self):
        if self.app.robot:
            self.app.robot.stop()

    def show_error(self, e):
        a = self.app
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("로봇이 멈췄어요")
        box.setText(f"{e}\n\n수동 모드로 로봇을 안전한 곳으로 옮긴 뒤 ① HOLD부터 다시 실행하세요.\n"
                    "같은 곳에서 계속 멈추면 위 내용을 지원팀에 보내 주세요.")
        clear = box.addButton("에러 지우고 닫기", QMessageBox.AcceptRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is clear and a.robot:
            a.robot.reset_error()
        self.idx = -1
        self.refresh()
        self.say("멈췄어요. ① HOLD부터 다시 실행하세요.")

    def back(self):
        self.app.connect_page.refresh()
        self.app.stack.setCurrentWidget(self.app.connect_page)

    # ── adjust Hold ──
    def open_adjust(self):
        self.dlg = AdjustDialog(self)
        self.refresh()
        self.dlg.show()

    def leave(self, save):
        """Close the adjust dialog; save Hold (+ rail) or go back to the saved Hold; then UNHOLD."""
        a, d = self.app, self.dlg
        hold = self.m["hold_point"]
        base = a.store.point(hold)
        d.close()
        self.dlg = None
        rail_new = d.rail_value()

        def work():
            if save:
                p = a.robot.pose()
                a.store.save_point(hold, p[:3] + base[3:])   # only XYZ is jogged; keep the saved rotation
                if rail_new is not None and rail_new != d.rail0:
                    a.store.save_rail(self.m["rail_cmd"], self.n, rail_new)
            else:
                self.target = base
                a.robot.move("L", base)   # like production: UNHOLD leaves from the saved Hold
        msg = "저장했어요." if save else "저장하지 않았어요. 저장된 위치로 돌아갔어요."

        def then():
            if self.step_mode:
                self.say(f"{msg} ② UNHOLD의 ‘한 단계씩’으로 빼세요.")
            else:
                self.say(f"{msg} 빼는 중…")
                self.run_phase("unhold")
        self.start(work, then)


class AdjustDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page, a = page, page.app
        self.setWindowTitle("컵 잡는 위치 조정")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.base = a.store.point(page.m["hold_point"])
        self.rail0 = a.store.rail_pulse(page.m["rail_cmd"], page.n)
        v = QVBoxLayout(self)
        v.addWidget(label(f"<b style='font-size:17px'>컵 {page.n}번 · 컵 잡는 위치</b>"))
        v.addWidget(label("1 mm씩 움직여서 맞추세요. 저장된 위치에서 ±%d mm까지 움직일 수 있어요." % LIMIT, sub=True))
        pad = QGridLayout()
        self.jogs = []
        for (r, c, ax, mm, t) in ((0, 1, "y", 1, "+Y"), (1, 0, "x", -1, "-X"), (1, 2, "x", 1, "+X"),
                                  (2, 1, "y", -1, "-Y"), (0, 4, "z", 1, "+Z"), (2, 4, "z", -1, "-Z")):
            b = button(t, lambda _=False, a_=ax, m_=mm: self.jog(a_, m_), jog=True)
            pad.addWidget(b, r, c)
            self.jogs.append(b)
        mid = label("1 mm", sub=True)
        mid.setAlignment(Qt.AlignCenter)
        pad.addWidget(mid, 1, 1)
        pad.setColumnMinimumWidth(3, 16)
        v.addLayout(pad)
        self.readout = label()
        self.readout.setAlignment(Qt.AlignCenter)
        v.addWidget(self.readout)
        self.rail_row = QWidget()
        rr = QHBoxLayout(self.rail_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.addWidget(label("레일 위치 (pulse)", sub=True))
        self.rail = QLineEdit("" if self.rail0 is None else str(self.rail0))
        rr.addWidget(self.rail, 1)
        self.rail_btn = button("레일 이동", self.move_rail)
        rr.addWidget(self.rail_btn)
        self.rail_row.setVisible(a.rail is not None)
        v.addWidget(self.rail_row)
        self.save_btn = button("저장하고 빼기", lambda: page.leave(True), primary=True)
        self.leave_btn = button("저장 없이 빼기", lambda: page.leave(False))
        v.addWidget(self.save_btn)
        v.addWidget(self.leave_btn)
        self.resize(420, 0)

    def reject(self):   # Esc must not hide the dialog: leaving goes through save / leave
        pass

    def rail_value(self):
        try:
            return int(self.rail.text().strip())
        except ValueError:
            return None

    def set_busy(self, busy):
        for b in self.jogs + [self.rail_btn, self.save_btn, self.leave_btn]:
            b.setEnabled(not busy)

    def update_readout(self, p):
        d = [p[i] - self.base[i] for i in range(3)]
        self.readout.setText("저장된 위치에서  " + "   ".join(f"{k} {v:+.0f}" for k, v in zip("XYZ", d)) + "  mm")

    def jog(self, axis, mm):
        a, i = self.page.app, "xyz".index(axis)
        if abs(a.robot.pose()[i] + mm - self.base[i]) > LIMIT:
            self.page.say(f"저장된 위치에서 {LIMIT} mm 넘게는 못 움직여요.")
            return
        self.page.start(lambda: a.robot.jog(axis, mm))

    def move_rail(self):
        a, v = self.page.app, self.rail_value()
        if v is None:
            self.page.say("레일 위치는 숫자로 넣어 주세요.")
            return
        self.page.start(lambda: a.rail.move_to_pulse_and_wait(target_pulse=v, pps=100000, tol=50,
                                                             timeout_s=20.0, log_poll=False),
                        lambda: self.page.say(f"레일을 {v} pulse로 옮겼어요. 저장하면 이 값도 저장돼요."))


def main():
    # PyQt5 aborts the whole app on an exception in a slot; log it instead so a UI bug can't kill the tool mid-move.
    sys.excepthook = lambda *exc: traceback.print_exception(*exc)
    qa = QApplication(sys.argv)
    qa.setStyleSheet(QSS)
    w = App()
    w.show()
    sys.exit(qa.exec_())


if __name__ == "__main__":
    main()
