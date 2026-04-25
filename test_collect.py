"""
采集模式测试脚本（独立运行）
流程：
  step1: 点"搜索"
  step2: 点"采集"
  step3: 点"搜索"（位置在屏幕Y轴 50%-80%）
  step4: 点游戏窗口中心（采集点图标）
  step5: 点"采集"（弹窗）
  step6: 点"出发"
  → 循环
"""

import time
import random
import re
import sys
import os
import msvcrt
import pyautogui
import mss
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
import pygetwindow as gw

# ============================================================
#  配置
# ============================================================

# 游戏窗口标题（按优先级）
GAME_WINDOW_TITLES = [
    "指尖王国",
    "小游戏",
    "LDPlayer",
    "雷电模拟器",
    "MuMu",
    "MuMu模拟器",
    "BlueStacks",
    "微信",
]

# 全局
region = None  # 游戏窗口区域 (left, top, width, height)
_sct = mss.mss()
_ocr = None  # 延迟加载


# ============================================================
#  工具函数
# ============================================================


def get_ocr():
    global _ocr
    if _ocr is None:
        print("🔤 加载 OCR 模型...")
        _ocr = RapidOCR()
        print("🔤 OCR 已就绪")
    return _ocr


def auto_detect_region():
    """自动检测游戏窗口"""
    global region
    all_matches = []
    for title in GAME_WINDOW_TITLES:
        try:
            wins = gw.getWindowsWithTitle(title)
            for w in wins:
                if w.width > 300 and w.height > 300:
                    is_portrait = w.height > w.width
                    score = w.width * w.height
                    if is_portrait:
                        score *= 2
                    all_matches.append((score, title, w))
        except:
            continue

    if all_matches:
        all_matches.sort(key=lambda x: -x[0])
        _, title, w = all_matches[0]
        region = (
            max(0, w.left + 10),
            max(0, w.top + 10),
            w.width - 20,
            w.height - 20,
        )
        return f"{title} ({w.width}x{w.height})"
    region = None
    return None


def screenshot():
    """截图返回 BGR 图像"""
    if region:
        mon = {
            "left": region[0],
            "top": region[1],
            "width": region[2],
            "height": region[3],
        }
    else:
        mon = _sct.monitors[1]
    img = np.array(_sct.grab(mon))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def find_text(
    target_text,
    y_pct_start=0.0,
    y_pct_end=1.0,
    x_pct_start=0.0,
    x_pct_end=1.0,
    conf=0.5,
):
    """
    在屏幕(或游戏窗口)的指定Y范围内找文字
    y_pct_start, y_pct_end: 0.0~1.0，表示Y轴百分比范围
    返回 (绝对x, 绝对y) 或 None
    """
    try:
        ocr = get_ocr()
        img = screenshot()
        h, w = img.shape[:2]

        # 裁剪 Y 范围
        y_start = int(h * y_pct_start)
        y_end = int(h * y_pct_end)
        x_start = int(w * x_pct_start)
        x_end = int(w * x_pct_end)
        cropped = img[y_start:y_end, x_start:x_end]

        result, _ = ocr(cropped)
        if not result:
            return None

        # 调试：打印第一次的格式（只打印一次）
        global _debug_printed
        if not _debug_printed:
            print(f"   类型: {type(result)}")
            if len(result) > 0:
                print(f"   第一项: {result[0]}")
                print(f"   第一项类型: {type(result[0])}")
            _debug_printed = True

        for item in result:
            # 安全解析：只取 box 和 text，忽略 score
            try:
                box = item[0]
                # 找出哪个是字符串（text）
                text = None
                for x in item[1:]:
                    if isinstance(x, str):
                        # 跳过明显是数字字符串的（score）
                        try:
                            float(x)
                            continue  # 是数字字符串，跳过
                        except ValueError:
                            text = x  # 真正的文字
                            break
                if text is None:
                    continue

                if target_text in text:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    cx = int(sum(xs) / 4) + x_start
                    cy = int(sum(ys) / 4) + y_start

                    if region:
                        cx += region[0]
                        cy += region[1]
                    return (cx, cy)
            except Exception as e2:
                print(f"  解析单项错误: {e2}")
                continue
    except Exception as e:
        print(f"OCR 错误: {e}")
    return None


