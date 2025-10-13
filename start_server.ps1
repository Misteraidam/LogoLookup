# Start your Flask app using Waitress
Write-Host "🚀 Starting Logo Preview Editor on Waitress..."
Start-Process powershell -ArgumentList "python run_server.py"

Start-Sleep -Seconds 5  # wait a few seconds for Flask to start

# Create a public Cloudflare Tunnel
Write-Host "🌍 Opening Cloudflare Tunnel..."
cloudflared tunnel --url http://127.0.0.1:5000
