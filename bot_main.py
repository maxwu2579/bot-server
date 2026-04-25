import tkinter as tk
from tkinter import messagebox
import threading
import time
import random
import re
import hashlib
import uuid
import sys
import os
import requests
import hmac
import json


def is_yellow_button(x, y, size=50):
    try:
        import numpy as np
        import cv2

        # 截取按钮附近区域
        left = int(x - size // 2)
        top = int(y - size // 2)

        screenshot = np.array(
            _sct.grab({"left": left, "top": top, "width": size, "height": size})
        )

        img = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 黄色范围（可以调）
        lower = np.array([10, 50, 50])
        upper = np.array([45, 255, 255])

        mask = cv2.inRange(hsv, lower, upper)
        ratio = (mask > 0).sum() / (size * size)

        return ratio > 0.08  # 超过15%算黄色按钮
    except:
        return False


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
    parts = []
    parts.append(str(uuid.getnode()))
    parts.append(os.environ.get("USERNAME", "unknown"))
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
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


# ============================================================
#  授权码本地保存（加密）
# ============================================================


def _get_config_path():
    """配置文件放在用户AppData目录"""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder = os.path.join(appdata, "BotHelper")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.dat")


def _simple_encrypt(text: str) -> str:
    """用设备码做异或加密"""
    key = get_machine_id()
    result = []
    for i, c in enumerate(text):
        result.append(chr(ord(c) ^ ord(key[i % len(key)])))
    return "".join(result).encode("utf-8", errors="replace").hex()


def _simple_decrypt(hex_str: str) -> str:
    try:
        key = get_machine_id()
        encrypted = bytes.fromhex(hex_str).decode("utf-8", errors="replace")
        result = []
        for i, c in enumerate(encrypted):
            result.append(chr(ord(c) ^ ord(key[i % len(key)])))
        return "".join(result)
    except:
        return ""


def save_license(key: str, plan: str):
    """保存授权码"""
    try:
        data = json.dumps({"key": key, "plan": plan})
        encrypted = _simple_encrypt(data)
        with open(_get_config_path(), "w") as f:
            f.write(encrypted)
    except:
        pass


def load_license():
    """读取上次保存的授权码"""
    try:
        path = _get_config_path()
        if not os.path.exists(path):
            return None, None
        with open(path, "r") as f:
            encrypted = f.read().strip()
        decrypted = _simple_decrypt(encrypted)
        data = json.loads(decrypted)
        return data.get("key"), data.get("plan")
    except:
        return None, None


def clear_license():
    """清除保存的授权码"""
    try:
        path = _get_config_path()
        if os.path.exists(path):
            os.remove(path)
    except:
        pass


# ============================================================
#  图像识别
# ============================================================

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

region = None  # 自动检测游戏窗口后会自动设置

# ⭐ 游戏窗口标题（部分匹配）
# ⭐ 支持的窗口标题列表（按优先级）
# 会按顺序尝试匹配：原生游戏 → 各种模拟器
GAME_WINDOW_TITLES = [
    "指尖王国",  # ← 游戏窗口（必须放第一位，优先匹配）
    "小游戏",
    "LDPlayer",
    "雷电模拟器",
    "MuMu",
    "MuMu模拟器",
    "BlueStacks",
    "NoxPlayer",
    "夜神模拟器",
    "逍遥模拟器",
    "腾讯手游助手",
    # ← 微信放最后（兜底，用户没装游戏专属窗口时才用）
]


# ============================================================
#  快速图像识别 (mss + cv2，比 pyautogui 快 5-10 倍)
# ============================================================

try:
    import mss
    import cv2
    import numpy as np

    FAST_MODE = True
    _sct = mss.mss()
    _template_cache = {}
except ImportError:
    FAST_MODE = False


def _load_template(name):
    """加载并缓存模板图（灰度）"""
    if name in _template_cache:
        return _template_cache[name]
    path = resource_path(name)
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    _template_cache[name] = img
    return img


def fast_find(name, conf=0.85):
    """用 mss+cv2 快速找图，返回 (x, y, w, h) 或 None"""
    if not FAST_MODE:
        return None
    try:
        template = _load_template(name)
        if template is None:
            return None

        if region:
            mon = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
            }
        else:
            mon = _sct.monitors[1]

        screenshot = np.array(_sct.grab(mon))
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= conf:
            h, w = template.shape
            x = max_loc[0] + (region[0] if region else 0)
            y = max_loc[1] + (region[1] if region else 0)
            return (x, y, w, h)
    except:
        pass
    return None


def auto_detect_region():
    """自动检测游戏窗口位置（优先手机竖屏比例的窗口）"""
    global region
    try:
        import pygetwindow as gw

        # 先收集所有匹配的窗口
        all_matches = []
        for title in GAME_WINDOW_TITLES:
            wins = gw.getWindowsWithTitle(title)
            for w in wins:
                if w.width > 300 and w.height > 300:
                    # 给竖屏窗口加分（手机游戏多为竖屏）
                    is_portrait = w.height > w.width
                    score = w.width * w.height
                    if is_portrait:
                        score *= 2  # 竖屏优先级翻倍
                    all_matches.append((score, title, w))

        if all_matches:
            # 选评分最高的
            all_matches.sort(key=lambda x: -x[0])
            _, title, w = all_matches[0]
            region = (
                max(0, w.left + 10),
                max(0, w.top + 10),  # ← 10 改成 40，跳过标题栏
                w.width - 20,
                w.height - 20,  # ← 20 改成 50，对应减少
            )
            return f"{title} ({w.width}x{w.height})"
    except:
        pass
    region = None
    return None


# ============================================================
#  OCR 文字识别 (RapidOCR，不依赖分辨率)
# ============================================================

try:
    from rapidocr_onnxruntime import RapidOCR

    _ocr_engine = None
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def _get_ocr():
    """延迟初始化 OCR（第一次用时才加载）"""
    global _ocr_engine
    if _ocr_engine is None and OCR_AVAILABLE:
        _ocr_engine = RapidOCR()
    return _ocr_engine


def find_text(
    target_text: str,
    y_pct_start=0.0,
    y_pct_end=1.0,
    x_pct_start=0.0,
    x_pct_end=1.0,
    conf=0.5,
):
    """
    在屏幕上找文字，返回按钮中心坐标 (x, y) 或 None
    支持指定 X/Y 区域百分比
    """
    if not OCR_AVAILABLE or not FAST_MODE:
        return None
    try:
        ocr = _get_ocr()
        if ocr is None:
            return None

        # 截图
        if region:
            mon = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
            }
        else:
            mon = _sct.monitors[1]
        screenshot = np.array(_sct.grab(mon))
        img = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
        h, w = img.shape[:2]

        # 裁剪指定区域
        y_start = int(h * y_pct_start)
        y_end = int(h * y_pct_end)
        x_start = int(w * x_pct_start)
        x_end = int(w * x_pct_end)
        cropped = img[y_start:y_end, x_start:x_end]

        # OCR 识别
        result, _ = ocr(cropped)
        if not result:
            return None

        # 查找匹配的文字
        targets = [t.strip() for t in target_text.split("|")]
        for box, text, score in result:
            try:
                if float(score) < conf:
                    continue
            except (ValueError, TypeError):
                pass
            for t in targets:
                if t in text:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    cx = int(sum(xs) / 4) + x_start
                    cy = int(sum(ys) / 4) + y_start
                    if region:
                        cx += region[0]
                        cy += region[1]
                    return (cx, cy)
    except Exception as e:
        print(f"OCR 错误: {e}")
    return None


