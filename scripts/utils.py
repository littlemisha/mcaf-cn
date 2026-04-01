import json
import os
import requests
import zipfile
import time
import sys
from typing import Dict, Any, Optional

# ---------- 翻译 API ----------
def call_translate_api(text_data: Dict[str, str], is_missing: bool = False) -> Dict[str, str]:
    """调用魔塔社区 API 翻译 JSON 对象"""
    api_key = os.environ.get('MODELSCOPE_API_KEY')
    if not api_key:
        raise ValueError("环境变量 MODELSCOPE_API_KEY 未设置")

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    prompt = f"""将以下 Minecraft Java 版愚人节版本的英语语言文件翻译为简体中文。要求：
- 尽量使用书面语和成语，但不要太像文言文；
- 按照汉语的语序调整语句；
- 对于玩梗的语句可以使用口语表达；
- 游戏名 Minecraft 保留不译；
- 保持 JSON 格式不变，只翻译值部分，不要修改键名；
- 不要添加任何解释或注释，直接返回 JSON 对象。

待翻译内容：
"""
    json_str = json.dumps(text_data, ensure_ascii=False, indent=2)
    full_prompt = prompt + json_str

    payload = {
        "model": "deepseek-ai/DeepSeek-V3.2",
        "messages": [{"role": "user", "content": full_prompt}]
    }

    for retry in range(2):   # 总共尝试2次（第一次 + 重试1次）
        try:
            response = requests.post(
                "https://api-inference.modelscope.cn/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=900
            )
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']

            # 提取 JSON（处理 markdown 代码块）
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            return json.loads(content.strip())
        except Exception as e:
            print(f"API 调用失败，重试 {retry+1}/2: {e}", file=sys.stderr)
            if retry == 1:
                raise
            time.sleep(5)

    raise RuntimeError("翻译 API 调用多次失败")


# ---------- 版本信息获取 ----------
def get_version_json_url(version_id: str) -> Optional[str]:
    """根据版本 ID 从版本清单中获取 version.json 的 URL"""
    manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
    resp = requests.get(manifest_url)
    resp.raise_for_status()
    manifest = resp.json()

    for v in manifest['versions']:
        if v['id'] == version_id:
            return v['url']
    return None


def download_jar_and_extract_lang(source: str, target_path: str, is_jar_url: bool = False) -> None:
    """
    通用函数：从 JAR 中提取 en_us.json
    source: 如果是 is_jar_url=True，则 source 是 client.jar 的直接下载 URL；
            否则 source 是 version.json 的 URL，函数会从中获取 client 的下载链接。
    """
    jar_url = source
    if not is_jar_url:
        # 获取版本 JSON
        resp = requests.get(source)
        resp.raise_for_status()
        version_meta = resp.json()
        jar_url = version_meta['downloads']['client']['url']

    print(f"正在下载客户端 JAR: {jar_url}")
    jar_resp = requests.get(jar_url, stream=True)
    jar_resp.raise_for_status()
    jar_path = "temp_client.jar"
    with open(jar_path, 'wb') as f:
        for chunk in jar_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    # 提取 en_us.json
    lang_path_in_jar = "assets/minecraft/lang/en_us.json"
    with zipfile.ZipFile(jar_path, 'r') as zf:
        with zf.open(lang_path_in_jar) as lang_file:
            content = lang_file.read().decode('utf-8')
            with open(target_path, 'w', encoding='utf-8') as out:
                out.write(content)

    os.remove(jar_path)
    print(f"语言文件已提取到 {target_path}")


# ---------- 文件读写 ----------
def load_json(file_path: str) -> Dict[str, str]:
    """加载 JSON 文件，文件不存在则返回空字典"""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path: str, data: Dict[str, str]) -> None:
    """保存 JSON 文件"""
    dirname = os.path.dirname(file_path)
    if dirname:                     # 仅当目录部分非空时才创建
        os.makedirs(dirname, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def get_last_version() -> Optional[str]:
    """读取上次处理的版本 ID"""
    if os.path.exists(".last_version"):
        with open(".last_version", 'r') as f:
            return f.read().strip()
    return None


def set_last_version(version_id: str) -> None:
    """保存当前处理的版本 ID"""
    with open(".last_version", 'w') as f:
        f.write(version_id)