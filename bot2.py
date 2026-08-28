import asyncio
import io
import os
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["API_TOKEN"]
CLIENT_ID = "1506685269032697866"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="_", intents=intents)
bot.remove_command("help")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Registered tree commands:", [cmd.name for cmd in bot.tree.get_commands()])

# -------------------------
# Sync global slash commands
# Works as: _syncglobal
# Owner only
# -------------------------
@bot.command()
@commands.is_owner()
async def syncglobal(ctx: commands.Context):
    synced = await bot.tree.sync()
    await ctx.send(f"Synced {len(synced)} global slash command(s).")


# -------------------------
# Steal emoji command
# Works as:
# _steal <:name:id>
# _steal <a:name:id>
# _steal [pasted custom emoji]
# -------------------------
@bot.command(name="steal")
@commands.guild_only()
@commands.has_guild_permissions(manage_emojis_and_stickers=True)
async def steal(ctx: commands.Context, *emoji_inputs: str):
    if not emoji_inputs:
        await ctx.send("Usage: `_steal <:name:id> <:name:id> ...`")
        return

    added = []
    failed = []

    async with aiohttp.ClientSession() as session:
        for emoji_input in emoji_inputs:
            emoji_input = emoji_input.strip()
            partial = discord.PartialEmoji.from_str(emoji_input)

            if partial.id is not None:
                target_name = partial.name or "emoji"
                target_id = partial.id
                target_animated = partial.animated
            else:
                lookup_name = emoji_input.strip(":")
                found_emoji = discord.utils.find(lambda e: e.name == lookup_name, bot.emojis)

                if found_emoji is None:
                    failed.append(f"`{emoji_input}` â€” not found")
                    continue

                target_name = found_emoji.name
                target_id = found_emoji.id
                target_animated = found_emoji.animated

            ext = "gif" if target_animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{target_id}.{ext}?quality=lossless"

            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        failed.append(f"`{emoji_input}` â€” download failed")
                        continue
                    image_bytes = await resp.read()

                created = await ctx.guild.create_custom_emoji(
                    name=target_name,
                    image=image_bytes,
                    reason=f"Emoji stolen by {ctx.author} ({ctx.author.id})",
                )
                added.append(str(created))

            except discord.Forbidden:
                await ctx.send("I do not have permission to create emojis here.")
                return
            except discord.HTTPException as e:
                failed.append(f"`{emoji_input}` â€” Discord rejected it: {e}")

    lines = []
    if added:
        lines.append("Added emojis:")
        lines.extend(f"- {emoji}" for emoji in added)
    if failed:
        if lines:
            lines.append("")
        lines.append("Failed:")
        lines.extend(f"- {item}" for item in failed)

    await ctx.send("\n".join(lines) if lines else "No emojis were added.")

