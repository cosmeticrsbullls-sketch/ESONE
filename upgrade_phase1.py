from sqlalchemy import inspect, text
from database.db import engine, Base
import database.models  # noqa: F401


def column_names(table):
    return {c['name'] for c in inspect(engine).get_columns(table)}


def add_column_if_missing(table, name, ddl):
    if name not in column_names(table):
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        print(f'Added {table}.{name}')


def main():
    # Creates all new Phase-1 tables without deleting existing data.
    Base.metadata.create_all(bind=engine)
    # SQLite create_all does not add columns to an existing table.
    add_column_if_missing('clients', 'whatsapp_phone', 'VARCHAR(20)')
    add_column_if_missing('clients', 'outstanding_amount', 'NUMERIC(12,2) DEFAULT 0')
    print('ES1 Phase-1 database upgrade complete.')

if __name__ == '__main__':
    main()
