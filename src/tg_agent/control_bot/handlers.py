"""Command handlers for control bot."""

from aiogram import F, Dispatcher, Router, types
from aiogram.filters import Command, CommandObject, CommandStart
from telethon import TelegramClient

from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger
from tg_agent.storage.db import Database
from tg_agent.storage.models import ChatMode, MessageDirection
from tg_agent.storage.repositories import (
    ChatSettingsRepo,
    GlobalStateRepo,
    MessageLogRepo,
    MonitoredChannelRepo,
    PendingActionRepo,
)

logger = get_logger(__name__)


def _command_args(command: CommandObject | None) -> str:
    return command.args.strip() if command and command.args else ""


def setup_control_handlers(
    dp: Dispatcher,
    settings: Settings,
    db: Database,
    control_bot: ControlBot,
    userbot_client: TelegramClient | None = None,
    channel_handler=None,
) -> None:
    """
    Set up all control bot command handlers.

    Args:
        dp: aiogram Dispatcher.
        settings: Application settings.
        db: Database instance.
        control_bot: Control bot instance.
    """
    router = Router(name="control_bot")
    router.message.filter(F.from_user.id == settings.owner_telegram_id)

    @router.message(CommandStart())
    async def start_handler(message: types.Message) -> None:
        await cmd_start(message, db)

    @router.message(Command("status"))
    async def status_handler(message: types.Message) -> None:
        await cmd_status(message, db, settings)

    @router.message(Command("pause"))
    async def pause_handler(message: types.Message) -> None:
        await cmd_pause(message, db)

    @router.message(Command("resume"))
    async def resume_handler(message: types.Message) -> None:
        await cmd_resume(message, db)

    @router.message(Command("chats"))
    async def chats_handler(message: types.Message) -> None:
        await cmd_chats(message, db)

    @router.message(Command("mode"))
    async def mode_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_mode(message, db, _command_args(command))

    @router.message(Command("trust"))
    async def trust_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_trust(message, db, _command_args(command))

    @router.message(Command("untrust"))
    async def untrust_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_untrust(message, db, _command_args(command))

    @router.message(Command("send"))
    async def send_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_send(message, db, _command_args(command), control_bot)

    @router.message(Command("recent"))
    async def recent_handler(message: types.Message) -> None:
        await cmd_recent(message, db)

    @router.message(Command("style"))
    async def style_handler(message: types.Message) -> None:
        await cmd_style(message, settings)

    @router.message(Command("persona"))
    async def persona_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_persona(message, settings, _command_args(command))

    @router.message(Command("channels"))
    async def channels_handler(message: types.Message) -> None:
        await cmd_channels(message, settings, db)

    @router.message(Command("add_channel"))
    async def add_channel_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_add_channel(message, settings, userbot_client, db, _command_args(command))

    @router.message(Command("remove_channel"))
    async def remove_channel_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_remove_channel(message, settings, db, _command_args(command))

    @router.message(Command("help"))
    async def help_handler(message: types.Message) -> None:
        await cmd_help(message)

    @router.message(Command("scan_channel"))
    async def scan_channel_handler(
        message: types.Message,
        command: CommandObject | None = None,
    ) -> None:
        await cmd_scan_channel(message, settings, control_bot, userbot_client, _command_args(command), channel_handler)

    dp.include_router(router)

    logger.info("Control bot handlers registered")


async def cmd_start(message: types.Message, db: Database) -> None:
    """Handle /start command."""
    text = (
        "🤖 <b>Telegram AI Userbot Agent</b>\n\n"
        "I'm your personal AI assistant for Telegram.\n\n"
        "Use /help to see available commands."
    )
    await message.answer(text, parse_mode="HTML")


