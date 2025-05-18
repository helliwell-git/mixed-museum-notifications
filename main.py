import os
from dotenv import load_dotenv  # For loading environment variables from .env
import openai                  # For AI-powered summaries
from newsapi import NewsApiClient  # To fetch news articles
from google.cloud import bigquery  # To access Google Analytics data via BigQuery
import smtplib                 # For sending emails
from email.mime.text import MIMEText  # For formatting email content
from email.mime.multipart import MIMEMultipart  # For multipart emails (with HTML, images)
from email.mime.image import MIMEImage  # For sending images as attachments
from datetime import datetime, timedelta  # For date/time operations
import imaplib                 # For checking email replies (IMAP)
import email                   # For parsing email messages
import matplotlib.pyplot as plt  # For creating charts/visualisations
import io                      # For handling image buffers in memory

# Load .env file containing API keys and credentials
load_dotenv()

# === API KEYS ===
openai.api_key = os.getenv("OPENAI_API_KEY")  # Set OpenAI API key for summaries
newsapi = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))  # NewsAPI client

# File to store the user's chosen email frequency ("DAILY", "WEEKLY", "FORTNIGHTLY")
FREQUENCY_FILE = "frequency.txt"
ALLOWED_SENDERS = ["chamion@themixedmuseum.org"]  # Who is allowed to send frequency commands

# === Frequency Control ===

def get_current_frequency():
    """
    Reads the current report frequency from file. Defaults to DAILY if not set.
    """
    if not os.path.exists(FREQUENCY_FILE):
        return "DAILY"
    with open(FREQUENCY_FILE, "r") as f:
        return f.read().strip().upper()

def update_frequency(new_freq):
    """
    Updates the frequency.txt file with the new frequency setting.
    """
    with open(FREQUENCY_FILE, "w") as f:
        f.write(new_freq.upper())
    print(f"Frequency updated to {new_freq}")

def parse_command_from_reply(body):
    """
    Parses the email body for a frequency command (e.g., 'daily', 'weekly', 'fortnightly').
    Only looks at first non-empty, non-quoted line.
    """
    for line in body.splitlines():
        cleaned = line.strip().lower()
        if cleaned in ["daily", "weekly", "fortnightly"]:
            return cleaned.upper()
        if cleaned and not cleaned.startswith('>'):  # Stop at first real line
            break
    return None

def check_email_for_command():
    """
    Connects to Gmail via IMAP and checks for new emails from allowed senders.
    If a frequency command is found, updates the frequency.
    """
    if not os.getenv("EMAIL_FROM") or not os.getenv("EMAIL_PASSWORD"):
        return
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(os.getenv("EMAIL_FROM"), os.getenv("EMAIL_PASSWORD"))
    mail.select("inbox")
    status, messages = mail.search(None, '(UNSEEN)')  # Only unread
    for num in messages[0].split():
        typ, msg_data = mail.fetch(num, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        sender = email.utils.parseaddr(msg['From'])[1]
        if sender.lower() not in [a.lower() for a in ALLOWED_SENDERS]:
            continue  # Ignore if not allowed
        # Extract plain text from email
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    charset = part.get_content_charset() or 'utf-8'
                    body += part.get_payload(decode=True).decode(charset, errors='ignore')
        else:
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='ignore')
        command = parse_command_from_reply(body)
        if command:
            update_frequency(command)
    mail.logout()

