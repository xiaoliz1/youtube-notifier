import feedparser
import requests
import json
import os
import sys
from datetime import datetime
import time

# ==================== 配置 ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

STATE_FILE = 'state.json'
CHANNELS_FILE = 'channels.txt'

# ==================== 加载频道（ID + 名称） ====================
def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        print(f"[警告] {CHANNELS_FILE} 不存在，使用空列表。")
        return []
    
    channels = []
    with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('|', 1)
                channel_id = parts[0].strip()
                channel_name = parts[1].strip() if len(parts) > 1 else None
                channels.append({'id': channel_id, 'name': channel_name})
                print(f"[加载] 频道 {len(channels)}: {channel_id} ({channel_name or '自动获取'})")
            elif line.startswith('#'):
                print(f"[注释] 行 {line_num}: {line}")
    return channels

# ==================== 获取频道名称（RSS） ====================
def get_channel_name(channel_id):
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.bozo:
            return feed.feed.get('title', '未知频道')
    except Exception as e:
        print(f"[异常] 获取频道 {channel_id} 名称失败: {e}")
    return '未知频道'

# ==================== 状态管理 ====================
def load_state(channels):
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception as e:
            print(f"[错误] 读取 state.json 失败: {e}")
            state = {}
    for ch in channels:
        cid = ch['id']
        if cid not in state:
            state[cid] = {'last_video_id': None}
    return state

def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        print(f"[状态] state.json 已保存")
    except Exception as e:
        print(f"[错误] 保存 state.json 失败: {e}")

# ==================== 获取最新视频 ====================
def get_latest_videos(channel_id):
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(rss_url)
        if feed.bozo or not feed.entries:
            return []
        entry = feed.entries[0]
        return [{
            'title': entry.title,
            'link': entry.link,
            'video_id': entry.yt_videoid,
            'description': entry.get('media_description', '') or entry.get('summary', ''),
            'thumbnail': entry.media_thumbnail[0]['url'] if entry.get('media_thumbnail') else '',
            'published': entry.published
        }]
    except Exception as e:
        print(f"[网络错误] 获取 {channel_id} 失败: {e}")
        return []

# ==================== Telegram 通知（按钮在缩略图下方，简介100字） ====================
def send_telegram_notification(video, channel_name):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[跳过] Telegram 配置缺失")
        return

    # 简介截断 100 字
    desc = video['description']
    short_desc = (desc[:100] + '…') if len(desc) > 100 else desc

    message = (
        f"*新视频更新！*\n"
        f"**频道**：{channel_name}\n\n"
        f"**标题**：{video['title']}\n"
        f"**时间**：{video['published']}\n"
        f"**简介**：{short_desc}"
    )

    # 按钮在缩略图正下方
    keyboard = {
        "inline_keyboard": [
            [{"text": "观看视频", "url": video['link']}]
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'photo': video['thumbnail'],
        'caption': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }

    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            print(f"[成功] 已发送通知: {video['title'][:30]}...")
        else:
            print(f"[失败] Telegram: {r.status_code} {r.text}")
    except Exception as e:
        print(f"[异常] 发送失败: {e}")

# ==================== 主逻辑 ====================
def check_updates():
    channels = load_channels()
    if not channels:
        print("[退出] 无频道配置")
        return

    state = load_state(channels)
    updated = False

    for idx, ch in enumerate(channels, 1):
        cid = ch['id']
        name = ch['name'] or get_channel_name(cid)
        print(f"\n[检查 {idx}/{len(channels)}] {cid} ({name})")

        videos = get_latest_videos(cid)
        if not videos:
            print(f"[跳过] 无视频数据")
            continue

        latest = videos[0]
        last_id = state[cid].get('last_video_id')

        if latest['video_id'] != last_id:
            print(f"[新视频] {latest['video_id']}")
            send_telegram_notification(latest, name)
            state[cid]['last_video_id'] = latest['video_id']
            updated = True
        else:
            print(f"[无更新]")

    if updated:
        save_state(state)
    else:
        print("[完成] 无新视频")

# ==================== 入口 ====================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--check-id':
        check_channel_id(sys.argv[2])
    else:
        check_updates()