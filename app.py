import os
import sys
import csv
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
)

# ==================== 诊断代码：打印所有可用的类 ====================
print("=" * 50)
print("🔍 正在诊断 linebot.models 可用的类...")
try:
    import linebot.models
    available_classes = [x for x in dir(linebot.models) if x[0].isupper()]
    print(f"linebot.models 中可用的类: {available_classes}")
except Exception as e:
    print(f"诊断 linebot.models 失败: {e}")

print("-" * 50)

print("🔍 正在诊断 linebot.v3.messaging 可用的类...")
try:
    from linebot.v3 import messaging
    available_classes_v3 = [x for x in dir(messaging) if x[0].isupper()]
    print(f"linebot.v3.messaging 中可用的类: {available_classes_v3}")
except Exception as e:
    print(f"诊断 linebot.v3.messaging 失败: {e}")

print("-" * 50)

print("🔍 正在诊断 linebot.v3.messaging.models 可用的类...")
try:
    from linebot.v3.messaging import models
    available_classes_v3_models = [x for x in dir(models) if x[0].isupper()]
    print(f"linebot.v3.messaging.models 中可用的类: {available_classes_v3_models}")
except Exception as e:
    print(f"诊断 linebot.v3.messaging.models 失败: {e}")

print("=" * 50)
# ==================== 诊断代码结束 ====================

app = Flask(__name__)

# ==================== LINE 配置 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

print("=== 启动 LINE Bot 服务 ===")
print(f"LINE_CHANNEL_SECRET 是否设置: {bool(LINE_CHANNEL_SECRET)}")
print(f"LINE_CHANNEL_ACCESS_TOKEN 是否设置: {bool(LINE_CHANNEL_ACCESS_TOKEN)}")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    print("错误: 缺少必要的环境变量!")
    sys.exit(1)

try:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
    print("LINE Bot API 初始化成功")
except Exception as e:
    print(f"LINE Bot API 初始化失败: {e}")
    sys.exit(1)

CSV_FILE = 'contacts.csv'
SENT_FILE = 'sent_contacts.csv'

def load_available_contacts():
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
    try:
        with open(SENT_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for contact in contacts:
                writer.writerow([contact['phone'], contact['name']])
        print(f"✅ 已标记 {len(contacts)} 个联系人为已发送")
    except Exception as e:
        print(f"标记已发送失败: {e}")

def send_contact_card(user_id, contact):
    """尝试发送 LINE 联系人卡片 - 使用诊断发现的正确类名"""
    try:
        # 先尝试使用 v3 的 ContactMessage
        try:
            from linebot.v3.messaging import ContactMessage
            print("✅ 使用 linebot.v3.messaging.ContactMessage")
            contact_message = ContactMessage(
                display_name=contact['name'],
                name=contact['name'],
                phone_number=contact['phone']
            )
            # 这里需要 v3 的 ApiClient，暂时用旧版方式
            # 如果导入成功，我们后续再调整
            return False
        except ImportError:
            pass
        
        # 再尝试使用 v2 的 ContactMessage
        try:
            from linebot.models import ContactMessage
            print("✅ 使用 linebot.models.ContactMessage")
            contact_message = ContactMessage(
                display_name=contact['name'],
                name=contact['name'],
                phone_number=contact['phone']
            )
            line_bot_api.push_message(user_id, contact_message)
            print(f"✅ 已发送 {contact['name']} 的联系人卡片")
            return True
        except ImportError:
            pass
        
        # 尝试 Contact（不带 Message）
        try:
            from linebot.models import Contact
            print("✅ 使用 linebot.models.Contact")
            contact_message = Contact(
                display_name=contact['name'],
                name=contact['name'],
                phone_number=contact['phone']
            )
            line_bot_api.push_message(user_id, contact_message)
            print(f"✅ 已发送 {contact['name']} 的联系人卡片")
            return True
        except ImportError:
            pass
        
        print("❌ 所有尝试都失败了，找不到联系人卡片类")
        return False
        
    except Exception as e:
        print(f"发送联系人卡片失败: {e}")
        return False

# ==================== 路由和处理器 ====================

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    print(f"收到消息: {text} from {user_id}")

    if text.startswith("要"):
        try:
            match = re.search(r'要(\d+)个', text)
            if not match:
                match = re.search(r'要(\d+)', text)
            if not match:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text="请发送「要10个粉」或「要20个」这样的指令")
                )
                return

            count = int(match.group(1))
            if count <= 0 or count > 100:
                line_bot_api.push_message(user_id, TextSendMessage(text="请输入1-100之间的数字"))
                return

            available = load_available_contacts()
            if not available:
                line_bot_api.push_message(user_id, TextSendMessage(text="🎉 所有名片已经发完了！"))
                return

            to_send = available[:count]
            if len(to_send) < count:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=f"只剩 {len(to_send)} 个了，全部给您发完")
                )

            success_count = 0
            for contact in to_send:
                if send_contact_card(user_id, contact):
                    success_count += 1

            mark_as_sent(to_send)

            remaining = len(available) - len(to_send)
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"✅ 已发送 {success_count} 张联系人卡片\n📊 剩余 {remaining} 个待发")
            )

        except Exception as e:
            print(f"处理指令出错: {e}")
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text="处理出错，请稍后再试")
            )
        return

    else:
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text="📋 使用说明：\n发送「要10个粉」领取10张联系人卡片\n发送「要50个」领取50张\n一次最多100个，发完自动标记")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
