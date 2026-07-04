"""Pydantic request/response models. Separate Create / Read / Update shapes
keep the API contract explicit and validated.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# ----- shared config: allow building from ORM objects -----
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----- Product -----
class ProductCreate(BaseModel):
    product_id: str
    name: str
    family: str
    routing_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    family: Optional[str] = None
    routing_id: Optional[int] = None
    is_active: Optional[bool] = None


class ProductRead(ORMModel):
    id: int
    product_id: str
    name: str
    family: str
    routing_id: Optional[int]
    is_active: bool


# ----- BOM -----
class BomCreate(BaseModel):
    product_id: int
    material: str
    qty_per_unit: float = Field(gt=0)
    uom: str
    supplier: Optional[str] = None
    lead_days: int = Field(ge=0, default=0)


class BomUpdate(BaseModel):
    material: Optional[str] = None
    qty_per_unit: Optional[float] = Field(default=None, gt=0)
    uom: Optional[str] = None
    supplier: Optional[str] = None
    lead_days: Optional[int] = Field(default=None, ge=0)


class BomRead(ORMModel):
    id: int
    product_id: int
    material: str
    qty_per_unit: float
    uom: str
    supplier: Optional[str]
    lead_days: int


# ----- Order -----
class OrderCreate(BaseModel):
    order_id: str
    product_id: int
    customer: str
    order_qty: int = Field(gt=0)
    order_date: date
    committed_delivery_date: date
    priority: str = "MED"
    plant_id: Optional[int] = None
    sched_mode: str = "backward"


class OrderUpdate(BaseModel):
    customer: Optional[str] = None
    order_qty: Optional[int] = Field(default=None, gt=0)
    committed_delivery_date: Optional[date] = None
    priority: Optional[str] = None
    sched_mode: Optional[str] = None


class OrderRead(ORMModel):
    id: int
    order_id: str
    product_id: int
    customer: str
    order_qty: int
    order_date: date
    committed_delivery_date: date
    priority: str
    plant_id: Optional[int]
    sched_mode: str
    replan_count: int


# ----- Event -----
class EventCreate(BaseModel):
    event_id: str
    order_id: int
    operation_seq: Optional[int] = None
    event_type: str
    event_timestamp: datetime
    event_qty: Optional[int] = None
    downtime_reason: Optional[str] = None
    downtime_mins: int = 0
    entered_by: Optional[str] = None


class EventRead(ORMModel):
    id: int
    event_id: str
    order_id: int
    operation_seq: Optional[int]
    event_type: str
    event_timestamp: datetime
    event_qty: Optional[int]
    downtime_reason: Optional[str]
    downtime_mins: int
    entered_by: Optional[str]


# ----- Routing (read with nested ops) -----
class RoutingOpRead(ORMModel):
    id: int
    operation_seq: int
    work_center: str
    setup_min: Optional[float]
    run_per_unit_min: Optional[float]
    queue_min: Optional[float]
    move_min: Optional[float]
    predecessor_seq: Optional[int]
    parallel_group: Optional[str]


class RoutingRead(ORMModel):
    id: int
    route_id: str
    description: Optional[str]
    operations: list[RoutingOpRead] = []


# ----- Routing / operation write models -----
class RoutingCreate(BaseModel):
    route_id: str
    description: Optional[str] = None


class RoutingOpCreate(BaseModel):
    operation_seq: int = Field(ge=0)
    work_center: str
    setup_min: float = Field(ge=0, default=0)
    run_per_unit_min: float = Field(ge=0, default=0)
    queue_min: float = Field(ge=0, default=0)
    move_min: float = Field(ge=0, default=0)
    predecessor_seq: Optional[int] = None
    parallel_group: Optional[str] = None


class RoutingOpUpdate(BaseModel):
    operation_seq: Optional[int] = Field(default=None, ge=0)
    work_center: Optional[str] = None
    setup_min: Optional[float] = Field(default=None, ge=0)
    run_per_unit_min: Optional[float] = Field(default=None, ge=0)
    queue_min: Optional[float] = Field(default=None, ge=0)
    move_min: Optional[float] = Field(default=None, ge=0)
    predecessor_seq: Optional[int] = None
    parallel_group: Optional[str] = None


# ----- auth -----
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=6)
    full_name: Optional[str] = None
    role: str = "viewer"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6)


class UserRead(ORMModel):
    id: int
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool


class AuditRead(ORMModel):
    id: int
    actor_username: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    at: Optional[datetime]


# ----- auth hardening -----
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    username: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)