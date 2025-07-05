#!/usr/bin/env python3
"""
Steam Price Tracking Management CLI
Command-line interface for managing price tracking subscriptions
"""

import argparse
import sys
from steam_price_tracker import SteamPriceTracker

def add_game_to_tracking():
    """Add a game to price tracking"""
    parser = argparse.ArgumentParser(description='Add a game to price tracking')
    parser.add_argument('app_id', type=int, help='Steam App ID')
    parser.add_argument('game_name', help='Game name')
    parser.add_argument('--target-price', type=float, help='Target price for notification')
    parser.add_argument('--email', help='Notification email address')
    
    args = parser.parse_args()
    
    tracker = SteamPriceTracker()
    if tracker.connect():
        success = tracker.add_price_tracking_subscription(
            args.app_id, 
            args.game_name, 
            args.target_price, 
            args.email
        )
        if success:
            print(f"✅ Added {args.game_name} (ID: {args.app_id}) to price tracking")
        else:
            print(f"❌ Failed to add {args.game_name} to price tracking")
        tracker.disconnect()

def remove_game_from_tracking():
    """Remove a game from price tracking"""
    parser = argparse.ArgumentParser(description='Remove a game from price tracking')
    parser.add_argument('app_id', type=int, help='Steam App ID')
    
    args = parser.parse_args()
    
    tracker = SteamPriceTracker()
    if tracker.connect():
        success = tracker.remove_price_tracking_subscription(args.app_id)
        if success:
            print(f"✅ Removed app_id {args.app_id} from price tracking")
        else:
            print(f"❌ Failed to remove app_id {args.app_id} from price tracking")
        tracker.disconnect()

def list_tracked_games():
    """List all tracked games"""
    tracker = SteamPriceTracker()
    if tracker.connect():
        try:
            tracker.cursor.execute("""
                SELECT app_id, game_name, current_price, target_price, is_active, last_checked
                FROM price_tracking_subscriptions
                ORDER BY game_name
            """)
            
            games = tracker.cursor.fetchall()
            
            if not games:
                print("📭 No games are currently being tracked")
                return
            
            print(f"📊 Currently tracking {len(games)} games:")
            print("-" * 80)
            print(f"{'App ID':<8} {'Game Name':<30} {'Current':<8} {'Target':<8} {'Status':<8} {'Last Checked'}")
            print("-" * 80)
            
            for game in games:
                app_id, name, current_price, target_price, is_active, last_checked = game
                status = "Active" if is_active else "Inactive"
                current = f"${current_price:.2f}" if current_price else "N/A"
                target = f"${target_price:.2f}" if target_price else "N/A"
                
                print(f"{app_id:<8} {name[:29]:<30} {current:<8} {target:<8} {status:<8} {last_checked}")
            
        except Exception as e:
            print(f"❌ Error listing tracked games: {str(e)}")
        finally:
            tracker.disconnect()

def show_price_changes():
    """Show recent price changes"""
    tracker = SteamPriceTracker()
    if tracker.connect():
        try:
            tracker.cursor.execute("""
                SELECT app_id, game_name, old_price, new_price, discount_percent, created_at
                FROM price_change_notifications
                ORDER BY created_at DESC
                LIMIT 20
            """)
            
            changes = tracker.cursor.fetchall()
            
            if not changes:
                print("📭 No recent price changes found")
                return
            
            print(f"💰 Recent price changes ({len(changes)} most recent):")
            print("-" * 80)
            print(f"{'App ID':<8} {'Game Name':<25} {'Old Price':<10} {'New Price':<10} {'Discount':<10} {'Date'}")
            print("-" * 80)
            
            for change in changes:
                app_id, name, old_price, new_price, discount, created_at = change
                old = f"${old_price:.2f}" if old_price else "N/A"
                new = f"${new_price:.2f}" if new_price else "Free"
                discount_text = f"-{discount}%" if discount else "N/A"
                
                print(f"{app_id:<8} {name[:24]:<25} {old:<10} {new:<10} {discount_text:<10} {created_at}")
            
        except Exception as e:
            print(f"❌ Error showing price changes: {str(e)}")
        finally:
            tracker.disconnect()

def run_tracking_cycle():
    """Run a price tracking cycle"""
    tracker = SteamPriceTracker()
    tracker.run_price_tracking_cycle()

def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description='Steam Price Tracking Management')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a game to price tracking')
    add_parser.add_argument('app_id', type=int, help='Steam App ID')
    add_parser.add_argument('game_name', help='Game name')
    add_parser.add_argument('--target-price', type=float, help='Target price for notification')
    add_parser.add_argument('--email', help='Notification email address')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a game from price tracking')
    remove_parser.add_argument('app_id', type=int, help='Steam App ID')
    
    # List command
    subparsers.add_parser('list', help='List all tracked games')
    
    # Changes command
    subparsers.add_parser('changes', help='Show recent price changes')
    
    # Run command
    subparsers.add_parser('run', help='Run a price tracking cycle')
    
    # Summary command
    subparsers.add_parser('summary', help='Show tracking summary')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    tracker = SteamPriceTracker()
    
    if args.command == 'add':
        if tracker.connect():
            success = tracker.add_price_tracking_subscription(
                args.app_id, 
                args.game_name, 
                args.target_price, 
                args.email
            )
            if success:
                print(f"✅ Added {args.game_name} (ID: {args.app_id}) to price tracking")
            else:
                print(f"❌ Failed to add {args.game_name} to price tracking")
            tracker.disconnect()
    
    elif args.command == 'remove':
        if tracker.connect():
            success = tracker.remove_price_tracking_subscription(args.app_id)
            if success:
                print(f"✅ Removed app_id {args.app_id} from price tracking")
            else:
                print(f"❌ Failed to remove app_id {args.app_id} from price tracking")
            tracker.disconnect()
    
    elif args.command == 'list':
        list_tracked_games()
    
    elif args.command == 'changes':
        show_price_changes()
    
    elif args.command == 'run':
        run_tracking_cycle()
    
    elif args.command == 'summary':
        if tracker.connect():
            summary = tracker.get_tracking_summary()
            print("📊 Price Tracking Summary:")
            print(f"  Total subscriptions: {summary.get('total_subscriptions', 0)}")
            print(f"  Active subscriptions: {summary.get('active_subscriptions', 0)}")
            print(f"  Target prices set: {summary.get('target_price_set', 0)}")
            print(f"  Free games: {summary.get('free_games', 0)}")
            tracker.disconnect()

if __name__ == "__main__":
    main() 