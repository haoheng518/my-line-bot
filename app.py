import os
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ContactMessage

app = Flask(__name__)

# 从环境变量读取 LINE 配置
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("请设置环境变量 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

EXCEL_FILE = 'contacts.xlsx'

def load_contacts():
    """读取 Excel 中的联系人"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Sheet2', header=None)
        df.columns = ['name', 'phone']
        contacts = []
        for _, row in df.iterrows():
            name = str(row['name']).strip()
            phone = ''.join(filter(str.isdigit, str(row['phone']).strip()))
            if len(phone) == 10 and phone.startswith('09'):
                contacts.append({'name': name, 'phone': phone})
        return contacts
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return []

def send_contact_card(user_id, contact):
    """发送联系人名片消息"""
    contact_message = ContactMessage(
        display_name=contact['name'],
        name=contact['name'],
        phone_number=contact['phone']
    )
    line_bot_api.push_message(user_id, contact_message)

@app.route("/callback", methods=['POST'])
def callback():
    """LINE Webhook 回调接口"""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """处理用户发来的文字消息"""
    user_id = event.source.user_id
    text = event.message.text.strip()
    contacts = load_contacts()

    if text == "所有名片":
        if not contacts:
            line_bot_api.push_message(user_id, TextSendMessage(text="通讯录为空，请检查 Excel 文件。"))
            return
        for contact in contacts:
            send_contact_card(user_id, contact)
        line_bot_api.push_message(user_id, TextSendMessage(text=f"✅ 已发送 {len(contacts)} 张名片"))

    elif text.startswith("搜索"):
        keyword = text.replace("搜索", "").strip()
        results = [c for c in contacts if keyword in c['name']]
        if not results:
            line_bot_api.push_message(user_id, TextSendMessage(text=f"❌ 未找到包含「{keyword}」的联系人"))
        elif len(results) == 1:
            send_contact_card(user_id, results[0])
            line_bot_api.push_message(user_id, TextSendMessage(text=f"✅ 已发送 {results[0]['name']} 的名片"))
        else:
            names = "\n".join([f"{i+1}. {c['name']}" for i, c in enumerate(results[:10])])
            line_bot_api.push_message(user_id, TextSendMessage(text=f"找到多个联系人，请输入完整姓名：\n{names}"))

    else:
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text="请输入「所有名片」查看全部，或「搜索 姓名」查找特定联系人")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
