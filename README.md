========================================
MIXED MUSEUM MEDIA & ANALYTICS BOT
========================================

DESCRIPTION
-----------
This bot fetches and summarises relevant news stories, analyses recent web analytics (GA4 via BigQuery), generates simple charts, and emails an insight report to the Museum. All scheduling, configuration, and ownership details are below.

-------------------------
1. WHAT THE BOT DOES
-------------------------
- Fetches news on mixed heritage topics from major, trusted sources
- Uses AI (OpenAI API) to summarise relevance
- Connects to your Google Analytics 4 (GA4) via BigQuery for web traffic trends and comparisons
- Builds visualisations of top sources and countries
- Sends a professional HTML email (with embedded images) to the recipient
- The frequency can be changed at any time by replying to the email (see section 8)

-------------------------------
2. PREREQUISITES / DEPENDENCIES
-------------------------------
- Python 3.8+
- The following Python packages (in requirements.txt):

    openai
    python-dotenv
    newsapi-python
    google-cloud-bigquery
    matplotlib

-------------------------
3. SETUP INSTRUCTIONS
-------------------------

A. Clone or copy this code to your server or computer.

B. Install dependencies:

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

C. Set up your .env file with the following values:

    OPENAI_API_KEY=sk-... (from https://platform.openai.com)
    NEWS_API_KEY=...      (from https://newsapi.org)
    GOOGLE_APPLICATION_CREDENTIALS=/full/path/to/your/service-account.json
    EMAIL_FROM=yourbot@gmail.com (or other sending email)
    EMAIL_TO=chamion@themixedmuseum.org (can be changed as needed)
    EMAIL_PASSWORD=app-specific-password (never use your actual Google password)
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587

  (Note: GOOGLE_APPLICATION_CREDENTIALS should be the full absolute path to your downloaded service account JSON file.)

D. Google Cloud setup:

    1. Go to https://console.cloud.google.com
    2. Ensure your Google Analytics 4 property is linked to BigQuery (Admin > BigQuery Linking).
    3. Create a Service Account with BigQuery Data Viewer role on the correct project.
    4. Download the JSON key, save securely, and reference the path in your .env file.
    5. NEVER send this file over Slack or email—use Google Drive or a secure sharing service.

E. (Optional, for email reply commands): Set up IMAP access on your email provider (Gmail IMAP enabled).

------------------------
4. RUNNING THE SCRIPT
------------------------
- To run the script manually:

    python main.py

- To automate, schedule with cron, Task Scheduler, or GitHub Actions.
  Example cron (every day at 8am):

    0 8 * * * /path/to/venv/bin/python /path/to/main.py

---------------------------
5. EMAIL REPORT CONTENTS
---------------------------
- Summary of latest relevant news stories (headline, short summary, link)
- Analytics trends for the past 3 days vs previous 3 days (pageviews, sources, countries)
- AI-written summary of notable trends
- Visualisations: Bar charts of top traffic sources and top countries
- (Optional): Additional recipients can be added by editing EMAIL_TO in .env

-----------------------
6. SECURITY PRACTICES
-----------------------
- All credentials are stored in .env, never in code.
- Google service account has read-only BigQuery access (no editing, no other services).
- No data is stored locally or logged permanently.
- Only summary analytics (not personally identifiable information) is queried.
- Email reply commands can only be read from ALLOWED_SENDERS (see code).

-------------------------------
7. TRANSFER/CHANGE OF OWNERSHIP
-------------------------------
- Give new maintainer:
    - The codebase
    - The .env file (never email passwords; use Google Drive, etc)
    - Service account JSON key (again: send securely)
    - API keys for OpenAI and NewsAPI (these can be generated anew if needed)
- Update EMAIL_TO as needed
- Update scheduled jobs if moving to a new server/user

----------------------------------------
8. HOW TO CHANGE REPORT FREQUENCY
----------------------------------------
- Reply to any bot email.
- The FIRST line should be one of the following (case-insensitive):

    Daily
    Weekly
    Fortnightly

- The bot will scan for these commands and update its schedule.
- "Weekly" means every Monday. "Fortnightly" means every other Monday.

----------------------------------------
9. TROUBLESHOOTING
----------------------------------------
- Email not sending? Check SMTP server, port, password, and allow "less secure apps" or use Gmail app password.
- BigQuery error? Check service account role and project dataset/table path.
- No news or analytics? Check API keys and that quotas haven't been reached.

--------------------------
10. SUPPORT & QUESTIONS
--------------------------
- Contact the previous maintainer (Ewan) if available, or pass along documentation to your internal IT support.
- For future ownership, be sure to rotate passwords and revoke access when maintainers change.

---------------------------------
11. MAINTAINER'S NOTES / FAQ
---------------------------------
- The bot is fully modular and easy to modify for new data sources or report sections.
- To add more allowed senders for email commands, update ALLOWED_SENDERS in main.py.
- For multiple recipients, use a comma-separated list in EMAIL_TO.
- Service account keys should be rotated every 6–12 months.

-----------------------------
END OF README
-----------------------------
