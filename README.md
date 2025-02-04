# product-search-ai-agent

A FastAPI-based AI agent that searches for products and recommends the best options.

## Prerequisites

Before setting up the project, ensure you have the following installed:

- **Python 3.10+**
- **Pipenv** (`pip install pipenv`)
- **Git**
- **Pre-Commit** (`pip install pre-commit`)

---

## Installation

### **Clone the Repository**

```bash
git clone https://github.com/your-username/product-search-ai-agent.git
cd product-search-ai-agent
```

## Set Up Virtual Environment & Install Dependencies

```bash
pipenv install
```

## Activate the Virtual Environment

```bash
pipev shell
```

## Run Ruff to Check for Issues

```bash
ruff check .
```

## Fix Formatting Issues with Ruff

```bash
ruff format .
```

## Install Pre-Commit Hooks

```bash
pre-commit install
pre-commit install --hook-type pre-push
```

## Run Pre-Commit Hooks Manually

```bash
pre-commit run --all-files
```

## Running Tests

```bash
pytest src/tests/
```

## Health Check

```bash
curl http://127.0.0.1:8000/healthcheck
```

## Running the Application

```bash
uvicorn src.main:app --reload
```
