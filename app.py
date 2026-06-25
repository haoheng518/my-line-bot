import os
import sys
import csv
import re
import base64
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    FlexSendMessage,
    BubbleContainer,
    BoxComponent,
    TextComponent,
    ButtonComponent,
    URIAction,
    SeparatorComponent
)

app = Flask(__name__)

# ==================== LINE 配置 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

print("=== 启动 LINE Bot 服务 (vCard 上传方案) ===")
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
IMGBB_API_KEY = "ff882946769eae6ae4133abbb791945e"

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

def generate_vcard(contact):
    """生成 vCard 格式文本"""
    name = contact['name']
    phone = contact['phone']
    return f"""BEGIN:VCARD
VERSION:3.0
FN:{name}
TEL:{phone}
END:VCARD"""

def upload_vcard_to_imgbb(vcard_text, filename):
    """上传 vCard 文本到 ImgBB，返回公开 URL"""
    try:
        url = "https://api.imgbb.com/1/upload"
        # 将文本转为 Base64
        vcard_bytes = vcard_text.encode('utf-8')
        image_base64 = base64.b64encode(vcard_bytes).decode('utf-8')
        
        payload = {
            "key": IMGBB_API_KEY,
            "image": image_base64,
            "name": filename,
        }
        response = requests.post(url, data=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result['data']['url']
        print(f"ImgBB 上传失败: {response.text}")
        return None
    except Exception as e:
        print(f"上传到图床失败: {e}")
        return None

def create_contact_flex(contact):
    """创建包含 vCard 下载按钮的 Flex Message"""
    name = contact['name']
    phone = contact['phone']
    
    # 生成 vCard 并上传
    vcard = generate_vcard(contact)
    filename = f"{name}_{phone}.vcf"
    vcard_url = upload_vcard_to_imgbb(vcard, filename)
    
    if not vcard_url:
        # 上传失败时，返回只有号码的简化版本
        return FlexSendMessage(
            alt_text=f"📇 {name} 的名片",
            contents=BubbleContainer(
                direction='ltr',
                header=BoxComponent(
                    layout='vertical',
                    contents=[
                        TextComponent(
                            text='📇 联系人名片',
                            weight='bold',
                            size='sm',
                            color='#FFFFFF'
                        )
                    ],
                    backgroundColor='#00B900'
                ),
                body=BoxComponent(
                    layout='vertical',
                    spacing='sm',
                    contents=[
                        TextComponent(
                            text=name,
                            weight='bold',
                            size='lg',
                            wrap=True
                        ),
                        SeparatorComponent(),
                        BoxComponent(
                            layout='horizontal',
                            spacing='sm',
                            contents=[
                                TextComponent(
                                    text='📞 电话',
                                    size='sm',
                                    color='#AAAAAA',
                                    flex=1
                                ),
                                TextComponent(
                                    text=phone,
                                    size='sm',
                                    color='#000000',
                                    flex=2
                                )
                            ]
                        )
                    ]
                ),
                footer=BoxComponent(
                    layout='vertical',
                    spacing='sm',
                    contents=[
                        ButtonComponent(
                            style='link',
                            action=URIAction(
                                label='📋 复制号码',
                                uri=f'tel:{phone}'
                            )
                        )
                    ]
                )
            )
        )
    
    # 正常返回带下载按钮的卡片
    return FlexSendMessage(
        alt_text=f"📇 {name} 的名片",
        contents=BubbleContainer(
            direction='ltr',
            header=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(
                        text='📇 联系人名片',
                        weight='bold',
                        size='sm',
                        color='#FFFFFF'
                    )
                ],
                backgroundColor='#00B900'
            ),
            body=BoxComponent(
                layout='vertical',
                spacing='sm',
                contents=[
                    TextComponent(
                        text=name,
                        weight='bold',
                        size='lg',
                        wrap=True
                    ),
                    SeparatorComponent(),
                    BoxComponent(
                        layout='horizontal',
                        spacing='sm',
                        contents=[
                            TextComponent(
                                text='📞 电话',
                                size='sm',
                                color='#AAAAAA',
                                flex=1
                            ),
                            TextComponent(
                                text=phone,
                                size='sm',
                                color='#000000',
                                flex=2
                            )
                        ]
                    )
                ]
            ),
            footer=BoxComponent(
                layout='vertical',
                spacing='sm',
                contents=[
                    ButtonComponent(
                        style='primary',
                        color='#00B900',
                        action=URIAction(
                            label='📥 保存到通讯录',
                            uri=vcard_url
                        )
                    ),
                    ButtonComponent(
                        style='link',
                        action=URIAction(
                            label='📋 复制号码',
                            uri=f'tel:{phone}'
                        )
                    )
                ]
            )
        )
    )

def send_contact_card(user_id, contact):
    """发送联系人名片 Flex Message"""
    try:
        flex_message = create_contact_flex(contact)
        line_bot_api.push_message(user_id, flex_message)
        print(f"✅ 已发送 {contact['name']} 的联系人名片")
        return True
    except Exception as e:
        print(f"发送联系人名片失败: {e}")
        return False

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
                TextSendMessage(text=f"✅ 已发送 {success_count} 张名片\n📊 剩余 {remaining} 个待发")
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
            TextSendMessage(text="📋 使用说明：\n发送「要10个粉」领取10张名片\n发送「要50个」领取50张\n一次最多100个，发完自动标记")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
