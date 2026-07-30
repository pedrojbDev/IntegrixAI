from fastapi import APIRouter
from fastapi.responses import Response

from ...core.metrics.prometheus import INTERNAL_METRICS_PATH, render_prometheus_metrics


router = APIRouter()


@router.get(INTERNAL_METRICS_PATH, include_in_schema=False)
async def prometheus_metrics() -> Response:
    content, content_type = render_prometheus_metrics()
    return Response(content=content, headers={"Content-Type": content_type})
