from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db, get_current_device, get_current_api_key
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice
from app.schemas.device import (
    DevicePairRequest,
    DevicePairResponse,
    DeviceHeartbeatRequest,
    GatewayDeviceResponse,
    DeviceJobResponse,
    DeviceSendResultRequest,
)
from app.services.device_service import (
    pair_device,
    update_heartbeat,
    get_next_job,
    report_send_result,
)
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/devices", tags=["Gateway Devices"])


@router.post("/pair", response_model=DevicePairResponse)
def pair_phone(
    payload: DevicePairRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Exchanges an active one-time pairing code for permanent device credentials.
    Called by the Android application during initial setup.
    """
    client_ip = request.client.host if request.client else None
    try:
        device, raw_token = pair_device(db, payload, ip_address=client_ip)
        return DevicePairResponse(
            device_id=device.id,
            device_token=raw_token,
            name=device.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/heartbeat", response_model=GatewayDeviceResponse)
def phone_heartbeat(
    payload: DeviceHeartbeatRequest,
    device: GatewayDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """
    Called periodically by the Android gateway service to report SIM state, signal, and keep device marked online.
    """
    return update_heartbeat(db, device, payload)


@router.get("/jobs/next", response_model=Optional[DeviceJobResponse])
def fetch_next_job(
    response: Response,
    device: GatewayDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """
    Polls the server for the next eligible outgoing SMS job.
    Returns 204 No Content when queue is empty.
    """
    job = get_next_job(db, device)
    if not job:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return job


@router.post("/jobs/{job_id}/result")
def submit_job_result(
    job_id: str,
    payload: DeviceSendResultRequest,
    device: GatewayDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """
    Reports the final or intermediate send result (sent, delivered, failed)
    received from Android's SmsManager broadcast callbacks.
    """
    try:
        message = report_send_result(db, device, job_id, payload)
        return {
            "status": "success",
            "message_id": message.id,
            "message_status": message.status,
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[GatewayDeviceResponse])
def list_devices(
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Lists all paired gateway devices and their current status."""
    devices = db.scalars(
        select(GatewayDevice).order_by(GatewayDevice.created_at.desc())
    ).all()
    return devices


@router.delete("/{device_id}")
def revoke_device(
    device_id: str,
    request: Request,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Revokes a gateway device, preventing it from fetching jobs or reporting status."""
    device = db.get(GatewayDevice, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )

    device.is_revoked = True
    device.is_online = False
    db.commit()

    client_ip = request.client.host if request.client else None
    record_audit_event(
        db,
        action="device.revoke",
        actor_type="api_key",
        actor_id=api_key.id,
        details={"device_id": device_id, "name": device.name},
        ip_address=client_ip,
    )

    return {"status": "success", "message": f"Device '{device.name}' revoked"}
