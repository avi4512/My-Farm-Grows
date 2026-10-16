
from fastapi import APIRouter, Depends

from app.core.permissions import require_admin
from app.models.customer import Customer

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
)


@router.get("/test")
def admin_test(
    current_admin: Customer = Depends(require_admin),
):
    return {
        "message": "Admin access granted",
        "admin_id": current_admin.id,
        "role": current_admin.role,
    }
