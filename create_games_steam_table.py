#!/usr/bin/env python3
"""
Create games_steam table from existing games table
Stage 1: Copy games table to games_steam with new structure
"""

import psycopg2
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('../.Renv')

# Set the Supabase connection string
os.environ['SUPABASE_CONNECTION_STRING'] = 'postgresql://postgres.ymmbpcjkhikugbcyssxn:crankyCATS_31@aws-0-eu-west-1.pooler.supabase.com:6543/postgres'

class SteamGamesMigration:
    """Migrate games table to games_steam table with new structure"""
    
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Connect to Supabase database"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            print("✅ Connected to Supabase database")
            return True
        except Exception as e:
            print(f"❌ Error connecting to database: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from database"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("Disconnected from database")
    
    def create_games_steam_table(self):
        """Create the games_steam table with the new structure"""
        try:
            # Drop existing table if it exists
            self.cursor.execute("DROP TABLE IF EXISTS games_steam")
            
            # Create the new games_steam table
            self.cursor.execute("""
                CREATE TABLE games_steam (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id INTEGER NOT NULL,
                    change_date TIMESTAMP NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT,
                    required_age INTEGER,
                    is_free BOOLEAN,
                    detailed_description TEXT,
                    short_description TEXT,
                    supported_languages JSONB,
                    header_image TEXT,
                    website TEXT,
                    developers JSONB,
                    publishers JSONB,
                    price_overview JSONB,
                    platforms JSONB,
                    metacritic INTEGER,
                    categories JSONB,
                    genres JSONB,
                    screenshots JSONB,
                    movies JSONB,
                    recommendations INTEGER,
                    release_date JSONB,
                    support_info JSONB,
                    background TEXT,
                    content_descriptors JSONB,
                    minimum_requirements JSONB,
                    recommended_requirements JSONB,
                    num_reviews INTEGER,
                    review_score INTEGER,
                    review_score_desc TEXT,
                    total_positive INTEGER,
                    total_negative INTEGER,
                    total_reviews INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(app_id, change_date, name)
                )
            """)
            
            # Create indexes for better performance
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_steam_app_id ON games_steam(app_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_steam_name ON games_steam(name)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_steam_change_date ON games_steam(change_date)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_steam_type ON games_steam(type)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_steam_is_free ON games_steam(is_free)")
            
            self.conn.commit()
            print("✅ Created games_steam table with UUID primary key and indexes")
            return True
            
        except Exception as e:
            print(f"❌ Error creating games_steam table: {str(e)}")
            self.conn.rollback()
            return False
    
    def migrate_data_from_games(self):
        """Migrate data from the existing games table to games_steam"""
        try:
            # Get current timestamp for change_date
            current_timestamp = datetime.now()
            
            # Insert data from games table to games_steam table
            self.cursor.execute("""
                INSERT INTO games_steam (
                    app_id, change_date, name, type, required_age, is_free,
                    detailed_description, short_description, supported_languages,
                    header_image, website, developers, publishers, price_overview,
                    platforms, metacritic, categories, genres, screenshots, movies,
                    recommendations, release_date, support_info, background,
                    content_descriptors, minimum_requirements, recommended_requirements,
                    num_reviews, review_score, review_score_desc, total_positive,
                    total_negative, total_reviews
                )
                SELECT 
                    app_id, %s, name, type, required_age, is_free,
                    detailed_description, short_description, 
                    CASE 
                        WHEN supported_languages IS NOT NULL AND supported_languages != '' 
                        AND supported_languages ~ '^[\[{].*[\]}]$'
                        THEN supported_languages::jsonb 
                        ELSE NULL 
                    END,
                    header_image, website,
                    CASE 
                        WHEN developers IS NOT NULL AND developers != '' 
                        AND developers ~ '^[\[{].*[\]}]$'
                        THEN developers::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN publishers IS NOT NULL AND publishers != '' 
                        AND publishers ~ '^[\[{].*[\]}]$'
                        THEN publishers::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN price_overview IS NOT NULL AND price_overview != '' 
                        AND price_overview ~ '^[\[{].*[\]}]$'
                        THEN price_overview::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN platforms IS NOT NULL AND platforms != '' 
                        AND platforms ~ '^[\[{].*[\]}]$'
                        THEN platforms::jsonb 
                        ELSE NULL 
                    END,
                    metacritic,
                    CASE 
                        WHEN categories IS NOT NULL AND categories != '' 
                        AND categories ~ '^[\[{].*[\]}]$'
                        THEN categories::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN genres IS NOT NULL AND genres != '' 
                        AND genres ~ '^[\[{].*[\]}]$'
                        THEN genres::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN screenshots IS NOT NULL AND screenshots != '' 
                        AND screenshots ~ '^[\[{].*[\]}]$'
                        THEN screenshots::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN movies IS NOT NULL AND movies != '' 
                        AND movies ~ '^[\[{].*[\]}]$'
                        THEN movies::jsonb 
                        ELSE NULL 
                    END,
                    recommendations,
                    CASE 
                        WHEN release_date IS NOT NULL AND release_date != '' 
                        AND release_date ~ '^[\[{].*[\]}]$'
                        THEN release_date::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN support_info IS NOT NULL AND support_info != '' 
                        AND support_info ~ '^[\[{].*[\]}]$'
                        THEN support_info::jsonb 
                        ELSE NULL 
                    END,
                    background,
                    CASE 
                        WHEN content_descriptors IS NOT NULL AND content_descriptors != '' 
                        AND content_descriptors ~ '^[\[{].*[\]}]$'
                        THEN content_descriptors::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN minimum_requirements IS NOT NULL AND minimum_requirements != '' 
                        AND minimum_requirements ~ '^[\[{].*[\]}]$'
                        THEN minimum_requirements::jsonb 
                        ELSE NULL 
                    END,
                    CASE 
                        WHEN recommended_requirements IS NOT NULL AND recommended_requirements != '' 
                        AND recommended_requirements ~ '^[\[{].*[\]}]$'
                        THEN recommended_requirements::jsonb 
                        ELSE NULL 
                    END,
                    num_reviews, review_score, review_score_desc, total_positive,
                    total_negative, total_reviews
                FROM games
                WHERE type = 'game'
            """, (current_timestamp,))
            
            migrated_count = self.cursor.rowcount
            self.conn.commit()
            
            print(f"✅ Successfully migrated {migrated_count} games to games_steam table")
            return migrated_count
            
        except Exception as e:
            print(f"❌ Error migrating data: {str(e)}")
            self.conn.rollback()
            return 0
    
    def verify_migration(self):
        """Verify the migration was successful"""
        try:
            # Check total count
            self.cursor.execute("SELECT COUNT(*) FROM games_steam")
            steam_count = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM games WHERE type = 'game'")
            original_count = self.cursor.fetchone()[0]
            
            print(f"📊 Migration verification:")
            print(f"   Original games (type='game'): {original_count}")
            print(f"   Migrated to games_steam: {steam_count}")
            
            if steam_count == original_count:
                print("✅ Migration successful - all games migrated")
            else:
                print(f"⚠️  Migration incomplete - {original_count - steam_count} games missing")
            
            # Check sample data
            self.cursor.execute("""
                SELECT id, app_id, change_date, name, type, is_free 
                FROM games_steam 
                LIMIT 5
            """)
            
            sample_data = self.cursor.fetchall()
            print(f"\n📋 Sample data from games_steam:")
            for row in sample_data:
                print(f"   ID: {row[0]}, App ID: {row[1]}, Name: {row[3]}, Type: {row[4]}, Free: {row[5]}")
            
            return steam_count == original_count
            
        except Exception as e:
            print(f"❌ Error verifying migration: {str(e)}")
            return False

def main():
    """Main migration function"""
    print("🔄 Starting Steam Games Migration")
    print("=" * 50)
    
    migration = SteamGamesMigration()
    
    if not migration.connect():
        return
    
    try:
        # Step 1: Create the new table structure
        print("\n📋 Step 1: Creating games_steam table...")
        if not migration.create_games_steam_table():
            print("❌ Failed to create games_steam table")
            return
        
        # Step 2: Migrate data from games table
        print("\n📋 Step 2: Migrating data from games table...")
        migrated_count = migration.migrate_data_from_games()
        
        if migrated_count == 0:
            print("❌ No data migrated")
            return
        
        # Step 3: Verify migration
        print("\n📋 Step 3: Verifying migration...")
        migration.verify_migration()
        
        print("\n🎉 Migration completed successfully!")
        print(f"📊 Total games migrated: {migrated_count}")
        
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
    finally:
        migration.disconnect()

if __name__ == "__main__":
    main() 