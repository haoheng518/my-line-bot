import os
import sys
import pandas as pd
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

EXCEL_FILE = 'contacts.xlsx'

# ==================== 改进后的读取函数 ====================
def load_contacts():
    """更稳健地读取 Excel 中的联系人"""
    try:
        if not os.path.exists(EXCEL_FILE):
            print(f"警告: Excel 文件 '{EXCEL_FILE}' 不存在")
            return []

        # 先获取所有工作表名称，避免写死 sheet_name
        xl_file = pd.ExcelFile(EXCEL_FILE)
        sheet_names = xl_file.sheet_names
        print(f"Excel 中的工作表: {sheet_names}")

        # 优先使用第一个有数据的工作表（通常是 Sheet1）
        target_sheet = sheet_names[0] if sheet_names else 'Sheet1'
        print(f"将读取工作表: '{target_sheet}'")

        # 读取时让 pandas 自动检测表头
        df = pd.read_excel(EXCEL_FILE, sheet_name=target_sheet, header=None)

        # 如果第一行看起来像表头（比如包含"姓名"、"电话"），则用第二行作为数据
        first_row = df.iloc[0].astype(str).str.strip()
        if first_row.str.contains('姓名|电话|序號|分數|号码|编号').any():
            print("检测到表头行，自动跳过")
            df = df.iloc[1:].reset_index(drop=True)

        # 提取前两列作为姓名和电话
        # 如果第一列看起来像序号（全是数字），则用第二列作为姓名，第三列作为电话
        col0 = df.iloc[:, 0].astype(str).str.strip()
        if col0.str.isdigit().all():
            print("检测到序号列，自动跳过")
            name_col = 1
            phone_col = 2
        else:
            name_col = 0
            phone_col = 1

        # 确保列存在
        if df.shape[1] <= max(name_col, phone_col):
            print(f"错误: 列数不足，只有 {df.shape[1]} 列")
            return []

        contacts = []
        for _, row in df.iterrows():
            try:
                name = str(row.iloc[name_col]).strip()
                phone_raw = str(row.iloc[phone_col]).strip()
                phone = ''.join(filter(str.isdigit, phone_raw))

                # 只保留有效的台湾手机号（10位，09开头）
                if len(phone) == 10 and phone.startswith('09'):
                    contacts.append({'name': name, 'phone': phone})
                elif len(phone) >= 9 and not phone.startswith('09'):
                    # 可能是其他格式，保留但需清洗
                    print(f"非标准台湾号码: {name} -> {phone}")
            except Exception as e:
                print(f"处理行时出错: {e}")
                continue

        print(f"成功加载 {len(contacts)} 个有效联系人")
        return contacts

    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        import traceback
        traceback.print_exc()
        return []

# ==================== 发送名片函数 ====================
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

    # 只在需要时加载联系人（优化性能）
    if text in ["所有名片", "搜索"] or text.startswith("搜索"):
        contacts = load_contacts()
    else:
        contacts = []

    if text == "所有名片":
        if not contacts:
            line_bot_api.push_message(user_id, line_models.TextSendMessage(text="通讯录为空，请检查 Excel 文件。"))
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