def find_text_in_region(target_text: str, y_pct_start=0.0, y_pct_end=1.0, conf=0.4):
    """
    在窗口的指定纵向百分比区域内找文字（不依赖分辨率）
    y_pct_start=0.6 表示从窗口60%高度开始找
    """
    if not OCR_AVAILABLE or not FAST_MODE:
        return None
    try:
        ocr = _get_ocr()
        if ocr is None:
            return None

        # 计算截图区域
        if region:
            rx, ry, rw, rh = region
        else:
            mon = _sct.monitors[1]
            rx, ry, rw, rh = mon["left"], mon["top"], mon["width"], mon["height"]

        # 按比例裁剪纵向范围
        crop_top = ry + int(rh * y_pct_start)
        crop_h = int(rh * (y_pct_end - y_pct_start))

        mon = {"left": rx, "top": crop_top, "width": rw, "height": crop_h}
        screenshot = np.array(_sct.grab(mon))
        img = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

        result, _ = ocr(img)
        if not result:
            return None

        targets = [t.strip() for t in target_text.split("|")]
        for box, text, score in result:
            if float(score) < conf:
                continue
            for t in targets:
                if t in text:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    cx = int(sum(xs) / 4) + rx
                    cy = int(sum(ys) / 4) + crop_top
                    return (cx, cy)
    except Exception as e:
        print(f"OCR 错误: {e}")
    return None


def click_text(
    target_text: str, y_pct_start=0.0, y_pct_end=1.0, x_pct_start=0.0, x_pct_end=1.0
):
    """用 OCR 找文字并点击（支持区域）"""
    pos = find_text(target_text, y_pct_start, y_pct_end, x_pct_start, x_pct_end)
    if pos:
        cx, cy = pos
        pyautogui.click(cx + random.randint(-8, 8), cy + random.randint(-5, 5))
        time.sleep(random.uniform(0.3, 0.5))
        return True
    return False


def wait_for_text(target_text: str, timeout=8):
    """等待某个文字出现"""
    for _ in range(timeout):
        if find_text(target_text):
            return True
        time.sleep(1)
    return False


def find_img(name, conf=0.85):
    # 优先用 mss+cv2 快速模式
    if FAST_MODE:
        pos = fast_find(name, conf)
        if pos:
            return pos
        return None
    # 兜底用 pyautogui
    if not PYAUTOGUI_AVAILABLE:
        return None
    try:
        return pyautogui.locateOnScreen(
            resource_path(name), region=region, confidence=conf, grayscale=True
        )
    except:
        return None


def find_img_multi(names, conf=0.85):
    for name in names:
        pos = find_img(name, conf)
        if pos:
            return pos
    return None


