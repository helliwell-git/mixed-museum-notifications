import os
from dotenv import load_dotenv
import openai
import pandas as pd
from newsapi import NewsApiClient
from google.cloud import bigquery
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

load_dotenv()

# === API KEYS ===
openai.api_key = os.getenv("OPENAI_API_KEY")
newsapi = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))

# === Fetch Relevant News Articles ===
def get_news_articles():
    # Keywords to identify culturally relevant stories
    keywords = [
        "mixed heritage", "mixed race", "biracial", "dual heritage",
        "multiethnic", "racial identity", "cultural identity", "interracial family",
        "representation", "ethnicity", "racial diversity", "hybridity",
        "migrant heritage", "diaspora", "postcolonial", "black British history",
        "Afro-European", "racial justice", "intersectionality",
        "heritage month", "identity politics", "intercultural"
    ]

    # News domains to restrict search to reputable outlets
    domains = [
        # UK
        "bbc.co.uk", "theguardian.com", "independent.co.uk", "thetimes.co.uk",
        "telegraph.co.uk", "ft.com", "mirror.co.uk", "metro.co.uk", "express.co.uk",
        "standard.co.uk", "channel4.com", "sky.com", "newstatesman.com", "prospectmagazine.co.uk",

        # US
        "nytimes.com", "washingtonpost.com", "npr.org", "cnn.com", "abcnews.go.com",
        "nbcnews.com", "reuters.com", "apnews.com", "bloomberg.com", "usatoday.com",
        "latimes.com", "pbs.org", "theatlantic.com", "vox.com", "slate.com",

        # Europe
        "euronews.com", "dw.com", "lemonde.fr", "spiegel.de", "elpais.com",
        "politico.eu", "ilpost.it", "la Repubblica", "derstandard.at", "nos.nl"
    ]

    # Only fetch stories from the last 24 hours
    from_param = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Query NewsAPI
    articles = newsapi.get_everything(
        q=' OR '.join(keywords),              # Combine keywords using OR
        domains=','.join(domains),            # Restrict to trusted sources
        language='en',
        sort_by='publishedAt',
        page_size=40,
        from_param=from_param                 # Only articles published in last 24 hours
    )

    # Deduplicate by stripping URL parameters
    seen_urls = set()
    clean_articles = []

    for article in articles.get('articles', []):
        url = article['url'].split('?')[0]  # Strip tracking params like ?utm=...
        if url not in seen_urls:
            seen_urls.add(url)
            clean_articles.append(article)

    return clean_articles

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

# === GA4 via BigQuery with Comparison ===
def get_ga4_data(period='recent'):
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

# === GA4 Comparison Summary ===
def summarise_ga4_with_comparison():
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
    return "\n\n".join(summary_parts), response.choices[0].message.content.strip()

# === GA4 Section Output ===
def build_ga4_section():
    try:
        table, summary = summarise_ga4_with_comparison()
        return f"<pre>{table}</pre><br><b>AI Summary:</b><br>{summary}"
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