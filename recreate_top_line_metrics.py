import psycopg2
from datetime import datetime
import sys
import os
from dotenv import load_dotenv

load_dotenv()

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
    
    def drop_top_line_metrics_table(self):
        """Drop the existing top_line_metrics table if it exists."""
        try:
            self.cursor.execute("DROP TABLE IF EXISTS top_line_metrics")
            self.conn.commit()
            print("🗑️  Dropped existing top_line_metrics table")
            return True
        except Exception as e:
            print(f"Error dropping table: {str(e)}")
            return False
    
    def create_top_line_metrics_table(self):
        """Create the top_line_metrics table with proper structure."""
        try:
            self.cursor.execute("""
                CREATE TABLE top_line_metrics (
                    id SERIAL PRIMARY KEY,
                    review_score_desc TEXT NOT NULL,
                    num_games INTEGER NOT NULL,
                    num_reviews INTEGER NOT NULL,
                    avg_num_reviews INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for better performance
            self.cursor.execute("""
                CREATE INDEX idx_top_line_metrics_review_score_desc 
                ON top_line_metrics(review_score_desc)
            """)
            
            self.conn.commit()
            print("✅ Created top_line_metrics table with proper structure")
            return True
        except Exception as e:
            print(f"Error creating table: {str(e)}")
            return False
    
    def populate_top_line_metrics(self):
        """Populate the top_line_metrics table with aggregated data from games."""
        try:
            # Clear existing data
            self.cursor.execute("DELETE FROM top_line_metrics")
            
            # Insert aggregated data by review_score_desc
            self.cursor.execute("""
                INSERT INTO top_line_metrics (
                    review_score_desc, 
                    num_games, 
                    num_reviews, 
                    avg_num_reviews
                )
                SELECT 
                    CASE WHEN lower(COALESCE(review_score_desc, '')) LIKE '%user reviews%' THEN 'Under 11 Reviews' ELSE COALESCE(review_score_desc, 'No Reviews') END as review_score_desc,
                    COUNT(*) as num_games,
                    SUM(COALESCE(total_reviews, 0)) as num_reviews,
                    CASE WHEN COUNT(*) > 0 THEN SUM(COALESCE(total_reviews, 0)) / COUNT(*) ELSE 0 END as avg_num_reviews
                FROM games 
                WHERE type = 'game' 
                AND lower(name) NOT LIKE '%playtest%'
                GROUP BY 1
                ORDER BY 2 DESC
            """)
            
            inserted_rows = self.cursor.rowcount
            self.conn.commit()
            print(f"✅ Populated top_line_metrics table with {inserted_rows} rows")
            return True
        except Exception as e:
            print(f"Error populating table: {str(e)}")
            self.conn.rollback()
            return False
    
    def verify_data(self):
        """Verify the populated data."""
        try:
            # Get total counts
            self.cursor.execute("SELECT COUNT(*) FROM top_line_metrics")
            total_metrics = self.cursor.fetchone()[0]
            
            # Get sample data
            self.cursor.execute("""
                SELECT review_score_desc, num_games, num_reviews, avg_num_reviews
                FROM top_line_metrics
                ORDER BY num_games DESC
                LIMIT 10
            """)
            sample_data = self.cursor.fetchall()
            
            print(f"\n🔍 Data Verification:")
            print(f"📊 Total metric categories: {total_metrics}")
            print(f"\n📋 Sample data:")
            for row in sample_data:
                review_desc, num_games, num_reviews, avg_reviews = row
                print(f"   {review_desc}: {num_games:,} games, {num_reviews:,} reviews, {avg_reviews} avg")
            
            return True
        except Exception as e:
            print(f"Error verifying data: {str(e)}")
            return False

def recreate_top_line_metrics():
    """Main function to recreate the top_line_metrics table."""
    pipeline = SupabasePipeline()
    
    # Connect to Supabase
    if not pipeline.connect():
        return False
    
    try:
        print("🔄 Starting top_line_metrics table recreation")
        print("=" * 50)
        
        # Step 1: Drop existing table
        if not pipeline.drop_top_line_metrics_table():
            return False
        
        # Step 2: Create new table
        if not pipeline.create_top_line_metrics_table():
            return False
        
        # Step 3: Populate with data
        if not pipeline.populate_top_line_metrics():
            return False
        
        # Step 4: Verify data
        if not pipeline.verify_data():
            return False
        
        print("\n🎉 Top line metrics table recreation completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during table recreation: {str(e)}")
        return False
    finally:
        pipeline.disconnect()

if __name__ == "__main__":
    print("🔄 Starting Top Line Metrics Table Recreation")
    print("=" * 50)
    
    success = recreate_top_line_metrics()
    
    if success:
        print("\n✅ Top line metrics table has been recreated successfully!")
        print("📊 The table is now ready for use with your Cube.js analytics and Shiny app.")
    else:
        print("\n❌ Failed to recreate top line metrics table.")
        sys.exit(1) 