import requests
import time
import json
import re
from datetime import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import threading

from exchange import process_grok_signal

# Configuration
TELEGRAM_BASE_URL = "https://t.me/drprofitsignal/{}"
GROK_API_URL = "https://api.x.ai/v1/grok"  # Replace with actual Grok API endpoint
GROK_API_KEY = "xai-xKSvy7L4KycaeEuWtMsLRRoeJjWSk0QItzO3tUvkoQ9PHZIC4hOP0Eu7LOJphW5AEqS4iWvCgYesR4lI"  # Replace with your actual Grok API key
CHECK_INTERVAL = 1  # Seconds between checks
PROMPT = """
Analyze the following Telegram post from Doctor Profit and identify if it suggests a token to short or long. The post may mention searching for "food" or similar terms, followed by a specific token and a "short," "long," or "bullish" setup. Treat "bullish" as a "long" position. Return a JSON object with the format {{"token": "<token_name>", "side": "short" or "long"}} if a trading signal is found, or {{"result": false}} if the post is unrelated to trading signals.

Post content:
{post_content}
"""
BOT_TOKEN = "7678223861:AAHSRp5d78DBEs5J8Va_V7IbJ1LHWhY2ejw"

# Global variables for thread management
monitoring_thread = None
should_stop_event = threading.Event()

def fetch_telegram_post(post_id):
    """Fetch the content of a Telegram post by ID."""
    url = TELEGRAM_BASE_URL.format(post_id)
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching post {post_id}: {e}")
        return None

def extract_post_content(html_content):
    """Extract the relevant post text from Telegram HTML."""
    if not html_content:
        return None
    # Try to extract from og:description meta tag
    meta_pattern = r'<meta property="og:description" content="(.*?)">'
    meta_match = re.search(meta_pattern, html_content, re.DOTALL)
    if meta_match:
        content = meta_match.group(1)
        # Clean up HTML entities
        content = content.replace(' ', ' ').replace('"', '"').replace('&', '&')
        return content.strip()
    # Fallback to message text div
    div_pattern = r'<div class="tgme_widget_message_text js-message_text" dir="auto">(.*?)</div>'
    div_match = re.search(div_pattern, html_content, re.DOTALL)
    if div_match:
        content = div_match.group(1)
        # Clean up HTML tags and entities
        content = re.sub(r'<br\s*/?>', '\n', content)
        content = re.sub(r'<.*?>', '', content)
        content = content.replace(' ', ' ').replace('"', '"').replace('&', '&')
        return content.strip()
    return None

def query_grok_api(post_content):
    """Send post content to Grok API and get the trading signal."""
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Correct payload structure for Grok API
    payload = {
        "messages": [
            {
                "role": "system",
                "content": """You are a trading signal analyzer for Doctor Profit's Telegram posts. Look for trading signals that follow these patterns: 1) Posts saying 'Watching for food', 'Food coming', 'Food found' are usually followed by trading signals. 2) Signals contain token symbols like #H, #PARTI, #CHILLGUY, #ARK, #MKR. 3) Look for 'Short set up', 'Buy set up spot', 'buy set up spot', or just 'Buy' followed by token name. 4) 'Bullish' means long position. Return only valid JSON.
Example if post is like this:
Post content: #H

Short set up
{'token': 'H', 'side': 'short'}
JSON output should be:

"""
            },
            {
                "role": "user",
                "content": PROMPT.format(post_content=post_content)
            }
        ],
        "model": "grok-3-latest",
        "stream": False,
        "temperature": 0
    }
    
    try:
        response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        # Extract the actual response content
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            try:
                # Try to parse the content as JSON
                return json.loads(content)
            except json.JSONDecodeError:
                print(f"Failed to parse Grok response as JSON: {content}")
                return None
        else:
            print(f"Unexpected Grok API response structure: {result}")
            return None
            
    except requests.RequestException as e:
        print(f"Error querying Grok API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding Grok API response: {e}")
        return None

