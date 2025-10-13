from waitress import serve
from logo_preview_editor import app

if __name__ == "__main__":
    print("🚀 Running Flask on production WSGI server (Waitress)...")
    serve(app, host="0.0.0.0", port=5000)
