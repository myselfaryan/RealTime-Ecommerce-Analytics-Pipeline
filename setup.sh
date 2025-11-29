#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Real-Time Data Pipeline Environment...${NC}"

# 1. Start Docker Containers
echo -e "${GREEN}Step 1: Starting Docker Containers (Kafka, Zookeeper, Postgres, Spark)...${NC}"
docker compose up -d

echo -e "${GREEN}Waiting for containers to initialize (15 seconds)...${NC}"
sleep 15

# 2. Create and Activate Virtual Environment
echo -e "${GREEN}Step 2: Creating Python Virtual Environment...${NC}"
python3 -m venv venv
source venv/bin/activate

# 3. Install Python Dependencies
echo -e "${GREEN}Step 3: Installing Python Dependencies...${NC}"
pip install -r requirements.txt

# 4. Initialize Database
echo -e "${GREEN}Step 4: Initializing Database...${NC}"
python init_db.py

echo -e "${GREEN}Setup Complete!${NC}"
echo -e "To run the pipeline, open 3 separate terminals and run:"
echo -e "1. source venv/bin/activate && python producer.py"
echo -e "2. source venv/bin/activate && python spark_processor.py"
echo -e "3. source venv/bin/activate && streamlit run dashboard.py"
