import os
import sys
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
import linebot.models as line_models  # 导入整个模块

app = Flask(__name__)

# 从环境变量读取 LINE 配置
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

# 添加启动日志
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

EXCEL_FILE = 'contacts.xlsx'

def load_contacts():
    """读取 Excel 中的联系人"""
    try:
        if not os.path.exists(EXCEL_FILE):
            print(f"警告: Excel 文件 '{EXCEL_FILE}' 不存在")
            return []
        df = pd.read_excel(EXCEL_FILE, sheet_name='Sheet2', header=None)
        df.columns = ['name', 'phone']
        contacts = []
        for _, row in df.iterrows():
            name = str(row['name']).strip()
            phone = ''.join(filter(str.isdigit, str(row['phone']).strip()))
            if len(phone) == 10 and phone.startswith('09'):
                contacts.append({'name': name, 'phone': phone})
        print(f"成功加载 {len(contacts)} 个联系人")
        return contacts
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return []

def send_contact_card(user_id, contact):
    """发送联系人名片消息"""
    try:
        # 使用 line_models.Contact 尝试正确的类
        contact_message = line_models.Contact(
            display_name=contact['name'],
            name=contact['name'],
            phone_number=contact['phone']
        )
        line_bot_api.push_message(user_id, contact_message)
        print(f"已发送名片: {contact['name']}")
    except AttributeError:
        # 如果 Contact 不存在，尝试使用 ContactMessage
        try:
            contact_message = line_models.ContactMessage(
                display_name=contact['name'],
                name=contact['name'],
                phone_number=contact['phone']
            )
            line_bot_api.push_message(user_id, contact_message)
            print(f"已发送名片 (ContactMessage): {contact['name']}")
        except Exception as e:
            print(f"发送名片失败: {e}")
            raise

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

@handler.add(line_models.MessageEvent, message=line_models.TextMessage)
def handle_message(event):
    """处理用户发来的文字消息"""
    user_id = event.source.user_id
    text = event.message.text.strip()
    print(f"收到消息: {text} from {user_id}")
    contacts = load_contacts()

    if text == "所有名片":
        if not contacts:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text="通讯录为空，请检查 Excel 文件。"))
            return
        for contact in contacts:
            send_contact_card(user_id, contact)
        line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"✅ 已发送 {len(contacts)} 张名片"))

    elif text.startswith("搜索"):
        keyword = text.replace("搜索", "").strip()
        results = [c for c in contacts if keyword in c['name']]
        if not results:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"❌ 未找到包含「{keyword}」的联系人"))
        elif len(results) == 1:
            send_contact_card(user_id, results[0])
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"✅ 已发送 {results[0]['name']} 的名片"))
        else:
            names = "\n".join([f"{i+1}. {c['name']}" for i, c in enumerate(results[:10])])
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"找到多个联系人，请输入完整姓名：\n{names}"))

    else:
        line_bot_api.push_message(
            user_id,
            line_models.TextSendMessage(text="请输入「所有名片」查看全部，或「搜索 姓名」查找特定联系人")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