def _center_of(pos):
    """兼容 mss+cv2 的元组 和 pyautogui 的 Box"""
    if pos is None:
        return None
    if isinstance(pos, tuple):
        x, y, w, h = pos
        return (x + w // 2, y + h // 2)
    return pyautogui.center(pos)


def click_btn(name):
    pos = find_img(name)
    if pos:
        center = _center_of(pos)
        if center:
            cx, cy = center
            pyautogui.click(cx + random.randint(-10, 10), cy + random.randint(-10, 10))
            time.sleep(random.uniform(0.2, 0.3))
            return True
    return False


def click_btn_multi(names):
    pos = find_img_multi(names)
    if pos:
        center = _center_of(pos)
        if center:
            cx, cy = center
            pyautogui.click(cx + random.randint(-10, 10), cy + random.randint(-10, 10))
            time.sleep(random.uniform(0.2, 0.3))
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
TRIAL_URL = "https://bot-server-production-f910.up.railway.app/trial"
SIGN_SECRET = "2579561724a"
TRIAL_SECONDS = 1800
HEARTBEAT_INTERVAL = 1800


def make_signature(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True)
    return hmac.new(SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_trial():
    """试用验证：返回 (可用?, 剩余秒数/原因)"""
    try:
        machine_id = get_machine_id()
        payload = {"machine_id": machine_id}
        payload["sig"] = make_signature({"machine_id": machine_id})
        resp = requests.post(TRIAL_URL, json=payload, timeout=8)
        data = resp.json()
        if data.get("valid"):
            return True, data.get("remaining", 3600)
        return False, data.get("reason", "试用失败")
    except requests.exceptions.ConnectionError:
        return False, "无法连接验证服务器"
    except Exception as e:
        return False, f"验证出错: {e}"


def verify_license(key, plan):
    if plan == "trial":
        ok, result = verify_trial()
        if ok:
            return True, f"试用剩余 {int(result)//60} 分钟"
        return False, str(result)

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
        return False, data.get("reason", "授权码无效")
    except requests.exceptions.ConnectionError:
        return False, "无法连接验证服务器"
    except Exception as e:
        return False, f"验证出错: {e}"


# ============================================================
#  采集模式辅助函数
# ============================================================


def get_all_texts_in_region(
    x_pct_start=0.0,
    x_pct_end=1.0,
    y_pct_start=0.0,
    y_pct_end=1.0,
    return_box=False,
):
    """
    获取指定区域内所有 OCR 识别到的文字
    return_box=False 返回 [text, ...]
    return_box=True  返回 [(box, text), ...]  box 是相对裁剪区域的坐标
    """
    results_out = []
    if not OCR_AVAILABLE or not FAST_MODE:
        return results_out
    try:
        ocr = _get_ocr()
        if ocr is None:
            return results_out
        if region:
            mon = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
            }
        else:
            mon = _sct.monitors[1]
        screenshot_img = np.array(_sct.grab(mon))
        img = cv2.cvtColor(screenshot_img, cv2.COLOR_BGRA2BGR)
        h, w = img.shape[:2]

        y_start = int(h * y_pct_start)
        y_end = int(h * y_pct_end)
        x_start = int(w * x_pct_start)
        x_end = int(w * x_pct_end)
        cropped = img[y_start:y_end, x_start:x_end]

        result, _ = ocr(cropped)
        if not result:
            return results_out

        for item in result:
            box = item[0]
            text = None
            for x in item[1:]:
                if isinstance(x, str):
                    try:
                        float(x)
                        continue
                    except ValueError:
                        text = x
                        break
            if text is None:
                continue
            if return_box:
                results_out.append((box, text))
            else:
                results_out.append(text)
    except Exception as e:
        print(f"OCR 区域识别错误: {e}")
    return results_out


def check_team_status():
    raw = get_all_texts_in_region(
        x_pct_start=0.0,
        x_pct_end=0.30,
        y_pct_start=0.10,
        y_pct_end=0.45,  # ← 从 0.18-0.40 改成 0.10-0.45
        return_box=True,
    )

    team_candidates = []  # [(current, total, box), ...]
    edit_boxes = []  # [box, ...]

    for box, text in raw:
        clean = text.replace(" ", "")
        # 找 X/Y 数字
        m = re.search(r"(\d+)\s*/\s*(\d+)", clean)
        if m:
            current = int(m.group(1))
            total = int(m.group(2))
            if total <= 10:
                # 修正 OCR 错误：current 不可能比 total 大（如 10/3 实际是 0/3）
                if current > total:
                    current_str = str(current)
                    if len(current_str) > 1:
                        current = int(current_str[1:])  # 去掉首位字符
                    else:
                        continue
                team_candidates.append((current, total, box))
        # 找"编辑"（模糊：含"编"或"辑"）
        if "编" in text or "辑" in text:
            edit_boxes.append(box)

    # 没找到"编辑" → 直接返回 None
    if not edit_boxes:
        return None

    # 配对：X/Y 必须和"编辑"同一行
    for current, total, num_box in team_candidates:
        for edit_box in edit_boxes:
            if _is_same_row(num_box, edit_box):
                return (current, total)

    return None


def _is_same_row(box1, box2):
    """判断两个文字框是否在同一行（Y 中心距离 < 文字高度的 1.5 倍）"""
    cy1 = sum(p[1] for p in box1) / 4
    cy2 = sum(p[1] for p in box2) / 4
    h1 = max(p[1] for p in box1) - min(p[1] for p in box1)
    h2 = max(p[1] for p in box2) - min(p[1] for p in box2)
    avg_h = (h1 + h2) / 2
    return abs(cy1 - cy2) < avg_h * 1.5


def parse_time_to_seconds(time_str):
    """把 'HH:MM:SS' 或 'MM:SS' 转秒数"""
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def get_shortest_collect_time():
    """获取最短的采集剩余时间（秒）"""
    texts = get_all_texts_in_region(
        x_pct_start=0.0,
        x_pct_end=0.4,
        y_pct_start=0.2,
        y_pct_end=0.8,
    )
    all_seconds = []
    pattern = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?)")
    for text in texts:
        for match in pattern.findall(text):
            sec = parse_time_to_seconds(match)
            if sec is not None and sec > 0:
                all_seconds.append((match, sec))
    if not all_seconds:
        return None
    all_seconds.sort(key=lambda x: x[1])
    return all_seconds[0][1]


