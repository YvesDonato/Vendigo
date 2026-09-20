from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Protocol

from vendi.errors import VoiceFailure
from vendi.conversation.knowledge import vendi_knowledge


@dataclass(frozen=True)
class InventoryItem:
    id: str
    name: str
    stock: int

    def __post_init__(self):
        if not self.id or not self.name or type(self.stock) is not int or self.stock < 0:
            raise ValueError("Inventory needs an ID, name, and nonnegative integer stock")


@dataclass(frozen=True)
class ApplicationContext:
    inventory: List[InventoryItem] = field(default_factory=list)
    prices: Dict[str, int] = field(default_factory=dict)  # Integer cents, keyed by product ID.
    order_status: Optional[str] = None
    robot_state: str = "UNKNOWN"
    currency: str = "CAD"
    inventory_known: bool = False  # An empty unknown inventory is not a sold-out claim.
    payment_verified: bool = False

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in self.prices.values()):
            raise ValueError("Prices must be nonnegative integer cents")
        if type(self.payment_verified) is not bool or type(self.inventory_known) is not bool:
            raise ValueError("Context verification flags must be explicit booleans")
        if len({item.id for item in self.inventory}) != len(self.inventory):
            raise ValueError("Inventory IDs must be unique")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Currency must be a three-letter code")

    def get_inventory(self):
        return [asdict(item) for item in self.inventory]

    def get_prices(self):
        return dict(self.prices)

    def get_order_status(self):
        return self.order_status

    def get_purchase_process(self):
        return vendi_knowledge()["purchase_process"]

    def as_dict(self):
        return asdict(self)


class ContextProvider(Protocol):
    async def snapshot(self) -> ApplicationContext: ...


class StaticContext:
    """Explicit offline/test fixture. Live agents use VendigoContext instead."""

    def __init__(self, context=None):
        self.context = context or ApplicationContext()

    async def snapshot(self):
        return self.context


class VendigoContext:
    """Read-only adapter to the existing GET /api/state. Never invokes a robot endpoint."""

    def __init__(self, base_url, robot_id="robot-001", order_id=None, timeout=5):
        self.url = base_url.rstrip("/") + "/api/state"
        self.robot_id = robot_id
        # Bind this explicitly to the customer's order; do not borrow someone else's order.
        self.order_id = order_id
        self.timeout = timeout

    async def snapshot(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url, headers={"Cache-Control": "no-cache"})
                response.raise_for_status()
                data = response.json()
            robot = next(robot for robot in data["robots"] if robot["id"] == self.robot_id)
            products = {product["id"]: product for product in data["products"]}
            stock = {}
            for item in data["inventory"]:
                if item["robotId"] == self.robot_id:
                    if type(item["stock"]) is not int or item["stock"] < 0:
                        raise ValueError("Invalid stock")
                    stock[item["productId"]] = stock.get(item["productId"], 0) + item["stock"]
            items = [InventoryItem(id, products[id]["name"], count if products[id].get("enabled", True) else 0)
                     for id, count in stock.items()]
            order = next((order for order in data["activeOrders"]
                          if self.order_id and order["id"] == self.order_id and order["robotId"] == self.robot_id), None)
            return ApplicationContext(
                inventory=items, prices={id: products[id]["priceCents"] for id in stock},
                inventory_known=True, robot_state=robot["status"],
                order_status=order["status"] if order else None,
                # The demo storefront simulates checkout and supplies no payment verification.
                payment_verified=False,
            )
        except Exception as error:
            raise VoiceFailure("context", "Current Vendigo facts are unavailable; check the application connection.") from error
