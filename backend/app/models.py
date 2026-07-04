"""SQLAlchemy ORM models mapped to the PostgreSQL schema
(db/migrations/0001_initial_schema.sql).

Only the columns the API needs are mapped; the database remains the source of
truth for constraints, defaults, and enums.
"""
from sqlalchemy import (
    Column, BigInteger, Integer, Text, Date, DateTime, Numeric, Boolean,
    ForeignKey, Time,
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM
from sqlalchemy.orm import relationship

from .database import Base

# Existing Postgres enum types (created by the migration). create_type=False
# tells SQLAlchemy not to try to CREATE them — they already exist.
sched_mode_t = ENUM("backward", "forward", name="sched_mode_t", create_type=False)
priority_t = ENUM("HIGH", "MED", "LOW", name="priority_t", create_type=False)
material_status_t = ENUM("ordered", "ready", "risk", "late", name="material_status_t", create_type=False)
event_type_t = ENUM("material_ready", "start", "pause", "resume", "complete",
                    "scrap", "dispatch", "delivered", name="event_type_t", create_type=False)
schedule_status_t = ENUM("feasible", "infeasible", name="schedule_status_t", create_type=False)
solve_job_status_t = ENUM("queued", "running", "succeeded", "failed", name="solve_job_status_t", create_type=False)
user_role_t = ENUM("admin", "planner", "supervisor", "procurement", "viewer", name="user_role_t", create_type=False)
severity_t = ENUM("Medium", "High", "Critical", name="severity_t", create_type=False)
alert_status_t = ENUM("open", "ack", "closed", name="alert_status_t", create_type=False)
alert_type_t = ENUM("crit", "warn", "info", name="alert_type_t", create_type=False)
resolution_status_t = ENUM("Open", "In progress", "Resolved", name="resolution_status_t", create_type=False)


class Plant(Base):
    __tablename__ = "plant"
    id = Column(BigInteger, primary_key=True)
    plant_code = Column(Text, unique=True, nullable=False)
    plant_name = Column(Text, nullable=False)
    location = Column(Text)
    is_active = Column(Boolean, default=True)


class PlantCalendar(Base):
    __tablename__ = "plant_calendar"
    id = Column(BigInteger, primary_key=True)
    plant_id = Column(BigInteger, ForeignKey("plant.id", ondelete="CASCADE"))
    shift_name = Column(Text, nullable=False)
    start_time = Column(Time)
    end_time = Column(Time)
    available_min = Column(Integer)
    days_active = Column(Text)
    is_holiday = Column(Boolean, default=False)
    holiday_date = Column(Date)


class LeadTimeMaster(Base):
    __tablename__ = "lead_time_master"
    id = Column(BigInteger, primary_key=True)
    product_family = Column(Text, unique=True, nullable=False)
    inbound_days = Column(Numeric)
    qa_days = Column(Numeric)
    packing_days = Column(Numeric)
    transport_days = Column(Numeric)
    buffer_days = Column(Numeric)


class AlertThreshold(Base):
    __tablename__ = "alert_threshold"
    id = Column(BigInteger, primary_key=True)
    threshold_key = Column(Text, unique=True, nullable=False)
    label = Column(Text, nullable=False)
    value = Column(Numeric, nullable=False)
    unit = Column(Text, nullable=False)
    fires_when = Column(Text)


class Routing(Base):
    __tablename__ = "routing"
    id = Column(BigInteger, primary_key=True)
    route_id = Column(Text, unique=True, nullable=False)
    description = Column(Text)
    operations = relationship("RoutingOperation", back_populates="routing",
                              cascade="all, delete-orphan")


class RoutingOperation(Base):
    __tablename__ = "routing_operation"
    id = Column(BigInteger, primary_key=True)
    routing_id = Column(BigInteger, ForeignKey("routing.id", ondelete="CASCADE"))
    operation_seq = Column(Integer, nullable=False)
    work_center = Column(Text, nullable=False)
    setup_min = Column(Numeric)
    run_per_unit_min = Column(Numeric)
    queue_min = Column(Numeric)
    move_min = Column(Numeric)
    predecessor_seq = Column(Integer)
    parallel_group = Column(Text)
    eligible_work_centers = Column(Text)
    setup_family = Column(Text)
    routing = relationship("Routing", back_populates="operations")


class Product(Base):
    __tablename__ = "product"
    id = Column(BigInteger, primary_key=True)
    product_id = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    family = Column(Text, nullable=False)
    routing_id = Column(BigInteger, ForeignKey("routing.id", ondelete="SET NULL"))
    is_active = Column(Boolean, default=True)
    bom_lines = relationship("BomLine", back_populates="product",
                             cascade="all, delete-orphan")
    routing = relationship("Routing")


class BomLine(Base):
    __tablename__ = "bom_line"
    id = Column(BigInteger, primary_key=True)
    product_id = Column(BigInteger, ForeignKey("product.id", ondelete="CASCADE"))
    material = Column(Text, nullable=False)
    qty_per_unit = Column(Numeric, nullable=False)
    uom = Column(Text, nullable=False)
    supplier = Column(Text)
    lead_days = Column(Integer)
    product = relationship("Product", back_populates="bom_lines")


class OrderHeader(Base):
    __tablename__ = "order_header"
    id = Column(BigInteger, primary_key=True)
    order_id = Column(Text, unique=True, nullable=False)
    product_id = Column(BigInteger, ForeignKey("product.id", ondelete="RESTRICT"),
                        nullable=False)
    customer = Column(Text, nullable=False)
    order_qty = Column(Integer, nullable=False)
    order_date = Column(Date, nullable=False)
    committed_delivery_date = Column(Date, nullable=False)
    priority = Column(priority_t, default="MED")
    plant_id = Column(BigInteger, ForeignKey("plant.id", ondelete="SET NULL"))
    sched_mode = Column(sched_mode_t, default="backward")
    replan_count = Column(Integer, default=0)


class PlannedSchedule(Base):
    __tablename__ = "planned_schedule"
    id = Column(BigInteger, primary_key=True)
    schedule_id = Column(Text, unique=True, nullable=False)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    baseline_version = Column(Integer, nullable=False)
    sched_mode = Column(sched_mode_t, nullable=False)
    planned_material_ready_dt = Column(DateTime(timezone=True))
    planned_prod_start_dt = Column(DateTime(timezone=True))
    planned_prod_end_dt = Column(DateTime(timezone=True))
    planned_pack_dt = Column(DateTime(timezone=True))
    planned_dispatch_dt = Column(DateTime(timezone=True))
    planned_delivery_dt = Column(DateTime(timezone=True))
    prod_duration_mins = Column(Numeric)
    original_buffer_hrs = Column(Numeric)
    buffer_hrs = Column(Numeric)
    schedule_status = Column(schedule_status_t)
    is_current = Column(Boolean, default=True)
    is_stale = Column(Boolean, default=False)
    stale_reason = Column(Text)


class OrderOperation(Base):
    __tablename__ = "order_operation"
    id = Column(BigInteger, primary_key=True)
    order_operation_id = Column(Text, nullable=False)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    schedule_id = Column(BigInteger, ForeignKey("planned_schedule.id", ondelete="CASCADE"))
    operation_seq = Column(Integer, nullable=False)
    work_center = Column(Text, nullable=False)
    setup_time_min = Column(Numeric)
    run_time_per_unit_min = Column(Numeric)
    queue_time_min = Column(Numeric)
    move_time_min = Column(Numeric)
    planned_qty = Column(Integer)
    predecessor_operation_seq = Column(Integer)
    parallel_group = Column(Text)
    planned_start = Column(DateTime(timezone=True))
    planned_end = Column(DateTime(timezone=True))
    duration_mins = Column(Numeric)
    version = Column(Integer, default=1)
    chosen_work_center = Column(Text)


class MaterialStatus(Base):
    __tablename__ = "material_status"
    id = Column(BigInteger, primary_key=True)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"),
                      unique=True)
    product_id = Column(BigInteger, ForeignKey("product.id", ondelete="RESTRICT"))
    material_count = Column(Integer)
    max_lead_days = Column(Integer)
    planned_ready_dt = Column(DateTime(timezone=True))
    actual_ready_dt = Column(DateTime(timezone=True))
    expected_ready_dt = Column(DateTime(timezone=True))
    status = Column(material_status_t, default="ordered")
    slip_days = Column(Numeric, default=0)
    risk_reason = Column(Text)


