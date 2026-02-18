
import os
import datetime
import sys

# Ensure we can import from agent
sys.path.append(os.getcwd())

from agent.config import Config
from agent.tools import Toolkit

def cleanup_storage(dry_run=True, older_than_days=30):
    print("--- Google Drive Storage Cleanup ---")
    
    try:
        config = Config()
        toolkit = Toolkit(config)
        
        # 1. Check Quota
        print("Checking current quota...")
        quota = toolkit.sheets.check_quota()
        usage = int(quota.get('usage', 0))
        limit = int(quota.get('limit', -1))
        
        print(f"Storage Usage: {usage/1024/1024:.2f} MB")
        if limit > 0:
            print(f"Storage Limit: {limit/1024/1024:.2f} MB")
            print(f"Percent Used: {usage/limit*100:.1f}%")
        
        # 2. List Files
        print(f"\nScanning for files older than {older_than_days} days...")
        files = toolkit.sheets.list_files(page_size=100)
        
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=older_than_days)
        
        files_to_process = []
        for f in files:
            try:
                # API returns '2025-01-21T12:00:00.000Z'
                created_time = datetime.datetime.fromisoformat(f['createdTime'].replace('Z', '+00:00'))
                if created_time < cutoff_date:
                    files_to_process.append(f)
            except:
                continue
        
        # Sort oldest first
        files_to_process.sort(key=lambda x: x.get('createdTime', ''))
        
        if not files_to_process:
            print("No old files found to cleanup.")
            return

        print(f"\nFound {len(files_to_process)} potentially deletable files:")
        for f in files_to_process:
            print(f" - {f.get('name')} (ID: {f.get('id')}) [Created: {f.get('createdTime')}]")
            
        if dry_run:
            print(f"\n[DRY RUN] No files were deleted. To delete these files, set dry_run=False.")
            print(f"Expected recovery: ~{len(files_to_process) * 5 / 1024:.2f} MB (Estimated)")
        else:
            print("\nDeleting files...")
            count = 0
            for f in files_to_process:
                try:
                    toolkit.sheets.delete_file(f['id'])
                    print(f"✅ Deleted: {f.get('name')}")
                    count += 1
                except Exception as e:
                    print(f"❌ Failed to delete {f.get('name')}: {e}")
            print(f"\nCleanup complete. Deleted {count} files.")
            
            # Re-check
            q2 = toolkit.sheets.check_quota()
            u2 = int(q2.get('usage', 0))
            print(f"New Usage: {u2/1024/1024:.2f} MB")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Default to Dry Run
    cleanup_storage(dry_run=True, older_than_days=30)
