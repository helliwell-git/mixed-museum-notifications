import os
from dotenv import load_dotenv
import openai
import pandas as pd
from newsapi import NewsApiClient
from google.cloud import bigquery
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

# === API KEYS ===
openai.api_key = os.getenv("OPENAI_API_KEY")
newsapi = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))

# === Fetch Relevant News Articles ===
def get_news_articles():
    keywords = [
        "mixed heritage", "mixed race", "biracial", "dual heritage",
        "multiethnic", "racial identity", "cultural identity", "interracial family"
    ]
    domains = ','.join([
        'bbc.co.uk', 'theguardian.com', 'independent.co.uk',
        'nytimes.com', 'cnn.com', 'npr.org',
        'euronews.com', 'dw.com', 'lemonde.fr', 'spiegel.de'
    ])

    articles = newsapi.get_everything(
        q=' OR '.join(keywords),
        domains=domains,
        language='en',
        sort_by='publishedAt',
        page_size=10
    )
    return articles.get('articles', [])

# === Summarise News Relevance ===
def summarise_article(title, content):
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

# === News Section Output ===
def build_news_section():
    section = ""
    for article in get_news_articles():
        title = article['title']
        desc = article.get('description') or article.get('content', '')
        url = article['url']
        summary = summarise_article(title, desc)
        if summary.lower() != "not relevant":
            section += f"<b>{title}</b><br>{summary}<br><a href='{url}'>{url}</a><br><br>"
    return section if section else "No relevant news articles today."

# === GA4 via BigQuery ===
def get_ga4_data():
    client = bigquery.Client.from_service_account_json(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    query = """
    SELECT
      traffic_source.source as source,
      traffic_source.medium as medium,
      COUNT(*) as sessions
    FROM
      `your_project_id.analytics_XXXXXXX.events_*`
    WHERE
      event_name = 'session_start'
      AND _TABLE_SUFFIX BETWEEN FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY))
      AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
    GROUP BY
      source, medium
    ORDER BY
      sessions DESC
    LIMIT 10
    """
    return client.query(query).to_dataframe()

# === GPT Summary for GA4 ===
def summarise_ga4(df):
    prompt = f"""Summarise the recent traffic trends for The Mixed Museum based on this breakdown of sessions by source/medium.

{df.to_string(index=False)}

Write 2–3 sentences identifying standout traffic patterns or opportunities.
"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )
    return response.choices[0].message.content.strip()

# === GA4 Section Output ===
def build_ga4_section():
    try:
        df = get_ga4_data()
        summary = summarise_ga4(df)
        section = "<b>Traffic Sources (last 3 days)</b><br><br>"
        for _, row in df.iterrows():
            section += f"- {row['source']} / {row['medium']}: {row['sessions']} sessions<br>"
        section += f"<br><b>AI Summary:</b><br>{summary}"
        return section
    except Exception as e:
        return f"⚠️ Error retrieving GA4 data: {e}"

# === Email Sending ===
def send_daily_email(subject, news_html, ga4_html):
    sender = os.getenv("EMAIL_FROM")
    recipient = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT"))

    msg = MIMEMultipart("alternative")
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

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
    </style>
    </head>
    <body>
      <p>Hello Chamion,</p>
      <p>Here is your daily insight report for The Mixed Museum:</p>

      <h2>🗞 Relevant News Opportunities</h2>
      {news_html}

      <h2>📊 Website Trends from GA4</h2>
      {ga4_html}

      <p>—<br><i>This email was generated automatically by mixed-heritage-alert-bot.</i></p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, 'html'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        print("✅ Daily email sent successfully.")

# === Main Execution ===
if __name__ == "__main__":
    news = build_news_section()
    ga4 = build_ga4_section()
    send_daily_email("📬 The Mixed Museum: Daily Media & Analytics Brief", news, ga4)