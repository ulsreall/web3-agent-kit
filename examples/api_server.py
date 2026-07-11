"""
Example: Run the Web3 Agent Kit REST API server.

Usage:
    # Basic (no auth)
    python examples/api_server.py

    # With API key
    WEB3_API_KEY=your-secret-key python examples/api_server.py

    # Custom port
    API_PORT=3000 python examples/api_server.py

Endpoints:
    GET  /docs              — Swagger UI
    GET  /redoc             — ReDoc docs
    GET  /health            — Health check
    GET  /wallet/info       — Wallet info
    GET  /swap/quote        — Swap quote
    GET  /portfolio/        — Portfolio dashboard
    GET  /gas/estimate      — Gas estimates
    GET  /watcher/list      — Watched wallets
    GET  /approval/scan     — Scan approvals
    GET  /dca/orders        — List DCA orders
    GET  /yield/opportunities — Yield scan
    GET  /bridge/quote      — Bridge quote

Test with curl:
    curl http://localhost:8000/health
    curl http://localhost:8000/gas/estimate?chain=ethereum
    curl http://localhost:8000/portfolio/?chain=ethereum
    curl -H "X-API-Key: your-key" http://localhost:8000/wallet/info
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3_agent_kit.api import app, main

if __name__ == "__main__":
    print("🚀 Starting Web3 Agent Kit API...")
    print("📖 Docs: http://localhost:8000/docs")
    print("📖 ReDoc: http://localhost:8000/redoc")
    print()
    main()
