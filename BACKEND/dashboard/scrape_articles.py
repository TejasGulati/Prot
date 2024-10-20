import os
import logging
import random
import re
import time
import json
from functools import wraps
import traceback
import requests
import requests_cache
from bs4 import BeautifulSoup
from django.utils import timezone
from dashboard.models import Article
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import google.generativeai as genai
from dotenv import load_dotenv
import langdetect

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Disable SSL warnings (use with caution)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up caching
requests_cache.install_cache('news_cache', expire_after=3600)  # Cache for 1 hour

# Configure Gemini AI
genai.configure(api_key=os.getenv("API_KEY"))
ai_model = genai.GenerativeModel('gemini-pro')

# Define the lists of websites by category
WEBSITES = {
    'technology': [
        'https://www.medianama.com/',
        'https://www.news18.com/technology/',
        'https://www.theverge.com/tech',
        'https://www.cnet.com/tech/',
        'https://www.techcrunch.com/',
        'https://www.wired.com/',
    ],
    'sports': [
        'https://www.news18.com/sports/',
        'https://www.indianexpress.com/sports/',
        'https://www.espn.com/',
        'https://www.skysports.com/',
        'https://www.bbc.com/sport',
    ],
    'entertainment': [
        'https://www.radioandmusic.com/',
        'https://www.news18.com/movies/',
        'https://www.news18.com/entertainment/',
        'https://variety.com/',
        'https://www.ew.com/',
    ],
    'politics': [
        'https://www.washingtonpost.com/politics/',
        'https://www.news18.com/politics/',
        'https://www.msnbc.com/',
        'https://www.politico.com/',
        'https://www.theguardian.com/us-news/us-politics',
    ],
    'science': [
        'https://www.scientificamerican.com/',
        'https://www.sciencenews.org/',
        'https://www.livescience.com/',
        'https://www.nationalgeographic.com/science',
        'https://www.sciencedaily.com/',
    ]
}

MAX_ARTICLES_PER_CATEGORY = 2  # Number of articles to fetch per category
ARTICLES_TO_SAVE_PER_CATEGORY = 1 # Number of articles to save per category

