from sqlmodel import Field, SQLModel


class OrderItem(SQLModel, table=True):
    """Read-only mirror of the order service's table."""

    __tablename__: str = "order_items"

    f_id: int = Field(default=None, primary_key=True)
    f_order_id: int = Field(foreign_key="orders.f_id")
    f_stall_order_id: int = Field(default=None, foreign_key="stall_orders.f_id")
    f_stall_id: int = Field(index=True)
    f_dish_id: int
    f_dish_name: str
    f_quantity: int
    f_price: float