async def cmd_status(message: types.Message, db: Database, settings: Settings) -> None:
    """Handle /status command."""
    with db.get_sync_session() as session:
        global_repo = GlobalStateRepo(session)
        chat_repo = ChatSettingsRepo(session)
        pending_repo = PendingActionRepo(session)
        log_repo = MessageLogRepo(session)

        # Get global state
        agent_enabled = global_repo.get_bool("agent_enabled", settings.agent_global_enabled)
        default_mode = global_repo.get("default_mode") or settings.default_chat_mode

        # Get counts
        all_chats = chat_repo.get_all()
        pending_count = len(pending_repo.get_pending())

        # Get recent activity
        last_message_log = log_repo.get_most_recent()
        last_message_time = last_message_log.created_at if last_message_log else None
        last_agent_log = log_repo.get_most_recent_by_direction(
            MessageDirection.AGENT_SENT
        )

        # Count by mode
        mode_counts = {
            mode: len([c for c in all_chats if c.mode == mode])
            for mode in ChatMode
        }

        text = (
            f"📊 <b>Agent Status</b>\n\n"
            f"🔌 <b>Enabled:</b> {'Yes' if agent_enabled else 'No'}\n"
            f"📁 <b>Default mode:</b> {default_mode}\n"
            f"💬 <b>Watched chats:</b> {len(all_chats)}\n"
            f"  • OFF: {mode_counts.get(ChatMode.OFF, 0)}\n"
            f"  • WATCH: {mode_counts.get(ChatMode.WATCH, 0)}\n"
            f"  • DRAFT: {mode_counts.get(ChatMode.DRAFT, 0)}\n"
            f"  • AUTO: {mode_counts.get(ChatMode.AUTO, 0)}\n"
            f"⏳ <b>Pending actions:</b> {pending_count}\n"
            f"🤖 <b>LLM Provider:</b> {settings.llm_provider}\n"
            f"📅 <b>Last activity:</b> {last_message_time.strftime('%Y-%m-%d %H:%M') if last_message_time else 'None'}\n"
            f"🤖 <b>Last agent reply:</b> "
            f"{last_agent_log.created_at.strftime('%Y-%m-%d %H:%M') if last_agent_log else 'None'}\n"
        )

        await message.answer(text, parse_mode="HTML")


async def cmd_pause(message: types.Message, db: Database) -> None:
    """Handle /pause command."""
    with db.get_sync_session() as session:
        global_repo = GlobalStateRepo(session)
        global_repo.set_bool("agent_enabled", False)

    await message.answer("⏸️ <b>Agent paused</b>\n\nNo new messages will be processed.", parse_mode="HTML")


async def cmd_resume(message: types.Message, db: Database) -> None:
    """Handle /resume command."""
    with db.get_sync_session() as session:
        global_repo = GlobalStateRepo(session)
        global_repo.set_bool("agent_enabled", True)

    await message.answer("▶️ <b>Agent resumed</b>\n\nProcessing messages again.", parse_mode="HTML")


async def cmd_chats(message: types.Message, db: Database) -> None:
    """Handle /chats command."""
    with db.get_sync_session() as session:
        chat_repo = ChatSettingsRepo(session)
        chats = chat_repo.get_all()

        if not chats:
            await message.answer("📭 No chats configured yet.")
            return

        lines = ["📋 <b>Configured Chats:</b>\n"]
        for chat in chats[:20]:
            trust_icon = "🔒" if chat.is_trusted else "🔓"
            name = chat.chat_title or f"ID: {chat.chat_id}"
            lines.append(
                f"• <b>{name}</b>\n"
                f"  ID: <code>{chat.chat_id}</code> | Режим: {chat.mode.value} {trust_icon}"
            )

        if len(chats) > 20:
            lines.append(f"\n... and {len(chats) - 20} more")

        await message.answer("\n".join(lines), parse_mode="HTML")


async def cmd_mode(message: types.Message, db: Database, args: str) -> None:
    """Handle /mode command."""
    # Parse arguments: /mode <chat_id_or_title> <MODE>
    parts = args.strip().split()
    if len(parts) < 2:
        await message.answer(
            "❌ Usage: /mode &lt;chat_id_or_title&gt; &lt;OFF|WATCH|DRAFT|AUTO&gt;\n"
            "Example: /mode 12345 DRAFT"
        )
        return

    chat_identifier = parts[0]
    mode_str = parts[1].upper()

    try:
        mode = ChatMode(mode_str)
    except ValueError:
        await message.answer(f"❌ Invalid mode: {mode_str}\nMust be: OFF, WATCH, DRAFT, AUTO")
        return

    with db.get_sync_session() as session:
        chat_repo = ChatSettingsRepo(session)

        # Try to find chat by ID or title
        chat_id = int(chat_identifier) if chat_identifier.isdigit() else None
        if chat_id:
            chat_settings = chat_repo.get_by_chat_id(chat_id)
        else:
            # Search by title (simplified)
            all_chats = chat_repo.get_all()
            chat_settings = next(
                (c for c in all_chats if chat_identifier.lower() in (c.chat_title or "").lower()),
                None,
            )

        if chat_settings is None and chat_id is not None:
            chat_settings = chat_repo.get_or_create(chat_id=chat_id, default_mode=mode)
        elif chat_settings is None:
            await message.answer(f"❌ Chat not found: {chat_identifier}")
            return

        # Update mode
        chat_repo.update_mode(chat_settings.chat_id, mode)

        await message.answer(
            f"✅ Mode updated for {chat_settings.chat_title or chat_settings.chat_id}\n"
            f"New mode: {mode.value}"
        )


