import logging
import re
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.enums import ParseMode
from urllib.parse import urljoin
import nest_asyncio
import json
import asyncio
import os
import signal
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - Set your credentials directly here
BOT_TOKEN = "8174269081:AAEe4vVT9RDTJ6VKh8qkcjjauQiBGkshnWY"
API_ID = 22225430
API_HASH = "4c5c28abd62233ef4b993fb972f83262"
TMDB_API_KEY = "6bcc83f27058964856b4f2e98b38bb8f"
TMDB_API_URL = "https://api.themoviedb.org/3"
DATA_FILE = "/app/data/data.json"

# Dictionary to store post data for reconstruction
post_data = {}

# Health check handler
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')

# Start health check server
def start_health_server():
    server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
    server.serve_forever()

# Apply nest_asyncio to handle Colab's event loop
nest_asyncio.apply()

app = Client(
    "anime_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# Dictionary to track recent error messages to avoid spam
recent_errors = {}

# Initialize data file if it doesn't exist
def init_data_file():
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump({"channels": []}, f)

# Load channels from data file
def load_channels():
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return data.get("channels", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Save channels to data file
def save_channels(channels):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({"channels": channels}, f)

# Initialize data file
init_data_file()

@app.on_message(filters.command("start"))
async def start(client, message):
    """Send a message when the command /start is issued."""
    await message.reply_text("Send me an AnimeDekho URL to create a formatted post!")

@app.on_message(filters.command("help"))
async def help_command(client, message):
    """Send a message with all available commands."""
    help_text = (
        "<b>Available Commands:</b>\n\n"
        "<b>/start</b> - Start the bot and get instructions\n"
        "<b>/help</b> - Show this help message\n"
        "<b>/setchnl &lt;channel_id&gt;</b> - Set a channel for forwarding posts\n"
        "<b>/s</b> - Reply to a post with this command to post it to all set channels\n\n"
        "<b>Usage:</b>\n"
        "• Send an AnimeDekho URL to create a formatted post\n"
        "• Use /setchnl to add a channel (you must be an admin in that channel)\n"
        "• Reply to any post with /s to post it to all set channels"
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("setchnl"))
async def set_channel(client, message):
    """Set a channel for forwarding posts."""
    # Check if the user provided a channel ID
    if len(message.command) < 2:
        await message.reply_text("Please provide a channel ID. Usage: /setchnl <channel_id>")
        return
    
    channel_id = message.command[1]
    
    # Try to convert to integer if it's a numeric ID
    try:
        channel_id = int(channel_id)
    except ValueError:
        # If it's not numeric, keep it as is (username)
        pass
    
    # Load current channels
    channels = load_channels()
    
    # Check if channel is already in the list
    if channel_id in channels:
        await message.reply_text("This channel is already set.")
        return
    
    # Try to get chat info to verify the channel exists and bot is admin
    try:
        chat = await client.get_chat(channel_id)
        # Check if bot is admin
        bot_member = await client.get_chat_member(chat.id, "me")
        if bot_member.status.value not in ["administrator", "creator"]:
            await message.reply_text("I'm not an admin in this channel. Please add me as an admin first.")
            return
        
        # Add channel to list
        channels.append(channel_id)
        save_channels(channels)
        await message.reply_text(f"Channel {chat.title} has been set successfully!")
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")

@app.on_message(filters.command("s"))
async def post_to_channels(client, message):
    """Post a message to all set channels."""
    # Check if the message is a reply
    if not message.reply_to_message:
        await message.reply_text("Please reply to a post with /s to post it to all set channels.")
        return
    
    # Load channels
    channels = load_channels()
    
    if not channels:
        await message.reply_text("No channels set. Use /setchnl to add channels first.")
        return
    
    # Get the message to post
    reply_msg = message.reply_to_message
    
    # Try to get stored post data
    msg_id = str(reply_msg.id)
    stored_data = post_data.get(msg_id)
    
    # Post to each channel
    success_count = 0
    for channel_id in channels:
        try:
            if reply_msg.photo:
                # If we have stored data, reconstruct the caption with links
                if stored_data:
                    caption = (
                        f"<b>➥ <a href=\"{stored_data['url']}\">{stored_data['base_title']} Episode {stored_data['ep_range']} Added 👈🏻</a></b>\n\n"
                        f"<b>➪ Quality: 480p | 720p | 1080p</b>\n"
                        f"<b>➪ Audio: Multi Audio (Hindi-English-Jap)</b>\n"
                        f"<b>☏ Powerd By : - @NineAnimeOfficial ☏</b>\n\n"
                        f"<b>〖 <a href=\"https://t.me/BlakiteFF/4\">Join Our All Channels</a> 〗</b>\n"
                        f"<b>〖 <a href=\"https://t.me/BlakiteFF\">How To Download & Watch</a> 〗</b>"
                    )
                    
                    # Create inline keyboard with a single episode button showing only the last episode
                    keyboard = [
                        [InlineKeyboardButton(text=f"Episode {stored_data['last_episode']} Added", url=stored_data['url'])]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Send photo with reconstructed caption and reply markup
                    await client.send_photo(
                        chat_id=channel_id,
                        photo=reply_msg.photo.file_id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                else:
                    # Fallback to original caption if no stored data
                    await client.send_photo(
                        chat_id=channel_id,
                        photo=reply_msg.photo.file_id,
                        caption=reply_msg.caption,
                        parse_mode=ParseMode.HTML if reply_msg.caption else None,
                        reply_markup=reply_msg.reply_markup
                    )
            elif reply_msg.text:
                # If we have stored data, reconstruct the caption with links
                if stored_data:
                    caption = (
                        f"<b>➥ <a href=\"{stored_data['url']}\">{stored_data['base_title']} Episode {stored_data['ep_range']} Added 👈🏻</a></b>\n\n"
                        f"<b>➪ Quality: 480p | 720p | 1080p</b>\n"
                        f"<b>➪ Audio: Multi Audio (Hindi-English-Jap)</b>\n"
                        f"<b>☏ Powerd By : - @NineAnimeOfficial ☏</b>\n\n"
                        f"<b>〖 <a href=\"https://t.me/BlakiteFF/4\">Join Our All Channels</a> 〗</b>\n"
                        f"<b>〖 <a href=\"https://t.me/BlakiteFF\">How To Download & Watch</a> 〗</b>"
                    )
                    
                    # Create inline keyboard with a single episode button showing only the last episode
                    keyboard = [
                        [InlineKeyboardButton(text=f"Episode {stored_data['last_episode']} Added", url=stored_data['url'])]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Send text with reconstructed caption and reply markup
                    await client.send_message(
                        chat_id=channel_id,
                        text=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                else:
                    # Fallback to original text if no stored data
                    await client.send_message(
                        chat_id=channel_id,
                        text=reply_msg.text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_msg.reply_markup,
                        disable_web_page_preview=True
                    )
            success_count += 1
        except Exception as e:
            logger.error(f"Error posting to channel {channel_id}: {e}")
    
    await message.reply_text(f"Post sent to {success_count}/{len(channels)} channels.")

def get_tmdb_banner(anime_title):
    """Fetch backdrop image from TMDB API"""
    # Clean up the title for better TMDB matching
    clean_title = re.sub(r'\s*Season\s*\d+', '', anime_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*\(Hindi\)', '', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*Hindi Dubbed.*', '', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*\(ORG\)', '', clean_title, flags=re.IGNORECASE)
    clean_title = clean_title.strip()
    
    # Try multiple search variations
    search_terms = [
        clean_title,
        clean_title.split(':')[0],  # Try without subtitle
        re.sub(r'\s*\([^)]*\)', '', clean_title).strip()  # Remove anything in parentheses
    ]
    
    for term in search_terms:
        try:
            # Search for TV show
            search_url = f"{TMDB_API_URL}/search/tv"
            params = {
                'api_key': TMDB_API_KEY,
                'query': term,
                'include_adult': 'false'
            }
            
            response = requests.get(search_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if 'results' in data and data['results']:
                    # Get the first result
                    show_id = data['results'][0]['id']
                    
                    # Get show details for backdrop
                    details_url = f"{TMDB_API_URL}/tv/{show_id}"
                    details_params = {
                        'api_key': TMDB_API_KEY
                    }
                    
                    details_response = requests.get(details_url, params=details_params)
                    if details_response.status_code == 200:
                        details_data = details_response.json()
                        if 'backdrop_path' in details_data and details_data['backdrop_path']:
                            # Construct full image URL
                            return f"https://image.tmdb.org/t/p/original{details_data['backdrop_path']}"
        except Exception as e:
            logger.error(f"Error fetching TMDB banner for '{term}': {e}")
    
    return None

def extract_anime_info(url):
    """Extract anime title and episodes from AnimeDekho page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title - try multiple methods
        title_tag = soup.find('h1', class_='entry-title')
        if not title_tag:
            title_tag = soup.find('h1')
        if not title_tag:
            title_tag = soup.find('title')
        
        if not title_tag:
            return None, None, None
        
        title = title_tag.text.strip()
        
        # Extract base title (remove episode info)
        base_title = re.sub(r'\s*Hindi Dubbed \(ORG\) Episode.*Added.*', '', title, flags=re.IGNORECASE)
        base_title = re.sub(r'\s*Hindi Dubbed.*', '', base_title, flags=re.IGNORECASE)
        base_title = base_title.strip()
        
        # Extract episodes from JavaScript data
        episodes = []
        scripts = soup.find_all('script')
        for script in scripts:
            if 'episodeData' in script.text:
                # Extract the episodeData object with improved regex
                match = re.search(r'let episodeData\s*=\s*({.*?});', script.text, re.DOTALL)
                if match:
                    try:
                        episode_data_str = match.group(1)
                        
                        # Fix common JSON issues with more robust processing
                        # Step 1: Add quotes around property names
                        episode_data_str = re.sub(r'(\s*)(\w+)(\s*):', r'\1"\2"\3:', episode_data_str)
                        
                        # Step 2: Fix single quotes around string values
                        episode_data_str = re.sub(r":\s*'([^']*)'", r': "\1"', episode_data_str)
                        
                        # Step 3: Handle unquoted string values (like TID: 71632)
                        episode_data_str = re.sub(r":\s*([a-zA-Z0-9]+)(\s*,|\s*})", r': "\1"\2', episode_data_str)
                        
                        # Step 4: Remove trailing commas
                        episode_data_str = re.sub(r',(\s*[}\]])', r'\1', episode_data_str)
                        
                        # Parse JSON
                        episode_data = json.loads(episode_data_str)
                        
                        # Get all episode numbers (keys) and convert to integers
                        episode_numbers = []
                        for key in episode_data.keys():
                            try:
                                episode_numbers.append(int(key))
                            except ValueError:
                                pass
                        
                        # Sort and get the highest episode number
                        if episode_numbers:
                            max_episode = max(episode_numbers)
                            # Create episode entries from 1 to max_episode
                            for ep_num in range(1, max_episode + 1):
                                episodes.append((str(ep_num), url))
                    except Exception as e:
                        logger.error(f"Error parsing episode data: {e}")
                break
        
        # If no episodes found from JS, try other methods
        if not episodes:
            content = soup.find('div', class_='entry-content')
            if not content:
                content = soup.find('div', class_='post-body')
            if not content:
                content = soup.find('article')
            
            if content:
                links = content.find_all('a', href=True)
                for link in links:
                    text = link.text.strip()
                    # Look for episode patterns
                    ep_match = re.search(r'episode\s*(\d+)', text, re.IGNORECASE)
                    if ep_match:
                        ep_num = ep_match.group(1)
                        link_url = link['href'] if link['href'].startswith('http') else urljoin(url, link['href'])
                        episodes.append((ep_num, link_url))
        
        # If still no episodes, create a default episode link
        if not episodes:
            episodes.append(("01", url))
        
        # Extract thumbnail from the page
        thumbnail = None
        separator_div = soup.find('div', class_='separator')
        if separator_div:
            img_tag = separator_div.find('img')
            if img_tag and img_tag.has_attr('src'):
                thumbnail = img_tag['src']
        
        return base_title, episodes, thumbnail
    except Exception as e:
        logger.error(f"Error extracting anime info: {e}")
        return None, None, None

@app.on_message(filters.text & ~filters.regex(r'^/'))
async def handle_message(client, message):
    """Handle incoming messages containing URLs"""
    # Get the user ID to track recent error messages
    user_id = message.from_user.id
    
    # Get the message text and trim whitespace
    url = message.text.strip()
    
    # Check if the URL is valid using a more flexible pattern
    if not re.match(r'https?://(www\.)?animedekho\.xyz/', url):
        # Check if we recently sent an error to this user
        current_time = time.time()
        if user_id in recent_errors and current_time - recent_errors[user_id] < 10:
            # Skip sending error if we sent one recently (within 10 seconds)
            return
        
        # Update the last error time for this user
        recent_errors[user_id] = current_time
        
        # Send error message
        await message.reply_text("Please send a valid AnimeDekho URL")
        return
    
    try:
        # Extract anime information
        base_title, episodes, thumbnail = extract_anime_info(url)
        if not base_title or not episodes:
            await message.reply_text("Could not extract anime information from the URL")
            return
        
        # Get banner image from TMDB
        banner_url = get_tmdb_banner(base_title)
        # Use thumbnail if banner is not available
        if not banner_url and thumbnail:
            banner_url = thumbnail
        
        # Format episode range for the caption
        if len(episodes) == 1:
            ep_range = episodes[0][0]
        else:
            ep_range = f"{episodes[0][0]}-{episodes[-1][0]}"
        
        # Get the last episode number for the button
        last_episode = episodes[-1][0]
        
        # Create caption with proper formatting - all in bold with quality info
        caption = (
            f"<b>➥ <a href=\"{url}\">{base_title} Hindi Dubbed (ORG) Episode {ep_range} Added 👈🏻</a></b>\n\n"
            f"<b>➪ Quality: 480p | 720p | 1080p</b>\n"
            f"<b>➪ Audio: Multi Audio (Hindi-English-Jap)</b>\n"
            f"<b>☏ Powerd By : - @NineAnimeOfficial ☏</b>\n\n"
            f"<b>〖 <a href=\"https://t.me/BlakiteFF/4\">Join Our All Channels</a> 〗</b>\n"
            f"<b>〖 <a href=\"https://t.me/BlakiteFF\">How To Download & Watch</a> 〗</b>"
        )
        
        # Create inline keyboard with a single episode button showing only the last episode
        keyboard = [
            [InlineKeyboardButton(text=f"Episode {last_episode} Added", url=url)]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send message with banner image if available
        if banner_url:
            sent_message = await message.reply_photo(
                photo=banner_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            sent_message = await message.reply_text(
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        
        # Store post data for reconstruction when posting to channels
        post_data[str(sent_message.id)] = {
            'url': url,
            'base_title': base_title,
            'ep_range': ep_range,
            'last_episode': last_episode,
            'banner_url': banner_url
        }
            
    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        # Only send error message if we haven't sent one recently
        current_time = time.time()
        if user_id not in recent_errors or current_time - recent_errors[user_id] >= 10:
            recent_errors[user_id] = current_time
            await message.reply_text(f"An error occurred: {e}")

# Graceful shutdown handler
def signal_handler(sig, frame):
    logger.info("Received shutdown signal, stopping bot...")
    asyncio.create_task(app.stop())
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def keep_alive():
    """Function to keep the bot alive by pinging Telegram servers periodically"""
    while True:
        try:
            # Get bot info to check if connection is alive
            await app.get_me()
            logger.info("Bot is alive and connected")
        except Exception as e:
            logger.error(f"Keep-alive check failed: {e}")
        
        # Sleep for 5 minutes before next check
        await asyncio.sleep(300)

async def main():
    """Start the bot with restart mechanism"""
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start keep-alive task
    asyncio.create_task(keep_alive())
    
    # Main loop with restart mechanism
    restart_count = 0
    max_restarts = 10
    restart_delay = 30  # seconds
    
    while restart_count < max_restarts:
        try:
            logger.info(f"Starting bot (attempt {restart_count + 1}/{max_restarts})")
            await app.start()
            logger.info("Bot started successfully!")
            
            # Reset restart count on successful start
            restart_count = 0
            
            # Keep the bot running indefinitely
            while True:
                await asyncio.sleep(60)  # Check every minute
                
                # Check if bot is still connected
                try:
                    await app.get_me()
                except:
                    logger.error("Bot disconnected, attempting to restart...")
                    break
                    
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            restart_count += 1
            
            if restart_count < max_restarts:
                logger.info(f"Restarting bot in {restart_delay} seconds...")
                await asyncio.sleep(restart_delay)
            else:
                logger.error("Maximum restart attempts reached. Exiting.")
                sys.exit(1)
        
        finally:
            try:
                await app.stop()
                logger.info("Bot stopped")
            except:
                pass
    
    logger.error("Bot terminated due to too many restarts")

if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())