# -------------------------
# Steal sticker command
# Works as: _stealsticker (then send a message containing a sticker)
# -------------------------
@commands.hybrid_command(name="stealsticker", description="Copy a sticker from your next message")
@commands.guild_only()
@commands.has_guild_permissions(manage_emojis_and_stickers=True)
async def stealsticker(ctx: commands.Context):
    await ctx.send("Send your next message with a sticker. If it does not contain one, the command will stop.")

    def check(message: discord.Message):
        return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for a sticker message.")
        return

    if not msg.stickers:
        await ctx.send("No sticker found in your next message. Command cancelled.")
        return

    sticker_item = msg.stickers[0]

    try:
        sticker = await sticker_item.fetch()
    except discord.HTTPException:
        await ctx.send("I could not fetch that sticker.")
        return

    file_ext_map = {
        discord.StickerFormatType.png: "png",
        discord.StickerFormatType.apng: "png",
        discord.StickerFormatType.lottie: "json",
        discord.StickerFormatType.gif: "gif",
    }
    ext = file_ext_map.get(sticker.format, "png")

    async with aiohttp.ClientSession() as session:
        async with session.get(sticker.url) as resp:
            if resp.status != 200:
                await ctx.send("I could not download that sticker.")
                return
            sticker_bytes = await resp.read()

    file = discord.File(fp=io.BytesIO(sticker_bytes), filename=f"{sticker.name}.{ext}")

    try:
        created = await ctx.guild.create_sticker(
            name=sticker.name[:30],
            description=(getattr(sticker, "description", "") or "")[:100],
            emoji="ðŸ˜€",
            file=file,
            reason=f"Sticker stolen by {ctx.author} ({ctx.author.id})",
        )
    except discord.Forbidden:
        await ctx.send("I do not have permission to create stickers here.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"Discord rejected the sticker: {e}")
        return

    await ctx.send(f"Added sticker: {created.name}")

bot.add_command(stealsticker)
  
# -------------------------
# Add emoji command
# Works as: _addemoji <name> (then send a message with an image attachment)
# -------------------------
@commands.hybrid_command(name="addemoji", description="Add an emoji from your next uploaded image")
@commands.guild_only()
@commands.has_guild_permissions(manage_emojis_and_stickers=True)
async def addemoji(ctx: commands.Context, name: str):
    await ctx.send(f"Send your next message with an image to add it as the emoji `{name}`.")

    def check(message: discord.Message):
        return (
            message.author.id == ctx.author.id
            and message.channel.id == ctx.channel.id
            and len(message.attachments) > 0
        )

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for an image message.")
        return

    attachment = msg.attachments[0]

    if not (attachment.content_type or "").startswith("image/"):
        await ctx.send("That attachment is not an image. Command cancelled.")
        return

    image_bytes = await attachment.read()

    try:
        created = await ctx.guild.create_custom_emoji(
            name=name,
            image=image_bytes,
            reason=f"Emoji added by {ctx.author} ({ctx.author.id})",
        )
    except discord.Forbidden:
        await ctx.send("I do not have permission to create emojis here.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"Discord rejected the emoji: {e}")
        return

    await ctx.send(f"Added emoji: {created}")

bot.add_command(addemoji)
  
# -------------------------
# Add sticker command
# Works as: _addsticker <name> (then send a message with an image attachment)
# -------------------------
@commands.hybrid_command(name="addsticker", description="Add a sticker from an uploaded image")
@commands.guild_only()
@commands.has_guild_permissions(manage_emojis_and_stickers=True)
async def addsticker(ctx: commands.Context, name: str):
    await ctx.send(f"Send your next message with an image to add it as the sticker `{name}`.")

    def check(message: discord.Message):
        return (
            message.author.id == ctx.author.id
            and message.channel.id == ctx.channel.id
            and len(message.attachments) > 0
        )

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for an image message.")
        return

    attachment = msg.attachments[0]

    if not (attachment.content_type or "").startswith("image/"):
        await ctx.send("That attachment is not an image. Command cancelled.")
        return

    image_bytes = await attachment.read()

    file = discord.File(fp=io.BytesIO(image_bytes), filename=attachment.filename)

    try:
        created = await ctx.guild.create_sticker(
            name=name[:30],
            description="Added via bot",
            emoji="ðŸ˜€",
            file=file,
            reason=f"Sticker added by {ctx.author} ({ctx.author.id})",
        )
    except discord.Forbidden:
        await ctx.send("I do not have permission to create stickers here.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"Discord rejected the sticker: {e}")
        return

    await ctx.send(f"Added sticker: {created.name}")

bot.add_command(addsticker)
  
# -------------------------
# Help command
# Works as: _help
# -------------------------
@commands.hybrid_command(name="help", description="Show the bot's commands")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="Help Menu",
        description="Available commands:",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Emoji & Sticker",
        value=(
            "`_steal <:name:id> ...` - Copy emoji(s) from mention or name\n"
            "`_addemoji <name>` - Add an emoji from an uploaded image\n"
            "`_stealsticker` - Copy a sticker from your next message\n"
            "`_addsticker <name>` - Add a sticker from an uploaded image"
        ),
        inline=False,
    )
    embed.add_field(name="Owner", value="`_syncglobal` - Sync global slash commands", inline=False)
    await ctx.send(embed=embed)

bot.add_command(help_command)

# -------------------------
# Error handler
# -------------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use that command.")
    elif isinstance(error, commands.NotOwner):
        await ctx.send("Only the bot owner can use that command.")
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: {error.param.name}")
    else:
        raise error


bot.run(TOKEN)