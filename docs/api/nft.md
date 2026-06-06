# NFT Module

NFT tools — collection creation, minting, and marketplace integration.

---

## NFT Minting

Mint NFTs with metadata and IPFS upload.

```python
from web3_agent_kit.nft import NFTMinter

minter = NFTMinter(chain=Chain.BASE, wallet=wallet)

# Mint single NFT
result = minter.mint(
    contract="0x...",
    to=wallet.address,
    metadata={
        "name": "My NFT #1",
        "description": "A unique digital collectible",
        "image": "ipfs://Qm...",
        "attributes": [{"trait_type": "Rarity", "value": "Legendary"}],
    },
)
print(f"TX: {result.tx_hash}")
print(f"Token ID: {result.token_id}")
```

## Collection Creation

Deploy a new NFT collection contract.

```python
from web3_agent_kit.nft import CollectionDeployer

deployer = CollectionDeployer(chain=Chain.BASE, wallet=wallet)
collection = deployer.deploy(
    name="My Collection",
    symbol="MYCOL",
    base_uri="ipfs://Qm.../",
    max_supply=10000,
    mint_price=0.01,
)
print(f"Contract: {collection.address}")
```

## Batch Operations

```python
from web3_agent_kit.nft import BatchMinter

batch = BatchMinter(chain=Chain.BASE, wallet=wallet)
results = batch.mint_batch(
    contract="0x...",
    recipients=["0x111...", "0x222...", "0x333..."],
    metadata_list=[meta1, meta2, meta3],
)
```

## Marketplace

```python
from web3_agent_kit.nft import Marketplace

marketplace = Marketplace(chain=Chain.BASE, wallet=wallet)

# List on OpenSea-compatible marketplace
marketplace.list(
    contract="0x...",
    token_id=42,
    price=0.5,
    currency="ETH",
)
```
