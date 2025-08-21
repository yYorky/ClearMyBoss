#!/usr/bin/env python3
"""
Demo script showing the Google Docs detection fix for service accounts.

This script demonstrates the before and after behavior of the Google Drive 
document detection for service accounts.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, '/home/runner/work/ClearMyBoss/ClearMyBoss')

from unittest.mock import MagicMock

def demo_old_behavior():
    """Simulate the old broken behavior with sharedWithMe=true."""
    print("🔴 OLD BEHAVIOR (BROKEN):")
    print("Using query: mimeType='application/vnd.google-apps.document' and sharedWithMe=true and trashed=false")
    
    # This is what happened with service accounts before the fix
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": []  # Empty because sharedWithMe=true doesn't work for service accounts
    }
    
    print("Documents found: 0")
    print("❌ Service accounts cannot use sharedWithMe=true - this is why no documents were detected!\n")

def demo_new_behavior():
    """Simulate the new fixed behavior without sharedWithMe=true."""
    print("🟢 NEW BEHAVIOR (FIXED):")
    print("Using query: mimeType='application/vnd.google-apps.document' and trashed=false")
    print("Plus filtering by capabilities.canComment = true")
    
    from src.google_drive import list_all_shared_docs
    
    # Mock service with various documents
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "doc123",
                "name": "Shared Document for Review",
                "capabilities": {"canComment": True},
                "modifiedTime": "2025-08-21T16:43:24Z"
            },
            {
                "id": "doc456", 
                "name": "Document Without Access",
                "capabilities": {"canComment": False}
            }
        ]
    }
    
    docs = list_all_shared_docs(service)
    
    print(f"Documents found: {len(docs)}")
    for doc in docs:
        print(f"  - {doc['name']} (ID: {doc['id']})")
    
    print("✅ Service accounts can now detect documents shared with them!\n")

def main():
    print("=== Google Docs Detection Fix Demo ===\n")
    
    print("This demonstrates why the service account was not detecting shared Google Docs")
    print("and how the fix resolves the issue.\n")
    
    demo_old_behavior()
    demo_new_behavior()
    
    print("=== Summary ===")
    print("The issue was that 'sharedWithMe=true' doesn't work for service accounts.")
    print("The fix queries all Google Docs and filters by 'canComment' capability,")
    print("which indicates the service account has been granted access to the document.")
    print("\nWith this fix, the service account should now detect shared documents!")

if __name__ == "__main__":
    main()