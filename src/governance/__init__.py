"""Governance Module — DAO voting, proposal tracking, delegation.

Monitor and participate in DAO governance across Snapshot, Tally,
on-chain proposals, and delegation management.

Usage::
    from web3_agent_kit.governance import GovernanceTracker, GovConfig

    tracker = GovernanceTracker(rpc_url="https://eth.llamarpc.com")

    # Get active proposals
    proposals = tracker.get_active_proposals(dao="uniswap")

    # Check voting power
    power = tracker.get_voting_power(
        address="0x...",
        token="0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",  # UNI
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ProposalStatus(Enum):
    """Proposal lifecycle status."""
    PENDING = "pending"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    EXECUTED = "executed"
    DEFEATED = "defeated"
    CANCELED = "canceled"
    QUEUED = "queued"
    EXPIRED = "expired"


class VoteChoice(Enum):
    """Vote choices."""
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


@dataclass
class GovConfig:
    """Governance tracker configuration."""
    rpc_url: str
    snapshot_graphql_url: str = "https://hub.snapshot.org/graphql"
    tally_api_key: Optional[str] = None
    cache_ttl: int = 300  # 5 min


@dataclass
class Proposal:
    """A governance proposal."""
    id: str
    title: str
    description: str = ""
    dao: str = ""
    status: ProposalStatus = ProposalStatus.PENDING
    start_time: int = 0
    end_time: int = 0
    for_votes: int = 0
    against_votes: int = 0
    abstain_votes: int = 0
    quorum: int = 0
    author: str = ""
    url: str = ""
    choices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "dao": self.dao,
            "status": self.status.value,
            "for_votes": self.for_votes,
            "against_votes": self.against_votes,
            "abstain_votes": self.abstain_votes,
            "end_time": self.end_time,
            "url": self.url,
        }


@dataclass
class VotingPower:
    """Voting power for an address."""
    address: str
    token: str
    power: float
    delegated_to: Optional[str] = None
    delegated_from: list[str] = field(default_factory=list)
    can_vote: bool = True


@dataclass
class DelegateInfo:
    """Information about a delegate."""
    address: str
    name: str = ""
    voting_power: float = 0.0
    proposals_created: int = 0
    votes_participated: int = 0
    delegators: int = 0
    url: str = ""


# Known DAO configurations
KNOWN_DAOS: dict[str, dict] = {
    "uniswap": {
        "name": "Uniswap",
        "token": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
        "governor": "0x408ED6354d4973f66138C91495F2f2FCbd8724C3",
        "snapshot": "uniswap",
        "chain": "ethereum",
    },
    "aave": {
        "name": "Aave",
        "token": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        "governor": "0xEC568fffba86c094cf06b22134B23074DFE2252c",
        "snapshot": "aave.eth",
        "chain": "ethereum",
    },
    "arbitrum": {
        "name": "Arbitrum DAO",
        "token": "0x912CE59144191C1204E64559FE8253a0e49E6548",
        "governor": "0xf07DeD9dC292157749B2D7E6f3392484C1e5B7E8",
        "snapshot": "arbitrumfoundation.eth",
        "chain": "arbitrum",
    },
    "optimism": {
        "name": "Optimism Collective",
        "token": "0x4200000000000000000000000000000000000042",
        "governor": "0xcDF27F107725988f2261Ce2256bDfCdE8B382B10",
        "snapshot": "opcollective.eth",
        "chain": "optimism",
    },
    "ens": {
        "name": "ENS DAO",
        "token": "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72",
        "governor": "0x323A76393544d5ecca80cd6ef2A560C6a395b7E3",
        "snapshot": "ens.eth",
        "chain": "ethereum",
    },
}


class GovernanceTracker:
    """DAO governance tracker supporting Snapshot + on-chain proposals.

    Monitors proposals, tracks voting power, manages delegation,
    and supports voting across multiple DAOs.

    Example::
        tracker = GovernanceTracker(rpc_url="https://eth.llamarpc.com")

        # Get active proposals
        proposals = tracker.get_active_proposals(dao="uniswap")
        for p in proposals:
            print(f"{p.title} — {p.status.value} (ends in {p.end_time - time.time()}s)")

        # Check voting power
        power = tracker.get_voting_power("0x...", token="0x1f98...")
        print(f"Voting power: {power.power}")
    """

    # Governor ABI (minimal)
    GOVERNOR_ABI = [
        {"inputs": [], "name": "proposalCount", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}], "name": "state", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}], "name": "proposalSnapshot", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}], "name": "proposalDeadline", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}], "name": "proposalProposer", "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}], "name": "proposalThreshold", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "account", "type": "address"}, {"name": "blockNumber", "type": "uint256"}], "name": "getVotes", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "proposalId", "type": "uint256"}, {"name": "support", "type": "uint8"}], "name": "castVote", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "nonpayable", "type": "function"},
    ]

    # Token ABI (minimal)
    TOKEN_ABI = [
        {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "delegatee", "type": "address"}], "name": "delegates", "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
        {"inputs": [{"name": "delegatee", "type": "address"}], "name": "delegate", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [], "name": "getCurrentVotes", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    ]

    PROPOSAL_STATES = {
        0: ProposalStatus.PENDING,
        1: ProposalStatus.ACTIVE,
        2: ProposalStatus.CANCELED,
        3: ProposalStatus.DEFEATED,
        4: ProposalStatus.SUCCEEDED,
        5: ProposalStatus.QUEUED,
        6: ProposalStatus.EXPIRED,
        7: ProposalStatus.EXECUTED,
    }

    def __init__(self, rpc_url: str, config: Optional[GovConfig] = None):
        self.rpc_url = rpc_url
        self.config = config or GovConfig(rpc_url=rpc_url)
        self._cache: dict[str, tuple[float, Any]] = {}

        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

    def get_active_proposals(
        self,
        dao: Optional[str] = None,
        governor_address: Optional[str] = None,
        limit: int = 10,
    ) -> list[Proposal]:
        """Get active proposals for a DAO.

        Args:
            dao: Known DAO name (e.g. "uniswap", "aave")
            governor_address: Direct governor contract address
            limit: Max proposals to return

        Returns:
            List of active Proposal objects
        """
        if dao and dao in KNOWN_DAOS:
            dao_config = KNOWN_DAOS[dao]
            governor_addr = dao_config["governor"]
        elif governor_address:
            governor_addr = governor_address
        else:
            raise ValueError("Either dao name or governor_address required")

        governor = self.w3.eth.contract(
            address=self.w3.to_checksum_address(governor_addr),
            abi=self.GOVERNOR_ABI,
        )

        proposals = []
        try:
            total = governor.functions.proposalCount().call()
            start = max(0, total - limit)

            for pid in range(start, total):
                state_code = governor.functions.state(pid).call()
                status = self.PROPOSAL_STATES.get(state_code, ProposalStatus.PENDING)

                if status in (ProposalStatus.ACTIVE, ProposalStatus.PENDING):
                    deadline = governor.functions.proposalDeadline(pid).call()
                    proposer = governor.functions.proposalProposer(pid).call()

                    proposals.append(Proposal(
                        id=str(pid),
                        title=f"Proposal #{pid}",
                        dao=dao or governor_addr[:10],
                        status=status,
                        end_time=deadline,
                        author=proposer,
                        url=f"https://www.tally.xyz/gov/{dao}/proposal/{pid}" if dao else "",
                    ))
        except Exception as e:
            logger.error(f"Failed to fetch proposals: {e}")

        # Also fetch from Snapshot GraphQL
        if dao and dao in KNOWN_DAOS:
            snapshot_proposals = self._fetch_snapshot_proposals(dao)
            proposals.extend(snapshot_proposals)

        return proposals

    def _fetch_snapshot_proposals(self, dao: str) -> list[Proposal]:
        """Fetch proposals from Snapshot GraphQL API."""
        import requests
        snapshot_name = KNOWN_DAOS.get(dao, {}).get("snapshot", dao)
        now = int(time.time())

        query = """
        query($space: String!, $now: Int!) {
            proposals(
                first: 10,
                where: { space: $space, state: "active" },
                orderBy: "end",
                orderDirection: "desc"
            ) {
                id
                title
                body
                start
                end
                state
                author
                choices
                scores_total
                quorum
                link
            }
        }
        """

        try:
            resp = requests.post(
                self.config.snapshot_graphql_url,
                json={"query": query, "variables": {"space": snapshot_name, "now": now}},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            proposals_data = data.get("data", {}).get("proposals", [])

            return [
                Proposal(
                    id=p["id"],
                    title=p["title"],
                    description=p.get("body", "")[:200],
                    dao=dao,
                    status=ProposalStatus.ACTIVE,
                    start_time=p["start"],
                    end_time=p["end"],
                    for_votes=sum(p.get("scores_total", [0])),
                    author=p.get("author", ""),
                    url=p.get("link", ""),
                    choices=p.get("choices", []),
                )
                for p in proposals_data
            ]
        except Exception as e:
            logger.debug(f"Snapshot fetch failed: {e}")
            return []

    def get_voting_power(
        self,
        address: str,
        token: Optional[str] = None,
        dao: Optional[str] = None,
        block_number: Optional[int] = None,
    ) -> VotingPower:
        """Get voting power for an address.

        Args:
            address: Wallet address
            token: Token contract (for token-weighted voting)
            dao: Known DAO name (auto-resolves token)
            block_number: Block number for historical power

        Returns:
            VotingPower object
        """
        if dao and dao in KNOWN_DAOS:
            token = KNOWN_DAOS[dao]["token"]

        if not token:
            raise ValueError("Either token or dao required")

        from web3 import Web3

        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token),
            abi=self.TOKEN_ABI,
        )

        block = block_number or "latest"

        balance = token_contract.functions.balanceOf(
            self.w3.to_checksum_address(address),
        ).call(block_identifier=block)

        # Check for delegation
        delegatee = None
        try:
            delegatee = token_contract.functions.delegates(
                self.w3.to_checksum_address(address),
            ).call(block_identifier=block)
        except Exception:
            pass

        # Get current votes (includes delegated)
        try:
            votes = token_contract.functions.getCurrentVotes(
                self.w3.to_checksum_address(address),
            ).call(block_identifier=block)
            power = float(Web3.from_wei(votes, "ether"))
        except Exception:
            power = float(Web3.from_wei(balance, "ether"))

        is_delegated = delegatee is not None and delegatee.lower() != address.lower()

        return VotingPower(
            address=address,
            token=token,
            power=power,
            delegated_to=delegatee if is_delegated else None,
            can_vote=power > 0,
        )

    def delegate(
        self,
        delegatee: str,
        token: str,
        private_key: str,
    ) -> str:
        """Delegate voting power.

        Args:
            delegatee: Address to delegate to
            token: Token contract address
            private_key: Signer private key

        Returns:
            Transaction hash
        """
        from web3 import Web3

        account = self.w3.eth.account.from_key(private_key)
        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token),
            abi=self.TOKEN_ABI,
        )

        tx = token_contract.functions.delegate(
            self.w3.to_checksum_address(delegatee),
        ).build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": 200000,
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def get_delegates(self, dao: str) -> list[DelegateInfo]:
        """Get list of delegates for a DAO.

        Args:
            dao: Known DAO name

        Returns:
            List of DelegateInfo objects
        """
        # Query Tally API for delegates
        import requests

        try:
            resp = requests.get(
                "https://api.tally.xyz/query",
                params={"dao": dao},
                headers={"Api-Key": self.config.tally_api_key or ""},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                delegates = data.get("delegates", [])
                return [
                    DelegateInfo(
                        address=d.get("address", ""),
                        name=d.get("name", ""),
                        voting_power=float(d.get("votingPower", 0)),
                        proposals_created=d.get("proposalsCreated", 0),
                        votes_participated=d.get("votesParticipated", 0),
                        delegators=d.get("delegators", 0),
                    )
                    for d in delegates[:20]
                ]
        except Exception as e:
            logger.debug(f"Tally API failed: {e}")

        return []

    def get_all_daos(self) -> list[dict]:
        """List all known DAOs."""
        return [
            {"name": name, "token": info["token"], "chain": info["chain"],
             "governor": info["governor"]}
            for name, info in KNOWN_DAOS.items()
        ]


__all__ = [
    "GovernanceTracker",
    "GovConfig",
    "Proposal",
    "ProposalStatus",
    "VoteChoice",
    "VotingPower",
    "DelegateInfo",
    "KNOWN_DAOS",
]
