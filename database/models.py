from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float, Text, Numeric, func
from database.db import Base

class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True); full_name=Column(String(150),nullable=False); email=Column(String(255),unique=True,nullable=False); password_hash=Column(String(255),nullable=False); role=Column(String(30),nullable=False); is_active=Column(Boolean,default=True); created_at=Column(DateTime,server_default=func.now())

class Client(Base):
    __tablename__='clients'
    id=Column(Integer,primary_key=True); client_name=Column(String(200)); business_name=Column(String(200),nullable=False,default=''); contact_person=Column(String(150)); phone=Column(String(20)); alternate_phone=Column(String(20)); whatsapp_phone=Column(String(20)); area=Column(String(120)); city=Column(String(120)); address=Column(String(500)); pincode=Column(String(12)); client_category=Column(String(10),default='B'); client_type=Column(String(30),default='SALON'); status=Column(String(30),default='LEAD'); assigned_sales_id=Column(Integer,ForeignKey('users.id')); created_by=Column(Integer,ForeignKey('users.id')); latitude=Column(Float); longitude=Column(Float); outstanding_amount=Column(Numeric(12,2),default=0); created_at=Column(DateTime,server_default=func.now()); updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())

class Activity(Base):
    __tablename__='activities'
    id=Column(Integer,primary_key=True); client_id=Column(Integer,ForeignKey('clients.id'),nullable=False,index=True); activity_type=Column(String(40),nullable=False,index=True); source=Column(String(40)); status=Column(String(40),default='OPEN',index=True); title=Column(String(200)); notes=Column(Text); scheduled_at=Column(DateTime); completed_at=Column(DateTime); assigned_user_id=Column(Integer,ForeignKey('users.id')); created_by=Column(Integer,ForeignKey('users.id')); parent_activity_id=Column(Integer,ForeignKey('activities.id')); created_at=Column(DateTime,server_default=func.now()); updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())

class Visit(Base):
    __tablename__='visits'
    id=Column(Integer,primary_key=True); activity_id=Column(Integer,ForeignKey('activities.id'),unique=True,nullable=False); visit_type=Column(String(30),nullable=False); check_in_at=Column(DateTime); check_out_at=Column(DateTime); check_in_latitude=Column(Float); check_in_longitude=Column(Float); check_out_latitude=Column(Float); check_out_longitude=Column(Float); outcome=Column(String(60)); next_followup_at=Column(DateTime); created_at=Column(DateTime,server_default=func.now())

class DemoBooking(Base):
    __tablename__='demo_bookings'
    id=Column(Integer,primary_key=True); activity_id=Column(Integer,ForeignKey('activities.id'),unique=True,nullable=False); product_or_treatment=Column(String(200)); booking_source=Column(String(40)); demo_date=Column(DateTime,nullable=False); assigned_educator_id=Column(Integer,ForeignKey('users.id')); location_verification_required=Column(Boolean,default=False); started_at=Column(DateTime); completed_at=Column(DateTime); execution_latitude=Column(Float); execution_longitude=Column(Float); conversion_status=Column(String(30),default='PENDING'); non_conversion_reason=Column(Text); followup_at=Column(DateTime); created_at=Column(DateTime,server_default=func.now())

class SalesOrder(Base):
    __tablename__='sales_orders'
    id=Column(Integer,primary_key=True); activity_id=Column(Integer,ForeignKey('activities.id'),unique=True,nullable=False); order_number=Column(String(50),unique=True,index=True); order_source=Column(String(40)); status=Column(String(40),default='PLACED',index=True); subtotal=Column(Numeric(12,2),default=0); discount_amount=Column(Numeric(12,2),default=0); total_amount=Column(Numeric(12,2),default=0); payment_terms=Column(String(200)); delivery_address=Column(Text); created_at=Column(DateTime,server_default=func.now()); updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())

class Delivery(Base):
    __tablename__='deliveries'
    id=Column(Integer,primary_key=True); order_id=Column(Integer,ForeignKey('sales_orders.id'),nullable=False,index=True); mode=Column(String(40)); provider_name=Column(String(150)); tracking_reference=Column(String(100)); status=Column(String(40),default='PENDING',index=True); dispatched_at=Column(DateTime); delivered_at=Column(DateTime); received_by=Column(String(150)); otp_status=Column(String(30),default='NOT_SENT'); otp_verified_at=Column(DateTime); notes=Column(Text); created_at=Column(DateTime,server_default=func.now())

class CollectionActivity(Base):
    __tablename__='collection_activities'
    id=Column(Integer,primary_key=True); activity_id=Column(Integer,ForeignKey('activities.id'),unique=True,nullable=False); channel=Column(String(30)); outcome=Column(String(50)); amount_discussed=Column(Numeric(12,2)); amount_received=Column(Numeric(12,2)); payment_mode=Column(String(30)); payment_reference=Column(String(120)); payment_otp_status=Column(String(30),default='NOT_SENT'); customer_verified_at=Column(DateTime); accounts_status=Column(String(30),default='PENDING'); accounts_verified_at=Column(DateTime); created_at=Column(DateTime,server_default=func.now())

class PromiseToPay(Base):
    __tablename__='ptps'
    id=Column(Integer,primary_key=True); collection_activity_id=Column(Integer,ForeignKey('collection_activities.id'),nullable=False,index=True); client_id=Column(Integer,ForeignKey('clients.id'),nullable=False,index=True); promised_amount=Column(Numeric(12,2),nullable=False); promise_date=Column(DateTime,nullable=False,index=True); status=Column(String(30),default='OPEN',index=True); notes=Column(Text); created_by=Column(Integer,ForeignKey('users.id')); created_at=Column(DateTime,server_default=func.now()); updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())

class CommunicationLog(Base):
    __tablename__='communication_logs'
    id=Column(Integer,primary_key=True); client_id=Column(Integer,ForeignKey('clients.id'),nullable=False,index=True); activity_id=Column(Integer,ForeignKey('activities.id'),index=True); channel=Column(String(30),default='WHATSAPP'); purpose=Column(String(60)); recipient=Column(String(30)); template_name=Column(String(120)); message_text=Column(Text); send_mode=Column(String(20),default='MANUAL'); provider_message_id=Column(String(150)); status=Column(String(30),default='QUEUED',index=True); sent_at=Column(DateTime); delivered_at=Column(DateTime); read_at=Column(DateTime); failure_reason=Column(Text); created_by=Column(Integer,ForeignKey('users.id')); created_at=Column(DateTime,server_default=func.now())

class AuditLog(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id')); entity_type=Column(String(50),nullable=False,index=True); entity_id=Column(Integer,index=True); action=Column(String(40),nullable=False); old_value=Column(Text); new_value=Column(Text); created_at=Column(DateTime,server_default=func.now())

class VerificationOTP(Base):
    __tablename__='verification_otps'
    id=Column(Integer,primary_key=True)
    client_id=Column(Integer,ForeignKey('clients.id'),nullable=False,index=True)
    activity_id=Column(Integer,ForeignKey('activities.id'),nullable=False,index=True)
    purpose=Column(String(50),nullable=False,index=True)
    otp_hash=Column(String(128),nullable=False)
    recipient=Column(String(30))
    status=Column(String(20),default='PENDING',index=True)
    expires_at=Column(DateTime,nullable=False)
    verified_at=Column(DateTime)
    created_at=Column(DateTime,server_default=func.now())
