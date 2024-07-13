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

# ボットが起動した時に呼ばれるイベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not check_pending_list.is_running():
        check_pending_list.start()  # 未提出リストのチェックを開始

# 未提出リストにIDがある人にメンションを飛ばすタスク
@tasks.loop(hours=12)  # 半日ごとに実行
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
                if attachment.filename ==PENDING_JSON:
                    await attachment.save(PENDING_JSON)
                    with open(PENDING_JSON, 'r', encoding='utf-8') as f:
                        pending_list_content = json.load(f)
                    mentions = [f"<@{user['ID']}>" for user in pending_list_content[PENDING]]
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
                pending_list_content = {
                    PENDING: participants
                }
                with open(PENDING_JSON, 'w', encoding='utf-8') as f:
                    json.dump(pending_list_content, f, ensure_ascii=False, indent=4)
                sent_message = await message.channel.send(file=discord.File(PENDING_JSON))
                await sent_message.pin()
                print(f"未提出リスト created in '{message.channel.name}'")
            except Exception as e:
                print(f"An error occurred while creating the 未提出リスト: {e}")

# URLを含むメッセージを処理する関数
async def process_message_with_url(message, url_match):
    author_id = str(message.author.id)
    author_name = str(message.author.name)
    message_id = message.id
    channel_id = message.channel.id
    guild_id = message.guild.id

    emoji = '👍'  # ここに使用したい絵文字を入力
    await message.add_reaction(emoji)
    
    message_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    url = url_match.group()
    values = [[author_id, author_name, url, message_link]]
    body = {'values': values}

    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{message.channel.name}'!A1",
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        print(f"Message from {author_name} recorded in sheet '{message.channel.name}'.")
    except Exception as e:
        print(f"An error occurred: {e}")
    
    sort_range = {
        'range': {
            'sheetId': 0,
            'startRowIndex': 1,
            'endRowIndex': 200,
            'startColumnIndex': 0,
            'endColumnIndex': 4
        },
        'sortSpecs': [{'dimensionIndex': 0, 'sortOrder': 'ASCENDING'}]
    }
    sheet.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': [{'sortRange': sort_range}]}
    ).execute()

    await update_pending_list(message, author_id)

# 未提出リストを更新する関数
async def update_pending_list(message, author_id):
    async for msg in message.channel.history(limit=100):
        if msg.attachments:
            for attachment in msg.attachments:
                if attachment.filename == PENDING_JSON:
                    await attachment.save(PENDING_JSON)
                    with open(PENDING_JSON, 'r', encoding='utf-8') as f:
                        pending_list_content = json.load(f)
                    new_users_list = [user for user in pending_list_content[PENDING] if str(user["ID"]) != author_id]
                    pending_list_content[PENDING] = new_users_list
                    with open(PENDING_JSON, 'w', encoding='utf-8') as f:
                        json.dump(pending_list_content, f, ensure_ascii=False, indent=4)
                    await msg.delete()  # 古いメッセージを削除
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
        else:
            url_pattern = re.compile(r'https?://\S+')
            url_match = url_pattern.search(message.content)
            if url_match:
                await process_message_with_url(message, url_match)

    await bot.process_commands(message)

# ボットを実行
bot.run(DISCORD_BOT_TOKEN)
