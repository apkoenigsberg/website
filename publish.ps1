# Load Netlify auth token from .env and publish the site
$env:NETLIFY_AUTH_TOKEN = (Get-Content .env | Where-Object { $_ -match "^NETLIFY_AUTH_TOKEN=" }) -replace "^NETLIFY_AUTH_TOKEN=", ""
quarto publish netlify --no-prompt
