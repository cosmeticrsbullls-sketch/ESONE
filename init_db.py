from database.db import Base, engine
from database import models

Base.metadata.create_all(bind=engine)

print("ESONE DATABASE INITIALIZED SUCCESSFULLY")