#!/usr/bin/env python3
"""
Steam Price Tracking System
Monitors specific games for price changes and sends notifications
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

# Load environment variables
load_dotenv('../.Renv')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('steam_price_tracker.log'),
        logging.StreamHandler()
    ]
)

class SteamPriceTracker:
    """Tracks Steam game prices and sends notifications on changes"""
    
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
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
    
    def create_price_tracking_tables(self):
        """Create tables for price tracking"""
        try:
            # Create price tracking subscriptions table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_tracking_subscriptions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    current_price DECIMAL(10,2),
                    target_price DECIMAL(10,2),
                    is_active BOOLEAN DEFAULT TRUE,
                    notification_email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(app_id)
                )
            """)
            
            # Create price change notifications table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_change_notifications (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    old_price DECIMAL(10,2),
                    new_price DECIMAL(10,2),
                    discount_percent INTEGER,
                    notification_sent BOOLEAN DEFAULT FALSE,
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_tracking_app_id ON price_tracking_subscriptions(app_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_tracking_active ON price_tracking_subscriptions(is_active)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_notifications_app_id ON price_change_notifications(app_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_notifications_sent ON price_change_notifications(notification_sent)")
            
            self.conn.commit()
            logging.info("✅ Created price tracking tables and indexes")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error creating price tracking tables: {str(e)}")
            self.conn.rollback()
            return False
    
    def add_price_tracking_subscription(self, app_id, game_name, target_price=None, notification_email=None):
        """Add a game to price tracking"""
        try:
            # Get current price from Steam
            current_price = self.get_current_steam_price(app_id)
            
            self.cursor.execute("""
                INSERT INTO price_tracking_subscriptions (
                    app_id, game_name, current_price, target_price, notification_email
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (app_id) DO UPDATE SET
                    game_name = EXCLUDED.game_name,
                    current_price = EXCLUDED.current_price,
                    target_price = EXCLUDED.target_price,
                    notification_email = EXCLUDED.notification_email,
                    last_checked = CURRENT_TIMESTAMP
            """, (app_id, game_name, current_price, target_price, notification_email))
            
            self.conn.commit()
            logging.info(f"✅ Added {game_name} (ID: {app_id}) to price tracking")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error adding price tracking subscription: {str(e)}")
            self.conn.rollback()
            return False
    
    def remove_price_tracking_subscription(self, app_id):
        """Remove a game from price tracking"""
        try:
            self.cursor.execute("""
                UPDATE price_tracking_subscriptions 
                SET is_active = FALSE 
                WHERE app_id = %s
            """, (app_id,))
            
            if self.cursor.rowcount > 0:
                self.conn.commit()
                logging.info(f"✅ Removed app_id {app_id} from price tracking")
                return True
            else:
                logging.warning(f"⚠️  No subscription found for app_id {app_id}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error removing price tracking subscription: {str(e)}")
            self.conn.rollback()
            return False
    
    def get_current_steam_price(self, app_id):
        """Get current price from Steam API"""
        try:
            # Add delay to be respectful
            time.sleep(random.uniform(0.3, 0.6))
            
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 429:
                logging.warning(f"Rate limited for app_id {app_id}, waiting 2 minutes...")
                time.sleep(120)
                return self.get_current_steam_price(app_id)
            
            if response.status_code != 200:
                logging.error(f"Failed to get price for app_id {app_id}: {response.status_code}")
                return None
            
            data = response.json()
            if str(app_id) in data and data[str(app_id)]['success']:
                game_data = data[str(app_id)]['data']
                
                # Check if game is free
                if game_data.get('is_free', False):
                    return 0.0
                
                # Get price from price_overview
                price_overview = game_data.get('price_overview', {})
                if price_overview:
                    final_price = price_overview.get('final', 0)
                    return final_price / 100  # Convert cents to dollars
                
                return None
            else:
                logging.warning(f"No price data available for app_id {app_id}")
                return None
                
        except Exception as e:
            logging.error(f"Error getting Steam price for app_id {app_id}: {str(e)}")
            return None
    
    def check_price_changes(self):
        """Check for price changes in tracked games"""
        try:
            # Get all active subscriptions
            self.cursor.execute("""
                SELECT app_id, game_name, current_price, target_price, notification_email
                FROM price_tracking_subscriptions 
                WHERE is_active = TRUE
            """)
            
            subscriptions = self.cursor.fetchall()
            logging.info(f"📊 Checking {len(subscriptions)} active price tracking subscriptions")
            
            price_changes = []
            
            for subscription in subscriptions:
                app_id, game_name, current_price, target_price, notification_email = subscription
                
                # Get new price from Steam
                new_price = self.get_current_steam_price(app_id)
                
                if new_price is not None and current_price != new_price:
                    # Calculate discount percentage
                    discount_percent = None
                    if current_price and new_price < current_price:
                        discount_percent = int(((current_price - new_price) / current_price) * 100)
                    
                    # Record price change
                    self.cursor.execute("""
                        INSERT INTO price_change_notifications (
                            app_id, game_name, old_price, new_price, discount_percent
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (app_id, game_name, current_price, new_price, discount_percent))
                    
                    # Update subscription with new price
                    self.cursor.execute("""
                        UPDATE price_tracking_subscriptions 
                        SET current_price = %s, last_checked = CURRENT_TIMESTAMP
                        WHERE app_id = %s
                    """, (new_price, app_id))
                    
                    price_changes.append({
                        'app_id': app_id,
                        'game_name': game_name,
                        'old_price': current_price,
                        'new_price': new_price,
                        'discount_percent': discount_percent,
                        'notification_email': notification_email
                    })
                    
                    logging.info(f"💰 Price change detected for {game_name}: ${current_price} → ${new_price}")
                    
                    # Check if target price is met
                    if target_price and new_price <= target_price:
                        logging.info(f"🎯 Target price reached for {game_name}: ${new_price} <= ${target_price}")
                
                # Small delay between requests
                time.sleep(random.uniform(0.5, 1.0))
            
            self.conn.commit()
            return price_changes
            
        except Exception as e:
            logging.error(f"❌ Error checking price changes: {str(e)}")
            self.conn.rollback()
            return []
    
    def send_price_change_notifications(self, price_changes):
        """Send email notifications for price changes"""
        if not self.email_enabled or not price_changes:
            return
        
        try:
            # Group notifications by email
            notifications_by_email = {}
            for change in price_changes:
                email = change['notification_email'] or self.notification_email
                if email:
                    if email not in notifications_by_email:
                        notifications_by_email[email] = []
                    notifications_by_email[email].append(change)
            
            # Send emails
            for email, changes in notifications_by_email.items():
                self.send_price_change_email(email, changes)
                
        except Exception as e:
            logging.error(f"❌ Error sending price change notifications: {str(e)}")
    
    def send_price_change_email(self, email, price_changes):
        """Send a single price change notification email"""
        try:
            # Create email content
            subject = f"Steam Price Changes - {len(price_changes)} game(s) updated"
            
            html_content = """
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; }
                    .game { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
                    .price-change { font-weight: bold; color: #28a745; }
                    .discount { color: #dc3545; font-weight: bold; }
                </style>
            </head>
            <body>
                <h2>🎮 Steam Price Changes Detected</h2>
                <p>The following games have had price changes:</p>
            """
            
            for change in price_changes:
                old_price = f"${change['old_price']:.2f}" if change['old_price'] else "N/A"
                new_price = f"${change['new_price']:.2f}" if change['new_price'] else "Free"
                
                discount_text = ""
                if change['discount_percent']:
                    discount_text = f"<span class='discount'>(-{change['discount_percent']}%)</span>"
                
                html_content += f"""
                <div class="game">
                    <h3>{change['game_name']}</h3>
                    <p>Price: <span class="price-change">{old_price} → {new_price}</span> {discount_text}</p>
                    <p>Steam ID: {change['app_id']}</p>
                    <p><a href="https://store.steampowered.com/app/{change['app_id']}">View on Steam</a></p>
                </div>
                """
            
            html_content += """
            </body>
            </html>
            """
            
            # Send email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = email
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logging.info(f"✅ Sent price change notification to {email}")
            
            # Mark notifications as sent
            for change in price_changes:
                self.cursor.execute("""
                    UPDATE price_change_notifications 
                    SET notification_sent = TRUE, sent_at = CURRENT_TIMESTAMP
                    WHERE app_id = %s AND created_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
                """, (change['app_id'],))
            
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"❌ Error sending email to {email}: {str(e)}")
    
    def get_tracking_summary(self):
        """Get summary of price tracking subscriptions"""
        try:
            self.cursor.execute("""
                SELECT 
                    COUNT(*) as total_subscriptions,
                    COUNT(CASE WHEN is_active THEN 1 END) as active_subscriptions,
                    COUNT(CASE WHEN target_price IS NOT NULL THEN 1 END) as target_price_set,
                    COUNT(CASE WHEN current_price = 0 THEN 1 END) as free_games
                FROM price_tracking_subscriptions
            """)
            
            summary = self.cursor.fetchone()
            return {
                'total_subscriptions': summary[0],
                'active_subscriptions': summary[1],
                'target_price_set': summary[2],
                'free_games': summary[3]
            }
            
        except Exception as e:
            logging.error(f"Error getting tracking summary: {str(e)}")
            return {}
    
    def run_price_tracking_cycle(self, check_interval_hours=6):
        """Run a complete price tracking cycle"""
        if not self.connect():
            return
        
        try:
            # Create tables if they don't exist
            if not self.create_price_tracking_tables():
                return
            
            # Get summary
            summary = self.get_tracking_summary()
            logging.info(f"📊 Price tracking summary: {summary}")
            
            # Check for price changes
            logging.info("🔄 Starting price change check...")
            price_changes = self.check_price_changes()
            
            if price_changes:
                logging.info(f"💰 Found {len(price_changes)} price changes")
                self.send_price_change_notifications(price_changes)
            else:
                logging.info("✅ No price changes detected")
            
            logging.info(f"✅ Price tracking cycle completed. Next check in {check_interval_hours} hours")
            
        except Exception as e:
            logging.error(f"❌ Error during price tracking cycle: {str(e)}")
        finally:
            self.disconnect()

def main():
    """Main function for price tracking"""
    print("🎮 Steam Price Tracking System")
    print("=" * 50)
    
    tracker = SteamPriceTracker()
    
    # Example: Add some games to track
    # tracker.add_price_tracking_subscription(730, "Counter-Strike 2", 15.00)
    # tracker.add_price_tracking_subscription(570, "Dota 2", 0.00)
    
    # Run tracking cycle
    tracker.run_price_tracking_cycle()

if __name__ == "__main__":
    main() 