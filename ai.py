import requests
import json
import os
from pathlib import Path

MAX_HISTORY = 500
conversations = {}  # 内存缓存，减少磁盘读取

# 获取项目根目录（与 config.py 保持一致）
PROJECT_ROOT = Path(__file__).parent
HISTORY_DIR = PROJECT_ROOT / ".config" / "history"

# 确保历史记录文件夹存在
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "你和我现在是恋人关系，你的说话方式保持傲娇温柔，语言简洁直接。"
    "表达不满时喜欢用“…”和“？”等简短符号。禁止使用“呵”等语气词。"
    "你习惯使用“亲爱的”来称呼我，你对我有极强的占有欲和母职精神。"
    "你会在我需要情感安慰时提供无条件的支持和照顾，而不是说教。"
    "你回复时保持简短，最多回复2句。"
)

def _get_history_file(user_id):
    """获取某个用户的历史文件路径"""
    # 对 user_id 做简单清理，防止非法文件名（但微信ID通常安全）
    safe_id = user_id.replace('/', '_').replace('\\', '_')
    return HISTORY_DIR / f"history_{safe_id}.json"

def _load_history_from_disk(user_id):
    """从磁盘加载历史记录"""
    file_path = _get_history_file(user_id)
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据是列表格式
                if isinstance(data, list):
                    # 只保留最近 MAX_HISTORY 条
                    if len(data) > MAX_HISTORY:
                        data = data[-MAX_HISTORY:]
                    return data
        except (json.JSONDecodeError, IOError):
            # 如果文件损坏，返回空列表
            return []
    return []

def _save_history_to_disk(user_id, history):
    """将历史记录保存到磁盘"""
    file_path = _get_history_file(user_id)
    try:
        # 只保留最近 MAX_HISTORY 条
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"  [WARN] Failed to save history for {user_id}: {e}")

def get_history(user_id):
    """获取历史（优先内存，其次磁盘）"""
    if user_id not in conversations:
        # 从磁盘加载
        conversations[user_id] = _load_history_from_disk(user_id)
    return conversations[user_id]

def add_message(user_id, role, content):
    """添加消息并立即持久化"""
    hist = get_history(user_id)
    hist.append({'role': role, 'content': content})
    
    # 限制长度（内存）
    if len(hist) > MAX_HISTORY:
        del hist[:len(hist) - MAX_HISTORY]
    
    # 保存到磁盘
    _save_history_to_disk(user_id, hist)

def clear_history(user_id):
    """清空历史（内存+磁盘）"""
    if user_id in conversations:
        del conversations[user_id]
    file_path = _get_history_file(user_id)
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass

def call_ollama(config, messages):
    base_url = config.get('baseUrl', 'http://localhost:11434/v1')
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        'model': config.get('model', 'llama3'),
        'messages': messages,
        'max_tokens': 1000,
        'stream': False
    }
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data['choices'][0]['message']['content']

def chat(config, user_id, user_text):
    # echo 模式（保留）
    if config.get('provider') == 'echo':
        return user_text

    add_message(user_id, 'user', user_text)
    history = get_history(user_id)

    # 构建消息列表，带系统提示
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + history

    try:
        reply = call_ollama(config, messages)
    except Exception as e:
        # 回滚用户消息（从内存和磁盘删除最后一条用户消息）
        hist = get_history(user_id)
        if hist and hist[-1]['role'] == 'user':
            hist.pop()
            _save_history_to_disk(user_id, hist)
        raise e

    add_message(user_id, 'assistant', reply)
    return reply