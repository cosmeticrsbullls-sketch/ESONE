"""Add feature tables without altering or seeding existing business tables."""
from database.db import engine
from database.models import PasswordReset, DocumentImport
if __name__=='__main__':
    PasswordReset.__table__.create(engine,checkfirst=True)
    DocumentImport.__table__.create(engine,checkfirst=True)
    print('Feature tables ready; no existing records modified.')
