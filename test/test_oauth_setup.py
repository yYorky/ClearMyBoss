from src.google_drive import build_drive_service
from src.google_docs import build_docs_service

def test_oauth_setup():
    try:
        print("Testing Google Drive API access...")
        drive_service = build_drive_service()
        
        # Get user info
        about = drive_service.about().get(fields="user").execute()
        print(f"✅ Authenticated as: {about.get('user', {}).get('emailAddress')}")
        
        # Test listing documents
        results = drive_service.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            fields="files(id,name,shared,capabilities)",
            pageSize=5
        ).execute()
        
        files = results.get('files', [])
        print(f"✅ Found {len(files)} Google Docs")
        
        for file in files[:3]:  # Show first 3
            print(f"  - {file.get('name')}")
            print(f"    Can Comment: {file.get('capabilities', {}).get('canComment')}")
        
        # Test Docs API
        print("\nTesting Google Docs API access...")
        docs_service = build_docs_service()
        print("✅ Docs service initialized successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_oauth_setup()
    if success:
        print("\n🎉 OAuth setup is working! You can now run your main application.")
    else:
        print("\n❌ OAuth setup failed. Check your credentials and try again.")