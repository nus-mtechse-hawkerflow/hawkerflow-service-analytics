import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from analytics.aggregation import hourly_orders, summarise, top_items
from analytics.time_window import singapore_today
from dependencies.identity import require_matching_stall
from models.analytics_summary import StallDaySummary
from repository.analytics_repo import AnalyticsRepo

logger = logging.getLogger("hawkerflow-analytics.routes")

analytics_router = APIRouter(prefix="/v1/analytics")


def get_repo(request: Request) -> AnalyticsRepo:
    return request.app.state.analytics_repo


@analytics_router.get("/stalls/{stall_id}/summary", response_model=StallDaySummary)
async def stall_day_summary(
    stall_id: int = Depends(require_matching_stall),
    day: date | None = Query(default=None, alias="date"),
    repo: AnalyticsRepo = Depends(get_repo),
) -> StallDaySummary:
    """Daily order statistics for one stall.

    A stall with no orders is a successful zero, not an error: the dashboard
    must be able to tell "nothing sold today" from "analytics is broken".
    """
    resolved_day = day or singapore_today()

    try:
        partitions = repo.fetch_partitions(stall_id, resolved_day)
        items = repo.fetch_completed_items(stall_id, resolved_day)
    except SQLAlchemyError:
        # Log the traceback for the operator, but never return it: the
        # exception text can carry the connection string and password.
        logger.exception("Analytics query failed for stall %s on %s", stall_id, resolved_day)
        raise HTTPException(
            status_code=503,
            detail="Analytics database is unavailable. Please retry.",
        ) from None

    totals = summarise(partitions)

    return StallDaySummary(
        stallId=stall_id,
        date=resolved_day.isoformat(),
        totalOrders=totals["totalOrders"],
        completedOrders=totals["completedOrders"],
        cancelledOrders=totals["cancelledOrders"],
        completedOrderValue=totals["completedOrderValue"],
        averageCompletedOrderValue=totals["averageCompletedOrderValue"],
        topItems=top_items(items),
        hourlyOrders=hourly_orders(partitions),
    )
