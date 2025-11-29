import psycopg2
import time

def create_table():
    # Wait for Postgres to start
    time.sleep(5) 
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="transactions_db",
            user="user",
            password="password",
            port="5432"
        )
        cur = conn.cursor()
        
        # Create table for aggregated sales
        create_table_query = """
        CREATE TABLE IF NOT EXISTS category_sales (
            window_start TIMESTAMP,
            window_end TIMESTAMP,
            category VARCHAR(50),
            total_sales DECIMAL(10, 2),
            transaction_count INT,
            PRIMARY KEY (window_start, category)
        );
        """
        cur.execute(create_table_query)
        conn.commit()
        print("Table 'category_sales' created successfully.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error creating table: {e}")

if __name__ == "__main__":
    create_table()
