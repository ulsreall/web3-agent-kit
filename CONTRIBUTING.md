# Contributing to Web3 Agent Kit

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a virtual environment
4. Install in development mode

```bash
git clone https://github.com/YOUR_USERNAME/web3-agent-kit.git
cd web3-agent-kit
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e ".[dev]"
```

## Development Workflow

1. Create a branch for your feature/fix
2. Make your changes
3. Add tests for new functionality
4. Run the test suite
5. Submit a pull request

```bash
git checkout -b feature/my-feature
# make changes
pytest tests/ -v
git push origin feature/my-feature
```

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Keep functions focused and small

## Adding DeFi Protocols

To add a new DeFi protocol integration:

1. Create a new file in `src/defi/`
2. Inherit from `DeFiTool`
3. Implement the required methods
4. Add tests
5. Update documentation

Example:

```python
from web3_agent_kit.defi import DeFiTool

class MyProtocol(DeFiTool):
    name = "my_protocol"
    supported_chains = [Chain.ETHEREUM]

    def execute(self, wallet, **kwargs):
        # Implement your logic
        pass
```

## Reporting Issues

- Use GitHub Issues
- Include reproduction steps
- Include error messages and stack traces
- Specify your Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
