# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.6.x | ✅ |
| 1.5.x | ✅ |
| < 1.5 | ❌ |

## Safe Harbor

Web3 Agent Kit considers security research conducted under this policy as authorized conduct. We will not pursue legal action against researchers who:

- Follow this disclosure policy
- Make a good-faith effort to avoid privacy violations, data destruction, and service interruption
- Do not exploit vulnerabilities beyond what is necessary to demonstrate the issue

## Reporting a Vulnerability

**DO NOT** open a public GitHub issue for security vulnerabilities.

### For Wallet/Key-Related Issues

If you find a vulnerability that could expose private keys, drain funds, or compromise wallet security:

1. **Email:** khasbimln@gmail.com
2. **Twitter DM:** [@itseywacc](https://twitter.com/itseywacc)
3. **PGP:** Available on request

### For Other Security Issues

For non-critical security issues (dependency vulnerabilities, info disclosure, etc.):

1. Open a [private security advisory](https://github.com/ulsreall/web3-agent-kit/security/advisories/new)
2. Or email khasbimln@gmail.com

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix/patch:** Within 2 weeks for critical issues

### Bug Bounty

We don't have a formal bug bounty program yet, but we acknowledge all security researchers in our changelog and README.

## Security Best Practices

When using Web3 Agent Kit:

- **Never commit private keys** to version control
- **Use environment variables** for all secrets
- **Enable the Spend Governor** to limit transaction amounts
- **Use the kill switch** for emergency stops
- **Audit smart contracts** before interacting with them
- **Test on testnets first** before mainnet deployment
