from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import date
import logging

# Set up basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- 1. CONFIGURATION ---
TOKEN = "8593641544:AAGN07F45l_bcFvpcsNOWu8YuBFw0DKaUOg" 
ADMIN_USER_ID = 7690675111       
PUBLIC_CHANNEL_ID = -1002949557151 
MIN_CONFESSION_LENGTH = 12
MAX_PENDING_CONFESSIONS = 3 # New limit for confessions in the queue per user

# --- 2. BOT STATE (Storage) ---
# Key: Unique Confession ID (from update_id), Value: Confession Text
CONFESSIONS_QUEUE = {} 

# Key: User ID, Value: Count of confessions currently waiting for approval from this user
USER_PENDING_COUNTS = {} 

# Simple counter for confession numbering
CONFESSION_COUNT = 0 


# --- 3. HANDLERS (start command is unchanged) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the user and prompts for a confession."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hello {user.first_name}! Send me your **anonymous confession** (must be at least 12 characters). "
        f"You can submit up to {MAX_PENDING_CONFESSIONS} confessions for review.",
    )


# --- 4. MESSAGE HANDLER (Confession Submission & Validation) ---
async def handle_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles an incoming text message, validates length and limit, and sends to admin."""
    
    global CONFESSIONS_QUEUE
    global USER_PENDING_COUNTS
    user_id = update.effective_user.id
    user_confession = update.message.text
    
    # --- 4.1. LENGTH VALIDATION ---
    if len(user_confession) < MIN_CONFESSION_LENGTH:
        await update.message.reply_text(
            f"❌ **Invalid Submission.** Your confession must be at least {MIN_CONFESSION_LENGTH} characters long. Please try again."
        )
        return

    # --- 4.2. PENDING LIMIT CHECK ---
    # Get current pending count, defaulting to 0
    current_pending = USER_PENDING_COUNTS.get(user_id, 0)
    
    if current_pending >= MAX_PENDING_CONFESSIONS:
        await update.message.reply_text(
            f"🛑 **Submission Limit Reached.** You already have {MAX_PENDING_CONFESSIONS} confessions pending review. "
            "Please wait for the admin to approve or reject them before submitting more."
        )
        return
        
    # --- 4.3. QUEUE & NOTIFY ADMIN ---
    
    # Increment pending count
    USER_PENDING_COUNTS[user_id] = current_pending + 1
    
    # Generate a unique key for this confession
    unique_confession_id = update.update_id 
    CONFESSIONS_QUEUE[unique_confession_id] = user_confession
    
    # Create the moderation buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve & Post", callback_data=f"APPROVE_{unique_confession_id}_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"REJECT_{unique_confession_id}_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Format the message for the Admin (you)
    moderation_message = (
        f"**🚨 NEW CONFESSION (ID: {unique_confession_id}) 🚨**\n"
        f"Submitted by User ID: `{user_id}` (Pending count: {current_pending + 1})\n\n"
        f"**Confession Text:**\n"
        f"-----------------------\n"
        f"{user_confession}\n"
        f"-----------------------"
    )

    # Send the message with buttons to your personal chat
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=moderation_message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        await update.message.reply_text("Confession received! It has been submitted for review.")
    except Exception as e:
        logging.error(f"Failed to send moderation message to ADMIN_USER_ID {ADMIN_USER_ID}: {e}")
        # Revert pending count if notification fails
        USER_PENDING_COUNTS[user_id] = current_pending
        await update.message.reply_text("❗ Submission failed. Admin must start a chat with the bot first.")
        


# --- 5. CALLBACK HANDLER (Button Clicks) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes button clicks for approval/rejection."""
    
    global CONFESSIONS_QUEUE
    global CONFESSION_COUNT
    global USER_PENDING_COUNTS
    
    query = update.callback_query
    await query.answer() 
    
    # 5.1. Authorization Check
    if query.from_user.id != ADMIN_USER_ID:
        await query.edit_message_text("❌ You are not authorized to approve confessions.")
        return
        
    # Data is now 'ACTION_CONFESSIONID_USERID'
    data = query.data.split('_')
    action = data[0]
    confession_id = int(data[1])
    submitted_user_id = int(data[2]) # ID of the user who submitted the confession
    
    # 5.2. Check if the confession is still pending
    if confession_id not in CONFESSIONS_QUEUE:
        await query.edit_message_text("This confession has already been processed or expired.")
        return

    # 5.3. Handle Approval
    if action == "APPROVE":
        CONFESSION_COUNT += 1
        confession_text = CONFESSIONS_QUEUE[confession_id]
        
        post_text = (
            f"**#EPSU_Confession {CONFESSION_COUNT}**\n\n"
            f"{confession_text}"
        )
        
        try:
            # Post to the public channel
            await context.bot.send_message(
                chat_id=PUBLIC_CHANNEL_ID,
                text=post_text,
                parse_mode="Markdown"
            )
            
            # Edit the message in the admin chat to confirm approval 
            await query.edit_message_text(
                f"✅ **APPROVED & POSTED:**\n\n{post_text}",
                parse_mode="Markdown"
            )

        except Exception as e:
            await query.edit_message_text(f"❌ **POSTING FAILED.** Bot may not be an admin in the channel: `{e}`", parse_mode="Markdown")
            
    # 5.4. Handle Rejection
    elif action == "REJECT":
        await query.edit_message_text(
            f"❌ **REJECTED.** Confession ID {confession_id} will not be posted.",
            parse_mode="Markdown"
        )
        
    # 5.5. Clean up & update pending counts (for both Approve and Reject)
    if confession_id in CONFESSIONS_QUEUE:
        del CONFESSIONS_QUEUE[confession_id]
        
    if submitted_user_id in USER_PENDING_COUNTS:
        USER_PENDING_COUNTS[submitted_user_id] -= 1
        # Remove the user if their count hits zero to keep the dictionary clean
        if USER_PENDING_COUNTS[submitted_user_id] <= 0:
             del USER_PENDING_COUNTS[submitted_user_id]


# --- 6. MAIN FUNCTION ---
def main() -> None:
    """Start the bot and register all handlers."""
    application = Application.builder().token(TOKEN).build()

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confession))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logging.info("Confessions Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()