#!/usr/bin/env python3
"""
Efficient Steam Price Change Detection System
Uses Steam's sale APIs and third-party services to identify price changes
without scanning the entire 142k game catalog
"""

import requests
import time
import json
import random
import psycopg2
from datetime import datetime, timedelta
import os
import logging
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set, Optional

# Load environment variables
load_dotenv('../.Renv')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('efficient_price_tracker.log'),
        logging.StreamHandler()
    ]
)

class EfficientSteamPriceTracker:
    """Efficiently tracks Steam price changes using multiple data sources"""
    
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # API Keys (optional)
        self.isthereanydeal_key = os.getenv('ISTHEREANYDEAL_API_KEY')
        
        # Email configuration
        self.email_enabled = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.notification_email = os.getenv('NOTIFICATION_EMAIL')
    
    def connect(self):
        """Connect to Supabase database"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            logging.info("✅ Connected to Supabase database")
            return True
        except Exception as e:
            logging.error(f"❌ Error connecting to database: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from database"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logging.info("Disconnected from database")
    
    def create_efficient_tracking_tables(self):
        """Create tables for efficient price tracking"""
        try:
            # Create price change detection table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS steam_price_changes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    old_price DECIMAL(10,2),
                    new_price DECIMAL(10,2),
                    discount_percent INTEGER,
                    is_free BOOLEAN,
                    source TEXT NOT NULL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE,
                    notification_sent BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Create sale detection log
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS steam_sale_detection_log (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    detection_date DATE NOT NULL,
                    source TEXT NOT NULL,
                    games_found INTEGER,
                    price_changes_detected INTEGER,
                    processing_time_seconds DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_changes_app_id ON steam_price_changes(app_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_changes_detected_at ON steam_price_changes(detected_at)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_changes_processed ON steam_price_changes(processed)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_sale_detection_date ON steam_sale_detection_log(detection_date)")
            
            self.conn.commit()
            logging.info("✅ Created efficient price tracking tables")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error creating tables: {str(e)}")
            self.conn.rollback()
            return False
    
    def get_steam_featured_sales(self) -> Set[int]:
        """Get currently discounted games from Steam's featured sales API"""
        try:
            logging.info("🔍 Checking Steam featured sales...")
            
            # Steam Featured Categories API
            url = "https://store.steampowered.com/api/featuredcategories"
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code != 200:
                logging.error(f"Failed to get featured sales: {response.status_code}")
                return set()
            
            data = response.json()
            discounted_app_ids = set()
            
            # Extract app IDs from various sale categories
            if 'specials' in data:
                for item in data['specials'].get('items', []):
                    if 'id' in item:
                        discounted_app_ids.add(item['id'])
            
            if 'top_sellers' in data:
                for item in data['top_sellers'].get('items', []):
                    if 'id' in item:
                        discounted_app_ids.add(item['id'])
            
            if 'new_releases' in data:
                for item in data['new_releases'].get('items', []):
                    if 'id' in item:
                        discounted_app_ids.add(item['id'])
            
            logging.info(f"📊 Found {len(discounted_app_ids)} games in Steam featured sales")
            return discounted_app_ids
            
        except Exception as e:
            logging.error(f"Error getting Steam featured sales: {str(e)}")
            return set()
    
    def get_steam_daily_deals(self) -> Set[int]:
        """Get daily deals from Steam"""
        try:
            logging.info("🔍 Checking Steam daily deals...")
            
            url = "https://store.steampowered.com/api/featuredcategories/dailydeal"
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code != 200:
                logging.error(f"Failed to get daily deals: {response.status_code}")
                return set()
            
            data = response.json()
            daily_deal_ids = set()
            
            if 'items' in data:
                for item in data['items']:
                    if 'id' in item:
                        daily_deal_ids.add(item['id'])
            
            logging.info(f"📊 Found {len(daily_deal_ids)} daily deals")
            return daily_deal_ids
            
        except Exception as e:
            logging.error(f"Error getting daily deals: {str(e)}")
            return set()
    
    def get_steamdb_price_changes(self) -> List[Dict]:
        """Get price changes from SteamDB (if available)"""
        try:
            logging.info("🔍 Checking SteamDB for price changes...")
            
            # Note: SteamDB doesn't have a public API for bulk price changes
            # This would require scraping or using their data feeds
            # For now, we'll return empty list
            logging.info("⚠️  SteamDB API not implemented (requires scraping)")
            return []
            
        except Exception as e:
            logging.error(f"Error getting SteamDB price changes: {str(e)}")
            return []
    
    def get_isthereanydeal_price_changes(self) -> List[Dict]:
        """Get price changes from IsThereAnyDeal API"""
        if not self.isthereanydeal_key:
            logging.info("⚠️  IsThereAnyDeal API key not configured")
            return []
        
        try:
            logging.info("🔍 Checking IsThereAnyDeal for price changes...")
            
            # Get recent price changes
            url = f"https://api.isthereanydeal.com/v01/game/prices/"
            params = {
                'key': self.isthereanydeal_key,
                'country': 'US',
                'shops': 'steam'
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code != 200:
                logging.error(f"Failed to get IsThereAnyDeal data: {response.status_code}")
                return []
            
            data = response.json()
            price_changes = []
            
            # Process the response based on IsThereAnyDeal API structure
            # This would need to be adapted based on their actual API response
            
            logging.info(f"📊 Found {len(price_changes)} price changes from IsThereAnyDeal")
            return price_changes
            
        except Exception as e:
            logging.error(f"Error getting IsThereAnyDeal price changes: {str(e)}")
            return []
    
    def get_steamspy_price_changes(self) -> List[Dict]:
        """Get price changes from SteamSpy"""
        try:
            logging.info("🔍 Checking SteamSpy for price changes...")
            
            # SteamSpy doesn't have a direct price change API
            # We'd need to compare current prices with historical data
            # For now, return empty list
            logging.info("⚠️  SteamSpy price change detection not implemented")
            return []
            
        except Exception as e:
            logging.error(f"Error getting SteamSpy price changes: {str(e)}")
            return []
    
    def get_detailed_price_data(self, app_ids: Set[int]) -> List[Dict]:
        """Get detailed price data for specific app IDs"""
        price_data = []
        
        for app_id in app_ids:
            try:
                # Add delay to be respectful
                time.sleep(random.uniform(0.3, 0.6))
                
                url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code == 429:
                    logging.warning(f"Rate limited for app_id {app_id}, waiting 2 minutes...")
                    time.sleep(120)
                    continue
                
                if response.status_code != 200:
                    continue
                
                data = response.json()
                if str(app_id) in data and data[str(app_id)]['success']:
                    game_data = data[str(app_id)]['data']
                    
                    # Extract price information
                    is_free = game_data.get('is_free', False)
                    price_overview = game_data.get('price_overview', {})
                    
                    if is_free:
                        current_price = 0.0
                        discount_percent = 0
                    elif price_overview:
                        current_price = price_overview.get('final', 0) / 100
                        discount_percent = price_overview.get('discount_percent', 0)
                    else:
                        continue
                    
                    price_data.append({
                        'app_id': app_id,
                        'game_name': game_data.get('name', 'Unknown'),
                        'current_price': current_price,
                        'discount_percent': discount_percent,
                        'is_free': is_free
                    })
                
            except Exception as e:
                logging.error(f"Error getting price data for app_id {app_id}: {str(e)}")
                continue
        
        return price_data
    
    def compare_with_database_prices(self, price_data: List[Dict]) -> List[Dict]:
        """Compare current prices with database prices to detect changes"""
        price_changes = []
        
        for item in price_data:
            try:
                # Get the most recent record from games_steam table
                self.cursor.execute("""
                    SELECT price_overview, is_free
                    FROM games_steam 
                    WHERE app_id = %s
                    ORDER BY change_date DESC
                    LIMIT 1
                """, (item['app_id'],))
                
                result = self.cursor.fetchone()
                
                if result:
                    old_price_overview, old_is_free = result
                    
                    # Extract old price information
                    old_price = 0.0
                    old_discount = 0
                    
                    if old_is_free:
                        old_price = 0.0
                        old_discount = 0
                    elif old_price_overview:
                        try:
                            price_data = json.loads(old_price_overview) if isinstance(old_price_overview, str) else old_price_overview
                            old_price = price_data.get('final', 0) / 100
                            old_discount = price_data.get('discount_percent', 0)
                        except:
                            old_price = 0.0
                            old_discount = 0
                    
                    # Check if price changed
                    if (old_price != item['current_price'] or 
                        old_discount != item['discount_percent'] or
                        old_is_free != item['is_free']):
                        price_changes.append({
                            'app_id': item['app_id'],
                            'game_name': item['game_name'],
                            'old_price': old_price,
                            'new_price': item['current_price'],
                            'discount_percent': item['discount_percent'],
                            'is_free': item['is_free'],
                            'source': 'steam_api'
                        })
                
            except Exception as e:
                logging.error(f"Error comparing prices for app_id {item['app_id']}: {str(e)}")
                continue
        
        return price_changes
    
    def record_price_changes(self, price_changes: List[Dict]):
        """Record price changes to database"""
        try:
            for change in price_changes:
                self.cursor.execute("""
                    INSERT INTO steam_price_changes (
                        app_id, game_name, old_price, new_price, 
                        discount_percent, is_free, source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    change['app_id'],
                    change['game_name'],
                    change['old_price'],
                    change['new_price'],
                    change['discount_percent'],
                    change['is_free'],
                    change['source']
                ))
            
            self.conn.commit()
            logging.info(f"✅ Recorded {len(price_changes)} price changes to database")
            
        except Exception as e:
            logging.error(f"❌ Error recording price changes: {str(e)}")
            self.conn.rollback()
    
    def log_detection_results(self, source: str, games_found: int, price_changes: int, processing_time: float):
        """Log detection results for monitoring"""
        try:
            self.cursor.execute("""
                INSERT INTO steam_sale_detection_log (
                    detection_date, source, games_found, 
                    price_changes_detected, processing_time_seconds
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                datetime.now().date(),
                source,
                games_found,
                price_changes,
                processing_time
            ))
            
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"Error logging detection results: {str(e)}")
    
    def run_efficient_price_detection(self):
        """Run the complete efficient price detection process"""
        if not self.connect():
            return
        
        try:
            # Create tables if they don't exist
            if not self.create_efficient_tracking_tables():
                return
            
            start_time = time.time()
            total_price_changes = 0
            
            # 1. Get Steam featured sales
            steam_start = time.time()
            featured_sales = self.get_steam_featured_sales()
            daily_deals = self.get_steam_daily_deals()
            
            # Combine all Steam sale sources
            steam_sale_ids = featured_sales.union(daily_deals)
            steam_time = time.time() - steam_start
            
            logging.info(f"📊 Steam sales detection: {len(steam_sale_ids)} games found in {steam_time:.2f}s")
            
            # 2. Get detailed price data for sale games
            if steam_sale_ids:
                price_data = self.get_detailed_price_data(steam_sale_ids)
                price_changes = self.compare_with_database_prices(price_data)
                self.record_price_changes(price_changes)
                total_price_changes += len(price_changes)
                
                logging.info(f"💰 Steam price changes detected: {len(price_changes)}")
            
            # 3. Check third-party sources (if configured)
            if self.isthereanydeal_key:
                itad_changes = self.get_isthereanydeal_price_changes()
                if itad_changes:
                    self.record_price_changes(itad_changes)
                    total_price_changes += len(itad_changes)
                    logging.info(f"💰 IsThereAnyDeal price changes: {len(itad_changes)}")
            
            # 4. Log results
            total_time = time.time() - start_time
            self.log_detection_results(
                'efficient_tracker',
                len(steam_sale_ids),
                total_price_changes,
                total_time
            )
            
            logging.info(f"🎉 Efficient price detection completed!")
            logging.info(f"📊 Total games checked: {len(steam_sale_ids)} (vs 142k full catalog)")
            logging.info(f"💰 Total price changes detected: {total_price_changes}")
            logging.info(f"⏱️  Total processing time: {total_time:.2f}s")
            
            # 5. Send notifications if enabled
            if self.email_enabled and total_price_changes > 0:
                self.send_price_change_summary(total_price_changes, steam_sale_ids)
            
        except Exception as e:
            logging.error(f"❌ Error during efficient price detection: {str(e)}")
        finally:
            self.disconnect()
    
    def send_price_change_summary(self, price_changes_count: int, games_checked: Set[int]):
        """Send summary email of price detection results"""
        try:
            subject = f"Steam Price Detection Summary - {price_changes_count} changes detected"
            
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .summary {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                    .highlight {{ color: #28a745; font-weight: bold; }}
                </style>
            </head>
            <body>
                <h2>🎮 Steam Price Detection Summary</h2>
                
                <div class="summary">
                    <h3>Detection Results</h3>
                    <p><span class="highlight">Price changes detected:</span> {price_changes_count}</p>
                    <p><span class="highlight">Games checked:</span> {len(games_checked)} (efficient detection)</p>
                    <p><span class="highlight">Detection method:</span> Steam sale APIs + third-party sources</p>
                </div>
                
                <p>Check the database for detailed price change information.</p>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = self.notification_email
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logging.info(f"✅ Sent price detection summary to {self.notification_email}")
            
        except Exception as e:
            logging.error(f"❌ Error sending summary email: {str(e)}")
    
    def get_detection_statistics(self, days: int = 7) -> Dict:
        """Get statistics about price detection performance"""
        try:
            self.cursor.execute("""
                SELECT 
                    AVG(games_found) as avg_games_checked,
                    AVG(price_changes_detected) as avg_price_changes,
                    AVG(processing_time_seconds) as avg_processing_time,
                    COUNT(*) as total_detections
                FROM steam_sale_detection_log
                WHERE detection_date >= CURRENT_DATE - INTERVAL '%s days'
            """, (days,))
            
            result = self.cursor.fetchone()
            
            return {
                'avg_games_checked': result[0] or 0,
                'avg_price_changes': result[1] or 0,
                'avg_processing_time': result[2] or 0,
                'total_detections': result[3] or 0
            }
            
        except Exception as e:
            logging.error(f"Error getting detection statistics: {str(e)}")
            return {}

def main():
    """Main function for efficient price tracking"""
    print("🎮 Efficient Steam Price Detection System")
    print("=" * 60)
    print("Detecting price changes without scanning the entire 142k catalog!")
    print("=" * 60)
    
    tracker = EfficientSteamPriceTracker()
    tracker.run_efficient_price_detection()
    
    # Show statistics
    stats = tracker.get_detection_statistics()
    if stats:
        print(f"\n📊 Last 7 days statistics:")
        print(f"  Average games checked: {stats['avg_games_checked']:.0f}")
        print(f"  Average price changes: {stats['avg_price_changes']:.0f}")
        print(f"  Average processing time: {stats['avg_processing_time']:.2f}s")
        print(f"  Total detections: {stats['total_detections']}")

if __name__ == "__main__":
    main() 