def save_latest_post_id(post_id):
    """Save the latest post ID to a JSON file."""
    with open("latest_post_id.json", "w") as f:
        json.dump({"latest_post_id": post_id}, f)

def load_latest_post_id():
    """Load the latest post ID from a JSON file if it exists."""
    try:
        with open("latest_post_id.json", "r") as f:
            data = json.load(f)
            return data.get("latest_post_id")
    except FileNotFoundError:
        return None

def monitoring_loop():
    """Main monitoring loop that runs in a separate thread."""
    current_post_id = load_latest_post_id()
    print(f"Starting monitoring from post ID: {current_post_id}")
    
    while not should_stop_event.is_set():
        print(f"Checking post ID: {current_post_id} at {datetime.now()}")
        html_content = fetch_telegram_post(current_post_id)
        
        if html_content:
            post_content = extract_post_content(html_content)
            if post_content and "All Dr.Profit Premium Signals for FREE here" not in post_content:
                print(f"Post content: {post_content}")
                grok_response = query_grok_api(post_content)
                
                if grok_response:
                    print(f"Grok response: {grok_response}")
                    # Validate response format
                    if isinstance(grok_response, dict) and ("token" in grok_response or "result" in grok_response):
                        print(f"Processed signal: {grok_response}")
                        process_grok_signal(grok_response)
                    else:
                        print("Invalid Grok response format")
                else:
                    print("Failed to get valid response from Grok API")
            
                current_post_id += 1
                save_latest_post_id(current_post_id)
                break
        else:
            print(f"Post ID {current_post_id} not found or error occurred")
        
        # Use event.wait() instead of time.sleep() for better responsiveness
        if should_stop_event.wait(CHECK_INTERVAL):
            break
    
    print("Monitoring loop stopped")

async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /run command to start checking for new posts."""
    global monitoring_thread
    
    if monitoring_thread and monitoring_thread.is_alive():
        await update.message.reply_text("Monitoring is already running! Use /stop to stop it first.")
        return
    
    # Clear the stop event and start monitoring
    should_stop_event.clear()
    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()
    
    await update.message.reply_text("Started post monitoring! Use /stop to stop monitoring.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /stop command to stop checking for new posts."""
    global monitoring_thread
    
    if not monitoring_thread or not monitoring_thread.is_alive():
        await update.message.reply_text("Monitoring is not currently running.")
        return
    
    # Signal the monitoring thread to stop
    should_stop_event.set()
    await update.message.reply_text("Stopping post monitoring...")
    
    # Wait for the thread to finish (with timeout)
    monitoring_thread.join(timeout=5)
    
    if monitoring_thread.is_alive():
        await update.message.reply_text("Warning: Monitoring thread did not stop cleanly.")
    else:
        await update.message.reply_text("Post monitoring stopped successfully.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /status command to check monitoring status."""
    global monitoring_thread
    
    if monitoring_thread and monitoring_thread.is_alive():
        await update.message.reply_text("✅ Monitoring is currently running.")
    else:
        await update.message.reply_text("❌ Monitoring is not running. Use /run to start.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command to greet the user."""
    welcome_message = """
Welcome to the Telegram Post Monitor Bot!

Available commands:
/run - Start monitoring posts
/stop - Stop monitoring posts  
/status - Check monitoring status
/help - Show this help message
    """
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
    help_message = """
📋 Available Commands:

/run - Start monitoring Telegram posts for trading signals
/stop - Stop the monitoring process
/status - Check if monitoring is currently active
/help - Show this help message

The bot monitors posts from Doctor Profit's channel and processes trading signals using Grok AI.
    """
    await update.message.reply_text(help_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors during bot operation."""
    print(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")

if __name__ == "__main__":
    # Initialize the bot application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("run", run_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))

    # Add error handler
    application.add_error_handler(error_handler)

    # Start the bot
    print("Starting Telegram bot...")
    print("Available commands: /start, /run, /stop, /status, /help")
    application.run_polling(allowed_updates=Update.ALL_TYPES)