async def cmd_trust(message: types.Message, db: Database, args: str) -> None:
    """Handle /trust command."""
    chat_identifier = args.strip()
    if not chat_identifier:
        await message.answer("❌ Usage: /trust &lt;chat_id_or_title&gt;")
        return

    with db.get_sync_session() as session:
        chat_repo = ChatSettingsRepo(session)

        chat_id = int(chat_identifier) if chat_identifier.isdigit() else None
        if chat_id:
            chat_settings = chat_repo.get_by_chat_id(chat_id)
        else:
            all_chats = chat_repo.get_all()
            chat_settings = next(
                (c for c in all_chats if chat_identifier.lower() in (c.chat_title or "").lower()),
                None,
            )

        if chat_settings is None:
            await message.answer(f"❌ Chat not found: {chat_identifier}")
            return

        chat_repo.set_trusted(chat_settings.chat_id, True)
        await message.answer(f"✅ Chat {chat_settings.chat_title or chat_settings.chat_id} marked as trusted")


async def cmd_untrust(message: types.Message, db: Database, args: str) -> None:
    """Handle /untrust command."""
    chat_identifier = args.strip()
    if not chat_identifier:
        await message.answer("❌ Usage: /untrust &lt;chat_id_or_title&gt;")
        return

    with db.get_sync_session() as session:
        chat_repo = ChatSettingsRepo(session)

        chat_id = int(chat_identifier) if chat_identifier.isdigit() else None
        if chat_id:
            chat_settings = chat_repo.get_by_chat_id(chat_id)
        else:
            all_chats = chat_repo.get_all()
            chat_settings = next(
                (c for c in all_chats if chat_identifier.lower() in (c.chat_title or "").lower()),
                None,
            )

        if chat_settings is None:
            await message.answer(f"❌ Chat not found: {chat_identifier}")
            return

        chat_repo.set_trusted(chat_settings.chat_id, False)
        await message.answer(f"✅ Chat {chat_settings.chat_title or chat_settings.chat_id} marked as untrusted")


async def cmd_send(message: types.Message, db: Database, args: str, control_bot: ControlBot) -> None:
    """Handle /send command - create pending action for manual message."""
    # Parse: /send <chat_id> <message>
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /send &lt;chat_id&gt; &lt;message text&gt;")
        return

    chat_identifier = parts[0]
    message_text = parts[1]

    with db.get_sync_session() as session:
        chat_repo = ChatSettingsRepo(session)
        pending_repo = PendingActionRepo(session)

        chat_id = int(chat_identifier) if chat_identifier.isdigit() else None
        if chat_id:
            chat_settings = chat_repo.get_by_chat_id(chat_id)
        else:
            all_chats = chat_repo.get_all()
            chat_settings = next(
                (c for c in all_chats if chat_identifier.lower() in (c.chat_title or "").lower()),
                None,
            )

        if chat_settings is None:
            await message.answer(f"❌ Chat not found: {chat_identifier}")
            return

        # Create pending action
        action = pending_repo.create(
            action_type="send_message",
            chat_id=chat_settings.chat_id,
            text=message_text,
        )

        # Send for approval
        await control_bot.send_draft_for_approval(
            pending_action_id=action.id,
            chat_id=chat_settings.chat_id,
            chat_title=chat_settings.chat_title or str(chat_settings.chat_id),
            original_message="(Manual message)",
            sender_id=None,
            reply_text=message_text,
        )

        await message.answer(f"✅ Message queued for approval (Action ID: {action.id})")


async def cmd_recent(message: types.Message, db: Database) -> None:
    """Handle /recent command - show recent agent activity."""
    with db.get_sync_session() as session:
        pending_repo = PendingActionRepo(session)
        actions = pending_repo.get_recent(10)

        if not actions:
            await message.answer("📭 No recent actions.")
            return

        lines = ["📜 <b>Recent Actions:</b>\n"]
        for action in actions:
            status_icon = {
                "pending": "⏳",
                "approved": "✅",
                "rejected": "❌",
                "executed": "✅",
                "expired": "⏰",
            }.get(action.status.value, "•")

            lines.append(
                f"{status_icon} #{action.id} - {action.action_type}\n"
                f"  Chat: {action.chat_id}\n"
                f"  Status: {action.status.value}\n"
            )

        await message.answer("\n".join(lines), parse_mode="HTML")


async def cmd_style(message: types.Message, settings: Settings) -> None:
    """Handle /style command - show current system prompt location."""
    text = (
        "📝 <b>System Prompt Configuration</b>\n\n"
        f"System prompt file: <code>{settings.prompts_dir / 'system.ru.txt'}</code>\n"
        f"Safety prompt file: <code>{settings.prompts_dir / 'safety.ru.txt'}</code>\n\n"
        "Edit these files to customize the agent's behavior."
    )
    await message.answer(text, parse_mode="HTML")


