# Contributing

We welcome contributions to Web3 Agent Kit! This guide will help you get started.

---

## 🚀 Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/ulsreall/web3-agent-kit.git
cd web3-agent-kit
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install in development mode
pip install -e ".[dev]"
```

### 3. Run Tests

```bash
pytest tests/ -v
```

---

## 📝 Development Guidelines

### Code Style

- Follow PEP 8
- Use type hints for all function signatures
- Write docstrings for all public classes and methods
- Keep functions focused and small

### Docstring Format

Use Google-style docstrings:

```python
def swap(self, token_in: str, token_out: str, amount: float) -> SwapResult:
    """
    Execute a token swap.

    Args:
        token_in: Input token address or symbol
        token_out: Output token address or symbol
        amount: Amount in human-readable units

    Returns:
        SwapResult with transaction hash and details

    Raises:
        ValueError: If token is not supported
        RuntimeError: If swap fails
    """
```

### Commit Messages

Use conventional commits:

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation
- `test:` — Tests
- `refactor:` — Code refactoring
- `chore:` — Maintenance

Example: `feat: add Aerodrome DEX integration`

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_core.py -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Use pytest fixtures for common setup
- Mock external dependencies (RPC calls, API calls)

Example:

```python
import pytest
from unittest.mock import Mock, patch
from web3_agent_kit import Agent, Wallet, Chain

@pytest.fixture
def mock_wallet():
    wallet = Mock(spec=Wallet)
    wallet.address = "0x1234..."
    return wallet

def test_agent_creation(mock_wallet):
    agent = Agent(wallet=mock_wallet, chains=[Chain.BASE])
    assert agent.wallet == mock_wallet
```

---

## 📚 Documentation

### Building Docs

```bash
# Install docs dependencies
pip install mkdocs-material mkdocstrings mkdocstrings-python

# Serve locally
mkdocs serve

# Build static site
mkdocs build
```

### Documentation Guidelines

- Keep documentation up to date with code changes
- Include code examples for all features
- Use admonitions for warnings and notes
- Link to relevant API reference pages

---

## 🐛 Reporting Bugs

1. Check existing issues first
2. Create a new issue with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS)

---

## 💡 Feature Requests

1. Check existing issues and discussions
2. Create a new issue with:
   - Clear description of the feature
   - Use case / motivation
   - Proposed implementation (if any)

---

## 📜 License

By contributing, you agree that your contributions will be licensed under
the [MIT License](https://github.com/ulsreall/web3-agent-kit/blob/main/LICENSE).

---

## 🙏 Thank You!

Thank you for contributing to Web3 Agent Kit! Your help makes this project better for everyone.
