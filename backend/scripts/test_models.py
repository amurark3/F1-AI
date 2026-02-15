import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load your .env file
load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("❌ Error: GOOGLE_API_KEY not found in .env")
else:
    print(f"✅ Found API Key: {api_key[:5]}...")
    
    # Configure the library
    genai.configure(api_key=api_key)

    print("\n🔍 Listing available models for this key...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"   - {m.name}")
    except Exception as e:
        print(f"❌ Error listing models: {e}")