class ActualEvent(Base):
    __tablename__ = "actual_event"
    id = Column(BigInteger, primary_key=True)
    event_id = Column(Text, unique=True, nullable=False)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    operation_seq = Column(Integer)
    event_type = Column(event_type_t, nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    event_qty = Column(Integer)
    downtime_reason = Column(Text)
    downtime_mins = Column(Integer, default=0)
    entered_by = Column(Text)


class RescheduleLog(Base):
    __tablename__ = "reschedule_log"
    id = Column(BigInteger, primary_key=True)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    version = Column(Integer, nullable=False)
    options = Column(JSONB, default=dict)
    baseline_delivery = Column(DateTime(timezone=True))
    new_delivery = Column(DateTime(timezone=True))
    performed_by = Column(Text)
    performed_at = Column(DateTime(timezone=True))


class SolveJob(Base):
    __tablename__ = "solve_job"
    id = Column(BigInteger, primary_key=True)
    job_id = Column(Text, unique=True, nullable=False)
    status = Column(solve_job_status_t, default="queued")
    mode = Column(Text, default="forward")
    time_budget_s = Column(Integer, default=30)
    order_ids = Column(JSONB)
    result = Column(JSONB)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))


class AppUser(Base):
    __tablename__ = "app_user"
    id = Column(BigInteger, primary_key=True)
    username = Column(Text, unique=True, nullable=False)
    full_name = Column(Text)
    role = Column(user_role_t, default="viewer", nullable=False)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    failed_login_count = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True)
    actor_id = Column(BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"))
    actor_username = Column(Text)
    action = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Text)
    detail = Column(JSONB)
    at = Column(DateTime(timezone=True))


