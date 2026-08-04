from app.db import close_pool, execute_schema

if __name__ == "__main__":
    execute_schema()
    close_pool()
    print("Rapid Discovery schema is ready.")
