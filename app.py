import os
import sys
import csv
import re
import base64
import qrcode
import requests
from io import BytesIO
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    ImageSendMessage
)

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

# ==================== ImgBB 图床配置 ====================
# 🔑 请去 https://imgbb.com 注册免费账号，获取你的 API Key 替换下面这行
IMGBB_API_KEY = "你的ImgBB_API_Key"

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

def generate_vcard_qr(contact):
    """
    生成包含 vCard 信息的二维码
    用户扫码后可直接保存到手机通讯录
    """
    name = contact['name']
    phone = contact['phone']
    
    # 构建 vCard 3.0 格式字符串
    vcard = f"""BEGIN:VCARD
VERSION:3.0
FN:{name}
TEL:{phone}
END:VCARD"""
    
    # 生成二维码
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(vcard)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

def upload_to_imgbb(image_bytes):
    """上传图片到 ImgBB 免费图床，返回公开 HTTPS URL"""
    try:
        url = "https://api.imgbb.com/1/upload"
        image_base64 = base64.b64encode(image_bytes.getvalue()).decode('utf-8')
        
        payload = {
            "key": IMGBB_API_KEY,
            "image": image_base64,
        }
        response = requests.post(url, data=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result['data']['url']
            else:
                print(f"ImgBB 上传失败: {result}")
                return None
        else:
            print(f"ImgBB 上传失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"上传到图床失败: {e}")
        return None

def send_contact_card(user_id, contact):
    """发送联系人 vCard 二维码名片"""
    try:
        # 1. 生成二维码
        qr_image = generate_vcard_qr(contact)
        
        # 2. 上传到图床获取 URL
        image_url = upload_to_imgbb(qr_image)
        
        if image_url:
            # 3. 发送二维码图片
            line_bot_api.push_message(
                user_id,
                ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                )
            )
            print(f"✅ 已发送 {contact['name']} 的 vCard 二维码")
            return True
        else:
            # 上传失败时发送文本提示
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"⚠️ {contact['name']} 的二维码上传失败，请稍后重试")
            )
            return False
    except Exception as e:
        print(f"发送二维码失败: {e}")
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
            # 解析数量，支持 "要10个粉" 或 "要10" 等格式
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
            if count <= 0:
                line_bot_api.push_message(user_id, TextSendMessage(text="数量必须大于0"))
                return
            if count > 100:
                line_bot_api.push_message(user_id, TextSendMessage(text="一次最多要100个，请分批领取"))
                return

            # 获取可用联系人
            available = load_available_contacts()
            if not available:
                line_bot_api.push_message(user_id, TextSendMessage(text="🎉 所有名片已经发完了！"))
                return

            # 取出前 N 个
            to_send = available[:count]
            if len(to_send) < count:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=f"只剩 {len(to_send)} 个了，全部给您发完")
                )

            # 逐一发送
            success_count = 0
            for contact in to_send:
                if send_contact_card(user_id, contact):
                    success_count += 1

            # 标记为已发送
            mark_as_sent(to_send)

            remaining = len(available) - len(to_send)
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"✅ 已发送 {success_count} 张名片二维码\n📊 剩余 {remaining} 个待发")
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
            TextSendMessage(text="📋 使用说明：\n发送「要10个粉」领取10张名片二维码\n发送「要50个」领取50张\n一次最多100个，发完自动标记")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
