"""
批量导入DL标准（前30条）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.db.models import Document
from app.tasks.scan_processor_tasks import process_scanned_pdf_task
from app.config import settings

# 前30条标准文件名
STANDARDS = [
    "《DL_T 5806-2020 高清版 水电水利工程堆石混凝土施工规范》 - 副本.pdf",
    "《DLT 5407-2019 高清版 水电水利工程竖井斜井施工规范》 - 副本.pdf",
    "《水电水利工程边坡施工技术规范》DLT 5255-2010.pdf",
    "《水电水利工程岩壁梁施工规程》DLT 5198-2013.pdf",
    "《水工混凝土钢筋施工规范》（DLT 5169-2013）.pdf",
    "21 水电水利工程边坡施工技术规范DLT-5255-2010.pdf",
    "22 水电水利工程爆破施工技术规范-DLT-5135-2013.pdf",
    "23 水工混凝土施工规范-DLT-5144-2015.pdf",
    "24 水工建筑物水泥灌浆施工技术规范-DL-T-5148-2021.pdf",
    "25 水电水利工程水下混凝土施工规范-DLT-5309-2013.pdf",
    "26 碾压式土石坝施工规范-DLT-5129-2013.pdf",
    "30 水工碾压式沥青混凝土施工规范--DL∕T-5363-2016.pdf",
    "31 水工建筑物岩石基础开挖工程施工技术规范-DL_T-5389-2007.pdf",
    "32 水工建筑物地下工程开挖施工技术规范-DLT-5099-2011.pdf",
    "33 水电水利工程混凝土防渗墙施工规范DL-T5199-2019.pdf",
    "34 水工建筑物滑动模板施工技术规范DL∕T-5400-2016.pdf",
    "35 水电水利工程聚脲涂层施工技术规程-DL_T-5317-2014.pdf",
    "36 水电水利工程截流施工技术规范-DLT-5741-2016.pdf",
    "《DLT 5406-2019 水电水利工程化学灌浆技术规范》 - 副本.pdf",
    "DLT-5083-2019-水电水利工程预应力锚固施工规范.pdf",
    "《DLT 5113.13-2019 水电水利基本建设工程单元工程质 量等级评定标准 第13部分：浆砌石坝工程》 - 副本.pdf",
    "38 水电水利基本建设工程单元工程质量等级评定标准第1部分：土建工程-DL∕T-5113.1-2019.pdf",
    "39 水电水利基本建设工程单元工程质量等级评定标准第9部分：土工合成材料应用工程DL_T-5113.9-2017.pdf",
    "40 水电水利基本建设工程单元工程质量等级评定标准第14部分：混凝土面板堆石坝工程-DL∕T-5113.14-2018.pdf",
    "41 水电水利基本建设工程单元工程质量等级评定标准第10部分：沥青混凝土工程-DLT-5113.10-2012.pdf",
    "42 水电水利基本建设工程单元工程质量等级评定标准第6部分：升压变电电气及二次回路系统-DLT-5113.6-2012.pdf",
    "45 水电水利基本建设工程单元工程质量等级评定标准第7部分：碾压式土石坝工程-DLT-5113.7-2015.pdf",
    "混凝土坝安全监测技术规范 DL.T5178-2016.pdf",
    "46 水电水利工程施工安全监测技术规范-DLT-5308-2013.pdf",
    "47 大坝安全监测自动化技术规范 DL.T 5211-2019.pdf",
]


async def batch_import():
    """批量导入前30条标准"""

    print("=" * 60)
    print("批量导入DL标准（前30条）")
    print("=" * 60)

    base_dir = Path("../实际数据/DL")

    if not base_dir.exists():
        print(f"\n错误: 目录不存在 - {base_dir}")
        return

    print(f"\n配置检查:")
    print(f"  ENABLE_SCANNED_PDF: {settings.ENABLE_SCANNED_PDF}")
    print(f"  ENABLE_VLM_DESCRIPTION: {settings.ENABLE_VLM_DESCRIPTION}")
    print(f"  VLM_PROVIDER: {settings.VLM_PROVIDER}")

    if not settings.ENABLE_SCANNED_PDF:
        print("\n警告: ENABLE_SCANNED_PDF=False")
        return

    print(f"\n准备导入 {len(STANDARDS)} 个标准")
    print("-" * 60)

    success_count = 0
    skip_count = 0
    fail_count = 0

    for idx, filename in enumerate(STANDARDS, start=1):
        pdf_path = base_dir / filename

        print(f"\n[{idx}/{len(STANDARDS)}] {filename[:50]}...")

        # 检查文件是否存在
        if not pdf_path.exists():
            print(f"  [SKIP] 文件不存在")
            skip_count += 1
            continue

        # 提取标准号
        standard_no = extract_standard_no(filename)

        # 创建文档记录
        db = SessionLocal()
        try:
            doc = Document(
                title=filename.replace('.pdf', ''),
                doc_type='standard',
                standard_no=standard_no,
                file_path=f"scanned_pdfs/{filename}",
                file_size=pdf_path.stat().st_size,
                process_status='pending',
                is_scanned=True
            )
            db.add(doc)
            db.commit()
            doc_id = doc.id

            print(f"  [OK] 文档记录已创建: doc_id={doc_id}, standard_no={standard_no}")

            # 提交Celery任务
            task = process_scanned_pdf_task.delay(str(pdf_path.absolute()), doc_id)
            print(f"  [OK] Celery任务已提交: task_id={task.id}")

            success_count += 1

        except Exception as e:
            db.rollback()
            print(f"  [ERROR] {e}")
            fail_count += 1
        finally:
            db.close()

    print("\n" + "=" * 60)
    print("批量导入完成")
    print("=" * 60)
    print(f"成功: {success_count}")
    print(f"跳过: {skip_count}")
    print(f"失败: {fail_count}")
    print(f"\n注意: 文档已提交到Celery队列，后台处理中")
    print("可以通过以下方式查看进度:")
    print("  1. 查看Celery worker日志")
    print("  2. 查询数据库: SELECT id, title, process_status FROM documents WHERE is_scanned=1;")


def extract_standard_no(filename: str) -> str:
    """从文件名中提取标准号"""
    import re

    # 匹配 DL/T 5806-2020 或 DLT 5806-2020 等格式
    patterns = [
        r'DL[∕/\s_-]*T?\s*(\d+[\.\-]\d+[-–]\d+)',
        r'DL[∕/\s_-]*(\d+[-–]\d+)',
        r'(DL\S+\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            standard_no = match.group(0).replace('∕', '/').replace('_', '/')
            standard_no = re.sub(r'\s+', ' ', standard_no)
            return standard_no

    return "Unknown"


if __name__ == '__main__':
    asyncio.run(batch_import())
