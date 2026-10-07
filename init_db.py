from database.db import Base, engine
from database import models

Base.metadata.create_all(bind=engine)

print("ES1 DATABASE INITIALIZED SUCCESSFULLY")