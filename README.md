# Steam to Supabase Pipeline

This pipeline automatically fetches new Steam games data and loads it directly into your Supabase database, including user tags for each game.

## Scripts Overview

### 1. `steam_to_supabase_pipeline.py` - Main Data Pipeline
Fetches new games and their tags from Steam API and loads them into Supabase.

### 2. `update_recent_reviews.py` - Review Data Updates
Updates review statistics for recently released games to keep data current.

### 3. `recreate_top_line_metrics.py` - Analytics Table Recreation
Recreates the top_line_metrics table used by Cube.js and your Shiny app for analytics.

## Features

- **Incremental Updates**: Automatically detects the last processed app_id and continues from there
- **Direct Supabase Integration**: Loads data directly into your Supabase PostgreSQL database
- **Tag Collection**: Fetches user tags from Steam store pages for each game
- **Review Updates**: Keeps review data current for recent releases
- **Analytics Tables**: Recreates materialized tables for fast analytics queries
- **Rate Limiting**: Built-in delays to respect Steam API rate limits
- **Error Handling**: Robust error handling with retry logic for API failures
- **Progress Tracking**: Real-time progress updates and statistics
- **Data Validation**: Filters out non-game content (DLC, software, etc.)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. The script uses your existing Supabase connection string (hardcoded for now)

3. The script uses your existing Steam API key

## Usage

### Main Pipeline (New Games + Tags)

#### Basic Usage (Auto-resume from last app_id with tags)
```bash
python steam_to_supabase_pipeline.py
```

#### Start from a specific app_id
Edit the script and set:
```python
START_APP_ID = 123456  # Replace with your desired app_id
```

#### Limit the number of games to process
Edit the script and set:
```python
LIMIT = 100  # Process only 100 games
```

#### Skip tag collection (faster processing)
Edit the script and set:
```python
FETCH_TAGS = False  # Skip tag collection
```

### Recent Reviews Update

#### Update reviews for games released in the past 30 days
```bash
python update_recent_reviews.py
```

#### Customize the time period
Edit the script and set:
```python
DAYS_BACK = 60  # Look back 60 days instead of 30
```

#### Limit the number of games to update
Edit the script and set:
```python
LIMIT = 50  # Update only 50 recent games
```

### Analytics Table Recreation

#### Recreate the top_line_metrics table
```bash
python recreate_top_line_metrics.py
```

This script will:
1. Drop the existing top_line_metrics table
2. Create a new table with proper structure
3. Populate it with aggregated data from your games table
4. Verify the data and show sample results

## What Each Script Does

### Main Pipeline (`steam_to_supabase_pipeline.py`)

1. **Connects to Supabase**: Uses your existing connection string
2. **Gets the highest app_id**: Queries your games table to find the last processed game
3. **Fetches Steam app list**: Gets the complete list of all Steam apps
4. **Filters new games**: Only processes games with app_id higher than the last one
5. **Fetches game details**: Gets comprehensive game information from Steam API
6. **Fetches review data**: Gets review scores and statistics
7. **Fetches user tags**: Scrapes user tags from Steam store pages
8. **Inserts into Supabase**: Loads all data directly into your games table
9. **Inserts tags**: Loads tags into the game_tags table
10. **Updates price history**: Also inserts price information if available

### Recent Reviews Update (`update_recent_reviews.py`)

1. **Connects to Supabase**: Uses your existing connection string
2. **Queries recent games**: Finds games with `release_date_actual` within the specified time period
3. **Fetches updated reviews**: Gets current review data from Steam API for each recent game
4. **Updates database**: Overwrites review fields in the games table
5. **Tracks progress**: Shows update statistics and progress

### Analytics Table Recreation (`recreate_top_line_metrics.py`)

1. **Connects to Supabase**: Uses your existing connection string
2. **Drops existing table**: Removes the old top_line_metrics table
3. **Creates new table**: Builds table with proper structure and indexes
4. **Aggregates data**: Groups games by review_score_desc and calculates metrics
5. **Populates table**: Inserts aggregated data for analytics
6. **Verifies data**: Shows sample results and statistics

