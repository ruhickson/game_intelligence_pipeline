#!/usr/bin/env python3
"""
PlayStation Store Scraper (Web Scraping Version)
Scrapes the PlayStation Store web page for game data and stores it in time-series format.
"""

import requests
import time
import random
import psycopg2
from datetime import datetime
import os
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

# Load environment variables
load_dotenv('../.Renv')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('playstation_scraper.log'),
        logging.StreamHandler()
    ]
)

BASE_URL = "https://store.playstation.com"
CATEGORY_URL = "https://store.playstation.com/en-ie/category/4cbf39e2-5749-4970-ba81-93a489e4570c/{page}"

class PlayStationStoreScraper:
    """Scrapes PlayStation Store web pages and stores data in time-series format"""
    
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    
    def connect(self):
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            logging.info("✅ Connected to Supabase database")
            return True
        except Exception as e:
            logging.error(f"❌ Error connecting to database: {str(e)}")
            return False
    
    def disconnect(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logging.info("Disconnected from database")
    
    def create_games_playstation_table(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS games_playstation (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    content_id TEXT NOT NULL,
                    change_date TIMESTAMP NOT NULL,
                    title TEXT NOT NULL,
                    price DECIMAL(10,2),
                    price_currency TEXT,
                    edition TEXT,
                    platform TEXT,
                    product_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(content_id, change_date, title)
                )
            """)
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_playstation_content_id ON games_playstation(content_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_playstation_title ON games_playstation(title)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_playstation_change_date ON games_playstation(change_date)")
            self.conn.commit()
            logging.info("✅ Created games_playstation table with time-series structure")
            return True
        except Exception as e:
            logging.error(f"❌ Error creating games_playstation table: {str(e)}")
            self.conn.rollback()
            return False
    
    def fetch_games_from_page(self, page=1):
        url = CATEGORY_URL.format(page=page)
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                logging.error(f"Failed to fetch PlayStation Store page {page}: {response.status_code}")
                return []
            soup = BeautifulSoup(response.text, 'html.parser')
            games = []
            # Each game is in an <li> with a product-tile class
            for li in soup.find_all('li', class_=re.compile('^psw-product-tile')):
                # Extract product URL
                a_tag = li.find('a', href=True)
                if not a_tag:
                    continue
                product_url = BASE_URL + a_tag['href']
                content_id = a_tag['href'].split('/')[-1]
                # Extract title
                title_tag = li.find('span', class_=re.compile('^psw-t-title'))
                title = title_tag.text.strip() if title_tag else 'Unknown'
                # Extract edition (if present)
                edition_tag = li.find('span', class_=re.compile('^psw-t-edition'))
                edition = edition_tag.text.strip() if edition_tag else ''
                # Extract platform (if present)
                platform_tag = li.find('span', class_=re.compile('^psw-t-platform'))
                platform = platform_tag.text.strip() if platform_tag else ''
                # Extract price (look for price or discounted price)
                price_tag = li.find('span', class_=re.compile('^psw-m-price__actual-value'))
                price = None
                price_currency = 'EUR'
                if price_tag:
                    price_text = price_tag.text.strip()
                    price_match = re.search(r'([€£$])([\d,.]+)', price_text)
                    if price_match:
                        price_currency = price_match.group(1)
                        price = float(price_match.group(2).replace(',', '').replace('.', '').replace(price_currency, '')) / 100
                # Fallback: look for price in another span
                if price is None:
                    price_tag = li.find('span', class_=re.compile('^psw-m-price__regular-value'))
                    if price_tag:
                        price_text = price_tag.text.strip()
                        price_match = re.search(r'([€£$])([\d,.]+)', price_text)
                        if price_match:
                            price_currency = price_match.group(1)
                            price = float(price_match.group(2).replace(',', '').replace('.', '').replace(price_currency, '')) / 100
                # If still no price, set to 0
                if price is None:
                    price = 0.0
                games.append({
                    'content_id': content_id,
                    'title': title,
                    'edition': edition,
                    'platform': platform,
                    'price': price,
                    'price_currency': price_currency,
                    'product_url': product_url
                })
            logging.info(f"Fetched {len(games)} games from page {page}")
            return games
        except Exception as e:
            logging.error(f"Error fetching games from page {page}: {str(e)}")
            return []
    
    def insert_games(self, games):
        inserted = 0
        for game in games:
            try:
                self.cursor.execute("""
                    INSERT INTO games_playstation (
                        content_id, change_date, title, price, price_currency, edition, platform, product_url
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (content_id, change_date, title) DO NOTHING
                """, (
                    game['content_id'],
                    datetime.now(),
                    game['title'],
                    game['price'],
                    game['price_currency'],
                    game['edition'],
                    game['platform'],
                    game['product_url']
                ))
                inserted += 1
            except Exception as e:
                logging.error(f"Error inserting game {game.get('title')}: {str(e)}")
                self.conn.rollback()
        self.conn.commit()
        logging.info(f"Inserted {inserted} new PlayStation games.")
        return inserted
    
    def run(self, max_pages=5):
        if not self.connect():
            return
        try:
            if not self.create_games_playstation_table():
                return
            total_inserted = 0
            for page in range(1, max_pages + 1):
                games = self.fetch_games_from_page(page)
                if not games:
                    break
                total_inserted += self.insert_games(games)
                time.sleep(random.uniform(1, 2))
            logging.info(f"🎉 Scraping completed. Total games inserted: {total_inserted}")
        finally:
            self.disconnect()

def main():
    print("🎮 PlayStation Store Scraper (Web)")
    print("=" * 50)
    print("Scraping PlayStation Store web pages with time-series structure")
    print("=" * 50)
    scraper = PlayStationStoreScraper()
    scraper.run(max_pages=5)

if __name__ == "__main__":
    main() 