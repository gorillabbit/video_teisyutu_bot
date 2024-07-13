import discord
from discord.ext import commands, tasks
import re
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from dotenv import load_dotenv

# .envファイルの内容を読み込み
load_dotenv()

# 環境変数から値を取得
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SPREADSHEET_SCOPE = os.getenv('SPREADSHEET_SCOPE')
SERVICE_ACCOUNT = os.getenv('SERVICE_ACCOUNT')
CATEGORY_ID = int(os.getenv('CATEGORY_ID'))

RANGE_NAME = 'シート1!A1:Z200'  # スプレッドシートの範囲

PENDING_JSON = "pending_list.json"
PENDING = "未提出"
PARTICIPANT_JSON = "participant.json"

# Google Sheets APIの認証情報を取得
creds = service_account.Credentials.from_service_account_file('service_account.json', scopes=["https://www.googleapis.com/auth/spreadsheets"])

service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

# ボットのプレフィックスを設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を取得するための意図を有効にする
intents.reactions = True  # リアクションの意図を有効にする
intents.guilds = True  # ギルド関連のイベントを受け取るために必要
intents.messages = True  # メッセージ関連のイベントを受け取るために必要
bot = commands.Bot(command_prefix='!', intents=intents)

# JSON読み込み関数
def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

# JSON書き込み関数
def save_json(filename, content):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=4)

# ボットが起動した時に呼ばれるイベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not check_pending_list.is_running():
        check_pending_list.start() # 未提出リストのチェックを開始

# 未提出リストにIDがある人にメンションを飛ばすタスク
@tasks.loop(hours=12) # 半日ごとに実行
async def check_pending_list():
    print("Checking pending list...")
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.category_id == CATEGORY_ID:
                await check_pending_list_in_channel(channel)

async def check_pending_list_in_channel(channel):
    async for msg in channel.history(limit=100):
        if msg.attachments:
            for attachment in msg.attachments:
                if attachment.filename == PENDING_JSON:
                    await attachment.save(PENDING_JSON)
                    pending_list_content = load_json(PENDING_JSON)
                    mentions = [f"<@{user['ID']}>" for user in pending_list_content.get(PENDING, [])]
                    if mentions:
                        mention_message = "以下はまだ提出していません:\n" + "\n".join(mentions)
                        await channel.send(mention_message)
                    break

# 参加者リストを処理する関数
async def process_participant_list(message):
    for attachment in message.attachments:
        if attachment.filename == PARTICIPANT_JSON:
            try:
                json_content = await attachment.read()
                participants = json.loads(json_content.decode('utf-8'))["参加者リスト"]
                pending_list_content = {PENDING: participants}
                save_json(PENDING_JSON, pending_list_content)
                sent_message = await message.channel.send(file=discord.File(PENDING_JSON))
                await sent_message.pin()
                print(f"未提出リスト created in '{message.channel.name}'")
            except Exception as e:
                print(f"An error occurred while creating the 未提出リスト: {e}")

async def update_pending_list(message, author_id):
    async for msg in message.channel.history(limit=100):
        if msg.attachments:
            for attachment in msg.attachments:
                if attachment.filename == PENDING_JSON:
                    await attachment.save(PENDING_JSON)
                    pending_list_content = load_json(PENDING_JSON)
                    new_users_list = [user for user in pending_list_content.get(PENDING, []) if str(user["ID"]) != author_id]
                    pending_list_content[PENDING] = new_users_list
                    save_json(PENDING_JSON, pending_list_content)
                    await msg.delete() # 古いメッセージを削除
                    await message.channel.send(file=discord.File(PENDING_JSON))
                    print(f"Updated 未提出リスト in '{message.channel.name}'")
                    break

# メッセージが投稿されたときに呼ばれるイベント
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.category_id == CATEGORY_ID:
        if message.attachments:
            await process_participant_list(message)
        url_pattern = re.compile(r'https?://\S+')  # URLの正規表現
        if url_pattern.search(message.content):
            emoji = '👍'  # ここに使用したい絵文字を入力
            await message.add_reaction(emoji)
            await update_pending_list(message, str(message.author.id))

    await bot.process_commands(message)

# ボットを実行
bot.run(DISCORD_BOT_TOKEN)
