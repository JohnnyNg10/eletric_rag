from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import csv
import re

# ========== 配置项 ==========
BASE_LIST_URL = "https://openstd.samr.gov.cn/bzgk/std/std_list_type?r=0.34940398036872067&p.p1={page}&p.p5=PUBLISHED&p.p6=29&p.p90=circulation_date&p.p91=desc"
TOTAL_PAGE = 5
START_PAGE = 4  # 【关键】从第4页开始续跑，不用重新跑前3页
SAVE_FILE = "电力国标清单_含hcno.csv"
PAGE_INTERVAL = 6  # 加长到6秒，降低风控概率
MAX_RETRY = 3     # 单页最大重试次数

# ========== 启动浏览器 ==========
driver = webdriver.Chrome()
all_std = []
hcno_pattern = re.compile(r"showInfo\('([A-Z0-9]+)'\)")

def save_result():
    """保存当前已采集的数据，异常时也不会丢失"""
    with open(SAVE_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["标准号", "标准名称", "hcno", "详情页链接", "下载链接"])
        writer.writeheader()
        writer.writerows(all_std)
    print(f"💾 已保存当前进度，共 {len(all_std)} 条")

try:
    for page in range(START_PAGE, TOTAL_PAGE + 1):
        url = BASE_LIST_URL.format(page=page)
        print(f"\n正在处理第 {page}/{TOTAL_PAGE} 页")

        retry = 0
        page_success = False
        while retry <= MAX_RETRY and not page_success:
            try:
                driver.get(url)
                # 等待「查看详细」按钮出现
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//button[text()='查看详细']"))
                )
                time.sleep(2)
                print("  页面加载完成，开始提取数据...")

                # 提取数据行
                rows = driver.find_elements(By.XPATH, "//table[contains(@class,'result_list')]/tbody[2]/tr")
                print(f"  当前页找到 {len(rows)} 条标准")

                for row in rows:
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) < 4:
                        continue

                    std_no = tds[1].text.strip()
                    std_name = tds[3].text.strip()

                    try:
                        btn = tds[-1].find_element(By.TAG_NAME, "button")
                        onclick_text = btn.get_attribute("onclick")
                        match = hcno_pattern.search(onclick_text)
                        hcno = match.group(1) if match else ""
                    except:
                        hcno = ""

                    detail_url = f"https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno={hcno}"
                    download_url = f"https://openstd.samr.gov.cn/bzgk/std/showGb?type=download&hcno={hcno}&request_locale=zh"

                    all_std.append({
                        "标准号": std_no,
                        "标准名称": std_name,
                        "hcno": hcno,
                        "详情页链接": detail_url,
                        "下载链接": download_url
                    })
                    print(f"    已采集：{std_no}")

                page_success = True
                save_result()
                print(f"✅ 第 {page} 页采集完成，累计 {len(all_std)} 条")

            except Exception as e:
                retry += 1
                print(f"⚠️  第 {page} 页第 {retry} 次失败：{str(e)[:50]}...")
                driver.save_screenshot(f"第{page}页_第{retry}次失败截图.png")
                if retry <= MAX_RETRY:
                    print("  刷新页面重试...")
                    driver.refresh()
                    time.sleep(5)

        if not page_success:
            print(f"❌ 第 {page} 页多次重试失败，已跳过")
            save_result()
            break

        time.sleep(PAGE_INTERVAL)

    print(f"\n🎉 全部任务完成，共采集 {len(all_std)} 条，已保存到 {SAVE_FILE}")

except Exception as e:
    print(f"\n❌ 全局运行出错：{e}")
    save_result()

finally:
    driver.quit()