_debug_printed = False


def click_at(x, y, jitter=8):
    """点击坐标（带随机抖动）"""
    pyautogui.click(
        x + random.randint(-jitter, jitter),
        y + random.randint(-jitter // 2, jitter // 2),
    )


def click_text(
    target_text, y_pct_start=0.0, y_pct_end=1.0, x_pct_start=0.0, x_pct_end=1.0
):
    pos = find_text(target_text, y_pct_start, y_pct_end, x_pct_start, x_pct_end)
    if pos:
        click_at(*pos)
        time.sleep(random.uniform(0.5, 0.8))
        return True
    return False


def click_window_center():
    """点击游戏窗口的正中心"""
    if region:
        cx = region[0] + region[2] // 2
        cy = region[1] + region[3] // 2
    else:
        # 没识别到窗口时用屏幕中心
        screen_w, screen_h = pyautogui.size()
        cx = screen_w // 2
        cy = screen_h // 2
    print(f"🎯 点击窗口中心 ({cx}, {cy})")
    click_at(cx, cy)
    time.sleep(random.uniform(0.5, 0.8))


def wait_for_text(
    target_text,
    timeout=8,
    y_pct_start=0.0,
    y_pct_end=1.0,
    x_pct_start=0.0,
    x_pct_end=1.0,
):
    for _ in range(timeout):
        if find_text(target_text, y_pct_start, y_pct_end, x_pct_start, x_pct_end):
            return True
        time.sleep(1)
    return False


# ============================================================
#  队伍数 & 采集时间检测
# ============================================================


def get_all_texts_in_region(
    x_pct_start=0.0, x_pct_end=1.0, y_pct_start=0.0, y_pct_end=1.0
):
    """获取指定区域内所有 OCR 识别到的文字（返回字符串列表）"""
    texts = []
    try:
        ocr = get_ocr()
        img = screenshot()
        h, w = img.shape[:2]

        y_start = int(h * y_pct_start)
        y_end = int(h * y_pct_end)
        x_start = int(w * x_pct_start)
        x_end = int(w * x_pct_end)
        cropped = img[y_start:y_end, x_start:x_end]

        result, _ = ocr(cropped)
        if not result:
            return texts

        for item in result:
            for x in item[1:]:
                if isinstance(x, str):
                    try:
                        float(x)
                        continue  # 是 score 字符串
                    except ValueError:
                        texts.append(x)
                        break
    except Exception as e:
        print(f"OCR 区域识别错误: {e}")
    return texts


def check_team_status():
    """
    检测队伍数（如 1/8）
    返回 (current, total) 或 None
    """
    texts = get_all_texts_in_region(
        x_pct_start=0.0,
        x_pct_end=0.3,
        y_pct_start=0.22,
        y_pct_end=0.33,
    )

    print(f"🔍 队伍区域识别到: {texts}")  # 调试

    for text in texts:
        clean = text.replace(" ", "")
        match = re.search(r"(\d+)\s*/\s*(\d+)", clean)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            # 队伍数最多 10，排除体力/能量等大数字
            if total > 10:
                continue
            return (current, total)
    return None


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
    shortest_str, shortest_sec = all_seconds[0]
    print(f"   找到 {len(all_seconds)} 个时间，最短：{shortest_str} = {shortest_sec}秒")
    return shortest_sec


def smart_sleep(seconds):
    """可中断的睡眠（支持紧急停止 + q退出）"""
    for _ in range(int(seconds)):
        try:
            x, y = pyautogui.position()
            if x <= 5 and y <= 5:
                print("🛑 紧急停止")
                return False
        except:
            pass
        if msvcrt.kbhit() and msvcrt.getch() == b"q":
            print("退出")
            return False
        time.sleep(1)
    return True


def wait_until_team_available():
    """队伍满时智能等待，返回 True=有空闲，False=用户中断"""
    while True:
        status = check_team_status()
        if status is None:
            print("⚠️ 未识别到队伍数，默认放行（A方案）")
            return True

        current, total = status
        print(f"🔍 队伍状态：{current}/{total}")

        if current < total:
            print(f"✅ 检测到空闲队伍 ({current}/{total})")
            return True

        # 满了，找时间
        shortest = get_shortest_collect_time()
        if shortest is None:
            print("⚠️ 队伍已满但未找到采集时间，等60秒后重试")
            wait_seconds = 60
        else:
            wait_seconds = shortest + 60
            mins = wait_seconds // 60
            secs = wait_seconds % 60
            print(f"💤 队伍已满，等待 {mins}分{secs}秒（含60秒缓冲）...")

        if not smart_sleep(wait_seconds):
            return False
        print("⏰ 等待结束，重新检测队伍...\n")


# ============================================================
#  主循环
# ============================================================


def main():
    pyautogui.FAILSAFE = True

    # 检测窗口
    found = auto_detect_region()
    if found:
        print(f"✅ 检测到窗口「{found}」")
    else:
        print("⚠️ 未检测到游戏窗口，使用全屏模式")

    # 预加载 OCR
    get_ocr()

    print("\n5秒后开始采集挂机...（按 q 退出，鼠标移到左上角紧急停止）\n")
    time.sleep(5)

    step = 1
    fail_count = 0

    while True:
        # 紧急停止：鼠标到左上角
        try:
            x, y = pyautogui.position()
            if x <= 5 and y <= 5:
                print("🛑 紧急停止")
                break
        except:
            pass

        # 按 q 退出
        if msvcrt.kbhit() and msvcrt.getch() == b"q":
            print("退出")
            break

        time.sleep(0.1)
        success = False

        # ============= 步骤机 =============
        if step == 1:
            # 第一次点搜索前，先检测队伍是否有空闲
            print("🔍 检测队伍状态...")
            if not wait_until_team_available():
                # 用户中断
                break

            # 第一次点搜索（位置不限）
            if click_text("搜索"):
                print("✅ 步骤1：点击搜索")
                step = 2
                success = True

        elif step == 2:
            # 点采集
            if click_text("采集"):
                print("✅ 步骤2：点击采集")
                step = 3
                success = True

        elif step == 3:
            # 第二次点搜索，位置限定 Y 50%-80%
            if click_text("搜索", y_pct_start=0.5, y_pct_end=0.8):
                print("✅ 步骤3：点击搜索（中下部）")
                time.sleep(random.uniform(1.0, 1.5))  # 等地图定位
                step = 4
                success = True

        elif step == 4:
            # 点游戏窗口中心（采集点图标）
            click_window_center()
            print("✅ 步骤4：点击窗口中心（采集点）")
            time.sleep(random.uniform(0.8, 1.2))  # 等弹窗

            # 等"采集"文字出现（弹窗）
            if wait_for_text(
                "采集",
                x_pct_start=0.4,
                x_pct_end=0.7,
                y_pct_start=0.6,
                y_pct_end=1.0,
                timeout=3,
            ):
                step = 5
                success = True
            else:
                print("⚠️ 没等到采集弹窗，重置")
                step = 1

        elif step == 5:
            # 点弹窗里的"采集"
            if click_text(
                "采集", x_pct_start=0.4, x_pct_end=0.7, y_pct_start=0.6, y_pct_end=1.0
            ):
                print("✅ 步骤5：点击采集（弹窗）")
                step = 6
                success = True

        elif step == 6:
            # 点出发
            if click_text("出发"):
                print("✅ 步骤6：点击出发！一轮完成\n")
                step = 1
                success = True

        # ============= 失败处理 =============
        if success:
            fail_count = 0
        else:
            fail_count += 1
            print(f"步骤{step} 失败 {fail_count}次")
            time.sleep(0.3)

        if fail_count >= 5:
            print("🔄 卡住，重置流程\n")
            step = 1
            fail_count = 0


if __name__ == "__main__":
    main()
