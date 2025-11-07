# 1. Setup and Imports
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# 2. Configuration (Your Provided Values)
TOKEN = "8219050849:AAH21B9yY1gooI6jjWEYkBwu7peqdXNTSok" # REPLACE with your actual bot token
ADMIN_USER_ID = 7690675111
PUBLIC_CHANNEL_ID = -1002949557151 # Use the correct format for the channel ID
MIN_CONFESSION_LENGTH = 12
MAX_PENDING_CONFESSIONS = 3 # Not strictly used in this simple flow, but good practice

# 3. Conversation States
CONFESSING = 1

# 4. Storage for Pending Confessions (In a real bot, use a database)
# Key: Unique ID (e.g., message_id or generated UUID)
# Value: Confession Text
pending_confessions = {}

# --- Utility Function to Generate Confession ID ---
def generate_confession_id():
    """Generates a simple unique ID for the confession."""
    return len(pending_confessions) + 1

# --- Bot Commands (START and CANCEL) ---

# 5. /start Command Handler (Initiates the Confession)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a welcome message and asks for the confession."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hello, {user.first_name}! You can share your anonymous confession here. "
        f"**Please write your confession now.** It must be at least {MIN_CONFESSION_LENGTH} characters long. "
        "Type /cancel to stop."
    )
    return CONFESSING # Transition to the CONFESSING state

# 6. /cancel Command Handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current confession process."""
    await update.message.reply_text("Confession process cancelled. Thank you!")
    return ConversationHandler.END # End the conversation

# --- Confession Handling (Message and Approval) ---

# 7. Confession Message Handler (State: CONFESSING)
async def receive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the text, validates it, and sends it to the admin for approval."""
    confession_text = update.message.text

    # 7a. Validation
    if len(confession_text) < MIN_CONFESSION_LENGTH:
        await update.message.reply_text(
            f"❌ Your confession is too short. It must be at least **{MIN_CONFESSION_LENGTH}** characters. "
            "Please try again or type /cancel."
        )
        return CONFESSING # Stay in the CONFESSING state

    # 7b. Storage and ID Generation
    confession_id = generate_confession_id()
    pending_confessions[confession_id] = confession_text

    # 7c. Admin Approval Message Setup
    approval_message = (
        f"**🚨 New Confession to Approve (ID: #{confession_id})**\n"
        "--------------------------------------\n"
        f"{confession_text}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve and Post", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 7d. Send to Admin
    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=approval_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    # 7e. Confirmation to User
    await update.message.reply_text(
        "✅ **Confession sent!** It is now pending admin review. You will not receive a further notification."
    )

    return ConversationHandler.END # End the conversation

# 8. Admin Callback Query Handler (Approval/Rejection)
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the inline button presses from the admin."""
    query = update.callback_query
    await query.answer() # Always answer the query to dismiss the loading state

    # Check if the user is the admin
    if query.from_user.id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to perform this action.")
        return

    data = query.data.split('_')
    action = data[0]
    confession_id = int(data[1])

    confession_text = pending_confessions.pop(confession_id, None)

    if not confession_text:
        await query.edit_message_text(f"Confession #{confession_id} not found or already processed.")
        return

    # 8a. Approve Logic
    if action == 'approve':
        # Create the anonymous post format
        anonymous_post = (
            f"**📣 ANONYMOUS CONFESSION #{confession_id}**\n\n"
            f"_{confession_text}_"
        )
        
        # Send the post to the public channel
        try:
            await context.bot.send_message(
                chat_id=PUBLIC_CHANNEL_ID,
                text=anonymous_post,
                parse_mode='Markdown'
            )
            
            # Update the admin's message
            await query.edit_message_text(
                f"✅ **APPROVED & POSTED:** Confession #{confession_id} has been posted to the channel."
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ **ERROR POSTING:** Could not post Confession #{confession_id}. Check channel permissions. Error: {e}"
            )

    # 8b. Reject Logic
    elif action == 'reject':
        await query.edit_message_text(f"❌ **REJECTED:** Confession #{confession_id} has been rejected and deleted.")

# --- Main Function ---

# 9. Application Setup
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # Define the conversation handler
    # 1. Entry point: /start
    # 2. State: CONFESSING (waiting for text message)
    # 3. Fallback: /cancel (or any other message/command not covered)
    conf_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONFESSING: [
                # Only accepts text messages while in this state
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True # Allows a user to /start again after /cancel
    )

    # Add the handlers to the application
    application.add_handler(conf_handler)
    application.add_handler(CallbackQueryHandler(admin_callback)) # Handle the admin's button clicks

    # Run the bot until the user presses Ctrl-C
    print("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Setup basic logging (optional, but good for debugging)
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    main()
