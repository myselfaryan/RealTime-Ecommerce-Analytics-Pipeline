from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, window, sum as _sum, count
from pyspark.sql.types import StructType, StructField, StringType, FloatType, TimestampType

# Define Schema
schema = StructType([
    StructField("transaction_id", StringType(), True),
    StructField("user_id", StringType(), True),
    StructField("product_category", StringType(), True),
    StructField("product_name", StringType(), True),
    StructField("amount", FloatType(), True),
    StructField("timestamp", StringType(), True), # Read as string first, then cast
    StructField("payment_method", StringType(), True)
])

def write_to_postgres(batch_df, batch_id):
    print(f"=== Writing batch {batch_id} to Postgres ===")
    
    try:
        # Convert to Pandas for easier upsert
        pandas_df = batch_df.toPandas()
        
        if pandas_df.empty:
            print(f"Batch {batch_id}: Empty batch, skipping...")
            return
        
        print(f"Batch {batch_id}: Processing {len(pandas_df)} rows")
        print(f"Batch {batch_id}: Sample data:\n{pandas_df.head(2)}")
        
        import psycopg2
        from psycopg2.extras import execute_values
        
        conn = psycopg2.connect(
            host="localhost",
            database="transactions_db",
            user="user",
            password="password",
            port="5432"
        )
        cursor = conn.cursor()
        
        # Upsert using ON CONFLICT
        # Assuming primary key is (window_start, category)
        insert_query = """
            INSERT INTO category_sales (window_start, window_end, category, total_sales, transaction_count)
            VALUES %s
            ON CONFLICT (window_start, category)
            DO UPDATE SET
                window_end = EXCLUDED.window_end,
                total_sales = EXCLUDED.total_sales,
                transaction_count = EXCLUDED.transaction_count;
        """
        
        # Prepare data as list of tuples
        data = [tuple(row) for row in pandas_df.to_numpy()]
        
        print(f"Batch {batch_id}: Executing upsert for {len(data)} rows...")
        execute_values(cursor, insert_query, data)
        conn.commit()
        
        print(f"Batch {batch_id}: ✓ Successfully written {len(pandas_df)} rows to database")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Batch {batch_id}: ✗ ERROR writing to database: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def main():
    spark = SparkSession.builder \
        .appName("EcommerceTransactionProcessor") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.6.0") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # Read from Kafka
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "127.0.0.1:9093") \
        .option("subscribe", "transactions") \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .option("kafka.session.timeout.ms", "60000") \
        .option("kafka.request.timeout.ms", "70000") \
        .option("kafka.default.api.timeout.ms", "90000") \
        .option("kafka.max.block.ms", "120000") \
        .load()

    # Parse JSON
    parsed_df = df.select(from_json(col("value").cast("string"), schema).alias("data")).select("data.*")
    
    # Convert timestamp string to TimestampType
    parsed_df = parsed_df.withColumn("timestamp", col("timestamp").cast(TimestampType()))

    # Watermark to handle late data (allow 1 minute late)
    parsed_df = parsed_df.withWatermark("timestamp", "1 minute")

    # Aggregate: Sales per Category per 1-minute window
    agg_df = parsed_df \
        .groupBy(
            window(col("timestamp"), "1 minute"),
            col("product_category").alias("category")
        ) \
        .agg(
            _sum("amount").alias("total_sales"),
            count("transaction_id").alias("transaction_count")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("category"),
            col("total_sales"),
            col("transaction_count")
        )

    # Write to Console (for debugging)
    query_console = agg_df.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .start()

    # Write to Postgres
    # Note: For 'update' mode in aggregation, we usually need 'foreachBatch' to write to DB
    # because JDBC sink doesn't support streaming directly in all modes easily.
    query_postgres = agg_df.writeStream \
        .outputMode("update") \
        .foreachBatch(write_to_postgres) \
        .start()

    query_console.awaitTermination()
    query_postgres.awaitTermination()

if __name__ == "__main__":
    main()