def should_send_email(frequency):
    """
    Determines whether the bot should send an email report today,
    based on frequency (DAILY, WEEKLY, FORTNIGHTLY).
    """
    today = datetime.utcnow().date()
    if frequency == "DAILY":
        return True
    elif frequency == "WEEKLY":
        return today.weekday() == 0  # Monday
    elif frequency == "FORTNIGHTLY":
        anchor = datetime(2024, 5, 6).date()  # First 'Monday' to start the fortnight cycle
        return ((today - anchor).days // 7) % 2 == 0 and today.weekday() == 0
    return False

# === News Article Fetching & Summarisation ===

def get_news_articles():
    """
    Uses NewsAPI to fetch articles from major media sources,
    filtering by keywords and deduplicating on URL.
    Only fetches from the last 24 hours.
    """
    keywords = [
        "mixed heritage", "mixed race", "biracial", "dual heritage",
        "multiethnic", "racial identity", "cultural identity", "interracial family",
        "representation", "ethnicity", "racial diversity", "hybridity",
        "migrant heritage", "diaspora", "postcolonial", "black British history",
        "Afro-European", "racial justice", "intersectionality",
        "heritage month", "identity politics", "intercultural"
    ]
    domains = [
        "bbc.co.uk", "theguardian.com", "independent.co.uk", "thetimes.co.uk",
        "telegraph.co.uk", "ft.com", "mirror.co.uk", "metro.co.uk", "express.co.uk",
        "standard.co.uk", "channel4.com", "sky.com", "newstatesman.com", "prospectmagazine.co.uk",
        "nytimes.com", "washingtonpost.com", "npr.org", "cnn.com", "abcnews.go.com",
        "nbcnews.com", "reuters.com", "apnews.com", "bloomberg.com", "usatoday.com",
        "latimes.com", "pbs.org", "theatlantic.com", "vox.com", "slate.com",
        "euronews.com", "dw.com", "lemonde.fr", "spiegel.de", "elpais.com",
        "politico.eu", "ilpost.it", "la Repubblica", "derstandard.at", "nos.nl"
    ]
    from_param = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    articles = newsapi.get_everything(
        q=' OR '.join(keywords),
        domains=','.join(domains),
        language='en',
        sort_by='publishedAt',
        page_size=40,
        from_param=from_param
    )
    seen_urls = set()
    clean_articles = []
    for article in articles.get('articles', []):
        url = article['url'].split('?')[0]
        if url not in seen_urls:
            seen_urls.add(url)
            clean_articles.append(article)
    return clean_articles

def summarise_article(title, content):
    """
    Sends each news article to OpenAI for a two-sentence summary
    (or a "Not relevant" response if it's not about mixed heritage).
    """
    prompt = f"""You are helping The Mixed Museum track public conversations about mixed heritage.
Given the following article, is it relevant to themes of mixed heritage, racial identity, or representation?
If yes, summarise in 2 sentences. If not, say 'Not relevant.'
Title: {title}
Content: {content}
"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100
    )
    return response.choices[0].message.content.strip()

def build_news_section():
    """
    Assembles the news HTML section with only relevant (AI-approved) stories.
    """
    section = ""
    for article in get_news_articles():
        title = article['title']
        desc = article.get('description') or article.get('content', '')
        url = article['url']
        summary = summarise_article(title, desc)
        if summary.lower() != "not relevant":
            section += f"<b>{title}</b><br>{summary}<br><a href='{url}'>{url}</a><br><br>"
    return section if section else "No relevant news articles today."

# === GA4 via BigQuery: Data, Summarisation, and Visualisation ===

def get_ga4_data(period='recent'):
    """
    Queries Google BigQuery for GA4 analytics, pulling the last three days (or previous three) of:
    - Top pageviews
    - Top visitor countries
    - Top traffic sources
    Returns as a DataFrame for analysis and charting.
    """
    client = bigquery.Client.from_service_account_json(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    if period == 'recent':
        start_offset = 3
        end_offset = 0
    else:
        start_offset = 6
        end_offset = 3
    query = f"""
    WITH sessions AS (
      SELECT
        user_pseudo_id,
        geo.country,
        traffic_source.source AS source,
        traffic_source.medium AS medium,
        event_name,
        event_params
      FROM
        `your_project_id.analytics_XXXXXXX.events_*`
      WHERE
        _TABLE_SUFFIX BETWEEN FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL {start_offset} DAY))
        AND FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL {end_offset} DAY))
    ),
    pageviews AS (
      SELECT
        event_params.value.string_value AS page_title,
        COUNT(*) AS views
      FROM sessions
      WHERE event_name = 'page_view'
      GROUP BY page_title
    ),
    sessions_by_country AS (
      SELECT
        country,
        COUNT(DISTINCT user_pseudo_id) AS sessions
      FROM sessions
      WHERE event_name = 'session_start'
      GROUP BY country
    ),
    source_summary AS (
      SELECT
        source,
        medium,
        COUNT(*) AS sessions
      FROM sessions
      WHERE event_name = 'session_start'
      GROUP BY source, medium
    )
    SELECT
      'pageviews' AS metric,
      page_title AS label,
      views AS value
    FROM pageviews
    UNION ALL
    SELECT
      'countries' AS metric,
      country AS label,
      sessions AS value
    FROM sessions_by_country
    UNION ALL
    SELECT
      'sources' AS metric,
      CONCAT(source, ' / ', medium) AS label,
      sessions AS value
    FROM source_summary
    ORDER BY metric, value DESC
    """
    return client.query(query).to_dataframe()

def summarise_ga4_with_comparison():
    """
    Compares GA4 metrics (current 3 days vs previous 3 days).
    Produces:
    - Table with top metrics and percent changes
    - AI summary of trends
    Also returns DataFrame for visualisation.
    """
    df_now = get_ga4_data(period='recent')
    df_prev = get_ga4_data(period='previous')
    summary_parts = []
    for metric in ['pageviews', 'countries', 'sources']:
        now = df_now[df_now['metric'] == metric].set_index('label')
        prev = df_prev[df_prev['metric'] == metric].set_index('label')
        combined = now.join(prev, lsuffix='_now', rsuffix='_prev', how='outer').fillna(0)
        combined['change'] = ((combined['value_now'] - combined['value_prev']) / combined['value_prev'].replace(0, 1)) * 100
        combined = combined.sort_values(by='value_now', ascending=False).head(5)
        table = combined[['value_now', 'value_prev', 'change']].round(1).to_string()
        summary_parts.append(f"\nTop {metric} (current vs. previous 3 days):\n{table}")
    prompt = f"""The Mixed Museum's GA4 report shows these comparisons between the last 3 days and the 3 days prior:
{chr(10).join(summary_parts)}
Please summarise any spikes, trends, or surprising drops across content, countries, or sources. Keep it under 5 sentences.
"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=180
    )
    return "\n\n".join(summary_parts), response.choices[0].message.content.strip(), df_now

