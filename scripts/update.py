#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from typing import Dict

sys.path.append(os.path.dirname(__file__))
from utils import (
    download_jar_and_extract_lang,
    get_version_json_url,
    load_json,
    save_json,
    get_last_version,
    set_last_version,
    call_translate_api
)

# 固定基准文件 URL（根据需求指定的 client.jar）
BASE_JAR_URL = "https://piston-data.mojang.com/v1/objects/191771837687b766537a8c4607cb6fad79c533a1/client.jar"

# 临时文件路径
BASE_FILE = "base_en_us.json"
NEW_LANG_FILE = "en_us_new.json"
TARGET_LANG_FILE = "en_us.json"
ZH_CN_FILE = "assets/minecraft/lang/zh_cn.json"
ZH_TW_FILE = "assets/minecraft/lang/zh_tw.json"
ZH_HK_FILE = "assets/minecraft/lang/zh_hk.json"
NEW_ENTRIES_FILE = "new_entries_to_translate.json"
TRANS_NEW_FILE = "translated_new_entries.json"

def generate_traditional(zh_cn_path: str, zh_tw_path: str, zh_hk_path: str) -> None:
    """使用 opencc 生成繁体版本"""
    if not os.path.exists(zh_cn_path):
        print(f"警告：{zh_cn_path} 不存在，跳过繁体生成")
        return

    subprocess.run(
        ["opencc", "-i", zh_cn_path, "-o", zh_tw_path, "-c", "s2tw.json"],
        check=True,
        capture_output=True,
        text=True
    )
    print(f"已生成 {zh_tw_path}")

    subprocess.run(
        ["opencc", "-i", zh_cn_path, "-o", zh_hk_path, "-c", "s2hk.json"],
        check=True,
        capture_output=True,
        text=True
    )
    print(f"已生成 {zh_hk_path}")

def main():
    # 1. 读取用户输入的版本号
    version = os.environ.get("VERSION")
    if not version:
        print("错误：环境变量 VERSION 未设置，请在 workflow_dispatch 中输入版本号。")
        sys.exit(1)

    # 2. 检查是否已经处理过该版本
    last_id = get_last_version()
    if last_id == version:
        print(f"版本 {version} 已处理过，无需重复操作。")
        return

    # 3. 下载基准文件（固定 URL 的 client.jar）
    print(f"正在从 {BASE_JAR_URL} 下载基准语言文件...")
    download_jar_and_extract_lang(BASE_JAR_URL, BASE_FILE, is_jar_url=True)
    print(f"基准文件已保存至 {BASE_FILE}")

    # 4. 根据用户输入的版本号获取 version.json URL，然后下载并提取最新语言文件
    version_url = get_version_json_url(version)
    if not version_url:
        print(f"错误：未找到版本 {version} 的 version.json URL。")
        sys.exit(1)

    print(f"正在获取版本 {version} 的客户端 JAR...")
    download_jar_and_extract_lang(version_url, NEW_LANG_FILE, is_jar_url=False)
    print(f"最新语言文件已保存至 {NEW_LANG_FILE}")

    # 5. 对比基准文件，提取新增条目
    base_dict = load_json(BASE_FILE)
    new_dict = load_json(NEW_LANG_FILE)
    diff_dict = {k: v for k, v in new_dict.items() if k not in base_dict}
    print(f"相对于基准文件，共发现 {len(diff_dict)} 个新增条目。")

    # 6. 过滤掉已经翻译过的条目
    existing_trans = load_json(ZH_CN_FILE)
    to_translate = {k: v for k, v in diff_dict.items() if k not in existing_trans}
    print(f"需要翻译的新增条目（尚未翻译）：{len(to_translate)} 个。")

    # 7. 分批翻译，记录失败
    translated_all = {}
    failed_entries = {}   # 收集失败的条目

    if to_translate:
        items = list(to_translate.items())
        batch_size = 280
        total_batches = (len(items) + batch_size - 1) // batch_size

        for i in range(0, len(items), batch_size):
            batch_items = items[i:i+batch_size]
            batch_dict = dict(batch_items)
            print(f"正在翻译第 {i//batch_size + 1}/{total_batches} 批，共 {len(batch_dict)} 条...")
            try:
                translated_batch = call_translate_api(batch_dict)
                translated_all.update(translated_batch)
            except Exception as e:
                print(f"警告：第 {i//batch_size + 1} 批翻译失败：{e}")
                failed_entries.update(batch_dict)

        # 保存失败条目
        if failed_entries:
            save_json("failed_translations.json", failed_entries)
            print(f"未翻译条目已保存至 failed_translations.json，共 {len(failed_entries)} 条。")

        # 合并成功翻译和失败条目（原文）
        merged = dict(existing_trans)
        merged.update(translated_all)        # 成功翻译部分
        merged.update(failed_entries)        # 失败部分用原文代替
        save_json(ZH_CN_FILE, merged)
        print(f"合并后的简体中文文件已保存，共 {len(merged)} 个条目。")
    else:
        print("没有需要翻译的新增条目。")

    # 8. 生成繁体版本（总是尝试，但只在 zh_cn.json 存在时才真正生成）
    generate_traditional(ZH_CN_FILE, ZH_TW_FILE, ZH_HK_FILE)

    # 9. 将最新源文件（筛选后）移动到正式位置，并记录版本号
    save_json(TARGET_LANG_FILE, diff_dict)
    print(f"英语文件已筛选保存至 {TARGET_LANG_FILE}（仅包含新增条目，共 {len(diff_dict)} 条）")

    set_last_version(version)

    # 10. 删除临时基准文件（可选）
    if os.path.exists(BASE_FILE):
        os.remove(BASE_FILE)
    if os.path.exists(NEW_LANG_FILE):
        os.remove(NEW_LANG_FILE)

    print("所有步骤完成！")

if __name__ == "__main__":
    main()