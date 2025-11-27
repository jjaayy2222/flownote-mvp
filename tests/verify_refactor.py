# tests/verify_refactor.py

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("Checking imports...")

try:
    from backend.routes import conflict_routes

    print("✅ backend.routes.conflict_routes imported successfully")
except ImportError as e:
    print(f"❌ Failed to import backend.routes.conflict_routes: {e}")
    sys.exit(1)

try:
    from backend.routes import onboarding_routes

    print("✅ backend.routes.onboarding_routes imported successfully")
except ImportError as e:
    print(f"❌ Failed to import backend.routes.onboarding_routes: {e}")
    sys.exit(1)

print("All imports successful!")
