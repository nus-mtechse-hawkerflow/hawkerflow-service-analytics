from pydantic import BaseModel

# Metrics the order schema cannot support. Reported by name so the dashboard
# can say so plainly rather than showing an invented number or a zero that
# reads as a measurement.
UNAVAILABLE_METRICS = [
    "paymentBreakdown",
    "preparationTime",
    "takeawayFees",
    "shiftClosure",
]


class TopItem(BaseModel):
    dishId: int
    name: str
    quantity: int
    completedItemValue: float


class HourlyBucket(BaseModel):
    hour: int
    orderCount: int
    completedOrderValue: float


class StallDaySummary(BaseModel):
    stallId: int
    date: str
    timezone: str = "Asia/Singapore"
    source: str = "postgresql"
    totalOrders: int
    completedOrders: int
    cancelledOrders: int
    completedOrderValue: float
    averageCompletedOrderValue: float | None
    topItems: list[TopItem]
    hourlyOrders: list[HourlyBucket]
    unavailableMetrics: list[str] = UNAVAILABLE_METRICS
