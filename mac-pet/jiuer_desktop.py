#!/usr/bin/env python3
"""九儿桌面宠物 — macOS tkinter 透明悬浮窗版（零依赖，系统自带 Python 可运行）
双击运行 / 终端运行均可。
操作：拖拽移动 | 单击比心 | 右键或 Esc 退出
"""
import os
import random
import tkinter as tk

# ============ 配置 ============
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(SCRIPT_DIR, "gifs")
EXTERNAL = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "桌宠成品-九儿"))
GIF_DIR = BUNDLED if os.path.isdir(BUNDLED) else EXTERNAL

STATE_GIFS = {
    "idle":          "idle.gif",
    "running-right": "running-right.gif",
    "running-left":  "running-left.gif",
    "waving":        "waving.gif",
    "heart":         "jumping.gif",   # 比心
    "failed":        "failed.gif",
    "waiting":       "waiting.gif",
    "running":       "running.gif",
    "review":        "review.gif",
}

FPS_MS = 90            # 帧间隔
AUTO_SWITCH_MS = 4000  # 自动状态切换间隔
HEART_PLAY_MS = 1400   # 比心播放时长

# 各 GIF 循环次数（None=无限）
LOOP_ONCE = {"heart"}


class GifPlayer:
    """预加载 GIF 全部帧，按 FPS 轮播。"""
    def __init__(self, path):
        self.frames = []
        i = 0
        while True:
            try:
                self.frames.append(tk.PhotoImage(file=path, format=f"gif -index {i}"))
                i += 1
            except tk.TclError:
                break
        self.n = len(self.frames)
        if self.n == 0:
            raise RuntimeError(f"无法加载 GIF: {path}")


class PetApp:
    def __init__(self):
        self.root = tk.Tk()
        r = self.root
        r.overrideredirect(True)                 # 无边框
        r.attributes("-topmost", True)           # 置顶
        r.attributes("-transparent", True)       # 整窗透明（macOS）
        r.config(bg="systemTransparent")

        self.label = tk.Label(r, bg="systemTransparent", bd=0, highlightthickness=0)
        self.label.pack()

        # 居中
        r.update_idletasks()
        w, h = 192, 208
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

        # 状态
        self.state = "idle"
        self.players = {}
        self.frame_idx = 0
        self.lock = False

        # 拖拽
        self._drag = None
        self._moved = False

        self._bind()
        self._load("idle")
        self._tick()
        self._auto()

    # ---------- 事件 ----------
    def _bind(self):
        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._move)
        self.label.bind("<ButtonRelease-1>", self._release)
        self.label.bind("<Button-2>", self._quit)   # macOS 右键
        self.label.bind("<Button-3>", self._quit)   # 兼容
        self.root.bind("<Escape>", self._quit)

    def _press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._moved = False

    def _move(self, e):
        if not self._drag:
            return
        x, y = self._drag
        self.root.geometry(f"+{e.x_root - x}+{e.y_root - y}")
        self._moved = True

    def _release(self, _e):
        if not self._moved and not self.lock:
            self.lock = True
            self._load("heart")
            self.root.after(HEART_PLAY_MS, self._back_idle)
        self._drag = None
        self._moved = False

    def _quit(self, _e=None):
        self.root.destroy()

    # ---------- 动画 ----------
    def _load(self, state):
        path = os.path.join(GIF_DIR, STATE_GIFS[state])
        if state not in self.players:
            if not os.path.exists(path):
                print(f"[warn] 缺少 {path}")
                return
            try:
                self.players[state] = GifPlayer(path)
            except RuntimeError as ex:
                print(ex)
                return
        self.state = state
        self.frame_idx = 0

    def _tick(self):
        player = self.players.get(self.state)
        if player and player.n:
            self.label.config(image=player.frames[self.frame_idx % player.n])
            self.frame_idx += 1
        self.root.after(FPS_MS, self._tick)

    def _back_idle(self):
        self.lock = False
        if self.state != "idle":
            self._load("idle")

    def _auto(self):
        if not self.lock:
            r = random.random()
            if self.state == "idle":
                if r < 0.12:
                    self._load("running")
                elif r < 0.22:
                    self._load("waiting")
                elif r < 0.27:
                    self._load("waving")
            elif self.state in ("running", "waiting", "waving"):
                if r < 0.35:
                    self._load("idle")
        self.root.after(AUTO_SWITCH_MS, self._auto)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print(f"[info] GIF_DIR={GIF_DIR} exists={os.path.isdir(GIF_DIR)}")
    PetApp().run()