def plot_bar_chart(df, metric, title, ylabel):
    """
    Generates a bar chart for the given metric (sources or countries).
    Returns a BytesIO buffer of the image for embedding.
    """
    import matplotlib
    matplotlib.use('Agg')  # Ensure works on servers with no GUI
    fig, ax = plt.subplots(figsize=(6, 3))
    data = df[df['metric'] == metric].sort_values('value', ascending=False).head(5)
    ax.bar(data['label'], data['value'], color='#4677C7')
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return buf

def build_ga4_section_with_charts():
    """
    Builds the HTML and in-memory images for GA4 section:
    - Table of top metrics
    - AI summary
    - Two bar charts: top sources and top countries
    """
    try:
        table, summary, df_now = summarise_ga4_with_comparison()
        chart_sources = plot_bar_chart(df_now, 'sources', 'Top Traffic Sources', 'Sessions')
        chart_countries = plot_bar_chart(df_now, 'countries', 'Top Countries', 'Sessions')
        html = f"<pre>{table}</pre><br><b>AI Summary:</b><br>{summary}"
        return html, [("chart_sources.png", chart_sources), ("chart_countries.png", chart_countries)]
    except Exception as e:
        return f"⚠️ Error retrieving GA4 data: {e}", []

# === Email Sending (with inline charts) ===

def send_daily_email(subject, news_html, ga4_html, images=[]):
    """
    Assembles and sends the full HTML report by email, with inline charts.
    """
    sender = os.getenv("EMAIL_FROM")
    recipient = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT"))
    msg = MIMEMultipart("related")
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

    # Embed image(s) in the HTML email
    img_html = ""
    for i, (name, img_buf) in enumerate(images):
        img_html += f'<img src="cid:img{i}" style="max-width:90%; margin-bottom:15px;"><br>'

    html_body = f"""
    <html>
    <head>
    <style>
      body {{
        font-family: Arial, sans-serif;
        font-size: 15px;
        color: #333;
        padding: 20px;
      }}
      h2 {{
        color: #0052cc;
        margin-top: 30px;
      }}
      a {{
        color: #0066cc;
      }}
      pre {{
        font-size: 13px;
        background-color: #f8f8f8;
        padding: 10px;
        border: 1px solid #eee;
        overflow-x: auto;
      }}
    </style>
    </head>
    <body>
      <p>Hello Chamion,</p>
      <p>Here is your insight report for The Mixed Museum:</p>
      <h2>🗞 Relevant News Opportunities</h2>
      {news_html}
      <h2>📊 Website Trends from GA4</h2>
      {ga4_html}
      {img_html}
      <br>
      <b>To change the frequency of these emails, simply reply to this email with the first line as one of: Daily, Weekly, Fortnightly.</b>
      <p>—<br><i>This email was generated automatically by mixed-heritage-alert-bot.</i></p>
    </body>
    </html>
    """
    msg_alt = MIMEMultipart("alternative")
    msg_alt.attach(MIMEText(html_body, 'html'))
    msg.attach(msg_alt)

    # Attach image buffers inline for each chart (referenced by CID above)
    for i, (name, img_buf) in enumerate(images):
        img = MIMEImage(img_buf.read(), name=name)
        img.add_header('Content-ID', f'<img{i}>')
        img.add_header('Content-Disposition', 'inline', filename=name)
        msg.attach(img)
        img_buf.seek(0)

    # Send the email using SMTP (Gmail or other)
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        print("✅ Email sent successfully with visualisations.")

# === Main Execution: Orchestrates All Functions ===

if __name__ == "__main__":
    check_email_for_command()  # See if there's a reply command to change frequency
    freq = get_current_frequency()
    if should_send_email(freq):
        news = build_news_section()
        ga4_html, images = build_ga4_section_with_charts()
        send_daily_email("The Mixed Museum: Media & Analytics Brief", news, ga4_html, images)
    else:
        print(f"Not time to send report ({freq}).")