import tkinter as tk
from tkinter import messagebox
import threading
import time
import random
import hashlib
import uuid
import sys
import os
import requests
import hmac
import json

# ============================================================
#  工具函数
# ============================================================


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_machine_id():
    """
    三合一机器码：MAC + Windows MachineGuid + 用户名
    比单纯 MAC 地址难伪造得多
    """
    parts = []
    parts.append(str(uuid.getnode()))  # MAC
    parts.append(os.environ.get("USERNAME", "unknown"))  # 用户名
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        parts.append(guid)
        winreg.CloseKey(key)
    except:
        pass
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


# ============================================================
#  图像识别函数
# ============================================================

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

region = None


def find_img(name, conf=0.85):
    if not PYAUTOGUI_AVAILABLE:
        return None
    try:
        return pyautogui.locateOnScreen(
            resource_path(name), region=region, confidence=conf, grayscale=False
        )
    except:
        return None


def find_img_multi(names, conf=0.85):
    for name in names:
        try:
            pos = pyautogui.locateOnScreen(
                resource_path(name), region=region, confidence=conf
            )
            if pos:
                return pos
        except:
            continue
    return None


def click_btn(name):
    pos = find_img(name)
    if pos:
        x, y = pyautogui.center(pos)
        x += random.randint(-10, 10)
        y += random.randint(-10, 10)
        pyautogui.click(x, y)
        time.sleep(random.uniform(1.5, 2.5))
        return True
    return False


def click_btn_multi(names):
    pos = find_img_multi(names)
    if pos:
        x, y = pyautogui.center(pos)
        x += random.randint(-10, 10)
        y += random.randint(-10, 10)
        pyautogui.click(x, y)
        time.sleep(random.uniform(1.5, 2.5))
        return True
    return False


def wait_for(name, timeout=8):
    for _ in range(timeout):
        if find_img(name):
            return True
        time.sleep(1)
    return False


# ============================================================
#  授权验证
# ============================================================

VERIFY_URL = "https://bot-server-production-f910.up.railway.app/verify"

# ⚠️ 必须和 server.py 里的 SIGN_SECRET 一致
SIGN_SECRET = "2579561724a"

TRIAL_SECONDS = 3600  # 试用 1 小时
HEARTBEAT_INTERVAL = 1800  # 每 30 分钟重新验证一次


