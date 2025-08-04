# CHawk API - Enhanced Production-Ready FastAPI

A secure, scalable FastAPI application with comprehensive authentication, rate limiting, monitoring, and production features.

## 🚀 Features

### Authentication & Security
- JWT access and refresh token system with rotation
- Token blacklisting for secure logout
- Rate limiting on all endpoints (no Redis required)
- Password complexity validation
- Bcrypt password hashing

### Monitoring & Observability  
- Prometheus metrics integration
- OpenTelemetry distributed tracing
- Structured logging with Loguru
- Health checks with database connectivity
- Application metrics endpoint

### Production Ready
- Docker containerization with Python 3.12
- Docker Compose with PostgreSQL and monitoring stack
- Comprehensive error handling
- Database connection pooling
- Background token cleanup utilities

## 🏗️ Architecture

```
app/
├── api/v1/
│   ├── endpoints/    # API route handlers
│   └── schemas/      # Pydantic models
├── auth/             # Authentication logic
├── core/             # Core configuration
├── db/               # Database layer
│   ├── crud/         # Database operations
│   └── models.py     # SQLAlchemy models
└── main.py           # FastAPI application
```

## 🚀 Quick Start

### Using Docker (Recommended)

1. **Clone and setup**:
   ```bash
   git clone <your-repo>
   cd chawk-api
   cp .env.example .env
   ```

2. **Update `.env`** with your settings (especially JWT_SECRET_KEY)

3. **Start services**:
   ```bash
   make docker-up
   ```

4. **Access the application**:
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs  
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (admin/admin123)

### Local Development

1. **Install dependencies**:
   ```bash
   make install
   ```

2. **Setup database** (PostgreSQL required):
   ```bash
   make upgrade  # Run migrations
   ```

3. **Start development server**:
   ```bash
   make dev
   ```

## 📊 Monitoring

The application includes comprehensive monitoring:

- **Prometheus Metrics**: HTTP requests, response times, custom metrics
- **Grafana Dashboards**: Visual monitoring (included in Docker setup)  
- **Health Checks**: `/health` endpoint with database connectivity
- **Application Metrics**: `/api/v1/users/admin/metrics` (authenticated)

## 🔒 Security Features

### Rate Limiting (In-Memory)
- Registration: 5 requests/minute per IP
- Login: 5 requests/minute per IP  
- Token refresh: 10 requests/minute per IP
- General endpoints: 30-100 requests/minute per IP

### Authentication Flow
1. Register/Login → Get access + refresh tokens
2. Use access token for API calls
3. Refresh access token using refresh token (rotation)
4. Logout blacklists current access token

## 🛠️ Common Tasks

```bash
# Development
make dev                    # Start dev server
make migrate msg="message"  # Create migration
make upgrade               # Apply migrations

# Docker
make docker-up             # Start all services  
make docker-down           # Stop services
make docker-build          # Rebuild images

# Maintenance
python scripts/cleanup_tokens.py     # Clean expired tokens
python scripts/create_admin_user.py  # Create admin user

# Testing
make test                  # Run tests
```

## 📝 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - OAuth2 login (form data)
- `POST /api/v1/auth/login-json` - JSON login  
- `POST /api/v1/auth/refresh-token` - Refresh access token
- `POST /api/v1/auth/logout` - Logout (blacklist token)

### Users
- `GET /api/v1/users/me` - Get current user info
- `GET /api/v1/users/{user_id}` - Get user by ID
- `GET /api/v1/users/admin/metrics` - Application metrics

### Monitoring  
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

## 🔧 Configuration

Key environment variables:

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
JWT_SECRET_KEY=your-secret-key-minimum-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7  
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
```

## 🚀 Production Deployment

1. **Set secure JWT secret key** (minimum 32 characters)
2. **Configure proper CORS origins**  
3. **Use production PostgreSQL database**
4. **Set up SSL/TLS termination**
5. **Configure log aggregation**
6. **Set up monitoring alerts**
7. **Schedule token cleanup** (`scripts/cleanup_tokens.py`)

## 📈 Performance

- **Database**: Connection pooling with 20 connections
- **Rate Limiting**: In-memory (no external dependencies)
- **Async**: Full async/await throughout
- **Monitoring**: Low-overhead Prometheus metrics

## 🧪 Testing

Run the test suite:
```bash
make test
```

Tests include:
- Authentication flow
- Token refresh and rotation  
- Rate limiting
- User management
- Error handling

## 📦 Dependencies

Core packages:
- **FastAPI**: Modern Python web framework
- **SQLAlchemy**: Async ORM  
- **Pydantic**: Data validation
- **slowapi**: Rate limiting
- **prometheus-client**: Metrics
- **loguru**: Structured logging
- **OpenTelemetry**: Distributed tracing

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.