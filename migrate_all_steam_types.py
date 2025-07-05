#!/usr/bin/env python3
"""
Comprehensive Steam Content Type Migration
Creates separate tables for each Steam content type and migrates data accordingly
"""

import requests
import json
import time
import logging
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import uuid

# Load environment variables
load_dotenv('../.Renv')

# Set the Supabase connection string
os.environ['SUPABASE_CONNECTION_STRING'] = 'postgresql://postgres.ymmbpcjkhikugbcyssxn:crankyCATS_31@aws-0-eu-west-1.pooler.supabase.com:6543/postgres'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('steam_types_migration.log'),
        logging.StreamHandler()
    ]
)

class SteamTypesMigrator:
    """Migrator for creating separate tables for each Steam content type"""
    
    def __init__(self):
        self.connection_string = os.getenv('SUPABASE_CONNECTION_STRING')
        self.conn = None
        self.cursor = None
        
        # Define all Steam content types
        self.content_types = [
            'mod', 'music', 'dlc', 'demo', 'game', 'series', 'advertising', 'video'
        ]
        
        # Statistics
        self.migration_stats = {}
    
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
    
    def get_table_schema(self, content_type):
        """Get the table schema for a specific content type"""
        return f"""
            CREATE TABLE IF NOT EXISTS {content_type}_steam (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                app_id INTEGER NOT NULL,
                change_date TIMESTAMP NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                required_age INTEGER,
                is_free BOOLEAN,
                detailed_description TEXT,
                short_description TEXT,
                supported_languages TEXT,
                header_image TEXT,
                website TEXT,
                developers TEXT,
                publishers TEXT,
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
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app_id, change_date, name)
            )
        """
    
    def create_indexes(self, content_type):
        """Create indexes for a specific content type table"""
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_app_id ON {content_type}_steam(app_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_name ON {content_type}_steam(name)",
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_type ON {content_type}_steam(type)",
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_is_free ON {content_type}_steam(is_free)",
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_review_score ON {content_type}_steam(review_score)",
            f"CREATE INDEX IF NOT EXISTS idx_{content_type}_steam_last_updated ON {content_type}_steam(last_updated)"
        ]
        
        for index_sql in indexes:
            try:
                self.cursor.execute(index_sql)
            except Exception as e:
                logging.warning(f"Warning creating index for {content_type}: {str(e)}")
    
    def create_content_type_table(self, content_type):
        """Create table for a specific content type"""
        try:
            # Create the table
            self.cursor.execute(self.get_table_schema(content_type))
            
            # Create indexes
            self.create_indexes(content_type)
            
            self.conn.commit()
            logging.info(f"✅ Created {content_type}_steam table with indexes")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error creating {content_type}_steam table: {str(e)}")
            self.conn.rollback()
            return False
    
    def get_content_type_count(self, content_type):
        """Get count of items for a specific content type"""
        try:
            self.cursor.execute("""
                SELECT COUNT(*) FROM games WHERE type = %s
            """, (content_type,))
            
            count = self.cursor.fetchone()[0]
            return count
            
        except Exception as e:
            logging.error(f"Error getting count for {content_type}: {str(e)}")
            return 0
    
    def migrate_content_type_data(self, content_type, batch_size=1000):
        """Migrate data for a specific content type"""
        try:
            # Get total count
            total_count = self.get_content_type_count(content_type)
            logging.info(f"📊 Found {total_count:,} {content_type} items to migrate")
            
            if total_count == 0:
                logging.info(f"⏭️  No {content_type} items found, skipping")
                return 0
            
            # Migrate in batches
            offset = 0
            migrated_count = 0
            
            while offset < total_count:
                # Get batch of data
                self.cursor.execute("""
                    SELECT 
                        app_id, name, type, required_age, is_free, detailed_description,
                        short_description, supported_languages, header_image, website,
                        developers, publishers, price_overview, platforms, metacritic,
                        categories, genres, screenshots, movies, recommendations,
                        release_date, support_info, background, content_descriptors,
                        minimum_requirements, recommended_requirements,
                        num_reviews, review_score, review_score_desc,
                        total_positive, total_negative, total_reviews, last_updated
                    FROM games 
                    WHERE type = %s
                    ORDER BY app_id
                    LIMIT %s OFFSET %s
                """, (content_type, batch_size, offset))
                
                batch_data = self.cursor.fetchall()
                
                if not batch_data:
                    break
                
                # Insert batch into target table
                for row in batch_data:
                    try:
                        # Prepare the values tuple
                        values = (
                            row[0],  # app_id
                            datetime.now(),  # change_date (current timestamp)
                            row[1],  # name
                            row[2],  # type
                            row[3],  # required_age
                            row[4],  # is_free
                            row[5],  # detailed_description
                            row[6],  # short_description
                            row[7],  # supported_languages
                            row[8],  # header_image
                            row[9],  # website
                            row[10], # developers
                            row[11], # publishers
                            self.safe_json_parse(row[12]),  # price_overview
                            self.safe_json_parse(row[13]),  # platforms
                            row[14], # metacritic
                            self.safe_json_parse(row[15]),  # categories
                            self.safe_json_parse(row[16]),  # genres
                            self.safe_json_parse(row[17]),  # screenshots
                            self.safe_json_parse(row[18]),  # movies
                            row[19], # recommendations
                            self.safe_json_parse(row[20]),  # release_date
                            self.safe_json_parse(row[21]),  # support_info
                            row[22], # background
                            self.safe_json_parse(row[23]),  # content_descriptors
                            self.safe_json_parse(row[24]),  # minimum_requirements
                            self.safe_json_parse(row[25]),  # recommended_requirements
                            row[26], # num_reviews
                            row[27], # review_score
                            row[28], # review_score_desc
                            row[29], # total_positive
                            row[30], # total_negative
                            row[31], # total_reviews
                            row[32]  # last_updated
                        )
                        
                        # Create placeholders
                        placeholders = ', '.join(['%s'] * len(values))
                        
                        # Insert into target table
                        self.cursor.execute(f"""
                            INSERT INTO {content_type}_steam (
                                app_id, change_date, name, type, required_age, is_free, 
                                detailed_description, short_description, supported_languages, 
                                header_image, website, developers, publishers, price_overview, 
                                platforms, metacritic, categories, genres, screenshots, movies, 
                                recommendations, release_date, support_info, background, 
                                content_descriptors, minimum_requirements, recommended_requirements,
                                num_reviews, review_score, review_score_desc, total_positive, 
                                total_negative, total_reviews, last_updated
                            ) VALUES ({placeholders})
                            ON CONFLICT (app_id, change_date, name) DO NOTHING
                        """, values)
                        
                        migrated_count += 1
                        
                    except Exception as e:
                        logging.error(f"Error migrating {content_type} item {row[0]}: {str(e)}")
                        continue
                
                # Commit batch
                self.conn.commit()
                
                # Update progress
                offset += batch_size
                progress = min(offset, total_count) / total_count * 100
                logging.info(f"📈 {content_type} migration progress: {progress:.1f}% ({min(offset, total_count):,}/{total_count:,})")
                
                # Small delay to be respectful
                time.sleep(0.1)
            
            logging.info(f"✅ Successfully migrated {migrated_count:,} {content_type} items")
            return migrated_count
            
        except Exception as e:
            logging.error(f"❌ Error migrating {content_type} data: {str(e)}")
            self.conn.rollback()
            return 0
    
    def safe_json_parse(self, value):
        """Safely parse JSON values"""
        if value is None or value == '':
            return None
        
        # Check if it's already valid JSON
        if isinstance(value, (dict, list)):
            return value
        
        # Try to parse as JSON
        try:
            if isinstance(value, str):
                # Check if it looks like JSON
                if value.strip().startswith(('{', '[')):
                    return json.loads(value)
                else:
                    return None
            return value
        except (json.JSONDecodeError, TypeError):
            return None
    
    def get_migration_summary(self):
        """Get summary of all content types and their counts"""
        try:
            summary = {}
            
            for content_type in self.content_types:
                count = self.get_content_type_count(content_type)
                summary[content_type] = count
            
            return summary
            
        except Exception as e:
            logging.error(f"Error getting migration summary: {str(e)}")
            return {}
    
    def migrate_all_types(self):
        """Migrate all content types"""
        if not self.connect():
            return
        
        try:
            # Get initial summary
            logging.info("📊 Getting content type summary...")
            summary = self.get_migration_summary()
            
            for content_type, count in summary.items():
                logging.info(f"📋 {content_type}: {count:,} items")
            
            # Migrate each content type
            for content_type in self.content_types:
                logging.info(f"\n🔄 Starting migration for {content_type}...")
                
                # Create table
                if not self.create_content_type_table(content_type):
                    logging.error(f"Failed to create table for {content_type}, skipping")
                    continue
                
                # Migrate data
                migrated_count = self.migrate_content_type_data(content_type)
                self.migration_stats[content_type] = migrated_count
                
                logging.info(f"✅ Completed {content_type} migration: {migrated_count:,} items")
            
            # Final summary
            logging.info("\n🎉 Migration completed!")
            logging.info("📊 Final Summary:")
            for content_type, count in self.migration_stats.items():
                logging.info(f"  {content_type}_steam: {count:,} items")
            
        except Exception as e:
            logging.error(f"❌ Error during migration: {str(e)}")
        finally:
            self.disconnect()

if __name__ == "__main__":
    print("🔄 Starting Steam Content Types Migration")
    print("=" * 60)
    
    migrator = SteamTypesMigrator()
    migrator.migrate_all_types() 