import os
import sys
import csv
import re
from flask import Flask, request, abort

# 导入 v3 版本的模块
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage
)
# ✅ 直接从子模块导入 ContactMessage
from linebot.v3.messaging.models.contact_message import ContactMessage
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

app = Flask(__name__)

# ==================== LINE 配置 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

print("=== 启动 LINE Bot 服务 (v3) ===")
print(f"LINE_CHANNEL_SECRET 是否设置: {bool(LINE_CHANNEL_SECRET)}")
print(f"LINE_CHANNEL_ACCESS_TOKEN 是否设置: {bool(LINE_CHANNEL_ACCESS_TOKEN)}")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    print("错误: 缺少必要的环境变量!")
    sys.exit(1)

# 初始化 v3 WebhookHandler
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化 v3 API 客户端配置
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

CSV_FILE = 'contacts.csv'
SENT_FILE = 'sent_contacts.csv'

# ==================== 核心功能函数 ====================

def load_available_contacts():
    """读取CSV，返回还没被发送过的联系人列表"""
    try:
        if not os.path.exists(CSV_FILE):
            print(f"警告: CSV 文件 '{CSV_FILE}' 不存在")
            return []

        all_contacts = []
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                first_cell = row[0].strip()
                if first_cell in ['姓名', '名字', 'name', '序号', '编号']:
                    continue
                name = row[0].strip()
                phone_raw = row[1].strip() if len(row) > 1 else ''
                phone = ''.join(filter(str.isdigit, phone_raw))
                if len(phone) >= 9:
                    all_contacts.append({'name': name, 'phone': phone})

        sent_phones = set()
        if os.path.exists(SENT_FILE):
            with open(SENT_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        sent_phones.add(row[0].strip())

        available = [c for c in all_contacts if c['phone'] not in sent_phones]
        print(f"总共 {len(all_contacts)} 个联系人，已发送 {len(sent_phones)} 个，剩余 {len(available)} 个")
        return available

    except Exception as e:
        print(f"读取 CSV 失败: {e}")
        return []

def mark_as_sent(contacts):
    """将已发送的联系人记录到 sent_contacts.csv"""
    try:
        with open(SENT_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for contact in contacts:
                writer.writerow([contact['phone'], contact['name']])
        print(f"✅ 已标记 {len(contacts)} 个联系人为已发送")
    except Exception as e:
        print(f"标记已发送失败: {e}")

def send_contact_card_v3(user_id, contact):
    """使用 v3 API 发送 LINE 原生联系人卡片"""
    try:
        # ✅ 使用正确的 ContactMessage 类
        contact_message = ContactMessage(
            display_name=contact['name'],
            name=contact['name'],
            phone_number=contact['phone']
        )
        
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[contact_message]
                )
            )
        print(f"✅ (v3) 已发送 {contact['name']} 的联系人卡片")
        return True
    except Exception as e:
        print(f"(v3) 发送联系人卡片失败: {e}")
        return False

# ==================== 路由和处理器 ====================

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("签名验证失败")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text
    print(f"收到消息: {text} from {user_id}")

    if text.startswith("要"):
        try:
            match = re.search(r'要(\d+)个', text)
            if not match:
                match = re.search(r'要(\d+)', text)
            if not match:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="请发送「要10个粉」或「要20个」这样的指令")]
                        )
                    )
                return

            count = int(match.group(1))
            if count <= 0 or count > 100:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="请输入1-100之间的数字")]
                        )
                    )
                return

            available = load_available_contacts()
            if not available:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="🎉 所有名片已经发完了！")]
                        )
                    )
                return

            to_send = available[:count]
            if len(to_send) < count:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text=f"只剩 {len(to_send)} 个了，全部给您发完")]
                        )
                    )

            success_count = 0
            for contact in to_send:
                if send_contact_card_v3(user_id, contact):
                    success_count += 1

            mark_as_sent(to_send)

            remaining = len(available) - len(to_send)
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text=f"✅ 已发送 {success_count} 张联系人卡片\n📊 剩余 {remaining} 个待发")]
                    )
                )

        except Exception as e:
            print(f"处理指令出错: {e}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="处理出错，请稍后再试")]
                    )
                )
        return

    else:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="📋 使用说明：\n发送「要10个粉」领取10张联系人卡片\n发送「要50个」领取50张\n一次最多100个，发完自动标记")]
                )
            )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
