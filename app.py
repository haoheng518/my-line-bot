import os
import sys
import csv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
import linebot.models as line_models

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

def load_contacts():
    """从 CSV 读取联系人"""
    try:
        if not os.path.exists(CSV_FILE):
            print(f"警告: CSV 文件 '{CSV_FILE}' 不存在")
            return []

        contacts = []
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                # 跳过可能存在的表头行
                first_cell = row[0].strip()
                if first_cell in ['姓名', '名字', 'name', '序号', '编号']:
                    continue

                # 取前两列作为姓名和电话
                name = row[0].strip()
                # 如果第二列存在，否则尝试第三列
                phone_raw = row[1].strip() if len(row) > 1 else ''
                if not phone_raw and len(row) > 2:
                    phone_raw = row[2].strip()

                phone = ''.join(filter(str.isdigit, phone_raw))

                # 只保留有效的台湾手机号（10位，09开头）
                if len(phone) == 10 and phone.startswith('09'):
                    contacts.append({'name': name, 'phone': phone})

        print(f"成功加载 {len(contacts)} 个联系人")
        return contacts

    except Exception as e:
        print(f"读取 CSV 失败: {e}")
        return []

def send_contact_card(user_id, contact):
    """发送联系人名片消息"""
    try:
        contact_message = line_models.Contact(
            display_name=contact['name'],
            name=contact['name'],
            phone_number=contact['phone']
        )
        line_bot_api.push_message(user_id, contact_message)
        print(f"已发送名片: {contact['name']} ({contact['phone']})")
    except AttributeError:
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

@handler.add(line_models.MessageEvent, message=line_models.TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    print(f"收到消息: {text} from {user_id}")

    if text in ["所有名片", "搜索"] or text.startswith("搜索"):
        contacts = load_contacts()
    else:
        contacts = []

    if text == "所有名片":
        if not contacts:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text="通讯录为空，请检查 CSV 文件。"))
            return
        for contact in contacts:
            send_contact_card(user_id, contact)
        line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"✅ 已发送 {len(contacts)} 张名片"))

    elif text.startswith("搜索"):
        keyword = text.replace("搜索", "").strip()
        if not keyword:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text="请输入要搜索的姓名，例如「搜索 陳小姐」"))
            return
        results = [c for c in contacts if keyword in c['name']]
        if not results:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"❌ 未找到包含「{keyword}」的联系人"))
        elif len(results) == 1:
            send_contact_card(user_id, results[0])
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"✅ 已发送 {results[0]['name']} 的名片"))
        else:
            names = "\n".join([f"{i+1}. {c['name']}" for i, c in enumerate(results[:10])])
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text=f"找到 {len(results)} 个联系人，请输入完整姓名：\n{names}"))

    else:
        line_bot_api.push_message(
            user_id,
            line_models.TextSendMessage(text="请输入「所有名片」查看全部，或「搜索 姓名」查找特定联系人")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"服务启动在端口 {port}")
    app.run(host="0.0.0.0", port=port)
