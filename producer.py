import time
import json
import random
import uuid
from datetime import datetime
from confluent_kafka import Producer
from faker import Faker

# Initialize Faker
fake = Faker()

# Kafka Configuration
KAFKA_TOPIC = 'transactions'
KAFKA_CONF = {
    'bootstrap.servers': '127.0.0.1:9093',
    'client.id': 'python-producer',
    'security.protocol': 'PLAINTEXT'
}

# Initialize Producer
producer = Producer(KAFKA_CONF)

CATEGORIES = ['Electronics', 'Fashion', 'Grocery', 'Home', 'Beauty', 'Sports']

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

def generate_transaction():
    """
    Generates a synthetic transaction.
    """
    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id": f"user_{random.randint(1, 100)}",
        "product_category": random.choice(CATEGORIES),
        "product_name": fake.word(),
        "amount": round(random.uniform(10.0, 1000.0), 2),
        "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "payment_method": random.choice(['Credit Card', 'Debit Card', 'PayPal', 'Apple Pay'])
    }

def main():
    print(f"Starting data producer. Sending data to topic: {KAFKA_TOPIC}")
    try:
        while True:
            transaction = generate_transaction()
            # Trigger any available delivery report callbacks from previous produce() calls
            producer.poll(0)
            
            # Asynchronously produce a message. The delivery_report callback will
            # be triggered from the call to poll() above, or flush() below, when the
            # message has been successfully delivered or failed permanently.
            producer.produce(KAFKA_TOPIC, json.dumps(transaction).encode('utf-8'), callback=delivery_report)
            
            print(f"Sent: {transaction}")
            
            # Simulate real-time streaming (random delay between 0.1 and 1 second)
            time.sleep(random.uniform(0.1, 1.0))
    except KeyboardInterrupt:
        print("Stopping producer...")
    finally:
        # Wait for any outstanding messages to be delivered and delivery report
        # callbacks to be triggered.
        producer.flush()

if __name__ == "__main__":
    main()
