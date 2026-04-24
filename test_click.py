import time
import random
import pyautogui
from bot_main import find_text_in_region

# 你已有的函数（必须能用）
# from your_module import find_text_in_region


def test_click():
    print("开始测试... 3秒后执行")
    time.sleep(3)

    for i in range(10):  # 尝试10次
        result = find_text_in_region("集结", y_pct_start=0.7, y_pct_end=1.0)

        if result:
            cx, cy = result
            print(f"找到集结: {cx}, {cy}")

            # 🔥 直接偏移点击（核心）
            click_x = cx + random.randint(-5, 5)
            click_y = cy + 30 + random.randint(-5, 5)

            print(f"点击位置: {click_x}, {click_y}")

            pyautogui.click(click_x, click_y)
            return

        else:
            print("没找到，重试...")
            time.sleep(1)

    print("测试失败：始终没找到")


if __name__ == "__main__":
    test_click()
