#!/usr/bin/env python3
"""
WeChat-Ollama-Python 版本
支持 Ollama 本地模型的微信机器人
"""

import sys
import json
import argparse
from pathlib import Path

from config import load_config_with_key, save_config, load_token, save_token, mask_key
from wechat import (
    get_qr_code, poll_qr_status, get_updates,
    send_text, send_typing, extract_text
)
from ai import chat, clear_history
from utils import render_qr_terminal, format_time
import time
import os

# ---------- 配置交互 ----------
def interactive_setup(config):
    print("\n  Ollama Setup\n")
    print("  This bot uses local Ollama as the AI backend.")
    print("  Make sure Ollama is running (ollama serve) and a model is pulled.")
    print("  Example: ollama run llama3\n")

    model = input("  Enter Ollama model name : ").strip()
    if not model:
        model = "llama3"
    config['model'] = model
    config['provider'] = 'ollama'
    config['apiKey'] = 'ollama'
    config['baseUrl'] = os.getenv('OLLAMA_HOST', 'http://localhost:11434/v1')
    print(f"\n  [OK] Ollama configured with model: {model}\n")
    print("  [INFO] You can change the model later by editing ./.config/config.json\n")
    return config

# ---------- 登录 ----------
def login(force_login=False):
    if not force_login:
        saved = load_token()
        if saved and saved.get('token'):
            print(f"  [OK] Using saved session (Bot: {saved.get('accountId', 'unknown')})")
            print(f"       Saved at: {saved.get('savedAt', 'unknown')}\n")
            return saved

    print("  [INFO] WeChat QR Login\n")
    qr_resp = get_qr_code()
    qrcode = qr_resp['qrcode']
    qr_img_url = qr_resp.get('qrcode_img_content') or qrcode

    # 显示二维码
    print("  [INFO] Scan with WeChat:\n")
    qr_art = render_qr_terminal(qr_img_url)
    if qr_art:
        for line in qr_art.split('\n'):
            print('  ' + line)
        print()
    print(f"  [INFO] Or open: {qrcode}\n")
    print("  Waiting for scan...")

    deadline = time.time() + 5 * 60
    refresh_count = 0

    while time.time() < deadline:
        status = poll_qr_status(qrcode)
        if status.get('status') == 'scaned':
            print("  [INFO] Scanned! Confirm on your phone...")
        if status.get('status') == 'expired':
            refresh_count += 1
            if refresh_count > 3:
                raise RuntimeError("QR expired 3 times")
            print(f"  [WARN] QR expired, refreshing ({refresh_count}/3)...")
            new_qr = get_qr_code()
            qrcode = new_qr['qrcode']
            # 重新显示二维码
            qr_art = render_qr_terminal(qrcode)
            if qr_art:
                for line in qr_art.split('\n'):
                    print('  ' + line)
                print()
        if status.get('status') == 'confirmed':
            session = {
                'token': status['bot_token'],
                'baseUrl': status.get('baseurl', 'https://ilinkai.weixin.qq.com'),
                'accountId': status['ilink_bot_id'],
                'userId': status['ilink_user_id'],
                'savedAt': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            save_token(session)
            print(f"  [OK] Login successful! Bot ID: {session['accountId']}\n")
            return session
        time.sleep(1)

    raise RuntimeError("Login timeout")

# ---------- 命令处理 ----------
COMMANDS = {
    '/clear': lambda user_id: f"[OK] Conversation cleared." if (clear_history(user_id), True) else "",
    '/help': lambda _: "可用命令：\n/clear — 清除聊天记录\n/help — 显示本帮助\n/ping — 测试机器人是否在线\n/status — 显示机器人状态",
    '/ping': lambda _: "Pong!",
}

# ---------- 主循环 ----------
def poll_loop(config, session, start_time, on_message):
    token = session['token']
    base_url = session['baseUrl']
    buf = ''
    reconnect_count = 0
    MAX_RECONNECT = 5
    RECONNECT_DELAY = [3, 5, 10, 20, 30]

    # 动态 /status
    def status_cmd(user_id):
        uptime = int((time.time() - start_time) / 60)
        return f"WeChat-Ollama status\nUptime: {uptime}m\nMessages: {on_message()}\nAI: {config['provider']} ({config['model']})"

    COMMANDS['/status'] = status_cmd

    while True:
        try:
            resp = get_updates(token, buf)
            if resp.get('get_updates_buf'):
                buf = resp['get_updates_buf']

            # 会话过期重连
            errcode = resp.get('errcode', 0)
            if errcode in (-14, -13):
                print(f"\n  [WARN] Session expired (code: {errcode})")
                if reconnect_count >= MAX_RECONNECT:
                    print("  [ERROR] Max reconnect attempts reached. Run with --login to re-authenticate.")
                    sys.exit(1)
                reconnect_count += 1
                delay = RECONNECT_DELAY[reconnect_count - 1]
                print(f"  [INFO] Reconnecting ({reconnect_count}/{MAX_RECONNECT}) in {delay}s...")
                time.sleep(delay)
                try:
                    new_session = login(True)
                    token = new_session['token']
                    base_url = new_session['baseUrl']
                    buf = ''
                    reconnect_count = 0
                    print("  [OK] Reconnected!\n")
                except Exception as e:
                    print(f"  [ERROR] Reconnect failed: {e}")
                continue

            reconnect_count = 0

            for msg in resp.get('msgs', []):
                if msg.get('message_type') != 1:
                    continue

                from_user = msg['from_user_id']
                text = extract_text(msg)
                ctx_token = msg.get('context_token')
                on_message()  # 增加计数

                safe_text = text.replace('\n', ' ')[:200]
                print(f"  [MSG] [{format_time()}] From: {from_user}")
                print(f"        Text: {safe_text}")

                # 斜杠命令
                cmd_key = text.strip().lower()
                if cmd_key in COMMANDS:
                    reply = COMMANDS[cmd_key](from_user)
                    send_text(token, from_user, reply, ctx_token)
                    print(f"        [OK] {reply.split(chr(10))[0]}\n")
                    continue

                # 媒体文件（图片等）——既然不搞图片，直接提示
                if text in ['[图片]', '[视频]', '[语音]'] or text.startswith('[文件]'):
                    send_text(token, from_user, f"收到{text}，目前仅支持文字对话~", ctx_token)
                    print(f"        [SKIP] Media ignored\n")
                    continue

                # 速率限制（与 Node.js 一致）
                if is_rate_limited(from_user):
                    send_text(token, from_user, '请稍等，消息太频繁了~', ctx_token)
                    print(f"        [RATE] Rate limited\n")
                    continue

                send_typing(token, from_user, ctx_token)
                print(f"        [AI] Thinking...")
                start = time.time()
                try:
                    reply = chat(config, from_user, text)
                    elapsed = time.time() - start
                    # 长消息分片
                    chunks = split_message(reply, 1800)
                    for chunk in chunks:
                        send_text(token, from_user, chunk, ctx_token)
                    preview = reply[:80] + '…' if len(reply) > 80 else reply
                    print(f"        [OK] [{elapsed:.1f}s] {preview}\n")
                except Exception as e:
                    print(f"        [ERROR] AI error: {e}\n")
                    send_text(token, from_user, '抱歉，AI 处理出错了，请稍后再试~', ctx_token)

        except KeyboardInterrupt:
            print("\n\n  [INFO] Bye!")
            sys.exit(0)
        except Exception as e:
            print(f"  [WARN] Poll error: {e}, retrying in 3s...")
            time.sleep(3)

# 速率限制
_rate_limits = {}
RATE_WINDOW = 2  # 秒
RATE_MAX = 100   # 每分钟

def is_rate_limited(user_id):
    now = time.time()
    if user_id not in _rate_limits:
        _rate_limits[user_id] = {'last': now, 'count': 1, 'window_start': now}
        return False
    entry = _rate_limits[user_id]
    if now - entry['window_start'] > 60:
        entry['window_start'] = now
        entry['count'] = 0
    entry['count'] += 1
    if entry['count'] > RATE_MAX:
        return True
    if now - entry['last'] < RATE_WINDOW:
        return True
    entry['last'] = now
    return False

def split_message(text, max_len):
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        # 尽量在换行或空格处分割
        split_at = remaining.rfind('\n', 0, max_len)
        if split_at < max_len * 0.3:
            split_at = remaining.rfind(' ', 0, max_len)
            if split_at < max_len * 0.3:
                split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip('\n')
    return chunks

# ---------- 主函数 ----------
def main():
    parser = argparse.ArgumentParser(description='WeChat-Ollama')
    parser.add_argument('--model', help='Ollama model name')
    parser.add_argument('--login', action='store_true', help='Force re-login')
    args = parser.parse_args()

    print("\n  WeChat-Ollama — WeChat AI Bot with local Ollama\n")

    config = load_config_with_key()
    # 强制 ollama
    config['provider'] = 'ollama'
    config['apiKey'] = 'ollama'
    config['baseUrl'] = os.getenv('OLLAMA_HOST', 'http://localhost:11434/v1')

    if args.model:
        config['model'] = args.model

    if not config.get('model'):
        config = interactive_setup(config)
        save_config(config)

    if not config.get('model'):
        config['model'] = 'llama3'

    # 登录
    session = login(args.login)

    provider_label = f"{config['provider']} ({config['model']})"
    print(f"  [OK] WeChat-Ollama is running!")
    print(f"  AI: {provider_label}")
    print(f"  Key: {mask_key(config.get('apiKey', ''))}")
    print(f"  Press Ctrl+C to stop.\n")
    print("  " + "─" * 30 + "\n")

    start_time = time.time()
    total_messages = 0

    def on_message():
        nonlocal total_messages
        total_messages += 1
        return total_messages

    poll_loop(config, session, start_time, on_message)

if __name__ == '__main__':
    main()