class AlertLog(Base):
    __tablename__ = "alert_log"
    id = Column(BigInteger, primary_key=True)
    alert_id = Column(Text, unique=True, nullable=False)
    dedup_key = Column(Text, unique=True, nullable=False)
    alert_type = Column(alert_type_t, nullable=False)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    title = Column(Text, nullable=False)
    meta = Column(Text)
    status = Column(alert_status_t, default="open")
    raised_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))


class DeviationLog(Base):
    __tablename__ = "deviation_log"
    id = Column(BigInteger, primary_key=True)
    deviation_id = Column(Text, nullable=False)
    order_id = Column(BigInteger, ForeignKey("order_header.id", ondelete="CASCADE"))
    milestone_name = Column(Text, nullable=False)
    baseline_dt = Column(DateTime(timezone=True))
    latest_forecast_dt = Column(DateTime(timezone=True))
    deviation_minutes = Column(Numeric, default=0)
    severity = Column(severity_t, nullable=False)
    root_cause_code = Column(Text)
    action_owner = Column(Text)
    resolution_status = Column(resolution_status_t, default="Open")
    generated_at = Column(DateTime(timezone=True))


class CapacityLoad(Base):
    __tablename__ = "capacity_load"
    id = Column(BigInteger, primary_key=True)
    work_center = Column(Text, nullable=False)
    load_date = Column(Date, nullable=False)
    available_min = Column(Integer, nullable=False)
    demand_min = Column(Numeric, default=0)
    load_pct = Column(Numeric, default=0)
    overloaded = Column(Boolean, default=False)
    computed_at = Column(DateTime(timezone=True))


class ChangeoverMatrix(Base):
    __tablename__ = "changeover_matrix"
    id = Column(BigInteger, primary_key=True)
    from_family = Column(Text, nullable=False)
    to_family = Column(Text, nullable=False)
    changeover_min = Column(Integer, default=0)


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, unique=True, nullable=False)
    issued_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))