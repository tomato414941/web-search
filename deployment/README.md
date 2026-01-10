# Deployment Guide

This directory contains the files needed for production deployment.

## Structure

```
deployment/
├── README.md               # This file
├── .gitignore             # Git ignore patterns
├── frontend/              # Frontend Server
│   ├── .env.example       # Environment variables template
│   └── docker-compose.yml # Docker Compose configuration
└── crawler/               # Crawler Server
    ├── .env.example       # Environment variables template
    └── docker-compose.yml # Docker Compose configuration
```

## Deployment Steps

### 1. Frontend Server

```bash
# Clone the repository
git clone https://github.com/tomato414941/web-search.git
cd web-search/deployment/frontend

# Create environment file
cp .env.example .env

# Edit environment variables (required)
nano .env

# Pull Docker image
docker pull ghcr.io/tomato414941/web-search:latest

# Start containers
docker compose up -d

# View logs
docker compose logs -f
```

### 2. Crawler Server

```bash
# Clone the repository
git clone https://github.com/tomato414941/web-search.git
cd web-search/deployment/crawler

# Create environment file
cp .env.example .env

# Configure Frontend IP address and API Key
nano .env
# FRONTEND_IP=<Frontend Server IP>
# INDEXER_API_KEY=<Same value as Frontend>

# Pull Docker image
docker pull ghcr.io/tomato414941/web-search-crawler:latest

# Start containers
docker compose up -d

# View logs
docker compose logs -f
```

## Environment Variables

See `.env.example` in each directory for detailed configuration options.

### Frontend Server

Required variables:
- `ADMIN_PASSWORD` - Admin dashboard password
- `INDEXER_API_KEY` - API key for crawler authentication
- `SESSION_SECRET` - Session encryption key
- `ALLOWED_HOSTS` - Comma-separated list of allowed hostnames

### Crawler Server

Required variables:
- `FRONTEND_IP` - Frontend Server IP address
- `INDEXER_API_KEY` - Same value as Frontend Server

## Update Procedure

```bash
# Pull latest code
git pull

# Pull latest Docker image
docker pull ghcr.io/tomato414941/web-search:latest

# Recreate containers
docker compose up -d --force-recreate
```

## Troubleshooting

### View Logs
```bash
docker compose logs -f
```

### Restart Containers
```bash
docker compose restart
```

### Complete Reset
```bash
docker compose down
docker compose up -d
```

### Check Container Status
```bash
docker compose ps
```

### Verify Environment Variables
```bash
docker compose exec frontend env | grep -E "ADMIN|API_KEY|ALLOWED"
```

## Security Considerations

- Store `.env` files securely (they are git-ignored)
- Generate strong random values for `ADMIN_PASSWORD`, `INDEXER_API_KEY`, and `SESSION_SECRET`
- Use `openssl rand -base64 32` to generate secure values
- Ensure `ALLOWED_HOSTS` includes only your production domain

## Support

For issues or questions, please open an issue on GitHub:
https://github.com/tomato414941/web-search/issues
