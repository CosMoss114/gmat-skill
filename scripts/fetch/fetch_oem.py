#!/usr/bin/env python3
"""
CSS OEM Data Fetcher — 从中国载人航天工程官网自动获取 CSS 轨道 OEM 数据。

用法:
    python fetch_oem.py                 # 全量下载 (去重)
    python fetch_oem.py --dry-run       # 仅列出可下载链接
    python fetch_oem.py --json          # JSON 输出结果
    python fetch_oem.py -o ./my_data    # 指定输出目录 (默认 data/oem/)

数据来源: https://www.cmse.gov.cn/gfgg/zgkjzgdcs/
"""

import argparse
import json
import os
import re
import sys
import zipfile
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ---- 配置 ----
PAGE_URL = "https://www.cmse.gov.cn/gfgg/zgkjzgdcs/"
FILENAME_PATTERN = re.compile(r"CSS_OEM_\d{14}_\d{4}\.zip")
TIMEOUT = 30  # 秒
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # gmat-agent/
DEFAULT_OUTPUT = os.path.join(SKILL_ROOT, "data", "oem")


def fetch_page(url: str = PAGE_URL) -> str:
    """获取页面 HTML。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def extract_links(html: str) -> list[dict]:
    """
    从 HTML 中提取所有 CSS_OEM_*.zip 下载链接。

    返回: [{"filename": "CSS_OEM_20260529...zip", "url": "https://..."}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    links = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]

        # 匹配链接文本: CSS_OEM_20260529004933_0001.zip
        if FILENAME_PATTERN.match(text):
            if text in seen:
                continue
            seen.add(text)

            # 处理相对路径 → 绝对路径
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = f"https://www.cmse.gov.cn{href}"
            else:
                full_url = f"{PAGE_URL.rstrip('/')}/{href}"

            links.append({"filename": text, "url": full_url})

    return links


def download_file(url: str, dest: str) -> bool:
    """下载文件到 dest；已存在则跳过。返回 True 表示新下载。"""
    if os.path.exists(dest):
        return False  # 已存在，跳过

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    print(f"  下载: {os.path.basename(dest)}", end="", flush=True)

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  下载: {os.path.basename(dest)}  {pct}%", end="", flush=True)

    print(f"\r  下载: {os.path.basename(dest)}  ✓ ({downloaded:,} bytes)")
    return True


def extract_oem(zip_path: str, dest_dir: str) -> list[str]:
    """
    解压 zip 中的 .dat OEM 文件到 dest_dir。
    返回解压出的文件路径列表。
    """
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            # OEM 数据文件: .dat 或 .oem 或 .txt
            if name.lower().endswith((".dat", ".oem", ".txt")):
                # 避免覆盖: 如已存在则跳过
                dest = os.path.join(dest_dir, os.path.basename(name))
                if not os.path.exists(dest):
                    zf.extract(name, dest_dir)
                    # 如果解压到子目录，移动到 dest_dir
                    extracted_path = os.path.join(dest_dir, name)
                    if extracted_path != dest:
                        if os.path.exists(extracted_path):
                            import shutil
                            shutil.move(extracted_path, dest)
                            # 清理空目录
                            subdir = os.path.dirname(extracted_path)
                            try:
                                os.removedirs(subdir)
                            except OSError:
                                pass
                    extracted.append(dest)
                    print(f"  解压: {os.path.basename(dest)} ✓")
                else:
                    extracted.append(dest)
    return extracted


def run(output_dir: str, dry_run: bool = False) -> dict:
    """
    主流程: 抓取 → 提取链接 → 下载 → 解压。

    返回:
        {"success": bool, "fetched": int, "skipped": int, "extracted": int,
         "errors": [...], "files": [...]}
    """
    result = {
        "success": False,
        "fetched": 0,
        "skipped": 0,
        "extracted": 0,
        "errors": [],
        "files": [],
    }

    os.makedirs(output_dir, exist_ok=True)

    # 1. 抓取页面
    try:
        html = fetch_page()
    except Exception as e:
        result["errors"].append(f"页面抓取失败: {e}")
        return result

    # 2. 提取链接
    links = extract_links(html)
    if not links:
        result["errors"].append("未找到任何 CSS_OEM_*.zip 下载链接，页面结构可能已变化")
        return result

    print(f"找到 {len(links)} 个 OEM 数据包:\n")

    # 3. 下载 + 解压
    publish_date = ""
    for link in links:
        filename = link["filename"]
        url = link["url"]

        # 提取发布日期 (从文件名: CSS_OEM_20260529...)
        date_match = re.search(r"(\d{8})", filename)
        file_date = date_match.group(1) if date_match else "?"
        if file_date != publish_date:
            publish_date = file_date
            formatted = f"{file_date[:4]}-{file_date[4:6]}-{file_date[6:8]}"
            print(f"[{formatted}]")

        if dry_run:
            print(f"  → {filename}")
            result["files"].append({"filename": filename, "url": url, "status": "dry-run"})
            continue

        zip_dest = os.path.join(output_dir, filename)

        # 下载 (自动去重)
        try:
            is_new = download_file(url, zip_dest)
            if is_new:
                result["fetched"] += 1
            else:
                result["skipped"] += 1
                print(f"  跳过: {filename} (已存在)")
        except Exception as e:
            result["errors"].append(f"下载 {filename}: {e}")
            result["files"].append({"filename": filename, "status": "download_failed", "error": str(e)})
            continue

        # 解压
        try:
            extracted = extract_oem(zip_dest, output_dir)
            result["extracted"] += len(extracted)
            result["files"].append({
                "filename": filename,
                "url": url,
                "status": "new" if is_new else "cached",
                "extracted": [os.path.basename(p) for p in extracted],
            })
        except Exception as e:
            result["errors"].append(f"解压 {filename}: {e}")
            result["files"].append({"filename": filename, "status": "extract_failed", "error": str(e)})

        print()

    # 4. 结果
    if not result["errors"]:
        result["success"] = True

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="从 cmse.gov.cn 自动获取 CSS 轨道 OEM 数据"
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT,
        help=f"输出目录 (默认: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅列出可下载链接，不实际下载"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="JSON 格式输出结果"
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN === (不会下载任何文件)\n")

    result = run(args.output, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if args.dry_run:
            print(f"\n共 {len(result['files'])} 个文件可下载。")
        else:
            total = result["fetched"] + result["skipped"]
            if result["success"]:
                print(f"完成: 新下载 {result['fetched']}, "
                      f"跳过 {result['skipped']}, "
                      f"解压 {result['extracted']} 个 OEM 文件")
            else:
                print(f"部分完成: 新下载 {result['fetched']}, "
                      f"跳过 {result['skipped']}, "
                      f"错误 {len(result['errors'])} 个")
                for e in result["errors"]:
                    print(f"  ✗ {e}")

    sys.exit(0 if result["success"] else 1)