def click_window_center():
    """点击游戏窗口的正中心（如果没点到，再往下点几次）"""
    if region:
        cx = region[0] + region[2] // 2
        cy_center = region[1] + region[3] // 2
        win_h = region[3]
    else:
        screen_w, screen_h = pyautogui.size()
        cx = screen_w // 2
        cy_center = screen_h // 2
        win_h = screen_h

    # 点 3 个位置：正中心、稍下、再下
    # 偏移用窗口高度的百分比，适配不同尺寸
    offsets = [0, int(win_h * 0.04), int(win_h * 0.08)]
    for offset in offsets:
        pyautogui.click(
            cx + random.randint(-8, 8),
            cy_center + offset + random.randint(-5, 5),
        )
        time.sleep(0.8)

        # 每点一次后检测有没有"采集"弹窗
        if find_text(
            "采集", x_pct_start=0.3, x_pct_end=0.8, y_pct_start=0.6, y_pct_end=0.9
        ):
            return  # 已经点到了，不用再点了
    time.sleep(random.uniform(0.5, 0.8))


# ============================================================
#  挂机逻辑 - 盾牌模式（原 bot_main）
# ============================================================


def bot_loop_shield(app):
    pyautogui.FAILSAFE = True
    step = 1
    fail_count = 0
    app._log("🛡️ 盾牌模式启动，2秒后开始...")
    found = auto_detect_region()
    if found:
        app._log(f"✅ 检测到窗口「{found}」")
    else:
        app._log("⚠️ 未检测到游戏窗口，使用全屏模式")
    if OCR_AVAILABLE:
        app._log("🔤 OCR文字识别已就绪（首次识别需1-2秒加载）")
    else:
        app._log("⚠️ OCR 未安装，请 pip install rapidocr_onnxruntime")
    time.sleep(2)

    while app.running:
        if time.time() - app.start_time > app.trial_limit:
            app._log("⏰ 试用时间已到")
            app.root.after(0, app._stop)
            break
        try:
            x, y = pyautogui.position()
            if x <= 5 and y <= 5:
                app._log("🛑 紧急停止")
                app.root.after(0, app._stop)
                break
        except:
            pass

        time.sleep(0.1)
        success = False

        for popup_img in ["close.png", "close2.png", "cancel.png"]:
            popup = find_img(popup_img)
            if popup:
                center = _center_of(popup)
                px, py = center
                pyautogui.click(px, py)
                app._log("关闭弹窗")
                time.sleep(1)
                break
        else:
            if step == 1:
                if click_text("搜索"):
                    app._log("✅ 步骤1：搜索")
                    step = 2
                    success = True
            elif step == 2:
                if click_text("特殊"):
                    app._log("✅ 步骤2：特殊")
                    step = 3
                    success = True
            elif step == 3:
                if click_text("召唤"):
                    app._log("✅ 步骤3：召唤，等待集结...")
                    success = True
                    if wait_for_text("集结", timeout=2):
                        step = 4
                    app._log("⏳ 还在等集结...")

            elif step == 4:
                # 弹窗里的集结按钮，限定在窗口下60%找，避免被上方文字干扰
                pos = find_text_in_region("集结", y_pct_start=0.7, y_pct_end=1.0)
                if pos:
                    cx, cy = pos
                    pyautogui.click(
                        cx + random.randint(-8, 8), cy + random.randint(-5, 5)
                    )
                    time.sleep(random.uniform(0.2, 0.3))
                    app._log("✅ 步骤4：集结")
                    step = 5
                    success = True

            elif step == 5:
                # 出发按钮也限定在下半区找
                pos = find_text_in_region("出发", y_pct_start=0.4, y_pct_end=0.9)
                if pos:
                    cx, cy = pos
                    pyautogui.click(
                        cx + random.randint(-8, 8), cy + random.randint(-5, 5)
                    )
                    time.sleep(random.uniform(0.5, 0.7))
                    app._log("✅ 步骤5：出发！重新开始")
                    step = 1
                    success = True

            if success:
                fail_count = 0
            else:
                fail_count += 1
                app._log(f"步骤{step} 失败 {fail_count}次")
                time.sleep(0.3)
            if fail_count >= 5:
                app._log("🔄 卡住，重置")
                step = 1
                fail_count = 0


# ============================================================
#  挂机逻辑 - 泰坦模式（原 test2）
# ============================================================