class AIContentProcessor:
    @staticmethod
    def generate_ai_content(title, content):
        prompt = f"""
        Given the following article title and raw content, please perform the following tasks:
        1. Clean and format the content, removing any irrelevant information or ads.
        2. STRICTLY verify this is a proper news article (reject contact pages, galleries, about us, etc.)
        3. Ensure the content is strictly relevant to its category and is newsworthy.
        4. Remove any special characters, formatting issues, or unprofessional elements.
        5. Return the processed content in a JSON format with the following structure:
        {{
            "title": "cleaned and formatted title",
            "content": "cleaned, formatted, and summarized content (max 500 words)",
            "keywords": ["list", "of", "relevant", "keywords"],
            "is_valid": true/false,
            "reason": "explanation if the article is not valid"
        }}

        IMPORTANT: Reject articles that:
        - Are not proper news articles (e.g., contact pages, galleries, etc.)
        - Contain unprofessional formatting or special characters
        - Are not pure English content
        - Don't provide substantial news value
        - Have poor formatting or structure

        Title: {title}

        Raw Content:
        {content}

        Please process and return the JSON response without any code block markers.
        """

        try:
            logger.debug(f"Generating AI content for title: {title}")
            response = ai_model.generate_content(prompt)
            
            if not response.parts:
                logger.warning(f"AI response empty for title: {title}")
                return None
            
            response_text = response.text
            logger.debug(f"AI response received: {response_text[:500]}...")  # Log first 500 chars of response
            return AIContentProcessor.parse_ai_response(response_text, title)
        except Exception as e:
            logger.error(f"Error generating AI content: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def parse_ai_response(response_text, original_title):
        try:
            logger.debug("Parsing AI response")
            cleaned_text = AIContentProcessor._clean_response_text(response_text)
            
            # Try parsing as JSON
            try:
                parsed_json = json.loads(cleaned_text)
                logger.debug(f"Successfully parsed JSON: {parsed_json.keys()}")
                return AIContentProcessor.clean_and_structure_json(parsed_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse AI response as JSON. Error: {str(e)}")
                logger.warning("Full response:")
                logger.warning(cleaned_text)
                logger.warning("Attempting to structure the raw text.")
                return AIContentProcessor.structure_raw_text(cleaned_text, original_title)
        except Exception as e:
            logger.error(f"Error parsing AI response: {str(e)}")
            logger.error(f"Original response: {response_text[:1000]}...")  # Log first 1000 chars
            return AIContentProcessor.fallback_structure(original_title, response_text)

    @staticmethod
    def _clean_response_text(text):
        # Remove code block markers and leading/trailing whitespace
        cleaned = re.sub(r'^```\s*json\s*|\s*```$', '', text.strip(), flags=re.IGNORECASE | re.MULTILINE)
        # Remove any non-printable characters except newlines
        cleaned = ''.join(char for char in cleaned if char.isprintable() or char in ['\n', '\r'])
        # Replace newlines within JSON string values
        cleaned = re.sub(r'(?<=": ").*?(?=")', lambda m: m.group().replace('\n', ' '), cleaned, flags=re.DOTALL)
        return cleaned

    @staticmethod
    def clean_and_structure_json(data):
        if isinstance(data, dict):
            return {AIContentProcessor._clean_key(k): AIContentProcessor.clean_and_structure_json(v) 
                    for k, v in data.items() if v is not None and v != ""}
        elif isinstance(data, list):
            return [AIContentProcessor.clean_and_structure_json(item) 
                    for item in data if item is not None and item != ""]
        elif isinstance(data, str):
            return AIContentProcessor._clean_text(data)
        else:
            return data

    @staticmethod
    def _clean_key(key):
        cleaned_key = ''.join(c.lower() if c.isalnum() else '_' for c in key)
        return '_'.join(word for word in cleaned_key.split('_') if word)

    @staticmethod
    def _clean_text(text):
        cleaned = text.replace('\\n', ' ').replace('\\', '').strip()
        return ' '.join(cleaned.split())

    @staticmethod
    def structure_raw_text(text, original_title):
        logger.debug("Structuring raw text")
        try:
            # Enhanced error handling for JSON parsing
            try:
                data = json.loads(text)
                # Validate required fields
                if not all(key in data for key in ['title', 'content', 'is_valid']):
                    raise ValueError("Missing required fields in JSON")
                return data
            except (json.JSONDecodeError, ValueError):
                # If JSON parsing fails, attempt structured text parsing
                return AIContentProcessor._parse_structured_text(text, original_title)
        except Exception as e:
            logger.error(f"Error in structure_raw_text: {str(e)}")
            return None

    @staticmethod
    def _parse_structured_text(text, original_title):
        lines = text.split('\n')
        data = {'title': original_title, 'content': '', 'keywords': [], 'is_valid': False, 'reason': ''}
        
        # Enhanced parsing logic
        try:
            current_section = None
            content_buffer = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check for section headers
                if ':' in line:
                    header, value = line.split(':', 1)
                    header = header.lower().strip()
                    value = value.strip()
                    
                    if header == 'title':
                        data['title'] = value or original_title
                        current_section = 'title'
                    elif header == 'content':
                        current_section = 'content'
                        if value:
                            content_buffer.append(value)
                    elif header == 'keywords':
                        current_section = 'keywords'
                        if value:
                            data['keywords'] = [k.strip() for k in value.split(',') if k.strip()]
                    elif header == 'is_valid':
                        data['is_valid'] = value.lower() == 'true'
                    elif header == 'reason':
                        data['reason'] = value
                elif current_section == 'content':
                    content_buffer.append(line)
                elif current_section == 'keywords' and line.startswith('-'):
                    data['keywords'].append(line[1:].strip())

            # Join content with proper spacing
            data['content'] = ' '.join(content_buffer).strip()
            
            # Validation checks
            if len(data['content']) < 100:  # Minimum content length
                data['is_valid'] = False
                data['reason'] = 'Content too short or parsing failed'
                return None
                
            # Check for special characters and formatting issues
            if re.search(r'[\x00-\x1F\x7F-\x9F]|[\*]{2,}|\\n', data['content']):
                data['is_valid'] = False
                data['reason'] = 'Contains invalid characters or formatting'
                return None

            return data
        except Exception as e:
            logger.error(f"Error parsing structured text: {str(e)}")
            return None

    @staticmethod
    def fallback_structure(original_title, text):
        logger.warning("Using fallback structure due to parsing failure")
        return {
            'title': original_title,
            'content': AIContentProcessor._clean_text(text)[:500],  # Limit to 500 characters
            'keywords': ["general"],
            'is_valid': True,
            'reason': ''
        }

def retry_with_backoff(retries=2, backoff_factor=0.3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_number = 0
            while retry_number < retries:
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    wait = backoff_factor * (2 ** retry_number)
                    logger.warning(f"Request failed. Retrying in {wait:.2f} seconds...")
                    time.sleep(wait)
                    retry_number += 1
            logger.error("Max retries reached. Request failed.")
            return None
        return wrapper
    return decorator

@retry_with_backoff()
def make_request(session, url):
    return session.get(url, timeout=30, verify=False)

def clean_text(text):
    if not isinstance(text, str):
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    text = soup.get_text()
    text = ' '.join(text.split())
    return text

def extract_content(article_soup, url):
    content = ""
    for elem in article_soup.find_all(['p', 'h2', 'h3', 'h4']):
        if not elem.find(['script', 'style']):
            text = elem.get_text(strip=True)
            if len(text) > 20:
                content += text + " "
    return content.strip()

def extract_media(article_soup, base_url):
    media_selectors = [
        ('meta', {'property': 'og:image'}),
        ('meta', {'itemprop': 'image'}),
        ('img', {'class': 'featured-image'})
    ]
    for tag, attrs in media_selectors:
        media_elem = article_soup.find(tag, attrs)
        if media_elem:
            media_url = media_elem.get('content') or media_elem.get('src')
            if media_url:
                return urljoin(base_url, media_url)
    return None

def is_english_content(text):
    try:
        return langdetect.detect(text) == 'en'
    except:
        return False

def fetch_articles_from_page(session, category, page_url):
    articles = []
    try:
        logger.info(f"Fetching articles from: {page_url}")
        response = make_request(session, page_url)
        if response:
            page_soup = BeautifulSoup(response.text, 'lxml')
            article_links = set(
                urljoin(page_url, a['href'])
                for a in page_soup.find_all('a', href=True)
                if a['href'].startswith(('http', 'https')) or a['href'].startswith('/')
            )
            
            for link in article_links:
                if len(articles) >= MAX_ARTICLES_PER_CATEGORY:
                    break
                try:
                    article_response = make_request(session, link)
                    if article_response:
                        article_soup = BeautifulSoup(article_response.text, 'lxml')
                        title_tag = article_soup.find('title') or article_soup.find('h1')
                        title = clean_text(title_tag.get_text()) if title_tag else None
                        content = extract_content(article_soup, link)
                        media_url = extract_media(article_soup, link)

                        # Enhanced validation
                        if not all([title, content, media_url, is_english_content(content)]):
                            continue

                        # Check for irrelevant content patterns
                        if any(pattern in title.lower() for pattern in [
                            'contact us', 'gallery', 'about us', 'privacy policy',
                            'terms of service', 'subscribe', 'newsletter'
                        ]):
                            continue

                        processed_content = AIContentProcessor.generate_ai_content(title, content)
                        if not processed_content:
                            continue

                        if not processed_content.get('is_valid', False):
                            logger.debug(f"Article rejected: {processed_content.get('reason', 'Unknown')}")
                            continue

                        # Additional content quality checks
                        if re.search(r'[\x00-\x1F\x7F-\x9F]|[\*]{2,}|\\n', processed_content['content']):
                            continue

                        articles.append({
                            'title': processed_content['title'],
                            'content': processed_content['content'],
                            'media_url': media_url,
                            'source_url': link,
                            'category': category,
                            'keywords': ','.join(processed_content['keywords']),
                            'created_at': timezone.now(),
                            'updated_at': timezone.now()
                        })
                        
                    time.sleep(random.uniform(1, 3))
                except Exception as e:
                    logger.error(f"Error processing article link {link}: {e}")
                    continue  # Skip this article and try the next one
            
        else:
            logger.warning(f"No articles found on page: {page_url}")
    except Exception as e:
        logger.error(f"Error fetching articles from page {page_url}: {e}")
    return articles

def scrape_articles():
    session = requests.Session()
    retry = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5))
    session.mount('http://', retry)
    session.mount('https://', retry)

    total_saved = 0
    for category, urls in WEBSITES.items():
        logger.info(f"Scraping category: {category}")
        category_articles = []
        saved_for_category = 0
        
        while saved_for_category < ARTICLES_TO_SAVE_PER_CATEGORY:
            for url in urls:
                if saved_for_category >= ARTICLES_TO_SAVE_PER_CATEGORY:
                    break
                articles = fetch_articles_from_page(session, category, url)
                if articles:
                    category_articles.extend(articles)

            logger.info(f"Fetched a total of {len(category_articles)} articles for category: {category}")
            
            for article_data in category_articles:
                if saved_for_category >= ARTICLES_TO_SAVE_PER_CATEGORY:
                    break
                try:
                    _, created = Article.objects.get_or_create(
                        source_url=article_data['source_url'],
                        defaults={
                            'title': article_data['title'],
                            'content': article_data['content'],
                            'media_url': article_data['media_url'],
                            'category': article_data['category'],
                            'keywords': article_data['keywords'],
                            'created_at': article_data['created_at'],
                            'updated_at': article_data['updated_at']
                        }
                    )
                    if created:
                        logger.info(f"Article '{article_data['title']}' saved to database.")
                        saved_for_category += 1
                        total_saved += 1
                    else:
                        logger.info(f"Article '{article_data['title']}' already exists in database.")
                except Exception as e:
                    logger.error(f"Error saving article '{article_data['title']}': {e}")
            
            # Clear the category_articles list to fetch new articles if needed
            category_articles.clear()
            
            if saved_for_category < ARTICLES_TO_SAVE_PER_CATEGORY:
                logger.info(f"Not enough new articles saved for {category}. Fetching more...")
            else:
                logger.info(f"Successfully saved {ARTICLES_TO_SAVE_PER_CATEGORY} articles for {category}")

    logger.info(f"Total articles saved across all categories: {total_saved}")

if __name__ == "__main__":
    scrape_articles()