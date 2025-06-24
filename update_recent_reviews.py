import requests
import time
import json
import random
import psycopg2
from datetime import datetime, timedelta
import os
import sys
from dotenv import load_dotenv

load_dotenv()

class SteamAPI:
    def __init__(self, api_key=None):
        if api_key is None:
            api_key = os.getenv('STEAM_API_KEY')
        self.api_key = api_key
        self.base_url = "https://api.steampowered.com"
        self.store_url = "https://store.steampowered.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_review_summary(self, app_id, retry_count=0):
        """Get review summary for a specific app."""
        try:
            # Add delay between requests (0.3-0.6 second)
            time.sleep(random.uniform(0.3, 0.6))
            url = f"https://store.steampowered.com/appreviews/{app_id}?json=1&language=all&filter=all&review_type=all&purchase_type=all"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 429:
                print(f"Received 429 Too Many Requests for app_id {app_id}. Waiting 2 minutes before retrying...")
                time.sleep(120)
                return self.get_review_summary(app_id, retry_count)
            if response.status_code != 200:
                print(f"Failed to get review summary for app_id {app_id}: {response.status_code}")
                return {}
            data = response.json()
            if data['success'] == 1:
                return {
                    'num_reviews': data['query_summary']['total_reviews'],
                    'review_score': data['query_summary']['review_score'],
                    'review_score_desc': data['query_summary']['review_score_desc'],
                    'total_positive': data['query_summary']['total_positive'],
                    'total_negative': data['query_summary']['total_negative'],
                    'total_reviews': data['query_summary']['total_reviews']
                }
            return {}
        except Exception as e:
            print(f"Error getting review summary for app_id {app_id}: {str(e)}")
            return {}

class SupabasePipeline:
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Connect to Supabase database."""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            print("✅ Connected to Supabase database")
            return True
        except Exception as e:
            print(f"❌ Error connecting to Supabase: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from Supabase database."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✅ Disconnected from Supabase database")
    
    def get_recent_games(self, days_back=30):
        """Get games released within the specified number of days."""
        try:
            # Calculate the date threshold
            threshold_date = datetime.now() - timedelta(days=days_back)
            
            # Query for games with release_date_actual within the past month
            self.cursor.execute("""
                SELECT app_id, name, release_date_actual
                FROM games 
                WHERE release_date_actual IS NOT NULL 
                AND release_date_actual >= %s
                AND type = 'game'
                ORDER BY release_date_actual DESC
            """, (threshold_date,))
            
            games = self.cursor.fetchall()
            print(f"📊 Found {len(games)} games released in the past {days_back} days")
            return games
            
        except Exception as e:
            print(f"Error getting recent games: {str(e)}")
            return []
    
    def update_game_reviews(self, app_id, review_data):
        """Update review data for a specific game."""
        try:
            self.cursor.execute("""
                UPDATE games 
                SET 
                    num_reviews = %s,
                    review_score = %s,
                    review_score_desc = %s,
                    total_positive = %s,
                    total_negative = %s,
                    total_reviews = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE app_id = %s
            """, (
                review_data.get('num_reviews'),
                review_data.get('review_score'),
                review_data.get('review_score_desc'),
                review_data.get('total_positive'),
                review_data.get('total_negative'),
                review_data.get('total_reviews'),
                app_id
            ))
            
            if self.cursor.rowcount > 0:
                self.conn.commit()
                return True
            else:
                print(f"⚠️  No rows updated for app_id {app_id}")
                return False
                
        except Exception as e:
            print(f"Error updating reviews for app_id {app_id}: {str(e)}")
            self.conn.rollback()
            return False

def update_recent_game_reviews(api_key, days_back=30, limit=None):
    """Update review data for games released in the past month."""
    steam_api = SteamAPI(api_key)
    pipeline = SupabasePipeline()
    
    # Connect to Supabase
    if not pipeline.connect():
        return
    
    try:
        print(f"🔄 Looking for games released in the past {days_back} days...")
        
        # Get recent games
        recent_games = pipeline.get_recent_games(days_back)
        
        if not recent_games:
            print("✅ No recent games found to update")
            return
        
        # Apply limit if specified
        if limit:
            recent_games = recent_games[:limit]
            print(f"📊 Limiting to {limit} games for processing")
        
        total_games = len(recent_games)
        print(f"📊 Processing {total_games} recent games")
        
        # Process games
        processed = 0
        updated = 0
        failed = 0
        
        for game in recent_games:
            app_id, name, release_date = game
            processed += 1
            
            print(f"\n🔄 Processing {processed}/{total_games}: {name} (ID: {app_id})")
            print(f"📅 Released: {release_date}")
            
            # Get updated review data
            print(f"📊 Fetching updated review data...")
            review_data = steam_api.get_review_summary(app_id)
            
            if review_data:
                print(f"📊 Review data: {json.dumps(review_data, indent=2)}")
                
                # Update the game in the database
                if pipeline.update_game_reviews(app_id, review_data):
                    print(f"✅ Successfully updated reviews for {name}")
                    updated += 1
                else:
                    print(f"❌ Failed to update reviews for {name}")
                    failed += 1
            else:
                print(f"📭 No review data available for {name}")
                failed += 1
            
            # Progress update every 5 games
            if processed % 5 == 0:
                print(f"\n📈 Progress: {processed}/{total_games} processed, {updated} updated, {failed} failed")
        
        print(f"\n🎉 Review update completed!")
        print(f"📊 Total processed: {processed}")
        print(f"✅ Successfully updated: {updated}")
        print(f"❌ Failed: {failed}")
        
    except Exception as e:
        print(f"❌ Error during review update: {str(e)}")
    finally:
        pipeline.disconnect()

if __name__ == "__main__":
    load_dotenv()
    STEAM_API_KEY = os.getenv('STEAM_API_KEY')
    DAYS_BACK = 30
    LIMIT = None
    print("🔄 Starting Recent Game Reviews Update")
    print("=" * 50)
    update_recent_game_reviews(STEAM_API_KEY, DAYS_BACK, LIMIT) 