from datetime import datetime

from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    """Read-only mirror of the order service's table.

    This service never creates, alters or drops it. The mirror exists only
    so SQLModel can build typed selects. f_created_at is timezone-naive and
    holds UTC wall-clock time.
    """

    __tablename__: str = "orders"

    f_id: int = Field(default=None, primary_key=True)
    f_total_price: float
    f_created_at: datetime
    f_status: str