async def cmd_persona(message: types.Message, settings: Settings, args: str) -> None:
    """Handle /persona [text] — view or update the persona prompt."""
    persona_file = settings.prompts_dir / "persona.ru.txt"
    if args:
        persona_file.write_text(args.strip(), encoding="utf-8")
        await message.answer("✅ Персона обновлена. Вступает в силу сразу, без рестарта.")
    else:
        current = persona_file.read_text(encoding="utf-8").strip() if persona_file.exists() else "(не задана)"
        await message.answer(
            f"👤 <b>Текущая персона:</b>\n<pre>{current}</pre>\n\n"
            "Чтобы изменить: <code>/persona Меня зовут ...</code>",
            parse_mode="HTML",
        )


async def cmd_scan_channel(
    message: types.Message,
    settings: Settings,
    control_bot: ControlBot,
    client: TelegramClient | None,
    args: str,
    channel_handler=None,
) -> None:
    """Handle /scan_channel [limit] — fetch recent posts and run outreach."""
    if not client:
        await message.answer("❌ Userbot client not available.")
        return

    channel_ids = settings.monitored_channel_ids
    if not channel_ids:
        await message.answer("❌ No channels configured in MONITORED_CHANNELS.")
        return

    try:
        limit = max(1, min(int(args), 50)) if args.isdigit() else 10
    except Exception:
        limit = 10

    do_outreach = channel_handler is not None and channel_handler.llm_client is not None
    await message.answer(
        f"🔍 Сканирую {len(channel_ids)} канал(ов), последние {limit} постов"
        + (" + запущу аутрич по новым контактам" if do_outreach else "") + "..."
    )

    total = 0
    outreach_count = 0
    for channel_id in channel_ids:
        try:
            msgs = await client.get_messages(channel_id, limit=limit)
            chat = await client.get_entity(channel_id)
            title = getattr(chat, "title", f"Channel {channel_id}")

            for msg in reversed(msgs):
                if not msg.text:
                    continue
                text = (
                    f"📢 <b>{title}</b> (история)\n\n"
                    f"{msg.text[:1000]}"
                )
                if len(msg.text) > 1000:
                    text += "\n\n<i>... (обрезано)</i>"
                await control_bot.send_message(
                    chat_id=settings.owner_telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
                total += 1

                if do_outreach:
                    before = len(channel_handler._contacted)
                    await channel_handler._try_outreach(msg.text)
                    outreach_count += len(channel_handler._contacted) - before

        except Exception as e:
            await message.answer(f"❌ Ошибка при сканировании {channel_id}: {e}")

    summary = f"✅ Переслано {total} постов."
    if do_outreach:
        summary += f" Написал {outreach_count} новым контактам."
    await message.answer(summary)


async def cmd_help(message: types.Message) -> None:
    """Handle /help command."""
    text = (
        "🤖 <b>Available Commands:</b>\n\n"
        "📊 <b>Status:</b>\n"
        "  /status - Show agent status\n"
        "  /pause - Pause agent\n"
        "  /resume - Resume agent\n\n"
        "💬 <b>Chats:</b>\n"
        "  /chats - List configured chats\n"
        "  /mode &lt;chat&gt; &lt;mode&gt; - Set chat mode (OFF/WATCH/DRAFT/AUTO)\n"
        "  /trust &lt;chat&gt; - Mark chat as trusted\n"
        "  /untrust &lt;chat&gt; - Remove trusted status\n\n"
        "✏️ <b>Actions:</b>\n"
        "  /send &lt;chat&gt; &lt;msg&gt; - Send message (requires approval)\n"
        "  /recent - Show recent actions\n\n"
        "📢 <b>Каналы:</b>\n"
        "  /channels - Список отслеживаемых каналов\n"
        "  /add_channel &lt;link|username&gt; [outreach] - Добавить канал\n"
        "  /remove_channel &lt;channel_id&gt; - Удалить канал\n"
        "  /scan_channel [N] - Последние N постов из каналов (по умолч. 10)\n\n"
        "⚙️ <b>Settings:</b>\n"
        "  /style - Show prompt configuration\n"
        "  /help - This help message"
    )
    await message.answer(text, parse_mode="HTML")


async def cmd_channels(message: types.Message, settings: Settings, db: Database) -> None:
    """Handle /channels command - list monitored channels."""
    with db.get_sync_session() as session:
        repo = MonitoredChannelRepo(session)
        channels = repo.get_all()
    
    if not channels:
        await message.answer(
            "📢 <b>Нет отслеживаемых каналов</b>\n\n"
            "Добавьте канал командой:\n"
            "  /add_channel &lt;ссылка_или_юзернейм&gt; [outreach]\n\n"
            "Примеры:\n"
            "  /add_channel @it_jobs\n"
            "  /add_channel https://t.me/+ucoAOCsXCwk3ZmFi outreach",
            parse_mode="HTML"
        )
        return
    
    text = "📢 <b>Отслеживаемые каналы:</b>\n\n"
    for i, ch in enumerate(channels, 1):
        outreach_icon = "📤" if ch.auto_outreach else "👁️"
        enabled_icon = "✅" if ch.enabled else "❌"
        text += f"{i}. <code>{ch.channel_id}</code> — {ch.channel_title or 'Без названия'}\n"
        text += f"   {enabled_icon} {outreach_icon} Outreach: {'✅' if ch.auto_outreach else '❌'}\n"
        if ch.keywords:
            text += f"   🔑 Keywords: {ch.keywords}\n"
        text += "\n"
    
    text += f"\nВсего: {len(channels)} канал(ов)"
    await message.answer(text, parse_mode="HTML")


async def cmd_add_channel(
    message: types.Message,
    settings: Settings,
    userbot_client: TelegramClient,
    db: Database,
    args: str
) -> None:
    """Handle /add_channel command - add channel by link or username."""
    if not args:
        await message.answer(
            "❌ <b>Укажите ссылку или юзернейм канала</b>\n\n"
            "Примеры:\n"
            "  /add_channel @it_jobs\n"
            "  /add_channel https://t.me/+ucoAOCsXCwk3ZmFi\n"
            "  /add_channel @design_jobs outreach",
            parse_mode="HTML"
        )
        return
    
    parts = args.split(maxsplit=1)
    channel_input = parts[0]
    enable_outreach = len(parts) > 1 and parts[1].lower() == "outreach"
    
    status_msg = await message.answer("⏳ Ищу канал...", parse_mode="HTML")
    
    try:
        # Get channel info via Telethon
        entity = await userbot_client.get_entity(channel_input)
        
        # Extract channel ID
        channel_id = entity.id
        if hasattr(channel_id, 'channel_id'):
            channel_id = channel_id.channel_id
        
        # Convert to superchannel format if needed
        if isinstance(channel_id, int) and channel_id > 0:
            channel_id = int(f"-100{channel_id}")
        
        channel_title = getattr(entity, 'title', 'Unknown')
        username = getattr(entity, 'username', None)
        
        # Save to database
        with db.get_sync_session() as session:
            repo = MonitoredChannelRepo(session)
            repo.add(
                channel_id=channel_id,
                channel_title=channel_title,
                auto_outreach=enable_outreach,
            )
        
        await status_msg.edit_text(
            f"✅ <b>Канал добавлен!</b>\n\n"
            f"📢 <b>Название:</b> {channel_title}\n"
            f"🆔 <b>ID:</b> <code>{channel_id}</code>\n"
            f"📤 <b>Outreach:</b> {'✅ Включён' if enable_outreach else '❌ Выключен'}\n\n"
            f"⚡ <b>Изменения применены немедленно!</b>",
            parse_mode="HTML"
        )
        
    except ValueError as e:
        await status_msg.edit_text(
            f"❌ <b>Канал не найден</b>\n\n"
            f"Убедитесь, что вы подписаны на этот канал.\n"
            f"Ошибка: {e}",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Ошибка:</b> {e}",
            parse_mode="HTML"
        )


async def cmd_remove_channel(
    message: types.Message,
    settings: Settings,
    db: Database,
    args: str
) -> None:
    """Handle /remove_channel command - remove channel by ID."""
    if not args:
        await message.answer(
            "❌ <b>Укажите ID канала</b>\n\n"
            "Пример:\n"
            "  /remove_channel -1001782596777\n\n"
            "Используйте /channels чтобы увидеть список.",
            parse_mode="HTML"
        )
        return
    
    try:
        channel_id = int(args)
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Должно быть число (например, -1001782596777)",
            parse_mode="HTML"
        )
        return
    
    # Remove from database
    with db.get_sync_session() as session:
        repo = MonitoredChannelRepo(session)
        removed = repo.remove(channel_id)
    
    if removed:
        await message.answer(
            f"✅ <b>Канал удалён!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{channel_id}</code>\n\n"
            f"⚡ <b>Изменения применены немедленно!</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ Канал {channel_id} не найден в базе",
            parse_mode="HTML"
        )
