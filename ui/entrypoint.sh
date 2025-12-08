#!/bin/sh
# Génère config.js avec l'URL de l'API

cat > /usr/share/nginx/html/config.js << EOF
window.CONFIG = {
    API_URL: "${API_URL:-http://localhost:8007}"
};
EOF

echo "Config: API_URL = ${API_URL:-http://localhost:8007}"

# Lance Nginx
exec nginx -g 'daemon off;'