## Data Structure

The pipeline loads the following data into your Supabase database:

### Games Table
- Basic game info (name, type, age rating, etc.)
- Descriptions and media (header image, screenshots, movies)
- Developer and publisher information
- Platform support and requirements
- Review scores and statistics
- Price information
- Categories and genres
- Release dates and support info

### Game Tags Table
- User-generated tags for each game
- Links to games via app_id foreign key
- Unique constraint on (app_id, tag) to prevent duplicates

### Top Line Metrics Table
- Aggregated metrics by review score description
- Number of games per review category
- Total reviews per category
- Average reviews per game per category
- Optimized for fast analytics queries

## Review Data Fields Updated

The recent reviews script updates these specific fields:
- `num_reviews`: Total number of reviews
- `review_score`: Numerical review score
- `review_score_desc`: Review score description (e.g., "Very Positive")
- `total_positive`: Number of positive reviews
- `total_negative`: Number of negative reviews
- `total_reviews`: Total review count
- `last_updated`: Timestamp of the update

## Tag Collection Details

The pipeline fetches user tags by:
1. **Scraping Steam store pages**: Visits each game's store page
2. **Extracting tag data**: Uses regex to find tag information in the HTML
3. **Rate limiting**: Adds delays between requests to respect Steam's limits
4. **Error handling**: Gracefully handles network issues and missing tags
5. **Batch insertion**: Efficiently inserts tags using PostgreSQL's executemany

## Analytics Table Structure

The top_line_metrics table contains:
- `review_score_desc`: Review category (e.g., "Very Positive", "Mixed")
- `num_games`: Number of games in this category
- `num_reviews`: Total reviews across all games in this category
- `avg_num_reviews`: Average reviews per game in this category
- `created_at` / `updated_at`: Timestamps for tracking

## Monitoring

The scripts provide detailed logging:
- ✅ Success messages
- ❌ Error messages  
- ⏭️ Skip messages (for non-games)
- 🏷️ Tag collection status
- 📊 Progress updates every 10 games
- 📈 Final statistics including tag counts
- 🔄 Review update progress
- 🗑️ Table recreation status

## Error Handling

- **API Rate Limits**: Automatically waits 2 minutes on 429 errors
- **Connection Issues**: Graceful handling of network problems
- **Data Validation**: Skips invalid or non-game content
- **Database Errors**: Rollback on insertion failures
- **Tag Extraction**: Handles missing or malformed tag data
- **Review Updates**: Handles missing review data gracefully
- **Table Recreation**: Safe drop and recreate with verification

## Performance

- **Rate Limiting**: 0.3-0.6 second delays between API calls
- **Batch Processing**: Processes games one by one with immediate commits
- **Memory Efficient**: Doesn't load all data into memory at once
- **Tag Efficiency**: Uses executemany for bulk tag insertion
- **Conflict Handling**: Uses ON CONFLICT DO NOTHING for tags
- **Selective Updates**: Only updates review data for recent games
- **Analytics Optimization**: Pre-aggregated tables for fast queries

## Configuration Options

You can customize the pipelines by editing these variables:

### Main Pipeline
```python
START_APP_ID = None      # Auto-detect or set specific app_id
LIMIT = None            # Process all games or set a limit
FETCH_TAGS = True       # Enable/disable tag collection
```

### Recent Reviews Update
```python
DAYS_BACK = 30          # Number of days to look back
LIMIT = None            # Limit number of games to update
```

## Scheduling Recommendations

- **Main Pipeline**: Run daily or weekly to catch new games
- **Recent Reviews Update**: Run weekly to keep review data current
- **Analytics Table Recreation**: Run after major data updates
- **Tag Collection**: Can be disabled for faster processing if needed

## Next Steps

These pipelines can be extended to:
- Add scheduling (run automatically)
- Add more data sources
- Add data transformation/cleaning
- Add notifications on completion
- Add monitoring and alerting
- Add tag popularity analysis
- Add tag-based game recommendations
- Add price tracking and alerts
- Add player count monitoring
- Add more analytics tables (genres, publishers, etc.) 