def bot_loop_titan(app):
    pyautogui.FAILSAFE = True
    step = 1
    fail_count = 0
    app._log("⚔️ 泰坦模式启动，2秒后开始...")
    found = auto_detect_region()
    if found:
        app._log(f"✅ 检测到窗口「{found}」")
    else:
        app._log("⚠️ 未检测到游戏窗口，使用全屏模式")
    if OCR_AVAILABLE:
        app._log("🔤 OCR文字识别已就绪（首次识别需1-2秒加载）")
    time.sleep(2)

    while app.running:
        if time.time() - app.start_time > app.trial_limit:
            app._log("⏰ 试用时间已到")
            app.root.after(0, app._stop)
            break
        try:
            x, y = pyautogui.position()
            if x <= 5 and y <= 5:
                app._log("🛑 紧急停止")
                app.root.after(0, app._stop)
                break
        except:
            pass

        time.sleep(0.1)
        success = False

        for popup_img in ["close.png"]:
            popup = find_img(popup_img)
            if popup:
                center = _center_of(popup)
                px, py = center
                pyautogui.click(px, py)
                app._log("关闭弹窗")
                time.sleep(1)
                break
        else:
            if step == 1:
                if click_text("搜索"):
                    app._log("✅ 步骤1：搜索")
                    step = 2
                    success = True
            elif step == 2:
                # 集结按钮限定在下半区找
                pos = find_text_in_region("集结", y_pct_start=0.1, y_pct_end=0.5)
                if pos:
                    cx, cy = pos
                    pyautogui.click(
                        cx + random.randint(-8, 8), cy + random.randint(-5, 5)
                    )
                    time.sleep(random.uniform(0.2, 0.3))
                    app._log("✅ 步骤2：集结按钮")
                    step = 3
                    success = True
            elif step == 3:
                if click_text("搜索"):
                    app._log("✅ 步骤3：搜索2，等待出发...")
                    success = True
                    if wait_for_text("集结", timeout=2):
                        step = 4
                    else:
                        app._log("⚠️ 超时，重置")
                        step = 1
            elif step == 4:
                pos = find_text_in_region("集结", y_pct_start=0.6, y_pct_end=1.0)
                if pos:
                    cx, cy = pos
                    pyautogui.click(
                        cx + random.randint(-8, 8), cy + random.randint(-5, 5)
                    )
                    time.sleep(random.uniform(0.3, 0.4))  # 等弹窗出现
                    app._log("✅ 步骤4：点击集结")

                    # 检测有没有"确认"弹窗（如果有就处理，没有就直接进 step5）
                    confirm_pos = find_text_in_region(
                        "确认", y_pct_start=0.4, y_pct_end=0.7
                    )
                    if confirm_pos:
                        fx, fy = confirm_pos
                        pyautogui.click(
                            fx + random.randint(-8, 8), fy + random.randint(-5, 5)
                        )
                        time.sleep(random.uniform(0.3, 0.4))
                        app._log("   → 检测到确认弹窗，已点击确认")

                    # 不管有没有弹窗，进入 step5 让它去点出发
                    step = 5
                    success = True
            elif step == 5:
                pos = find_text_in_region("出发", y_pct_start=0.5, y_pct_end=1.0)
                if pos:
                    cx, cy = pos
                    pyautogui.click(
                        cx + random.randint(-8, 8), cy + random.randint(-5, 5)
                    )
                    time.sleep(random.uniform(0.4, 0.6))  # 等弹窗出现
                    app._log("✅ 步骤5：点击出发")

                    # 🔍 检测是否有"使用"弹窗（体力不足提示等）
                    use_pos = find_text("使用")
                    if use_pos:
                        app._log("⚠️ 检测到'使用'弹窗")
                        # 1. 点击"使用"
                        ux, uy = use_pos
                        pyautogui.click(
                            ux + random.randint(-8, 8), uy + random.randint(-5, 5)
                        )
                        app._log("   → 点击使用")
                        time.sleep(random.uniform(0.4, 0.6))

                        # 2. 点击 X 关闭弹窗
                        closed = False
                        for close_img in [
                            "close.png",
                            "close2.png",
                            "close3.png",
                            "cancel.png",
                            "close4.png",
                        ]:
                            close_pos = find_img(close_img)
                            if close_pos:
                                ccx, ccy = _center_of(close_pos)
                                pyautogui.click(ccx, ccy)
                                app._log("   → 关闭弹窗 X")
                                time.sleep(random.uniform(0.5, 0.8))
                                closed = True
                                break
                        if not closed:
                            app._log("   ⚠️ 未找到关闭按钮")

                        # 3. 重新点击"出发"
                        pos2 = find_text_in_region(
                            "出发", y_pct_start=0.5, y_pct_end=1.0
                        )
                        if pos2:
                            cx2, cy2 = pos2
                            pyautogui.click(
                                cx2 + random.randint(-8, 8),
                                cy2 + random.randint(-5, 5),
                            )
                            app._log("   → 重新点击出发")
                            time.sleep(random.uniform(0.5, 0.8))
                            app._log("✅ 步骤5完成（处理了使用弹窗）！重新开始")
                        else:
                            app._log("   ⚠️ 重新点击出发失败")
                    else:
                        # 没有弹窗，直接完成
                        app._log("✅ 步骤5完成！重新开始")

                    step = 1
                    success = True

            if success:
                fail_count = 0
            else:
                fail_count += 1
                app._log(f"步骤{step} 失败 {fail_count}次")
                time.sleep(0.2)
            if fail_count >= 5:
                app._log("🔄 卡住，重置")
                step = 1
                fail_count = 0


# ============================================================
#  挂机逻辑 - 采集模式
# ============================================================


