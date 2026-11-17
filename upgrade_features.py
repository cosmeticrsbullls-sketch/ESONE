"""Add feature tables without altering or seeding existing business tables."""
from database.db import engine
from database.models import PasswordReset, DocumentImport, EmployeeProfile, Attendance, OrderLine, DemoEducator, NotificationRead, DemoBookingRequest
if __name__=='__main__':
    for model in [PasswordReset,DocumentImport,EmployeeProfile,Attendance,OrderLine,DemoEducator,NotificationRead,DemoBookingRequest]:
        model.__table__.create(engine,checkfirst=True)
    print('Feature tables ready; no existing records modified.')
