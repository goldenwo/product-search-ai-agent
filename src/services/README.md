# Services Architecture

This directory contains various services used throughout the application. The architecture follows clean design principles to ensure separation of concerns, testability, and extensibility.

## Design Patterns

The services are organized using several design patterns:

### 1. Factory Pattern

The `factory` package contains factories that create service instances based on configuration:

- `SerpServiceFactory`: Creates SERP API service instances for different providers
- `SerpProvider`: Enum of supported SERP API providers

### 2. Client-Service Separation

- **Clients**: Handle the raw API communication with external services
- **Services**: Provide business logic on top of clients
- **Normalizers**: Transform data between formats

### 3. Single Responsibility Principle

Each service has a specific responsibility:

- `SerpService`: Product search via SERP APIs
- `OpenAIService`: AI text generation and embeddings
- `RedisService`: Caching and rate limiting
- `ProductEnricher`: Extract detailed product information
- `AuthService`: User authentication and token management

## Directory Structure

```
services/
├── clients/           # API clients for external services
│   ├── serp_api_client.py
│   └── ...
├── factory/           # Service factories
│   ├── serp_factory.py
│   └── ...
├── normalizers/       # Data transformation between formats
│   ├── product_normalizer.py
│   └── ...
├── auth_service.py    # Authentication service
├── openai_service.py  # OpenAI API wrapper
├── redis_service.py   # Redis caching and rate limiting
├── serp_service.py    # Product search service
└── product_enricher.py # Product data enrichment
```

## Best Practices

1. **Error Handling**: All services include proper error handling and logging
2. **Dependency Injection**: Services accept dependencies in their constructors
3. **Configuration**: Services load configuration from environment variables
4. **Async/Await**: Services use async/await for I/O-bound operations
5. **Type Hints**: All code includes proper type hints for better IDE support
6. **Docstrings**: All public methods include comprehensive docstrings

## Adding New Services

When adding a new service:

1. Consider creating a dedicated client if it communicates with external APIs
2. Create normalizers if it transforms data between formats
3. Use factories if multiple implementations might be needed
4. Follow the established patterns for consistent code organization
