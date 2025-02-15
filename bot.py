"""This module provides functionality for a Discord bot."""
import logging
from json import dump, loads
from os import getenv
from pathlib import Path
from re import findall

from discord import File, Intents, Message, TextChannel
from discord.ext import commands, tasks
from dotenv import load_dotenv

# .envファイルの内容を読み込み
load_dotenv()

# 環境変数から値を取得
DISCORD_BOT_TOKEN = getenv("DISCORD_BOT_TOKEN")
CATEGORY_ID = int(getenv("CATEGORY_ID"))

PARTICIPANT_JSON = "participant.json"
PENDING_JSON = "pending_list.json"
PENDING = "未提出"
PARTICIPANTS = "参加者リスト"

# ボットのプレフィックスを設定
intents = Intents.default()
intents.message_content = True  # メッセージの内容を取得するための意図を有効にする
intents.reactions = True  # リアクションの意図を有効にする
intents.guilds = True  # ギルド関連のイベントを受け取るために必要
intents.messages = True  # メッセージ関連のイベントを受け取るために必要
bot = commands.Bot(command_prefix="!", intents=intents)

def save_json(filename: str, content:dict) -> None:
    """JSON書き込み関数"""
    with Path(filename).open("w", encoding="utf-8") as f:
        dump(content, f, ensure_ascii=False, indent=4)

async def read_attachment(attachment:File) -> dict:
    """ファイルを読み込む関数"""
    attachment_str = await attachment.read()
    return loads(attachment_str.decode("utf-8"))
@bot.event
async def on_ready() -> None:
    """ボットが起動した時に呼ばれるイベント"""
    if not check_pending_list.is_running():
        check_pending_list.start() # 未提出リストのチェックを開始

@tasks.loop(hours=12) # 半日ごとに実行
async def check_pending_list() -> None:
    """未提出リストにIDがある人にメンションを飛ばすタスク"""
    logging.info("Checking pending list...")
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.category_id == CATEGORY_ID:
                await check_pending_list_in_channel(channel)

async def check_pending_list_in_channel(channel:TextChannel) -> None:
    """チャンネル内の未提出リストを探しメンションを飛ばす"""
    async for msg in channel.history(limit=100):
        if msg.attachments:
            for attachment in msg.attachments:
                if attachment.filename == PENDING_JSON:
                    pending_list_content = await read_attachment(attachment)
                    mentions = [f"<@{user['ID']}>" for user in pending_list_content.get(PENDING, [])]
                    if mentions:
                        mention_message = "以下はまだ提出していません:\n" + "\n".join(mentions)
                        await channel.send(mention_message)
                    break

async def process_participant_list(message:Message) -> None:
    """参加者リストを処理する関数"""
    logging.info("参加者リストが投稿されたので未提出リストを作ります")
    for attachment in message.attachments:
        if attachment.filename == PARTICIPANT_JSON:
            participants = await read_attachment(attachment)
            save_json(PENDING_JSON,  {PENDING: participants.get(PARTICIPANTS, [])})
            sent_message = await message.channel.send(file=File(PENDING_JSON))
            await sent_message.pin()

async def update_pending_list(message:Message, author_id:int) -> None:
    """未提出リストをアップデートする"""
    logging.info("提出されたのでアップデートします")
    async for msg in message.channel.history(limit=100):
        if msg.attachments:
            for attachment in msg.attachments:
                if attachment.filename == PENDING_JSON:
                    pending_list_content = await read_attachment(attachment)
                    new_users_list = [user for user in pending_list_content.get(PENDING, []) if user["ID"] != author_id]
                    pending_list_content[PENDING] = new_users_list
                    save_json(PENDING_JSON, pending_list_content)
                    await msg.delete() # 古いメッセージを削除
                    await message.channel.send(file=File(PENDING_JSON))
                    break

@bot.event
async def on_message(message:Message) -> None:
    """メッセージが投稿されたときに呼ばれるイベント"""
    if message.author == bot.user:
        return

    if message.channel.category_id == CATEGORY_ID:
        if message.attachments:
            await process_participant_list(message)
        if findall(r"https://\d{1,3}\.gigafile\.nu", message.content):
            emoji = "👍"  # ここに使用したい絵文字を入力
            await message.add_reaction(emoji)
            await update_pending_list(message, message.author.id)

    await bot.process_commands(message)

# ボットを実行
bot.run(DISCORD_BOT_TOKEN)