def bot_loop_collect(app):
    pyautogui.FAILSAFE = True
    step = 1
    fail_count = 0
    app._log("⛏️ 采集模式启动，2秒后开始...")
    found = auto_detect_region()
    if found:
        app._log(f"✅ 检测到窗口「{found}」")
    else:
        app._log("⚠️ 未检测到游戏窗口，使用全屏模式")
    if OCR_AVAILABLE:
        app._log("🔤 OCR文字识别已就绪")
    time.sleep(2)

    while app.running:
        if time.time() - app.start_time > app.trial_limit:
            app._log("⏰ 试用时间已到")
            app.root.after(0, app._stop)
            break
        try:
            x, y = pyautogui.position()
            if x <= 5 and y <= 5:
                app._log("🛑 紧急停止")
                app.root.after(0, app._stop)
                break
        except:
            pass

        time.sleep(0.1)
        success = False

        if step == 1:
            auto_detect_region()
            # 检测队伍状态
            app._log("🔍 检测队伍状态...")
            status = check_team_status()
            if status is None:
                app._log("⚠️ 未识别到队伍数，默认放行")
            else:
                current, total = status
                app._log(f"🔍 队伍：{current}/{total}")
                if current >= total:
                    # 队伍满了
                    shortest = get_shortest_collect_time()
                    if shortest is None:
                        wait_seconds = 30
                        app._log("⚠️ 未找到采集时间，等30秒")
                    else:
                        wait_seconds = shortest + 30
                        mins = wait_seconds // 30
                        secs = wait_seconds % 30
                        app._log(f"💤 队伍已满，等待 {mins}分{secs}秒...")

                    # 可中断睡眠
                    slept = 0
                    interrupted = False
                    while slept < wait_seconds and app.running:
                        try:
                            mx, my = pyautogui.position()
                            if mx <= 5 and my <= 5:
                                app._log("🛑 紧急停止")
                                app.root.after(0, app._stop)
                                interrupted = True
                                break
                        except:
                            pass
                        time.sleep(1)
                        slept += 1
                    if interrupted or not app.running:
                        break
                    app._log("⏰ 等待结束，重新检测")
                    continue  # 跳回循环顶部重新检测

            # 队伍有空闲，点搜索
            if click_text("搜索"):
                app._log("✅ 步骤1：点击搜索")
                step = 2
                success = True

        elif step == 2:
            if click_text("采集"):
                app._log("✅ 步骤2：点击采集")
                step = 3
                success = True

        elif step == 3:
            if click_text("搜索", y_pct_start=0.5, y_pct_end=0.8):
                app._log("✅ 步骤3：点击搜索（中下部）")
                time.sleep(random.uniform(1.0, 1.5))
                step = 4
                success = True

        elif step == 4:
            click_window_center()
            app._log("✅ 步骤4：点击窗口中心（采集点）")
            time.sleep(random.uniform(0.8, 1.2))

            # 等弹窗里的"采集"
            found_popup = False
            for _ in range(3):
                if find_text(
                    "采集",
                    x_pct_start=0.4,
                    x_pct_end=0.7,
                    y_pct_start=0.6,
                    y_pct_end=1.0,
                ):
                    found_popup = True
                    break
                time.sleep(1)

            if found_popup:
                step = 5
                success = True
            else:
                app._log("⚠️ 没等到采集弹窗，重置")
                step = 1

        elif step == 5:
            if click_text(
                "采集", x_pct_start=0.4, x_pct_end=0.7, y_pct_start=0.6, y_pct_end=1.0
            ):
                app._log("✅ 步骤5：点击采集（弹窗）")
                time.sleep(random.uniform(1.5, 2.0))
                step = 6
                success = True

        elif step == 6:
            # 调试：打印整个屏幕识别到的文字

            if click_text(
                "出发", x_pct_start=0.4, x_pct_end=1.0, y_pct_start=0.4, y_pct_end=0.9
            ):
                app._log("✅ 步骤6：出发！一轮完成")
                time.sleep(random.uniform(0.8, 1.2))
                step = 1
                success = True

        if success:
            fail_count = 0
        else:
            fail_count += 1
            app._log(f"步骤{step} 失败 {fail_count}次")
            time.sleep(0.3)
        if fail_count >= 5:
            app._log("🔄 卡住，重置")
            step = 1
            fail_count = 0


# ============================================================
#  GUI
# ============================================================


class BotApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("挂机助手 v2.0")
        self.root.geometry("800x1400")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f0f1a")

        self.running = False
        self.thread = None
        self.plan_var = tk.StringVar(value="trial")
        self.mode = None  # "shield" 或 "titan"
        self._cached_key = ""
        self._cached_plan = ""

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动时自动加载上次保存的授权码
        self._auto_load_license()

    def _auto_load_license(self):
        """自动填入上次的授权码"""
        saved_key, saved_plan = load_license()
        if saved_key and saved_plan:
            self.plan_var.set(saved_plan)
            self._on_plan_change()
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, saved_key)

    # ----------------------------------------------------------
    def _build_ui(self):
        BG = "#0f0f1a"
        CARD = "#16213e"
        ACCENT = "#0f3460"
        GREEN = "#4ade80"
        YELLOW = "#fbbf24"
        BLUE = "#60a5fa"
        ORANGE = "#fb923c"
        FG = "#e2e8f0"
        GRAY = "#64748b"

        # ── 顶部标题 ──
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(
            header,
            text="⚙️ 挂机助手",
            font=("Microsoft YaHei", 18, "bold"),
            bg=BG,
            fg=GREEN,
        ).pack(side="left")
        tk.Label(header, text="v2.0", font=("Microsoft YaHei", 9), bg=BG, fg=GRAY).pack(
            side="left", padx=6, pady=4
        )

        # ── 模式选择（两个大按钮）──
        mode_label = tk.Label(
            self.root,
            text="选择模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg=BG,
            fg=GRAY,
        )
        mode_label.pack(anchor="w", padx=22, pady=(8, 4))

        mode_frame = tk.Frame(self.root, bg=BG)
        mode_frame.pack(fill="x", padx=20, pady=(0, 10))

        # 盾牌按钮
        self.shield_btn = tk.Button(
            mode_frame,
            text="🛡️\n盾牌模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg=CARD,
            fg=BLUE,
            width=8,
            height=3,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground=BLUE,
            command=lambda: self._select_mode("shield"),
        )
        self.shield_btn.pack(side="left", padx=(0, 6), expand=True, fill="x")

        # 泰坦按钮
        self.titan_btn = tk.Button(
            mode_frame,
            text="⚔️\n泰坦模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg=CARD,
            fg=ORANGE,
            width=8,
            height=3,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground=ORANGE,
            command=lambda: self._select_mode("titan"),
        )
        self.titan_btn.pack(side="left", padx=(0, 6), expand=True, fill="x")

        # 采集按钮
        self.collect_btn = tk.Button(
            mode_frame,
            text="⛏️\n采集模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg=CARD,
            fg="#22c55e",  # 绿色
            width=8,
            height=3,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground="#22c55e",
            command=lambda: self._select_mode("collect"),
        )
        self.collect_btn.pack(side="left", expand=True, fill="x")

        # 模式描述
        self.mode_desc = tk.Label(
            self.root,
            text="← 请选择一个模式开始",
            font=("Microsoft YaHei", 9),
            bg=BG,
            fg=GRAY,
        )
        self.mode_desc.pack(pady=(0, 6))

        # ── 分隔线 ──
        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill="x", padx=20, pady=4)

        # ── 套餐选择 ──
        pc = tk.Frame(self.root, bg=CARD)
        pc.pack(fill="x", padx=20, pady=8)

        tk.Label(
            pc, text="选择套餐", font=("Microsoft YaHei", 10, "bold"), bg=CARD, fg=FG
        ).pack(anchor="w", padx=15, pady=(10, 4))

        plans = [
            ("🆓  免费试用（0.5小时）", "trial", GRAY),
            ("📅  周卡   12", "week", YELLOW),
            ("👑  月卡  30", "month", GREEN),
        ]
        plan_row = tk.Frame(pc, bg=CARD)
        plan_row.pack(fill="x", padx=15, pady=(0, 4))
        for text, val, color in plans:
            tk.Radiobutton(
                plan_row,
                text=text,
                variable=self.plan_var,
                value=val,
                font=("Microsoft YaHei", 9),
                bg=CARD,
                fg=color,
                selectcolor=ACCENT,
                activebackground=CARD,
                activeforeground=color,
                command=self._on_plan_change,
            ).pack(anchor="w")

        tk.Frame(pc, bg=ACCENT, height=1).pack(fill="x", padx=15, pady=6)

        # 授权码
        kf = tk.Frame(pc, bg=CARD)
        kf.pack(fill="x", padx=15, pady=(0, 6))
        tk.Label(kf, text="授权码：", font=("Microsoft YaHei", 9), bg=CARD, fg=FG).pack(
            side="left"
        )
        self.key_entry = tk.Entry(
            kf,
            width=24,
            font=("Consolas", 9),
            bg=ACCENT,
            fg=GREEN,
            insertbackground=GREEN,
            relief="flat",
            bd=4,
            state="disabled",
        )
        self.key_entry.pack(side="left", padx=6)

        # 设备码
        mid = get_machine_id()
        mid_f = tk.Frame(pc, bg=CARD)
        mid_f.pack(fill="x", padx=15, pady=(0, 10))
        tk.Label(
            mid_f,
            text=f"设备码：{mid}",
            font=("Consolas", 7),
            bg=CARD,
            fg=GRAY,
            wraplength=370,
            justify="left",
        ).pack(anchor="w")

        # ── 开始/停止 按钮 ──
        self.start_btn = tk.Button(
            self.root,
            text="▶  选择模式后开始",
            font=("Microsoft YaHei", 12, "bold"),
            bg=GRAY,
            fg="#0f172a",
            width=20,
            height=2,
            relief="flat",
            cursor="hand2",
            state="disabled",
            command=self._toggle,
        )
        self.start_btn.pack(pady=8)

        # ── 状态栏 ──
        sf = tk.Frame(self.root, bg=CARD)
        sf.pack(fill="x", padx=20, pady=(0, 6))
        tk.Label(sf, text="状态：", font=("Microsoft YaHei", 9), bg=CARD, fg=GRAY).pack(
            side="left", padx=10, pady=5
        )
        self.status_label = tk.Label(
            sf, text="等待启动", font=("Microsoft YaHei", 9, "bold"), bg=CARD, fg=YELLOW
        )
        self.status_label.pack(side="left")
        self.timer_label = tk.Label(sf, text="", font=("Consolas", 9), bg=CARD, fg=GRAY)
        self.timer_label.pack(side="right", padx=10)

        # ── 日志 ──
        lf = tk.Frame(self.root, bg=CARD)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        tk.Label(
            lf, text="运行日志", font=("Microsoft YaHei", 8), bg=CARD, fg=GRAY
        ).pack(anchor="w", padx=10, pady=(6, 2))
        self.log_text = tk.Text(
            lf,
            height=6,
            font=("Consolas", 8),
            bg="#0d1117",
            fg="#7ee787",
            relief="flat",
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    # ----------------------------------------------------------
    def _select_mode(self, mode):
        if self.running:
            return  # 运行中不允许切换

        CARD = "#16213e"
        ACCENT = "#0f3460"
        BLUE = "#60a5fa"
        ORANGE = "#fb923c"
        GREEN = "#4ade80"

        self.mode = mode
        COLLECT_GREEN = "#22c55e"
        if mode == "shield":
            self.shield_btn.config(bg=ACCENT, relief="sunken")
            self.titan_btn.config(bg=CARD, relief="flat")
            self.collect_btn.config(bg=CARD, relief="flat")
            self.mode_desc.config(text="🛡️ 盾牌模式：副本挂机", fg=BLUE)
            self.start_btn.config(
                text="▶  启动盾牌模式", bg=BLUE, fg="#0f172a", state="normal"
            )
        elif mode == "titan":
            self.titan_btn.config(bg=ACCENT, relief="sunken")
            self.shield_btn.config(bg=CARD, relief="flat")
            self.collect_btn.config(bg=CARD, relief="flat")
            self.mode_desc.config(text="⚔️ 泰坦模式：泰坦挂机", fg=ORANGE)
            self.start_btn.config(
                text="▶  启动泰坦模式", bg=ORANGE, fg="#0f172a", state="normal"
            )
        else:  # collect
            self.collect_btn.config(bg=ACCENT, relief="sunken")
            self.shield_btn.config(bg=CARD, relief="flat")
            self.titan_btn.config(bg=CARD, relief="flat")
            self.mode_desc.config(text="⛏️ 采集模式：自动采集", fg=COLLECT_GREEN)
            self.start_btn.config(
                text="▶  启动采集模式", bg=COLLECT_GREEN, fg="#0f172a", state="normal"
            )

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
        if not self.mode:
            messagebox.showwarning("提示", "请先选择模式")
            return

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

        # 验证成功后保存授权码（试用不保存）
        if plan != "trial" and key:
            save_license(key, plan)

        mode_names = {"shield": "盾牌", "titan": "泰坦", "collect": "采集"}
        mode_name = mode_names.get(self.mode, "盾牌")
        self._log(f"✅ 授权通过 [{plan}] {reason}")
        self._log(f"🚀 启动{mode_name}模式")

        self.running = True
        self.start_time = time.time()

        # 试用用服务器返回的剩余秒数
        if plan == "trial":
            # 从 reason 里解析剩余分钟："试用剩余 60 分钟"
            try:
                mins = int(reason.split("剩余")[1].split("分钟")[0].strip())
                self.trial_limit = mins * 60
            except:
                self.trial_limit = TRIAL_SECONDS
        else:
            self.trial_limit = float("inf")

        self.start_btn.config(text="⏹  停 止", bg="#f87171", fg="white")
        self.shield_btn.config(state="disabled")
        self.titan_btn.config(state="disabled")
        self.collect_btn.config(state="disabled")
        self._set_status(f"{mode_name}模式运行中", "#4ade80")

        targets = {
            "shield": bot_loop_shield,
            "titan": bot_loop_titan,
            "collect": bot_loop_collect,
        }
        target = targets.get(self.mode, bot_loop_shield)
        self.thread = threading.Thread(target=target, args=(self,), daemon=True)
        self.thread.start()
        self._tick()

    def _stop(self):
        self.running = False
        mode_colors = {
            "shield": ("盾牌", "#60a5fa"),
            "titan": ("泰坦", "#fb923c"),
            "collect": ("采集", "#22c55e"),
        }
        name, color = mode_colors.get(self.mode, ("盾牌", "#60a5fa"))
        self.start_btn.config(
            text="▶  启动" + name + "模式",
            bg=color,
            fg="#0f172a",
        )
        self.shield_btn.config(state="normal")
        self.titan_btn.config(state="normal")
        self.collect_btn.config(state="normal")
        self._set_status("已停止", "#64748b")
        self.timer_label.config(text="")
        self._log("⏹ 已停止")

    def _tick(self):
        if not self.running:
            return
        elapsed = int(time.time() - self.start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self.timer_label.config(text=f"⏱ {h:02d}:{m:02d}:{s:02d}")

        if self.trial_limit != float("inf"):
            remain = int(self.trial_limit - elapsed)
            if 0 < remain <= 300 and remain % 60 == 0:
                self._log(f"⚠️ 试用剩余 {remain//60} 分钟")

        if elapsed > 0 and elapsed % HEARTBEAT_INTERVAL == 0:
            threading.Thread(target=self._heartbeat, daemon=True).start()

        self.root.after(1000, self._tick)

    def _heartbeat(self):
        if self._cached_plan == "trial":
            return
        ok, reason = verify_license(self._cached_key, self._cached_plan)
        if not ok:
            self._log(f"🚫 授权失效：{reason}")
            self.root.after(0, self._stop)

    def _on_close(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BotApp()
    app.run()
