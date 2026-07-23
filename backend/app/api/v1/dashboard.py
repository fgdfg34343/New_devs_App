from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.services.reservations import get_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, str]]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return await get_tenant_properties(tenant_id)


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    return {
        "property_id": revenue_data['property_id'],
        # JSON numbers are binary floating point. Keep financial values as a
        # fixed-scale decimal string across the API boundary.
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
