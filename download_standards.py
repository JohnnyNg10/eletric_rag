"""
国家标准下载爬虫 - 电力国标强制标准

功能：
- 自动从 openstd.samr.gov.cn 下载电力强制国标PDF
- 支持断点续传（已下载的跳过）
- 反爬虫措施：随机延迟、User-Agent轮换、失败重试
- 详细日志记录

使用方法：
    python download_standards.py
"""

import requests
import time
import random
import re
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download_standards.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StandardDownloader:
    """国家标准下载器"""

    def __init__(self, output_dir: str = "电力国标PDF"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # User-Agent 池（模拟不同浏览器）
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        ]

        # 基础URL
        self.base_url = "https://openstd.samr.gov.cn"
        self.list_url = f"{self.base_url}/bzgk/std/std_list"

        # 会话（保持连接）
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': self.base_url,
        })

    def _get_random_headers(self) -> dict:
        """获取随机请求头"""
        return {
            'User-Agent': random.choice(self.user_agents)
        }

    def _random_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """随机延迟（避免请求过快）"""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.2f} seconds...")
        time.sleep(delay)

    def get_standard_list(self, page: int = 1, category: int = 29) -> List[str]:
        """
        获取标准列表（HCNO编号列表）

        Args:
            page: 页码
            category: 分类（29=电力）

        Returns:
            List[str]: HCNO编号列表
        """
        params = {
            'p.p1': page,
            'p.p5': 'PUBLISHED',
            'p.p6': category,  # 29 = 电力
            'p.p90': 'circulation_date',
            'p.p91': 'desc',
            'r': str(random.random())  # 添加随机数防止缓存
        }

        try:
            logger.info(f"Fetching page {page}...")
            response = self.session.get(
                self.list_url,
                params=params,
                headers=self._get_random_headers(),
                timeout=30
            )
            response.raise_for_status()

            # 提取HCNO（在showInfo函数调用中）
            # 示例: onclick="showInfo('F8C9E208891B7BB5AF1B3E64933693C2');"
            hcno_pattern = r"showInfo\('([A-F0-9]{32})'\)"
            hcnos = re.findall(hcno_pattern, response.text)

            # 去重
            hcnos = list(set(hcnos))

            logger.info(f"Found {len(hcnos)} standards on page {page}")
            return hcnos

        except Exception as e:
            logger.error(f"Failed to fetch page {page}: {e}")
            return []

    def get_standard_info(self, hcno: str) -> Optional[Dict]:
        """
        获取标准详细信息

        Args:
            hcno: 标准HCNO编号

        Returns:
            Dict: {
                'hcno': str,
                'title': str,
                'std_no': str (标准号，如 GB 50057-2010)
            }
        """
        info_url = f"{self.base_url}/bzgk/std/newGbInfo"

        try:
            response = self.session.get(
                info_url,
                params={'hcno': hcno},
                headers=self._get_random_headers(),
                timeout=30
            )
            response.raise_for_status()

            html = response.text

            # 提取标准号 - 从<h1>标签中（如：标准号：GB 1002-2024）
            std_no_match = re.search(r'标准号[：:]\s*([^\s<]+(?:\s+[^\s<]+)*)', html)
            std_no = std_no_match.group(1).strip() if std_no_match else None

            # 如果上面没找到，尝试从title中提取
            if not std_no:
                title_match = re.search(r'<title>[^|]*\|([^<]+)</title>', html)
                if title_match:
                    std_no = title_match.group(1).strip()

            # 提取标准名称（中文）
            title_match = re.search(r'中文标准名称[：:]\s*([^<\n]+)', html)
            if not title_match:
                # 备用：从页面其他位置提取
                title_match = re.search(r'<h1[^>]*>([^<]*(?:规范|标准|方法)[^<]*)</h1>', html)

            title = title_match.group(1).strip() if title_match else f"标准_{hcno[:8]}"

            if not std_no:
                logger.warning(f"Failed to extract standard number for {hcno}")
                return None

            return {
                'hcno': hcno,
                'std_no': std_no,
                'title': title,
            }

        except Exception as e:
            logger.error(f"Failed to get info for {hcno}: {e}")
            return None

    def download_standard(self, hcno: str, std_info: Dict, max_retries: int = 3) -> bool:
        """
        下载标准PDF

        Args:
            hcno: 标准HCNO编号
            std_info: 标准信息（用于文件命名）
            max_retries: 最大重试次数

        Returns:
            bool: 是否下载成功
        """
        # 生成文件名（标准号.pdf）
        std_no = std_info['std_no'].replace('/', '-').replace(' ', '+')
        filename = f"{std_no}.pdf"
        filepath = self.output_dir / filename

        # 检查是否已存在
        if filepath.exists() and filepath.stat().st_size > 10000:  # 大于10KB认为有效
            logger.info(f"✓ Already exists: {filename}")
            return True

        # 先访问详情页和下载预览页（建立必要的Cookie/Session）
        detail_url = f"{self.base_url}/bzgk/std/newGbInfo?hcno={hcno}"
        preview_url = f"{self.base_url}/bzgk/std/showGb?type=download&hcno={hcno}"

        try:
            self.session.get(detail_url, headers=self._get_random_headers(), timeout=30)
            self.session.get(preview_url, headers=self._get_random_headers(), timeout=30)
        except:
            pass  # 忽略预访问错误

        # 真正的下载URL
        download_url = f"{self.base_url}/bzgk/std/viewGb"
        params = {'hcno': hcno}

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[{attempt}/{max_retries}] Downloading: {filename}")

                # 下载文件（流式）
                response = self.session.get(
                    download_url,
                    params=params,
                    headers=self._get_random_headers(),
                    timeout=60,
                    stream=True
                )
                response.raise_for_status()

                # 检查是否是PDF
                first_bytes = response.content[:10] if hasattr(response, 'content') else b''
                if first_bytes and not first_bytes.startswith(b'%PDF'):
                    logger.warning(f"Not a PDF file, may be an error page")
                    raise Exception("Downloaded file is not a PDF")

                # 写入文件
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # 验证文件大小
                file_size = filepath.stat().st_size
                if file_size < 10000:  # 小于10KB可能是错误页面
                    logger.warning(f"File too small ({file_size} bytes), may be invalid")
                    filepath.unlink()
                    raise Exception("Downloaded file is too small")

                logger.info(f"✓ Downloaded: {filename} ({file_size / 1024:.1f} KB)")
                return True

            except Exception as e:
                logger.error(f"✗ Failed (attempt {attempt}): {e}")
                if filepath.exists():
                    filepath.unlink()

                if attempt < max_retries:
                    # 失败后等待更长时间
                    self._random_delay(5.0, 10.0)
                else:
                    logger.error(f"✗ Gave up after {max_retries} attempts: {filename}")
                    return False

        return False

    def run(self, max_pages: int = 5, standards_per_page: int = 10):
        """
        运行下载任务

        Args:
            max_pages: 最大页数
            standards_per_page: 每页标准数（用于估算）
        """
        logger.info("="*60)
        logger.info("Starting standard download task")
        logger.info(f"Output directory: {self.output_dir.absolute()}")
        logger.info("="*60)

        all_hcnos = []

        # 1. 收集所有标准的HCNO
        logger.info(f"\nStep 1: Collecting standards from {max_pages} pages...")
        for page in range(1, max_pages + 1):
            hcnos = self.get_standard_list(page=page)
            all_hcnos.extend(hcnos)

            if len(hcnos) < standards_per_page:
                logger.info(f"Reached last page at page {page}")
                break

            # 页面间延迟
            if page < max_pages:
                self._random_delay(2.0, 4.0)

        # 去重
        all_hcnos = list(set(all_hcnos))
        logger.info(f"\n✓ Found {len(all_hcnos)} unique standards")

        # 2. 下载每个标准
        logger.info(f"\nStep 2: Downloading standards...")
        success_count = 0
        fail_count = 0
        skip_count = 0

        for idx, hcno in enumerate(all_hcnos, 1):
            logger.info(f"\n[{idx}/{len(all_hcnos)}] Processing: {hcno}")

            # 获取标准信息
            std_info = self.get_standard_info(hcno)
            if not std_info:
                logger.warning(f"Skipping {hcno}: failed to get info")
                skip_count += 1
                continue

            logger.info(f"  Standard: {std_info['std_no']} - {std_info['title']}")

            # 延迟（避免请求过快）
            self._random_delay(3.0, 6.0)

            # 下载PDF
            success = self.download_standard(hcno, std_info)

            if success:
                success_count += 1
            else:
                fail_count += 1

            # 每10个标准后稍作休息
            if idx % 10 == 0:
                logger.info(f"\n--- Progress: {idx}/{len(all_hcnos)} processed ---")
                logger.info(f"    Success: {success_count}, Failed: {fail_count}, Skipped: {skip_count}")
                self._random_delay(5.0, 8.0)

        # 3. 输出统计
        logger.info("\n" + "="*60)
        logger.info("Download task completed!")
        logger.info(f"Total standards: {len(all_hcnos)}")
        logger.info(f"  ✓ Success: {success_count}")
        logger.info(f"  ✗ Failed: {fail_count}")
        logger.info(f"  ⊘ Skipped: {skip_count}")
        logger.info(f"Output directory: {self.output_dir.absolute()}")
        logger.info("="*60)


def main():
    """主函数"""
    # 创建下载器
    downloader = StandardDownloader(output_dir="电力国标PDF")

    # 运行下载任务
    # 48条标准，每页10条，需要5页
    downloader.run(max_pages=5, standards_per_page=10)


if __name__ == "__main__":
    main()
