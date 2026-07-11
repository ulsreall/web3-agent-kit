# Contributing to Web3 Agent Kit

Thank you for your interest in contributing! 🎉

## Getting Started

### Prerequisites

- Python 3.10+
- Git
- pip or uv

### Setup

```bash
# Clone the repo
git clone https://github.com/ulsreall/web3-agent-kit.git
cd web3-agent-kit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## How to Contribute

### Reporting Bugs

1. Check existing [issues](https://github.com/ulsreall/web3-agent-kit/issues)
2. Create a new issue using the [bug report template](/.github/ISSUE_TEMPLATE/bug_report.md)
3. Include as much detail as possible

### Suggesting Features

1. Check existing [issues](https://github.com/ulsreall/web3-agent-kit/issues)
2. Create a new issue using the [feature request template](/.github/ISSUE_TEMPLATE/feature_request.md)

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest tests/ -v`
6. Commit your changes: `git commit -m 'feat: add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints where possible
- Write docstrings for all public methods
- Keep functions focused and small

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new feature
fix: resolve bug
docs: update documentation
test: add tests
refactor: improve code structure
chore: update dependencies
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_llm.py -v

# Run with coverage
pytest tests/ --cov=web3_agent_kit --cov-report=html
```

## Project Structure

```
web3-agent-kit/
├── src/                    # Source code
│   ├── agent.py           # Agent framework
│   ├── llm.py             # LLM integration
│   ├── wallet.py          # Wallet management
│   ├── chain.py           # Multi-chain support
│   ├── sniper.py          # Token sniper
│   ├── portfolio.py       # Portfolio tracking
│   ├── bridge.py          # Cross-chain bridges
│   └── defi/              # DeFi protocols
├── tests/                  # Test suite
├── examples/               # Usage examples
├── .github/                # GitHub templates
└── docs/                   # Documentation
```

## Questions?

Feel free to open an issue or reach out on [Twitter](https://twitter.com/itseywacc).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
