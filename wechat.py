import requests
import time
import json
import base64
import os

BASE_URL = "https://ilinkai.weixin.qq.com"
POLL_TIMEOUT = 10
API_TIMEOUT = 10

def _random_uin():
    return base64.b64encode(os.urandom(4)).decode()

def _headers(token=None, body=None):
    headers = {
        'Content-Type': 'application/json',
        'AuthorizationType': 'ilink_bot_token',
        'X-WECHAT-UIN': _random_uin(),
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers

def _post(endpoint, data=None, token=None, timeout=API_TIMEOUT):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    try:
        resp = requests.post(
            url,
            json={**(data or {}), 'base_info': {'channel_version': '1.0.0'}},
            headers=_headers(token),
            timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        return None
    except Exception as e:
        raise RuntimeError(f"WeChat API error: {e}")

# 获取二维码
def get_qr_code():
    url = f"{BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

# 轮询二维码状态
def poll_qr_status(qrcode):
    url = f"{BASE_URL}/ilink/bot/get_qrcode_status?qrcode={qrcode}"
    try:
        resp = requests.get(url, headers={'iLink-App-ClientVersion': '1'}, timeout=POLL_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        return {'status': 'wait'}
    except Exception as e:
        raise RuntimeError(f"Poll QR error: {e}")

# 获取更新（长轮询）
def get_updates(token, buf=''):
    resp = _post('/ilink/bot/getupdates', {'get_updates_buf': buf}, token, timeout=POLL_TIMEOUT)
    if resp is None:
        return {'msgs': [], 'get_updates_buf': buf}
    return resp

# 发送文本消息
def send_text(token, to_user_id, text, context_token):
    client_id = f"wb-{os.urandom(8).hex()}"
    _post('/ilink/bot/sendmessage', {
        'msg': {
            'from_user_id': '',
            'to_user_id': to_user_id,
            'client_id': client_id,
            'message_type': 2,
            'message_state': 2,
            'context_token': context_token,
            'item_list': [{'type': 1, 'text_item': {'text': text}}]
        }
    }, token)

# 发送“正在输入”状态
def send_typing(token, user_id, context_token):
    try:
        cfg = _post('/ilink/bot/getconfig', {
            'ilink_user_id': user_id,
            'context_token': context_token
        }, token, timeout=10)
        if cfg and cfg.get('typing_ticket'):
            _post('/ilink/bot/sendtyping', {
                'ilink_user_id': user_id,
                'typing_ticket': cfg['typing_ticket'],
                'status': 1
            }, token, timeout=10)
    except:
        pass

# 提取消息文本（仅文本，忽略图片等）
def extract_text(msg):
    text = ''
    mediaLabel = ''

    for item in msg.get('item_list', []):
        if item.get('type') == 1 and 'text_item' in item:
            text = item['text_item'].get('text', '')
        elif item.get('type') == 2 and not mediaLabel:
            mediaLabel = '[图片]'
        elif item.get('type') == 3 and not mediaLabel:
            mediaLabel = '[语音]'
        elif item.get('type') == 4 and not mediaLabel:
            mediaLabel = '[文件]'
        elif item.get('type') == 5 and not mediaLabel:
            mediaLabel = '[视频]'

    return text or mediaLabel or ''