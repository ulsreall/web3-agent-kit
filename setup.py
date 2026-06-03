from setuptools import setup, find_packages

setup(
    name="web3-agent-kit",
    version="0.1.0",
    author="Maulana",
    author_email="khasbim240803@gmail.com",
    description="Open-source framework for building autonomous AI agents that interact with blockchain networks",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ulsreall/web3-agent-kit",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "web3>=6.0.0",
        "eth-account>=0.10.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "llm": ["openai>=1.0.0", "anthropic>=0.40.0"],
        "solana": ["solana>=0.34.0"],
        "all": ["openai>=1.0.0", "anthropic>=0.40.0", "solana>=0.34.0"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
