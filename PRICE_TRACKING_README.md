# Steam Price Tracking System

A comprehensive system for tracking Steam game prices and receiving notifications when prices change.

## 🎯 Overview

This system allows you to:
- **Track specific games** for price changes
- **Set target prices** and get notified when reached
- **Receive email notifications** for price drops
- **Monitor price history** and discount percentages
- **Manage subscriptions** via command-line interface

## 🏗️ Architecture

### Database Tables

1. **`price_tracking_subscriptions`** - Stores games being tracked
   - `app_id` - Steam App ID
   - `game_name` - Game name
   - `current_price` - Current price from Steam
   - `target_price` - Optional target price for notifications
   - `is_active` - Whether tracking is active
   - `notification_email` - Email for notifications

2. **`price_change_notifications`** - Records price changes
   - `app_id` - Steam App ID
   - `game_name` - Game name
   - `old_price` - Previous price
   - `new_price` - New price
   - `discount_percent` - Discount percentage
   - `notification_sent` - Whether email was sent

## 🚀 Setup

### 1. Environment Variables

Add these to your `.Renv` file:

```bash
# Database
SUPABASE_CONNECTION_STRING=your_connection_string

# Email (optional)
EMAIL_ENABLED=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
NOTIFICATION_EMAIL=your_notification_email@example.com
```

### 2. Install Dependencies

```bash
pip install requests psycopg2-binary python-dotenv
```

## 📖 Usage

### Command Line Interface

The system provides a comprehensive CLI for managing price tracking:

#### Add a Game to Tracking

```bash
python manage_price_tracking.py add 730 "Counter-Strike 2" --target-price 15.00 --email user@example.com
```

#### Remove a Game from Tracking

```bash
python manage_price_tracking.py remove 730
```

#### List All Tracked Games

```bash
python manage_price_tracking.py list
```

#### Show Recent Price Changes

```bash
python manage_price_tracking.py changes
```

#### Run a Price Tracking Cycle

```bash
python manage_price_tracking.py run
```

#### Show Tracking Summary

```bash
python manage_price_tracking.py summary
```

### Programmatic Usage

```python
from steam_price_tracker import SteamPriceTracker

# Initialize tracker
tracker = SteamPriceTracker()

# Add a game to tracking
tracker.add_price_tracking_subscription(
    app_id=730,
    game_name="Counter-Strike 2",
    target_price=15.00,
    notification_email="user@example.com"
)

# Run a tracking cycle
tracker.run_price_tracking_cycle()
```

## 🔄 How It Works

### 1. Price Monitoring Process

1. **Fetch Current Prices**: Queries Steam API for each tracked game
2. **Compare Prices**: Compares new price with stored price
3. **Record Changes**: Logs price changes to database
4. **Send Notifications**: Emails users about price changes
5. **Update Database**: Updates current prices in tracking table

### 2. Steam API Integration

- Uses Steam's public store API: `https://store.steampowered.com/api/appdetails`
- Handles rate limiting with automatic retries
- Supports free games and discounted prices
- Extracts price data from `price_overview` field

### 3. Email Notifications

- **HTML emails** with game details and price changes
- **Discount percentages** automatically calculated
- **Direct links** to Steam store pages
- **Batch notifications** for multiple price changes

## 📊 Features

### Price Tracking
- ✅ Track unlimited games
- ✅ Set target prices
- ✅ Monitor price history
- ✅ Calculate discount percentages
- ✅ Handle free games

### Notifications
- ✅ Email notifications
- ✅ HTML formatted emails
- ✅ Multiple recipient support
- ✅ Price change history
- ✅ Target price alerts

### Management
- ✅ Add/remove games
- ✅ List tracked games
- ✅ View price changes
- ✅ Summary statistics
- ✅ Command-line interface

## 🔧 Configuration

### Check Intervals

Modify the check interval in `run_price_tracking_cycle()`:

```python
tracker.run_price_tracking_cycle(check_interval_hours=6)  # Check every 6 hours
```

### Rate Limiting

The system includes built-in rate limiting:
- 0.3-0.6 second delays between requests
- 2-minute waits on 429 errors
- Respectful API usage

### Email Settings

Configure email in environment variables:
- Gmail SMTP (recommended)
- Custom SMTP servers supported
- App passwords required for Gmail

## 📈 Monitoring and Maintenance

### Logs

The system creates detailed logs:
- `steam_price_tracker.log` - Main tracking logs
- Console output for real-time monitoring

### Database Maintenance

Regular maintenance tasks:
```sql
-- Clean old notifications (older than 30 days)
DELETE FROM price_change_notifications 
WHERE created_at < NOW() - INTERVAL '30 days';

-- Update inactive subscriptions
UPDATE price_tracking_subscriptions 
SET is_active = FALSE 
WHERE last_checked < NOW() - INTERVAL '7 days';
```

### Performance Optimization

- Indexes on frequently queried columns
- Batch processing for large datasets
- Connection pooling for database efficiency

## 🚨 Troubleshooting

### Common Issues

1. **Rate Limiting**
   - System automatically handles 429 errors
   - Increases delays between requests
   - Logs rate limit events

2. **Email Failures**
   - Check SMTP settings
   - Verify app passwords for Gmail
   - Test email configuration

3. **Database Connection**
   - Verify connection string
   - Check network connectivity
   - Ensure database is accessible

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔮 Future Enhancements

### Planned Features
- [ ] Web interface for management
- [ ] Discord/Slack notifications
- [ ] Price prediction algorithms
- [ ] Regional pricing support
- [ ] Bundle tracking
- [ ] Historical price charts

### Integration Opportunities
- [ ] SteamDB API integration
- [ ] IsThereAnyDeal API
- [ ] SteamSpy data integration
- [ ] Social media notifications

## 📝 Examples

### Track Popular Games

```bash
# Add popular games with target prices
python manage_price_tracking.py add 730 "Counter-Strike 2" --target-price 15.00
python manage_price_tracking.py add 570 "Dota 2" --target-price 0.00
python manage_price_tracking.py add 1172470 "Apex Legends" --target-price 10.00
```

### Monitor Free Games

```bash
# Track games that might become free
python manage_price_tracking.py add 1245620 "Elden Ring" --target-price 0.00
```

### Automated Scheduling

Set up a cron job for regular checks:
```bash
# Check every 6 hours
0 */6 * * * cd /path/to/project && python manage_price_tracking.py run
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**Happy Price Tracking! 🎮💰** 