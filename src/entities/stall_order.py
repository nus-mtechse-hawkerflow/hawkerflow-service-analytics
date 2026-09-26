from sqlmodel import Field, SQLModel


class StallOrder(SQLModel, table=True):
    """Read-only mirror of the order service's table.

    f_subtotal is this stall's share of a possibly multi-stall order, and is
    the only correct source of per-stall money. orders.f_total_price covers
    every stall in the order.
    """

    __tablename__: str = "stall_orders"

    f_id: int = Field(default=None, primary_key=True)
    f_order_id: int = Field(foreign_key="orders.f_id")
    f_stall_id: int = Field(index=True)
    f_status: str
    f_subtotal: float
