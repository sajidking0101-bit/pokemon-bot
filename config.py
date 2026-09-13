import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

BOT_NAME = "Pokemon File Sharing"

# Membership
MEMBERSHIP_ENABLED = True
MEMBERSHIP_DAYS = 30

# Default feature switches
FILES_ENABLED = True
CHANNEL_CHECK_ENABLED = False
ADS_ENABLED = False
PREMIUM_ENABLED = True
USER_BLOCK_ENABLED = True