def make_signature(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True)
    return hmac.new(SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_license(key, plan):
    if plan == "trial":
        return True, "试用模式"
    if not key:
        return False, "请输入授权码"
    try:
        machine_id = get_machine_id()
        payload = {"key": key, "machine_id": machine_id, "plan": plan}
        payload["sig"] = make_signature(
            {"key": key, "machine_id": machine_id, "plan": plan}
        )

        resp = requests.post(VERIFY_URL, json=payload, timeout=8)
        data = resp.json()
        if data.get("valid"):
            return True, data.get("expire_at", "")
        else:
            return False, data.get("reason", "授权码无效")
    except requests.exceptions.ConnectionError:
        return False, "无法连接验证服务器，请检查网络"
    except Exception as e:
        return False, f"验证出错: {e}"


# ============================================================
#  GUI
# ============================================================


class BotApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("挂机助手 v1.0")
        self.root.geometry("420x560")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.running = False
        self.thread = None
        self.plan_var = tk.StringVar(value="trial")
        self._cached_key = ""
        self._cached_plan = ""

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        BG = "#1a1a2e"
        CARD = "#16213e"
        ACCENT = "#0f3460"
        GREEN = "#4ade80"
        YELLOW = "#fbbf24"
        FG = "#e2e8f0"
        GRAY = "#64748b"

        # 标题
        tf = tk.Frame(self.root, bg=BG)
        tf.pack(fill="x", padx=20, pady=(20, 5))
        tk.Label(
            tf,
            text="🎮 挂机助手",
            font=("Microsoft YaHei", 20, "bold"),
            bg=BG,
            fg=GREEN,
        ).pack(side="left")
        tk.Label(tf, text="v1.0", font=("Microsoft YaHei", 10), bg=BG, fg=GRAY).pack(
            side="left", padx=6, pady=6
        )

        # 套餐
        pc = tk.Frame(self.root, bg=CARD)
        pc.pack(fill="x", padx=20, pady=8)
        tk.Label(
            pc, text="选择套餐", font=("Microsoft YaHei", 11, "bold"), bg=CARD, fg=FG
        ).pack(anchor="w", padx=15, pady=(12, 6))

        plans = [
            ("🆓  免费试用（1小时）", "trial", GRAY),
            ("📅  周卡  RM 15", "week", YELLOW),
            ("👑  月卡  RM 45", "month", GREEN),
        ]
        for text, val, color in plans:
            row = tk.Frame(pc, bg=CARD)
            row.pack(fill="x", padx=15, pady=2)
            tk.Radiobutton(
                row,
                text=text,
                variable=self.plan_var,
                value=val,
                font=("Microsoft YaHei", 10),
                bg=CARD,
                fg=color,
                selectcolor=ACCENT,
                activebackground=CARD,
                activeforeground=color,
                command=self._on_plan_change,
            ).pack(anchor="w")

        tk.Frame(pc, bg=ACCENT, height=1).pack(fill="x", padx=15, pady=8)

        # 授权码输入
        kf = tk.Frame(pc, bg=CARD)
        kf.pack(fill="x", padx=15, pady=(0, 8))
        tk.Label(
            kf, text="授权码：", font=("Microsoft YaHei", 10), bg=CARD, fg=FG
        ).pack(side="left")
        self.key_entry = tk.Entry(
            kf,
            width=26,
            font=("Consolas", 10),
            bg=ACCENT,
            fg=GREEN,
            insertbackground=GREEN,
            relief="flat",
            bd=4,
            state="disabled",
        )
        self.key_entry.pack(side="left", padx=6)

        # 设备码显示（方便用户截图给你）
        mid = get_machine_id()
        mid_frame = tk.Frame(pc, bg=CARD)
        mid_frame.pack(fill="x", padx=15, pady=(0, 12))
        tk.Label(
            mid_frame,
            text=f"设备码：{mid}",
            font=("Consolas", 7),
            bg=CARD,
            fg=GRAY,
            wraplength=360,
            justify="left",
        ).pack(anchor="w")

        # 开始/停止按钮
        self.start_btn = tk.Button(
            self.root,
            text="▶  开 始",
            font=("Microsoft YaHei", 13, "bold"),
            bg=GREEN,
            fg="#0f172a",
            width=18,
            height=2,
            relief="flat",
            cursor="hand2",
            command=self._toggle,
        )
        self.start_btn.pack(pady=10)

        # 状态栏
        sf = tk.Frame(self.root, bg=CARD)
        sf.pack(fill="x", padx=20, pady=(0, 8))
        tk.Label(
            sf, text="状态：", font=("Microsoft YaHei", 10), bg=CARD, fg=GRAY
        ).pack(side="left", padx=10, pady=6)
        self.status_label = tk.Label(
            sf,
            text="等待启动",
            font=("Microsoft YaHei", 10, "bold"),
            bg=CARD,
            fg=YELLOW,
        )
        self.status_label.pack(side="left")
        self.timer_label = tk.Label(
            sf, text="", font=("Consolas", 10), bg=CARD, fg=GRAY
        )
        self.timer_label.pack(side="right", padx=10)

        # 日志框
        lf = tk.Frame(self.root, bg=CARD)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        tk.Label(
            lf, text="运行日志", font=("Microsoft YaHei", 9), bg=CARD, fg=GRAY
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self.log_text = tk.Text(
            lf,
            height=7,
            font=("Consolas", 9),
            bg="#0d1117",
            fg="#7ee787",
            relief="flat",
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _on_plan_change(self):
        if self.plan_var.get() == "trial":
            self.key_entry.config(state="disabled")
        else:
            self.key_entry.config(state="normal")

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _set_status(self, text, color="#fbbf24"):
        self.status_label.config(text=text, fg=color)

    def _toggle(self):
        if not self.running:
            self._start()
        else:
            self._stop()

    def _start(self):
        plan = self.plan_var.get()
        key = self.key_entry.get().strip()

        self._set_status("验证中...", "#fbbf24")
        self.root.update()

        ok, reason = verify_license(key, plan)
        if not ok:
            self._set_status("验证失败", "#f87171")
            messagebox.showerror("授权失败", reason)
            return

        self._cached_key = key
        self._cached_plan = plan
        self._log(f"✅ 授权通过 [{plan}]  到期：{reason}")
        self.running = True
        self.start_time = time.time()
        self.trial_limit = TRIAL_SECONDS if plan == "trial" else float("inf")

        self.start_btn.config(text="⏹  停 止", bg="#f87171", fg="white")
        self._set_status("运行中", "#4ade80")

        self.thread = threading.Thread(target=self._bot_loop, daemon=True)
        self.thread.start()
        self._tick()

    def _stop(self):
        self.running = False
        self.start_btn.config(text="▶  开 始", bg="#4ade80", fg="#0f172a")
        self._set_status("已停止", "#64748b")
        self.timer_label.config(text="")
        self._log("已停止")

    def _tick(self):
        if not self.running:
            return
        elapsed = int(time.time() - self.start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self.timer_label.config(text=f"⏱ {h:02d}:{m:02d}:{s:02d}")

        # 试用剩余提醒
        if self.trial_limit != float("inf"):
            remain = int(self.trial_limit - elapsed)
            if 0 < remain <= 300 and remain % 60 == 0:
                self._log(f"⚠️ 试用剩余 {remain//60} 分钟")

        # 心跳验证
        if elapsed > 0 and elapsed % HEARTBEAT_INTERVAL == 0:
            threading.Thread(target=self._heartbeat, daemon=True).start()

        self.root.after(1000, self._tick)

    def _heartbeat(self):
        """每30分钟静默重新验证，防止授权被撤销后继续使用"""
        if self._cached_plan == "trial":
            return
        ok, reason = verify_license(self._cached_key, self._cached_plan)
        if not ok:
            self._log(f"🚫 授权已失效：{reason}，停止运行")
            self.root.after(0, self._stop)

    def _bot_loop(self):
        pyautogui.FAILSAFE = True
        step = 1
        fail_count = 0
        self._log("5秒后开始挂机...")
        time.sleep(5)

        while self.running:
            if time.time() - self.start_time > self.trial_limit:
                self._log("⏰ 试用时间已到，请购买授权码")
                self.root.after(0, self._stop)
                break

            try:
                x, y = pyautogui.position()
                if x <= 5 and y <= 5:
                    self._log("🛑 紧急停止")
                    self.root.after(0, self._stop)
                    break
            except:
                pass

            time.sleep(0.5)
            success = False

            for popup_img in ["close.png", "close2.png", "cancel.png"]:
                popup = find_img(popup_img)
                if popup:
                    px, py = pyautogui.center(popup)
                    pyautogui.click(px, py)
                    self._log("关闭弹窗")
                    time.sleep(1)
                    break
            else:
                if step == 1:
                    if click_btn("search.png"):
                        self._log("✅ 步骤1：点击搜索")
                        step = 2
                        success = True

                elif step == 2:
                    if click_btn_multi(["special_off.png", "special_on.png"]):
                        self._log("✅ 步骤2：点击特殊")
                        step = 3
                        success = True

                elif step == 3:
                    if click_btn("summon.png"):
                        self._log("✅ 步骤3：召唤，等待集结...")
                        success = True
                        if wait_for("gather.png", timeout=8):
                            step = 4
                        else:
                            self._log("⚠️ 等待超时，重置")
                            step = 1

                elif step == 4:
                    if click_btn("gather.png"):
                        self._log("✅ 步骤4：集结")
                        step = 5
                        success = True

                elif step == 5:
                    if click_btn("start.png"):
                        self._log("✅ 步骤5：出发！重新开始")
                        step = 1
                        success = True

                if success:
                    fail_count = 0
                else:
                    fail_count += 1
                    self._log(f"步骤{step} 失败 {fail_count}次")
                    time.sleep(1)

                if fail_count >= 5:
                    self._log("🔄 卡住，重置流程")
                    step = 1
                    fail_count = 0

    def _on_close(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BotApp()
    app.run()
